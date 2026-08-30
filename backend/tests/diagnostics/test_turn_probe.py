"""Isolated pytest-django live-server testbed for diagnose_ai_play.

This module may import pytest. backend/game/** must not.
"""

from __future__ import annotations

import json
import os
import subprocess
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from catalog.models import AIModel, AIPrompt
from catalog.selection import FREE_RIVAL_PAIRS, NVIDIA_NIM_PROVIDER
from game import services
from game.diagnostics import (
    DiagnosticScenario,
    FAKE_WORKER_SCRIPT,
    HANDOFF_ENV,
    LIVE_SENTINEL,
    LIVE_WORKER_SCRIPT,
    TurnAttemptRecord,
    TurnPersistenceEvidence,
    TurnSample,
    build_seeded_scenario,
    classify_complete_formed_words,
    classify_turn_sample,
    derive_executed_runtime_mode,
    formed_words_from_payload,
    is_diacritic_letter,
    load_named_scenario,
    load_variant_context,
    nfc_upper,
    placements_from_payload,
    prepare_probe_environment,
    resolve_engine_scenario,
    turn_sample_to_dict,
    worker_script_for_runtime_mode,
)
from game.models import GameSession

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND = _REPO_ROOT / "frontend"
_NIM = "nvidia/nemotron-3-super-120b-a12b"
_NIM_PROVIDER = "nvidia-nim"
_GEMMA = "google/gemma-4-31b-it:free"


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def seed_catalog() -> dict[str, AIModel]:
    rows: dict[str, AIModel] = {
        model.model_id: model for model in AIModel.objects.all()
    }
    for index, (provider, model_id) in enumerate(FREE_RIVAL_PAIRS):
        if model_id in rows:
            continue
        is_nim = provider == NVIDIA_NIM_PROVIDER
        rows[model_id] = AIModel.objects.create(
            provider=provider,
            model_id=model_id,
            display_name=f"Rival {index + 1}",
            openrouter_available=not is_nim,
            openrouter_managed=not is_nim,
            is_active=True,
            model_type="language",
            tags=["tools"],
            sort_order=(index + 1) * 10,
        )
    if not AIPrompt.objects.filter(is_active=True).exists():
        AIPrompt.objects.create(
            name="Initial",
            prompt="SEARCH PROFILE — diagnostic",
            is_active=True,
            sort_order=1,
        )
    return rows


def session_suffix() -> str:
    return uuid4().hex[:12]


def mint_token(user: User) -> str:
    return str(RefreshToken.for_user(user).access_token)


def new_origin(url: str) -> str:
    parsed = urlparse(url.rstrip("/"))
    return f"{parsed.scheme}://{parsed.netloc}"


def apply_scenario(session: GameSession, scenario: DiagnosticScenario, ai_model: AIModel) -> None:
    grid = ["." * 15 for _ in range(15)]
    for row, col, letter in scenario.board_letters:
        cells = list(grid[row])
        cells[col] = letter
        grid[row] = "".join(cells)
    session.board_state = grid
    session.blanks = []
    session.current_turn_slot = 1
    session.status = "active"
    session.game_over = False
    session.ai_model = ai_model
    if len(session.bag_tiles) < 20:
        session.bag_tiles = (session.bag_tiles or "") + ("E" * 24)
    session.save()
    ai_slot = session.slots.get(slot=1)
    ai_slot.rack = list(scenario.rack)
    ai_slot.save(update_fields=["rack"])


def prepare_game(
    *,
    user: User,
    variant_slug: str,
    fixture_id: str | None,
    seed: int | None,
    model_id: str,
) -> GameSession:
    catalog = {model.model_id: model for model in AIModel.objects.all()}
    created = services.create_game(
        user_id=user.id,
        variant_slug=variant_slug,
        ai_model_model_id=model_id,
    )
    session = GameSession.objects.get(public_id=created["game_id"])
    if fixture_id:
        scenario = load_named_scenario(fixture_id)
    elif seed is not None:
        scenario = build_seeded_scenario(variant_slug, seed)
    else:
        scenario = resolve_engine_scenario(
            variant_slug=variant_slug, fixture_id=fixture_id, seed=seed
        )
    apply_scenario(session, scenario, catalog[model_id])
    session.refresh_from_db()
    return session


def spawn_worker(
    *,
    live_origin: str,
    token: str,
    game_id: str,
    provider: str,
    model_id: str,
    timeout_seconds: int,
    max_steps: int,
    queue_mode: str,
    script: str,
    observation_path: Path,
    runtime_mode: str = "fake",
) -> dict[str, Any]:
    env = prepare_probe_environment(os.environ, runtime_mode=runtime_mode)
    env["LIBRETILES_AI_PLAY_WORKER"] = "1"
    env["BACKEND_URL"] = live_origin.rstrip("/")
    env["LIBRETILES_AI_PLAY_JWT"] = token
    env["LIBRETILES_AI_PLAY_GAME_ID"] = game_id
    env["LIBRETILES_AI_PLAY_PROVIDER"] = provider
    env["LIBRETILES_AI_PLAY_MODEL_ID"] = model_id
    env["LIBRETILES_AI_PLAY_TIMEOUT"] = str(timeout_seconds)
    env["LIBRETILES_AI_PLAY_MAX_STEPS"] = str(max_steps)
    env["LIBRETILES_AI_PLAY_QUEUE_MODE"] = queue_mode
    env["LIBRETILES_AI_PLAY_SCRIPT"] = script
    env["LIBRETILES_AI_PLAY_OBSERVATION"] = str(observation_path)
    worker = worker_script_for_runtime_mode(runtime_mode)
    completed = subprocess.run(
        ["npx", "vitest", "run", worker],
        cwd=_FRONTEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0 or not observation_path.is_file():
        detail = f"{completed.stderr or ''}\n{completed.stdout or ''}".strip()
        raise AssertionError((detail or "vitest worker failed")[-800:])
    payload = json.loads(observation_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _attempts_from_observation(payload: dict[str, Any]) -> tuple[TurnAttemptRecord, ...]:
    raw = payload.get("attempts")
    if not isinstance(raw, list):
        return ()
    records: list[TurnAttemptRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        provider = item.get("provider")
        model_id = item.get("model_id")
        if not isinstance(provider, str) or not isinstance(model_id, str):
            continue
        timeout = item.get("timeout_seconds")
        grant = item.get("step_grant")
        used = item.get("provider_requests_used")
        records.append(
            TurnAttemptRecord(
                provider=provider,
                model_id=model_id,
                timeout_seconds=timeout if isinstance(timeout, int) else 0,
                step_grant=grant if isinstance(grant, int) else 0,
                provider_requests_used=used if isinstance(used, int) else 0,
            )
        )
    return tuple(records)


def merge_turn_sample(
    *,
    session: GameSession,
    move_count_before: int,
    playability: dict[str, Any],
    observation: dict[str, Any],
    variant_slug: str,
    requested_runtime_mode: str = "fake",
) -> TurnSample:
    session.refresh_from_db()
    moves = list(session.moves.order_by("seq"))
    move = moves[-1] if len(moves) > move_count_before else None
    move_count_after = len(moves)
    delta = move_count_after - move_count_before
    sse_words = formed_words_from_payload(observation.get("formed_words"))
    sse_placements = placements_from_payload(observation.get("placements"))
    persisted_words = formed_words_from_payload(move.words_formed if move else [])
    persisted_placements = placements_from_payload(move.placements if move else [])
    action = observation.get("action")
    if move is not None:
        action = move.kind
    meta = move.ai_metadata if move is not None and isinstance(move.ai_metadata, dict) else {}
    source = observation.get("completion_source")
    if isinstance(meta.get("completion_source"), str):
        source = meta["completion_source"]
    cause = observation.get("terminal_cause")
    if isinstance(meta.get("terminal_cause"), str) and not cause:
        cause = meta["terminal_cause"]
    probe = observation.get("probe_status")
    if isinstance(meta.get("probe_status"), str) and not probe:
        probe = meta["probe_status"]
    formed = persisted_words or sse_words
    context = load_variant_context(variant_slug)
    rejected = classify_complete_formed_words(
        formed,
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )
    playability_status = str(playability.get("status") or "indeterminate")
    witness = playability.get("witness")
    terminal_kind = str(observation.get("terminal_kind") or "no_terminal")
    lost = bool(observation.get("lost_terminal"))
    coded = bool(observation.get("coded_provider_error"))
    score = move.points if move is not None else int(observation.get("score") or 0)
    driver_raw = observation.get("driver")
    driver = driver_raw if driver_raw in {"fake", "live"} else "fake"
    sentinel_present = bool(observation.get("sentinel_present"))
    executed_raw = observation.get("executed_runtime_mode")
    executed_runtime_mode = (
        executed_raw
        if executed_raw in {"fake", "live"}
        else derive_executed_runtime_mode(
            driver=driver, sentinel_present=sentinel_present
        )
    )
    verdict, reason = classify_turn_sample(
        playability_status=playability_status,
        action=action if isinstance(action, str) else None,
        formed_words=formed,
        sse_words=sse_words,
        persisted_words=persisted_words,
        sse_placements=sse_placements,
        persisted_placements=persisted_placements,
        rejected_two_letter_words=rejected,
        terminal_kind=terminal_kind,
        completion_source=source if isinstance(source, str) else None,
        terminal_cause=cause if isinstance(cause, str) else None,
        coded_provider_error=coded,
        move_count_delta=delta,
        move_id=move.id if move is not None else None,
        lost_terminal=lost,
        variant_letters=context.letters,
        requested_runtime_mode=requested_runtime_mode,
        executed_runtime_mode=executed_runtime_mode,
    )
    queue_raw = observation.get("queue_length")
    used_raw = observation.get("turn_provider_requests_used")
    unresolved_raw = observation.get("unresolved_in_flight")
    external_raw = observation.get("external_provider_invocations")
    backend_raw = observation.get("backend_origins")
    foreign_raw = observation.get("foreign_origins")
    return TurnSample(
        playability_status=playability_status,
        witness=witness if isinstance(witness, dict) else None,
        action=action if isinstance(action, str) else None,
        placements=persisted_placements or sse_placements,
        formed_words=formed,
        score=score,
        completion_source=source if isinstance(source, str) else None,
        probe_status=probe if isinstance(probe, str) else playability_status,
        repair_attempted=observation.get("repair_attempted")
        if isinstance(observation.get("repair_attempted"), bool)
        else None,
        terminal_cause=cause if isinstance(cause, str) else None,
        attempts=_attempts_from_observation(observation),
        turn_provider_requests_used=used_raw if isinstance(used_raw, int) else 0,
        queue_length=queue_raw if isinstance(queue_raw, int) else 0,
        unresolved_in_flight=unresolved_raw if isinstance(unresolved_raw, int) else 0,
        persistence=TurnPersistenceEvidence(
            move_id=move.id if move is not None else None,
            move_count_delta=delta,
            state_version_delta=delta,
            action_matches_sse=move is None
            or observation.get("action") in {None, move.kind},
            words_match_sse=not sse_words
            or {nfc_upper(word) for word in sse_words}
            <= {nfc_upper(word) for word in persisted_words},
            score_matches_sse=move is None
            or int(observation.get("score") or 0) in {0, move.points},
        ),
        rejected_two_letter_words=rejected,
        terminal_kind=terminal_kind,
        lost_terminal=lost,
        external_provider_invocations=external_raw if isinstance(external_raw, int) else 0,
        backend_origins=tuple(
            origin for origin in backend_raw if isinstance(origin, str)
        )
        if isinstance(backend_raw, list)
        else (),
        foreign_origins=tuple(
            origin for origin in foreign_raw if isinstance(origin, str)
        )
        if isinstance(foreign_raw, list)
        else (),
        executed_runtime_mode=executed_runtime_mode,
        verdict=verdict,
        reason_code=reason,
    )


def run_isolated_turn(
    live_server: Any,
    tmp_path: Path,
    *,
    variant_slug: str,
    fixture_id: str | None = None,
    provider: str,
    model_id: str,
    queue_mode: str = "selected-only",
    script: str = "noop_rescue",
    timeout_seconds: int = 60,
    max_steps: int = 30,
    seed: int | None = None,
    runtime_mode: str = "fake",
) -> tuple[TurnSample, GameSession, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    seed_catalog()
    user = User.objects.create_user(
        username=f"diag-turn-{session_suffix()}",
        password="diag-pass-xx",
    )
    token = mint_token(user)
    session = prepare_game(
        user=user,
        variant_slug=variant_slug,
        fixture_id=fixture_id,
        seed=seed,
        model_id=model_id,
    )
    move_count_before = session.moves.count()
    playability = services.get_ai_playability(str(session.public_id), user.id)
    observation_path = tmp_path / f"{session.public_id.hex}.obs.json"
    observation = spawn_worker(
        live_origin=live_server.url,
        token=token,
        game_id=str(session.public_id),
        provider=provider,
        model_id=model_id,
        timeout_seconds=timeout_seconds,
        max_steps=max_steps,
        queue_mode=queue_mode,
        script=script,
        observation_path=observation_path,
        runtime_mode=runtime_mode,
    )
    sample = merge_turn_sample(
        session=session,
        move_count_before=move_count_before,
        playability=playability,
        observation=observation,
        variant_slug=variant_slug,
        requested_runtime_mode=runtime_mode,
    )
    return sample, session, observation


@pytest.mark.django_db(transaction=True)
def test_run_turn_from_handoff(live_server: Any, tmp_path: Path) -> None:
    handoff_path = os.environ.get(HANDOFF_ENV)
    if not handoff_path:
        pytest.skip("handoff worker node")
    handoff = json.loads(Path(handoff_path).read_text(encoding="utf-8"))
    assert isinstance(handoff, dict)
    variant_slug = str(handoff["variant_slug"])
    provider = str(handoff["provider"])
    model_id = str(handoff["model_id"])
    fixture_id = handoff.get("fixture_id")
    seed = handoff.get("seed")
    turn_count = int(handoff.get("turn_count") or 1)
    queue_mode = str(handoff.get("queue_mode") or "selected-only")
    script = str(handoff.get("script") or "noop_rescue")
    timeout_seconds = int(handoff.get("timeout_seconds") or 60)
    max_steps = int(handoff.get("max_steps") or 30)
    runtime_mode = str(handoff.get("runtime_mode") or "fake")
    result_path = Path(str(handoff["result_path"]))
    samples: list[dict[str, Any]] = []
    for index in range(turn_count):
        sample, _session, _obs = run_isolated_turn(
            live_server,
            tmp_path / str(index),
            variant_slug=variant_slug,
            fixture_id=fixture_id if isinstance(fixture_id, str) else None,
            seed=seed if isinstance(seed, int) else None,
            provider=provider,
            model_id=model_id,
            queue_mode=queue_mode,
            script=script,
            timeout_seconds=timeout_seconds,
            max_steps=max_steps,
            runtime_mode=runtime_mode,
        )
        samples.append(turn_sample_to_dict(sample))
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps({"samples": samples}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.mark.django_db(transaction=True)
def test_diagnostic_worker_uses_isolated_live_server_and_persists_one_move(
    live_server: Any, tmp_path: Path
) -> None:
    sample, session, observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-empty-autolin",
        provider="openrouter",
        model_id=_GEMMA,
    )
    assert sample.persistence.move_count_delta == 1
    assert sample.persistence.move_id is not None
    assert session.moves.count() == 1
    assert sample.action == "place"
    assert sample.completion_source in {
        "provider_candidate",
        "backend_ranked_candidate",
        "repair_candidate",
        "backend_witness_rescue",
    }
    assert sample.verdict == "pass"
    assert new_origin(live_server.url) in sample.backend_origins


@pytest.mark.django_db(transaction=True)
def test_slovak_unicode_witness_round_trips_from_backend_through_sse_to_move(
    live_server: Any, tmp_path: Path
) -> None:
    sample, session, _observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="slovak",
        fixture_id="slovak-turn-diacritic-blank",
        provider=_NIM_PROVIDER,
        model_id=_NIM,
    )
    move = session.moves.get()
    placements = placements_from_payload(move.placements)
    letters = [str(item.get("letter")) for item in placements]
    blanks = [str(item.get("blank_as")) for item in placements if item.get("letter") == "?"]
    assert any(is_diacritic_letter(letter) for letter in letters)
    assert any(is_diacritic_letter(blank) for blank in blanks)
    assert sample.verdict == "pass"
    assert sample.reason_code != "stale_witness"
    meta = move.ai_metadata if isinstance(move.ai_metadata, dict) else {}
    assert meta.get("completion_source") != "stale_witness"
    formed = formed_words_from_payload(move.words_formed)
    assert any("Č" in _nfc(word).upper() or "Í" in _nfc(word).upper() for word in formed)
    assert sample.persistence.words_match_sse or sample.completion_source in {
        "backend_ranked_candidate",
        "backend_witness_rescue",
        "provider_candidate",
    }


@pytest.mark.django_db(transaction=True)
def test_found_probe_never_accepts_pass_or_exchange(
    live_server: Any, tmp_path: Path
) -> None:
    sample, session, _observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="slovak",
        fixture_id="slovak-hooks-umenasi",
        provider=_NIM_PROVIDER,
        model_id=_NIM,
    )
    assert sample.playability_status == "found"
    assert sample.action == "place"
    assert session.moves.get().kind == "place"
    assert sample.verdict == "pass"


@pytest.mark.django_db(transaction=True)
def test_none_probe_with_full_bag_exchanges_instead_of_passing(
    live_server: Any, tmp_path: Path
) -> None:
    sample, session, _observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-turn-dead-qqq",
        provider="openrouter",
        model_id=_GEMMA,
    )
    assert sample.playability_status == "none"
    assert sample.action == "exchange"
    assert session.moves.get().kind == "exchange"
    assert sample.completion_source == "genuine_no_move_exchange"
    assert sample.verdict == "pass"


@pytest.mark.django_db(transaction=True)
def test_generic_unchanged_turn_is_mechanical_failure(
    live_server: Any, tmp_path: Path
) -> None:
    sample, session, _observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-empty-autolin",
        provider="openrouter",
        model_id=_GEMMA,
        script="generic_unchanged",
    )
    assert session.moves.count() == 0
    assert sample.persistence.move_count_delta == 0
    assert sample.verdict == "fail"
    assert sample.reason_code == "generic_unchanged_turn"


@pytest.mark.django_db(transaction=True)
def test_persist_then_lost_terminal_is_pass_with_telemetry(
    live_server: Any, tmp_path: Path
) -> None:
    sample, session, _observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-empty-autolin",
        provider="openrouter",
        model_id=_GEMMA,
        script="drop_done",
    )
    assert session.moves.count() == 1
    assert sample.lost_terminal is True
    assert sample.verdict == "pass_with_telemetry"


@pytest.mark.django_db(transaction=True)
def test_selected_only_queue_runs_exact_requested_pair(
    live_server: Any, tmp_path: Path
) -> None:
    sample, _session, observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-empty-autolin",
        provider=_NIM_PROVIDER,
        model_id=_NIM,
        queue_mode="selected-only",
    )
    assert sample.queue_length == 1
    queue = observation.get("queue")
    assert queue == [{"provider": _NIM_PROVIDER, "model_id": _NIM}]
    assert sample.attempts[0].model_id == _NIM
    assert sample.attempts[0].provider == _NIM_PROVIDER


@pytest.mark.django_db(transaction=True)
def test_catalog_fallback_is_preference_first_and_at_most_three_pairs(
    live_server: Any, tmp_path: Path
) -> None:
    sample, _session, observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-empty-autolin",
        provider=_NIM_PROVIDER,
        model_id=_NIM,
        queue_mode="catalog-fallback",
    )
    queue = observation.get("queue")
    assert isinstance(queue, list)
    assert 1 <= len(queue) <= 3
    assert queue[0] == {"provider": _NIM_PROVIDER, "model_id": _NIM}
    assert sample.queue_length == len(queue)


@pytest.mark.django_db(transaction=True)
def test_fake_mode_contacts_no_origin_other_than_the_ephemeral_backend(
    live_server: Any, tmp_path: Path
) -> None:
    sample, _session, observation = run_isolated_turn(
        live_server,
        tmp_path,
        variant_slug="english",
        fixture_id="english-empty-autolin",
        provider="openrouter",
        model_id=_GEMMA,
    )
    origin = new_origin(live_server.url)
    assert sample.foreign_origins == ()
    assert observation.get("foreign_origins") == []
    assert origin in sample.backend_origins
    assert sample.external_provider_invocations == 0
    assert sample.executed_runtime_mode == "fake"
    assert sample.verdict == "pass"


def _capture_spawn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []

    def fake_run(
        args: list[object],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        argv = [str(item) for item in args]
        env = kwargs.get("env") or {}
        observation_raw = env.get("LIBRETILES_AI_PLAY_OBSERVATION")
        assert isinstance(observation_raw, str)
        Path(observation_raw).write_text("{}\n", encoding="utf-8")
        captured.append({"args": argv, "env": env})
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_probe_selects_live_driver_for_live_and_fake_driver_for_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_spawn(monkeypatch)
    spawn_worker(
        live_origin="http://127.0.0.1:9",
        token="t",
        game_id="g",
        provider=_NIM_PROVIDER,
        model_id=_NIM,
        timeout_seconds=60,
        max_steps=30,
        queue_mode="selected-only",
        script="noop_rescue",
        observation_path=tmp_path / "live.obs.json",
        runtime_mode="live",
    )
    spawn_worker(
        live_origin="http://127.0.0.1:9",
        token="t",
        game_id="g",
        provider="openrouter",
        model_id=_GEMMA,
        timeout_seconds=60,
        max_steps=30,
        queue_mode="selected-only",
        script="noop_rescue",
        observation_path=tmp_path / "fake.obs.json",
        runtime_mode="fake",
    )
    assert captured[0]["args"] == ["npx", "vitest", "run", LIVE_WORKER_SCRIPT]
    assert captured[1]["args"] == ["npx", "vitest", "run", FAKE_WORKER_SCRIPT]
    assert FAKE_WORKER_SCRIPT not in captured[0]["args"]
    assert LIVE_WORKER_SCRIPT not in captured[1]["args"]


def test_probe_preserves_sentinel_for_live_and_omits_it_for_fake(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_spawn(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nim-diagnostic-fixture-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-diagnostic-fixture-key")
    monkeypatch.setenv("UNRELATED_API_KEY", "decoy-must-not-be-special-cased")
    spawn_worker(
        live_origin="http://127.0.0.1:9",
        token="t",
        game_id="g",
        provider=_NIM_PROVIDER,
        model_id=_NIM,
        timeout_seconds=60,
        max_steps=30,
        queue_mode="selected-only",
        script="noop_rescue",
        observation_path=tmp_path / "live.obs.json",
        runtime_mode="live",
    )
    spawn_worker(
        live_origin="http://127.0.0.1:9",
        token="t",
        game_id="g",
        provider="openrouter",
        model_id=_GEMMA,
        timeout_seconds=60,
        max_steps=30,
        queue_mode="selected-only",
        script="noop_rescue",
        observation_path=tmp_path / "fake.obs.json",
        runtime_mode="fake",
    )
    live_env = captured[0]["env"]
    fake_env = captured[1]["env"]
    assert live_env.get(LIVE_SENTINEL) == "1"
    assert LIVE_SENTINEL not in fake_env
    assert "NVIDIA_API_KEY" in live_env
    assert "OPENROUTER_API_KEY" in live_env
    assert "NVIDIA_API_KEY" not in fake_env
    assert "OPENROUTER_API_KEY" not in fake_env
