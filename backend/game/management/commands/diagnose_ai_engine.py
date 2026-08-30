"""Provider-free variant-aware engine diagnostic command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from game.diagnostics import (
    DiagnosticInputError,
    PROBE_COUNT_MAX,
    PROBE_COUNT_MIN,
    UINT32_MAX,
    bound_text,
    build_diagnostic_report,
    dump_report_json,
    format_metric_line,
    load_variant_context,
    resolve_engine_scenario,
    run_engine_probe,
    write_report_atomically,
)


class Command(BaseCommand):
    help = (
        "Run a provider-free ranked-search engine probe and emit a v1 JSON report."
    )
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--variant-slug", required=True)
        parser.add_argument("--fixture-id", default=None)
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--probe-count", type=int, default=1)
        parser.add_argument("--output", default="-")

    def handle(self, *args: Any, **options: Any) -> None:
        fail_count = 0
        try:
            variant_slug, fixture_id, seed, probe_count, output = _validated_request(
                options
            )
            scenario = resolve_engine_scenario(
                variant_slug=variant_slug,
                fixture_id=fixture_id,
                seed=seed,
            )
            context = load_variant_context(variant_slug)
            samples = []
            for index in range(probe_count):
                sample = run_engine_probe(scenario, context)
                samples.append(sample)
                label = fixture_id if fixture_id is not None else f"seed={seed}#{index}"
                self.stderr.write(format_metric_line(variant_slug, str(label), sample))
            requested: dict[str, str | int] = {
                "variant_slug": variant_slug,
                "probe_count": probe_count,
            }
            if fixture_id is not None:
                requested["fixture_id"] = fixture_id
            else:
                requested["seed"] = seed if seed is not None else 0
            report = build_diagnostic_report(
                requested=requested,
                context=context,
                samples=samples,
            )
            payload = dump_report_json(report)
            if output == "-":
                self.stdout.write(payload, ending="")
            else:
                write_report_atomically(Path(output), payload)
            summary_fail = report["summary"]["fail_count"]
            fail_count = summary_fail if isinstance(summary_fail, int) else 0
        except DiagnosticInputError as exc:
            raise CommandError(bound_text(str(exc)), returncode=2) from None
        if fail_count > 0:
            raise CommandError(
                bound_text(f"engine diagnostic failed ({fail_count} sample(s))"),
                returncode=1,
            )


def _validated_request(
    options: dict[str, Any],
) -> tuple[str, str | None, int | None, int, str]:
    variant_slug = options.get("variant_slug")
    if not isinstance(variant_slug, str) or not variant_slug:
        raise DiagnosticInputError("--variant-slug is required")
    fixture_raw = options.get("fixture_id")
    fixture_id: str | None
    if fixture_raw is None or fixture_raw == "":
        fixture_id = None
    elif isinstance(fixture_raw, str):
        fixture_id = fixture_raw
    else:
        raise DiagnosticInputError("--fixture-id must be a string")
    seed_raw = options.get("seed")
    seed: int | None
    if seed_raw is None:
        seed = None
    elif isinstance(seed_raw, bool) or not isinstance(seed_raw, int):
        raise DiagnosticInputError("--seed must be a UINT32 integer")
    elif seed_raw < 0 or seed_raw > UINT32_MAX:
        raise DiagnosticInputError("--seed must be in 0..4294967295")
    else:
        seed = seed_raw
    probe_raw = options.get("probe_count", 1)
    if isinstance(probe_raw, bool) or not isinstance(probe_raw, int):
        raise DiagnosticInputError("--probe-count must be an integer")
    if probe_raw < PROBE_COUNT_MIN or probe_raw > PROBE_COUNT_MAX:
        raise DiagnosticInputError("--probe-count must be in 1..300")
    output_raw = options.get("output") or "-"
    if not isinstance(output_raw, str) or not output_raw:
        raise DiagnosticInputError("--output must be a path or '-'")
    if output_raw != "-":
        path = Path(output_raw)
        if path.exists():
            raise DiagnosticInputError("output path already exists")
        if not path.parent.is_dir():
            raise DiagnosticInputError("output directory does not exist")
    return variant_slug, fixture_id, seed, probe_raw, output_raw
