from __future__ import annotations

import random
import uuid
from datetime import timedelta
from typing import Any, cast

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.selection import get_selectable_models, get_selectable_prompts
from gamecore.legality import evaluate_scoring_move, placements_to_dicts
from gamecore.state import build_ai_state_dict, build_compact_state, has_multigraph_tile_token
from gamecore.variant_store import load_variant

from . import services
from .models import GameSession, PlaygroundSimulation, PlayerSlot
from .serializers import sanitize_ai_metadata

MAX_SIMULATION_PLIES = 300
LEASE_GRACE_SECONDS = 15


class SimulationNotFoundError(Exception):
    pass


class SimulationConflictError(Exception):
    def __init__(self, message: str, *, game_id: str | None = None) -> None:
        self.game_id = game_id
        super().__init__(message)


def _slot_snapshot(config: dict[str, Any]) -> tuple[dict[str, Any], Any, Any]:
    if config["kind"] == "cpu":
        return (
            {
                "kind": "cpu",
                "provider": "engine",
                "model_id": "engine/cpu",
                "display_name": "CPU Master",
                "prompt_id": None,
                "prompt_name": None,
                "policy": "ranked_witness_safe",
            },
            None,
            None,
        )
    model = next(
        item
        for item in get_selectable_models()
        if item.provider == config["provider"] and item.model_id == config["model_id"]
    )
    prompt = next(
        (item for item in get_selectable_prompts() if item.id == config.get("prompt_id")),
        None,
    )
    return (
        {
            "kind": "llm",
            "provider": model.provider,
            "model_id": model.model_id,
            "display_name": model.display_name,
            "prompt_id": prompt.id if prompt else None,
            "prompt_name": prompt.name if prompt else None,
        },
        model,
        prompt,
    )


@transaction.atomic
def create_playground_simulation(
    *,
    created_by_id: int,
    slot0: dict[str, Any],
    slot1: dict[str, Any],
    variant_slug: str,
    seed: int | None,
    ai_timeout: int,
    ai_max_steps: int,
) -> PlaygroundSimulation:
    existing = (
        PlaygroundSimulation.objects.select_related("game")
        .filter(created_by_id=created_by_id, ended_at__isnull=True)
        .first()
    )
    if existing is not None:
        raise SimulationConflictError(
            "An unfinished simulation already exists.", game_id=str(existing.game.public_id)
        )
    resolved_seed = seed if seed is not None else random.randint(0, 2_147_483_647)
    snapshot0, model0, prompt0 = _slot_snapshot(slot0)
    snapshot1, model1, prompt1 = _slot_snapshot(slot1)
    game = GameSession.objects.create(
        game_mode="vs_ai",
        is_diagnostic=False,
        status="active",
        variant_slug=variant_slug,
        board_state=services._empty_board_state(),
        premium_used=[],
        current_turn_slot=None,
        ai_model=None,
        ai_prompt=None,
    )
    player0 = PlayerSlot.objects.create(
        game=game, slot=0, user=None, is_ai=True, rack=[], ai_model=model0, ai_prompt=prompt0
    )
    player1 = PlayerSlot.objects.create(
        game=game, slot=1, user=None, is_ai=True, rack=[], ai_model=model1, ai_prompt=prompt1
    )
    try:
        simulation = PlaygroundSimulation.objects.create(
            game=game,
            created_by_id=created_by_id,
            config_json={
                "version": 1,
                "variant_slug": variant_slug,
                "seed": resolved_seed,
                "ai_timeout": ai_timeout,
                "ai_max_steps": ai_max_steps,
                "slots": [snapshot0, snapshot1],
            },
        )
    except IntegrityError as exc:
        raise SimulationConflictError("An unfinished simulation already exists.") from exc
    services._initialize_session(game, slot0=player0, slot1=player1, seed=resolved_seed)
    return simulation


def _simulation_queryset() -> Any:
    return PlaygroundSimulation.objects.select_related("game", "created_by").prefetch_related(
        "game__slots__ai_model",
        "game__slots__ai_prompt",
        "game__moves__player_slot",
    )


def get_playground_simulation(game_id: str) -> PlaygroundSimulation:
    try:
        parsed_game_id = uuid.UUID(game_id)
    except (ValueError, AttributeError) as exc:
        raise SimulationNotFoundError("Simulation not found") from exc
    try:
        return cast(
            PlaygroundSimulation,
            _simulation_queryset().get(game__public_id=parsed_game_id),
        )
    except PlaygroundSimulation.DoesNotExist as exc:
        raise SimulationNotFoundError("Simulation not found") from exc


def _move_payload(move: Any | None) -> dict[str, Any] | None:
    if move is None:
        return None
    return {
        "seq": move.seq,
        "kind": move.kind,
        "player_slot": move.player_slot.slot,
        "placements": move.placements or [],
        "words": move.words_formed or [],
        "points": move.points,
        "tiles_exchanged": move.tiles_exchanged,
        "created_at": move.created_at.isoformat(),
        "ai_metadata": sanitize_ai_metadata(move.ai_metadata),
    }


def serialize_simulation_state(simulation: PlaygroundSimulation) -> dict[str, Any]:
    game = simulation.game
    slots = list(game.slots.all().order_by("slot"))
    moves = list(game.moves.all().order_by("seq"))
    variant = load_variant(game.variant_slug)
    configs = simulation.config_json.get("slots", [])
    players = []
    racks: list[list[str]] = []
    scores: list[int] = []
    for index, slot in enumerate(slots):
        config = configs[index] if index < len(configs) else {}
        players.append(
            {
                "slot": slot.slot,
                "username": None,
                "score": slot.score,
                "is_ai": True,
                "model_id": config.get("model_id"),
                "model_display_name": config.get("display_name"),
            }
        )
        racks.append(list(slot.rack) if isinstance(slot.rack, list) else [])
        scores.append(slot.score)
    return {
        "simulation_schema_version": 1,
        "game_id": str(game.public_id),
        "config": simulation.config_json,
        "status": game.status,
        "variant_slug": game.variant_slug,
        "board": services._wire_board(game.board_state),
        "premium_used": game.premium_used,
        "racks": racks,
        "scores": scores,
        "players": players,
        "tile_points": dict(variant.tile_points),
        "bag_remaining": services._bag_remaining_count(game),
        "move_count": len(moves),
        "current_turn_slot": game.current_turn_slot,
        "game_over": game.game_over,
        "game_end_reason": game.game_end_reason,
        "winner_slot": game.winner_slot,
        "in_flight": bool(
            simulation.lease_id
            and simulation.lease_expires_at
            and simulation.lease_expires_at > timezone.now()
        ),
        "latest_move": _move_payload(moves[-1] if moves else None),
        "moves": [_move_payload(move) for move in moves[-50:]],
        "replay_url": f"/admin/replay/{game.public_id}",
    }


def _finish_if_terminal(simulation: PlaygroundSimulation) -> None:
    if simulation.game.game_over and simulation.ended_at is None:
        simulation.ended_at = simulation.game.finished_at or timezone.now()
        simulation.save(update_fields=["ended_at"])


def _clear_lease(simulation: PlaygroundSimulation) -> None:
    simulation.lease_id = None
    simulation.leased_move_count = None
    simulation.lease_expires_at = None


def _check_turn(simulation: PlaygroundSimulation, expected_move_count: int) -> PlayerSlot:
    game = simulation.game
    if game.game_over or game.status != "active":
        raise SimulationConflictError("Simulation is not active.")
    move_count = game.moves.count()
    if move_count != expected_move_count:
        raise SimulationConflictError("Simulation state is stale.")
    if move_count >= MAX_SIMULATION_PLIES:
        now = timezone.now()
        game.game_over = True
        game.status = "abandoned"
        game.game_end_reason = "simulation_ply_limit"
        game.winner_slot = None
        game.current_turn_slot = None
        game.finished_at = now
        game.save()
        simulation.ended_at = now
        _clear_lease(simulation)
        simulation.save()
        raise SimulationConflictError("Simulation reached its ply limit.")
    if game.current_turn_slot not in (0, 1):
        raise SimulationConflictError("Simulation has no acting slot.")
    slot = game.slots.filter(slot=game.current_turn_slot, is_ai=True).first()
    if slot is None:
        raise SimulationConflictError("Acting simulation slot is unavailable.")
    return slot


def execute_cpu_step(
    *, simulation: PlaygroundSimulation, expected_move_count: int
) -> dict[str, Any]:
    acting = _check_turn(simulation, expected_move_count)
    ranked = services._probe_ai_ranked_candidates(simulation.game, acting)
    placements: list[dict[str, Any]] | None = None
    source = "backend_ranked_candidate"
    if ranked.candidates:
        placements = cast(list[dict[str, Any]], placements_to_dicts(ranked.candidates[0].placements))
    if placements is None:
        playability = services._probe_ai_playability(simulation.game, acting)
        if playability.status == "indeterminate":
            raise SimulationConflictError("Playability could not be determined.")
        if playability.status == "found" and playability.witness is not None:
            placements = cast(list[dict[str, Any]], placements_to_dicts(playability.witness))
            source = "backend_witness_rescue"
        elif playability.status == "none":
            bag = services._bag_from_session(simulation.game)
            if bag.remaining() >= 7:
                return services._submit_exchange_locked(
                    session=simulation.game,
                    player_slot=acting,
                    letters_to_exchange=list(acting.rack),
                    ai_metadata={
                        "completion_source": "genuine_no_move_exchange",
                        "provider_requests_used": 0,
                    },
                )
            return services._submit_pass_locked(
                session=simulation.game,
                player_slot=acting,
                ai_metadata={
                    "completion_source": "genuine_no_move_pass",
                    "provider_requests_used": 0,
                },
            )
    assert placements is not None
    return services._submit_move_locked(
        session=simulation.game,
        player_slot=acting,
        placements_data=placements,
        ai_metadata={"completion_source": source, "provider_requests_used": 0},
    )


def step_playground_simulation(
    *, game_id: str, user_id: int, expected_move_count: int
) -> dict[str, Any]:
    with transaction.atomic():
        simulation = (
            _simulation_queryset().select_for_update().get(game__public_id=game_id)
        )
        if simulation.created_by_id != user_id:
            raise SimulationNotFoundError("Simulation not found")
        now = timezone.now()
        if simulation.lease_id and simulation.lease_expires_at and simulation.lease_expires_at > now:
            raise SimulationConflictError("A turn is already in progress.")
        if simulation.lease_id:
            _clear_lease(simulation)
            simulation.save(update_fields=["lease_id", "leased_move_count", "lease_expires_at"])
        acting = _check_turn(simulation, expected_move_count)
        slot_config = simulation.config_json["slots"][acting.slot]
        if slot_config["kind"] == "llm":
            lease_id = uuid.uuid4()
            timeout = int(simulation.config_json["ai_timeout"])
            simulation.lease_id = lease_id
            simulation.leased_move_count = expected_move_count
            simulation.lease_expires_at = now + timedelta(seconds=timeout + LEASE_GRACE_SECONDS)
            simulation.save(update_fields=["lease_id", "leased_move_count", "lease_expires_at"])
            return {
                "kind": "llm",
                "lease_id": str(lease_id),
                "expected_move_count": expected_move_count,
                "slot": acting.slot,
                "provider": slot_config["provider"],
                "model_id": slot_config["model_id"],
                "timeout": timeout,
                "max_steps": int(simulation.config_json["ai_max_steps"]),
            }
    with transaction.atomic():
        simulation = (
            PlaygroundSimulation.objects.select_for_update()
            .select_related("game")
            .prefetch_related("game__slots", "game__moves")
            .get(pk=simulation.pk)
        )
        result = execute_cpu_step(
            simulation=simulation, expected_move_count=expected_move_count
        )
        if not result.get("ok"):
            raise SimulationConflictError(str(result.get("error", "CPU turn failed.")))
        simulation.game.refresh_from_db()
        _finish_if_terminal(simulation)
    return {"kind": "cpu", "state": serialize_simulation_state(get_playground_simulation(game_id))}


def _locked_lease(
    *, game_id: str, user_id: int, lease_id: uuid.UUID, expected_move_count: int
) -> tuple[PlaygroundSimulation, PlayerSlot]:
    try:
        simulation = (
            PlaygroundSimulation.objects.select_for_update()
            .select_related("game")
            .get(game__public_id=game_id, created_by_id=user_id)
        )
    except PlaygroundSimulation.DoesNotExist as exc:
        raise SimulationNotFoundError("Simulation not found") from exc
    now = timezone.now()
    if (
        simulation.lease_id != lease_id
        or simulation.leased_move_count != expected_move_count
        or simulation.lease_expires_at is None
        or simulation.lease_expires_at <= now
        or simulation.game.moves.count() != expected_move_count
    ):
        raise SimulationConflictError("Simulation turn lease is stale.")
    acting = _check_turn(simulation, expected_move_count)
    return simulation, acting


def simulation_action(
    *, game_id: str, user_id: int, data: dict[str, Any]
) -> dict[str, Any]:
    operation = data["operation"]
    with transaction.atomic():
        simulation, acting = _locked_lease(
            game_id=game_id,
            user_id=user_id,
            lease_id=data["lease_id"],
            expected_move_count=data["expected_move_count"],
        )
        if operation == "release":
            _clear_lease(simulation)
            simulation.save(update_fields=["lease_id", "leased_move_count", "lease_expires_at"])
            return {"ok": True}
        if operation == "context":
            opponent = simulation.game.slots.get(slot=1 - acting.slot)
            board = services._board_from_session(simulation.game)
            ai_state = build_ai_state_dict(
                board=board,
                ai_rack=list(acting.rack),
                human_score=opponent.score,
                ai_score=acting.score,
                turn="AI",
            )
            variant = services._session_variant(simulation.game)
            prompt = acting.ai_prompt
            model = acting.ai_model
            return {
                "compact_state": build_compact_state(
                    ai_state,
                    multigraph=has_multigraph_tile_token(variant.playable_letters),
                ),
                "ai_state": dict(ai_state),
                "variant": simulation.game.variant_slug,
                "ai_model_id": model.model_id if model else None,
                "ai_model_display_name": model.display_name if model else None,
                "ai_prompt_id": prompt.id if prompt else None,
                "ai_prompt_name": prompt.name if prompt else None,
                "ai_prompt_fitness": prompt.fitness if prompt else None,
                "ai_prompt_text": prompt.prompt if prompt else None,
                "is_first_move": services._is_board_empty(simulation.game),
                "ai_move_max_output_tokens": settings.AI_MOVE_MAX_OUTPUT_TOKENS,
                **services._variant_snapshot_fields(simulation.game),
            }
        if operation == "candidates":
            return services._ranked_candidates_payload(
                services._probe_ai_ranked_candidates(simulation.game, acting)
            )
        if operation == "playability":
            return services._playability_payload(
                simulation.game,
                acting,
                services._probe_ai_playability(simulation.game, acting),
            )
        if operation == "validate":
            legality = evaluate_scoring_move(
                services._board_from_session(simulation.game),
                list(acting.rack),
                services._placements_from_data(data["placements"]),
                authority=services._session_authority(simulation.game),
                letters=services._session_letters(simulation.game),
                variant=simulation.game.variant_slug,
            )
            return {
                "valid": legality.ok,
                "reason": legality.reason,
                "reason_code": legality.reason_code,
                "total_score": legality.total_score,
                "words": [
                    {"word": verdict.word, "valid": verdict.valid}
                    for verdict in legality.word_results
                ],
            }
        metadata = data.get("ai_metadata")
        if operation == "place":
            result = services._submit_move_locked(
                session=simulation.game,
                player_slot=acting,
                placements_data=data["placements"],
                ai_metadata=metadata,
            )
        elif operation == "exchange":
            result = services._submit_exchange_locked(
                session=simulation.game,
                player_slot=acting,
                letters_to_exchange=data["letters"],
                ai_metadata=metadata,
            )
        else:
            result = services._submit_pass_locked(
                session=simulation.game, player_slot=acting, ai_metadata=metadata
            )
        if result.get("ok"):
            _clear_lease(simulation)
            if simulation.game.game_over:
                simulation.ended_at = simulation.game.finished_at or timezone.now()
            simulation.save()
        return result


def stop_playground_simulation(*, game_id: str, user_id: int) -> PlaygroundSimulation:
    with transaction.atomic():
        try:
            simulation = (
                PlaygroundSimulation.objects.select_for_update()
                .select_related("game")
                .get(game__public_id=game_id, created_by_id=user_id)
            )
        except PlaygroundSimulation.DoesNotExist as exc:
            raise SimulationNotFoundError("Simulation not found") from exc
        if simulation.ended_at is None:
            now = timezone.now()
            game = simulation.game
            game.game_over = True
            game.status = "abandoned"
            game.game_end_reason = "simulation_stopped"
            game.winner_slot = None
            game.current_turn_slot = None
            game.finished_at = now
            game.save()
            _clear_lease(simulation)
            simulation.ended_at = now
            simulation.save()
    return get_playground_simulation(game_id)
