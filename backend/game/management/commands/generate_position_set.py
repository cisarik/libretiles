"""Provider-free position-set generator command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from game.diagnostics import (
    UINT32_MAX,
    DiagnosticInputError,
    bound_text,
    write_report_atomically,
)
from game.position_sets import (
    TOTAL_MAX,
    TOTAL_MIN,
    PositionSetConfig,
    PositionSetError,
    default_output_path,
    dump_position_set_json,
    generate_position_set,
    positions_per_phase_for_total,
    trim_position_set,
)


class Command(BaseCommand):
    help = (
        "Generate a byte-stable engine position-set JSON asset with node-bound "
        "ranked-search baselines."
    )
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--variant-slug", required=True)
        parser.add_argument("--seeds", default="300,301,302")
        parser.add_argument("--total", type=int, default=24)
        parser.add_argument("--output", default=None)

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            variant_slug, seeds, total, output = _validated_request(options)
            config = PositionSetConfig(
                variant_slug=variant_slug,
                seeds=seeds,
                positions_per_phase=positions_per_phase_for_total(total),
            )
            asset = generate_position_set(config)
            if len(asset["positions"]) > total:
                asset = trim_position_set(asset, total)
            payload = dump_position_set_json(asset)
            set_digest = asset["set_digest"]
            if not isinstance(set_digest, str):
                raise PositionSetError("set_digest must be a string")
            path = output if output is not None else default_output_path(
                variant_slug, set_digest
            )
            write_report_atomically(path, payload)
            self.stdout.write(
                f"position-set {variant_slug} positions={len(asset['positions'])} "
                f"set_digest={set_digest}"
            )
        except DiagnosticInputError as exc:
            raise CommandError(bound_text(str(exc)), returncode=2) from None
        except PositionSetError as exc:
            raise CommandError(bound_text(str(exc)), returncode=1) from None


def _validated_request(
    options: dict[str, Any],
) -> tuple[str, tuple[int, ...], int, Path | None]:
    variant_slug = options.get("variant_slug")
    if not isinstance(variant_slug, str) or not variant_slug:
        raise DiagnosticInputError("--variant-slug is required")
    seeds = _parse_seeds(options.get("seeds"))
    total_raw = options.get("total", 24)
    if isinstance(total_raw, bool) or not isinstance(total_raw, int):
        raise DiagnosticInputError("--total must be an integer")
    if total_raw < TOTAL_MIN or total_raw > TOTAL_MAX:
        raise DiagnosticInputError(f"--total must be in {TOTAL_MIN}..{TOTAL_MAX}")
    output_raw = options.get("output")
    output: Path | None
    if output_raw is None or output_raw == "":
        output = None
    elif not isinstance(output_raw, str):
        raise DiagnosticInputError("--output must be a path")
    else:
        path = Path(output_raw)
        if path.exists():
            raise DiagnosticInputError("output path already exists")
        if not path.parent.is_dir():
            raise DiagnosticInputError("output directory does not exist")
        output = path
    return variant_slug, seeds, total_raw, output


def _parse_seeds(raw: object) -> tuple[int, ...]:
    if raw is None or raw == "":
        raise DiagnosticInputError("--seeds must be a comma-separated list of integers")
    if not isinstance(raw, str):
        raise DiagnosticInputError("--seeds must be a comma-separated list of integers")
    parts = [item.strip() for item in raw.split(",")]
    if not parts or any(not item for item in parts):
        raise DiagnosticInputError("--seeds must be a comma-separated list of integers")
    seeds: list[int] = []
    seen: set[int] = set()
    for item in parts:
        try:
            seed = int(item)
        except ValueError as exc:
            raise DiagnosticInputError(
                "--seeds must be a comma-separated list of integers"
            ) from exc
        if seed < 0 or seed > UINT32_MAX:
            raise DiagnosticInputError("--seeds values must be in 0..4294967295")
        if seed in seen:
            raise DiagnosticInputError("--seeds must not contain duplicates")
        seen.add(seed)
        seeds.append(seed)
    return tuple(seeds)
