from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from catalog.models import AIModel, AIPrompt
from catalog.selection import get_selectable_models, get_selectable_prompts

from .analytics_expressions import average, nonnegative_number, rounded
from .models import DiagnosticRun, GameSession, Move, PlayerSlot, PlaygroundSimulation

COMPLETION_SOURCES = (
    "provider_candidate",
    "backend_ranked_candidate",
    "repair_candidate",
    "backend_witness_rescue",
    "genuine_no_move_exchange",
    "genuine_no_move_pass",
)


def _model_row(provider: str, model_id: str, display_name: str, source: str) -> dict[str, Any]:
    return {
        "key": f"{provider}:{model_id}",
        "provider": provider,
        "model_id": model_id,
        "display_name": display_name,
        "source": source,
        "runtime_mode": "local" if provider == "engine" else "provider",
        "is_selectable": False,
        "is_current_flagship": False,
        "catalog_order": 10_000,
        "games": set(),
        "seat_appearances": 0,
        "completed_seats": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "scores": [],
        "spreads": [],
        "pass_streaks": [],
        "total_moves": 0,
        "completion_source_counts": Counter(),
        "known_completion_source_moves": 0,
        "attempt_latencies": [],
        "turn_latencies": [],
        "turn_requests": [],
        "limitations": [],
    }


def _preset_row(prompt_id: int | None, name: str) -> dict[str, Any]:
    return {
        "prompt_id": prompt_id,
        "name": name,
        "games": set(),
        "seat_appearances": 0,
        "completed_seats": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "scores": [],
    }


def _wilson_lower(wins: int, total: int) -> float:
    if total <= 0:
        return -1.0
    z = 1.959963984540054
    rate = wins / total
    denominator = 1 + z * z / total
    center = rate + z * z / (2 * total)
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * total)) / total)
    return (center - margin) / denominator


def _recommendation(
    *, status: str, model: dict[str, Any] | None = None, prompt: dict[str, Any] | None = None,
    reasons: list[str], variant_slug: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "provider": model.get("provider") if model else None,
        "model_id": model.get("model_id") if model else None,
        "display_name": model.get("display_name") if model else None,
        "prompt_id": prompt.get("prompt_id") if prompt else None,
        "prompt_name": prompt.get("name") if prompt else None,
        "reason_codes": reasons,
        "evidence": {
            "completed_seats": model.get("completed_seats", 0) if model else prompt.get("completed_seats", 0) if prompt else 0,
            "measured_attempts": len(model.get("attempt_latencies", [])) if model else 0,
            "variant_slug": variant_slug,
        },
    }


def build_admin_analytics(
    *, days: int, source: str, variant_slug: str, as_of: Any | None = None
) -> dict[str, Any]:
    as_of = as_of or timezone.now()
    games = GameSession.objects.filter(created_at__gte=as_of - timedelta(days=days), created_at__lt=as_of)
    if variant_slug != "all":
        games = games.filter(variant_slug=variant_slug)
    playground_ids = set(PlaygroundSimulation.objects.filter(game__in=games).values_list("game_id", flat=True))
    diagnostic_ids = set(games.filter(is_diagnostic=True).values_list("id", flat=True))
    if source == "playground":
        games = games.filter(id__in=playground_ids)
    elif source == "diagnostic":
        games = games.filter(id__in=diagnostic_ids)
    elif source == "gameplay":
        games = games.exclude(id__in=playground_ids | diagnostic_ids)

    game_rows = list(
        games.annotate(move_count=Count("moves", distinct=True)).values(
            "id", "status", "game_over", "winner_slot", "variant_slug", "move_count"
        )
    )
    game_by_id = {row["id"]: row for row in game_rows}
    game_ids = set(game_by_id)
    snapshots = {
        row["game_id"]: row["config_json"]
        for row in PlaygroundSimulation.objects.filter(game_id__in=game_ids).values("game_id", "config_json")
    }
    catalog = {
        row["id"]: row
        for row in AIModel.objects.values("id", "provider", "model_id", "display_name")
    }
    prompts = {row["id"]: row for row in AIPrompt.objects.values("id", "name")}
    selectable = get_selectable_models()
    selectable_pairs = {(row.provider, row.model_id): (index, row) for index, row in enumerate(selectable)}

    models: dict[tuple[str, str], dict[str, Any]] = {}
    presets: dict[tuple[int | None, str], dict[str, Any]] = {}
    for index, row in enumerate(selectable):
        metric = _model_row(row.provider, row.model_id, row.display_name, "catalog")
        metric["is_selectable"] = True
        metric["is_current_flagship"] = index == 0
        metric["catalog_order"] = index
        models[(row.provider, row.model_id)] = metric
    models[("engine", "engine/cpu")] = _model_row("engine", "engine/cpu", "CPU Master", "playground")

    selectable_prompts = get_selectable_prompts()
    for selectable_prompt in selectable_prompts:
        presets[(selectable_prompt.id, selectable_prompt.name)] = _preset_row(selectable_prompt.id, selectable_prompt.name)

    all_seats = list(
        PlayerSlot.objects.filter(game_id__in=game_ids).values(
            "id", "game_id", "slot", "score", "pass_streak", "is_ai", "ai_model_id", "ai_prompt_id"
        )
    )
    score_by_game_slot = {(seat["game_id"], seat["slot"]): seat["score"] for seat in all_seats}
    seat_identity: dict[int, tuple[str, str]] = {}
    for seat in (row for row in all_seats if row["is_ai"]):
        game = game_by_id[seat["game_id"]]
        snapshot_slots = snapshots.get(seat["game_id"], {}).get("slots", [])
        snapshot = snapshot_slots[seat["slot"]] if isinstance(snapshot_slots, list) and seat["slot"] < len(snapshot_slots) else {}
        model = catalog.get(seat["ai_model_id"])
        provider = snapshot.get("provider") if isinstance(snapshot, dict) else None
        model_id = snapshot.get("model_id") if isinstance(snapshot, dict) else None
        display_name = snapshot.get("display_name") if isinstance(snapshot, dict) else None
        if not isinstance(provider, str) or not isinstance(model_id, str):
            if model:
                provider, model_id, display_name = model["provider"], model["model_id"], model["display_name"]
            else:
                provider, model_id, display_name = "unknown", "unknown", "Unknown model"
        key = (provider, model_id)
        metric = models.setdefault(key, _model_row(provider, model_id, str(display_name or model_id), "historical"))
        selectable_item = selectable_pairs.get(key)
        if selectable_item:
            metric["is_selectable"] = True
            metric["catalog_order"] = selectable_item[0]
        metric["games"].add(seat["game_id"])
        metric["seat_appearances"] += 1
        seat_identity[seat["id"]] = key
        finished = game["status"] == "finished" and game["game_over"]
        if finished:
            metric["completed_seats"] += 1
            metric["scores"].append(float(seat["score"]))
            metric["pass_streaks"].append(float(seat["pass_streak"]))
            opponent_score = score_by_game_slot.get((seat["game_id"], 1 - seat["slot"]))
            if opponent_score is not None:
                metric["spreads"].append(float(seat["score"] - opponent_score))
            if game["winner_slot"] is None:
                metric["draws"] += 1
            elif game["winner_slot"] == seat["slot"]:
                metric["wins"] += 1
            else:
                metric["losses"] += 1

        prompt_id = snapshot.get("prompt_id") if isinstance(snapshot, dict) else seat["ai_prompt_id"]
        prompt_name = snapshot.get("prompt_name") if isinstance(snapshot, dict) else None
        prompt_record = prompts.get(prompt_id) if isinstance(prompt_id, int) else None
        if not isinstance(prompt_name, str) and prompt_record:
            prompt_name = prompt_record["name"]
        if prompt_id is not None and isinstance(prompt_name, str):
            preset = presets.setdefault((prompt_id, prompt_name), _preset_row(prompt_id, prompt_name))
            preset["games"].add(seat["game_id"])
            preset["seat_appearances"] += 1
            if finished:
                preset["completed_seats"] += 1
                preset["scores"].append(float(seat["score"]))
                if game["winner_slot"] is None:
                    preset["draws"] += 1
                elif game["winner_slot"] == seat["slot"]:
                    preset["wins"] += 1
                else:
                    preset["losses"] += 1

    unknown_runtime_moves = 0
    unknown_completion_moves = 0
    for move in Move.objects.filter(game_id__in=game_ids).values("player_slot_id", "ai_metadata"):
        metadata = move["ai_metadata"] if isinstance(move["ai_metadata"], dict) else {}
        provider = metadata.get("runtime_provider")
        model_id = metadata.get("runtime_model_id")
        move_key = (provider, model_id) if isinstance(provider, str) and isinstance(model_id, str) else seat_identity.get(move["player_slot_id"])
        if move_key is None:
            unknown_runtime_moves += 1
            continue
        metric = models.setdefault(move_key, _model_row(move_key[0], move_key[1], move_key[1], "runtime"))
        metric["total_moves"] += 1
        completion = metadata.get("completion_source")
        if completion in COMPLETION_SOURCES:
            metric["completion_source_counts"][completion] += 1
            metric["known_completion_source_moves"] += 1
        else:
            unknown_completion_moves += 1
        trace = metadata.get("inspection_trace")
        attempts = trace.get("attempts") if isinstance(trace, dict) and trace.get("version") == 1 else None
        parsed_attempts: list[tuple[tuple[str, str], float, float]] = []
        if isinstance(attempts, list):
            for attempt in attempts[:3]:
                if not isinstance(attempt, dict):
                    continue
                latency = nonnegative_number(attempt.get("latency_ms"))
                requests = nonnegative_number(attempt.get("provider_requests_used"))
                attempt_provider = attempt.get("provider")
                attempt_model = attempt.get("model_id")
                if latency is None or requests is None or not isinstance(attempt_provider, str) or not isinstance(attempt_model, str):
                    continue
                attempt_key = (attempt_provider, attempt_model)
                attempt_metric = models.setdefault(attempt_key, _model_row(*attempt_key, attempt_model, "runtime"))
                attempt_metric["attempt_latencies"].append(latency)
                parsed_attempts.append((attempt_key, latency, requests))
        if isinstance(attempts, list) and parsed_attempts and [item.get("attempt_index") for item in attempts if isinstance(item, dict)] == list(range(len(attempts))) and parsed_attempts[-1][0] == move_key:
            metric["turn_latencies"].append(sum(item[1] for item in parsed_attempts))
            metric["turn_requests"].append(sum(item[2] for item in parsed_attempts))

    variant_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_games": 0, "total_plies": 0}
    )
    for game_row in game_rows:
        variant_totals[game_row["variant_slug"]]["total_games"] += 1
        variant_totals[game_row["variant_slug"]]["total_plies"] += game_row["move_count"]
    variant_counts = [
        {"variant_slug": slug, **counts}
        for slug, counts in sorted(variant_totals.items())
    ]
    finished_by_variant = Counter(row["variant_slug"] for row in game_rows if row["status"] == "finished" and row["game_over"])
    variants = [
        {**row, "finished_games": finished_by_variant[row["variant_slug"]]}
        for row in variant_counts
    ]

    model_rows = []
    for metric in models.values():
        completed = metric["completed_seats"]
        known = metric["known_completion_source_moves"]
        model_rows.append({
            **{key: metric[key] for key in ("key", "provider", "model_id", "display_name", "source", "runtime_mode", "is_selectable", "is_current_flagship", "catalog_order")},
            "games_played": len(metric["games"]), "seat_appearances": metric["seat_appearances"],
            "completed_seats": completed, "wins": metric["wins"], "losses": metric["losses"], "draws": metric["draws"],
            "win_rate_pct": rounded(100 * metric["wins"] / completed) if completed else None,
            "avg_score": rounded(average(metric["scores"])), "avg_spread": rounded(average(metric["spreads"])),
            "avg_terminal_pass_streak": rounded(average(metric["pass_streaks"])),
            "total_moves": metric["total_moves"], "completion_source_counts": {name: metric["completion_source_counts"][name] for name in COMPLETION_SOURCES},
            "known_completion_source_moves": known,
            "provider_candidate_pct": rounded(100 * metric["completion_source_counts"]["provider_candidate"] / known) if known and metric["provider"] != "engine" else None,
            "avg_attempt_latency_ms": rounded(average(metric["attempt_latencies"])), "measured_attempts": len(metric["attempt_latencies"]),
            "avg_recorded_turn_latency_ms": rounded(average(metric["turn_latencies"])), "measured_turns": len(metric["turn_latencies"]),
            "avg_provider_requests_per_turn": rounded(average(metric["turn_requests"])), "request_measured_turns": len(metric["turn_requests"]),
            "identity_basis": metric["source"], "limitations": metric["limitations"],
            "_raw": metric,
        })
    model_rows.sort(key=lambda row: (row["catalog_order"], row["display_name"], row["key"]))

    preset_rows = []
    for preset in presets.values():
        completed = preset["completed_seats"]
        preset_rows.append({
            "prompt_id": preset["prompt_id"], "name": preset["name"], "games_played": len(preset["games"]),
            "seat_appearances": preset["seat_appearances"], "completed_seats": completed,
            "wins": preset["wins"], "losses": preset["losses"], "draws": preset["draws"],
            "win_rate_pct": rounded(100 * preset["wins"] / completed) if completed else None,
            "avg_score": rounded(average(preset["scores"])), "content_version_verified": False,
            "_raw": preset,
        })
    prompt_order = {prompt.name: index for index, prompt in enumerate(selectable_prompts)}
    preset_rows.sort(key=lambda row: (prompt_order.get(row["name"], 10_000), row["name"]))

    flagship = next((row for row in model_rows if row["is_current_flagship"]), None)
    candidates = [row for row in model_rows if row["is_selectable"] and row["completed_seats"] > 0]
    candidates.sort(key=lambda row: (_wilson_lower(row["wins"], row["completed_seats"]), row["win_rate_pct"] or -1, row["avg_score"] or -10**9, -row["catalog_order"]), reverse=True)
    leader = candidates[0] if candidates else flagship
    throughput = min((row for row in candidates if row["avg_attempt_latency_ms"] is not None), key=lambda row: (row["avg_attempt_latency_ms"], row["catalog_order"]), default=None)
    preset_candidates = [row for row in preset_rows if row["completed_seats"] > 0]
    preset_candidates.sort(key=lambda row: (row["win_rate_pct"] or -1, row["avg_score"] or -10**9, row["name"]), reverse=True)
    strategic = preset_candidates[0] if preset_candidates else None
    recommendation_variant = variant_slug if variant_slug != "all" else None
    recommendations = {
        "current_flagship": _recommendation(status="catalog_default", model=flagship, reasons=["catalog_order_row_1"], variant_slug=recommendation_variant),
        "primary_flagship": _recommendation(status="observed_leader" if candidates else "catalog_default", model=leader, reasons=["wilson_win_rate_score_rank"] if candidates else ["insufficient_comparable_outcomes"], variant_slug=recommendation_variant),
        "high_throughput_rival": _recommendation(status="observed_leader" if throughput else "insufficient_evidence", model=throughput, reasons=["lowest_measured_attempt_latency"] if throughput else ["no_measured_attempt_latency"], variant_slug=recommendation_variant),
        "offline_cpu": _recommendation(status="available", model=next(row for row in model_rows if row["model_id"] == "engine/cpu"), reasons=["zero_external_provider_requests"], variant_slug=recommendation_variant),
        "strategic_preset": _recommendation(status="observed_leader" if strategic else "insufficient_evidence", prompt=strategic, reasons=["highest_observed_win_rate"] if strategic else ["no_completed_preset_seats"], variant_slug=recommendation_variant),
        "reliability_notes": ["Observed results are descriptive, not a provider availability guarantee.", "CPU Master makes no external provider requests; VPS throughput remains host-dependent."],
        "changes_catalog": False,
    }
    for model_output in model_rows:
        model_output.pop("_raw")
    for preset_output in preset_rows:
        preset_output.pop("_raw")
    diagnostic_runs = DiagnosticRun.objects.filter(session_id__in=game_ids).count()
    return {
        "analytics_schema_version": 1,
        "as_of": as_of.isoformat(),
        "filters": {"days": days, "source": source, "variant_slug": variant_slug},
        "summary": {
            "total_games": len(game_rows), "finished_games": sum(row["status"] == "finished" and row["game_over"] for row in game_rows),
            "total_plies": sum(row["move_count"] for row in game_rows), "variants_played": len(variants), "variants": variants,
            "abandoned_games": sum(row["status"] == "abandoned" for row in game_rows), "diagnostic_runs": diagnostic_runs,
        },
        "models": model_rows, "presets": preset_rows, "recommendations": recommendations,
        "coverage": {
            "unknown_runtime_moves": unknown_runtime_moves, "unknown_completion_source_moves": unknown_completion_moves,
            "limitations": ["historical_prompt_content_unverified", "stored_turns_do_not_measure_provider_outages"],
        },
    }
