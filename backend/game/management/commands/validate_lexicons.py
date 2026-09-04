"""Read-only audit of every installed language asset.

Usage:
    python manage.py validate_lexicons

Exit status is 0 when every installed variant passes the expensive tier and non-zero
otherwise (Django turns ``CommandError`` into exit code 1). The command never writes, never
touches the database and never uses the network.

⛔ It is deliberately NOT wired into app startup, any AppConfig, or any request path.
AGENTS.md promises that AI-only local boot needs two terminals and no extra step, and the
per-request readiness check in ``game/views.py`` uses the CHEAP tier instead.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from gamecore.lexicon_health import (
    DEFAULT_MIN_SURVIVING_WORDS,
    LexiconAudit,
    audit_lexicon,
)
from gamecore.variant_store import VariantDefinition, list_installed_variants

# Real inflected forms, mirroring the PRESENT half of
# tests/test_variant_invariants.py::_LEXICON_PROBES, one row per installed variant. A range
# check is not a correctness check: only membership of real words catches a lexicon that is
# mechanically well formed but is the wrong word list. Several rows also witness the
# variant's FOLD RULE, so a build that silently stopped folding — or started folding a letter
# that bears a tile — fails the audit instead of shipping a wrong word list:
#   afrikaans/italian/dutch  `more` `citta` `perche` `reeel` are FOLDED forms
#   dutch                    `ijs` `dijk` are LIGATURE rewrites of U+0133
#   german/portuguese        `käse` `coraçao` are PRESERVATION witnesses of a PARTIAL fold
#   danish/swedish           `københavn` `väg` preserve tile-bearing Æ Ø Å Ä Ö; `cafe` folds
#   icelandic                every letter is a tile, so nothing folds at all
# ⚠ The ABSENT half of that table is per-variant (Swedish forbids `musli`, Icelandic forbids
# `madur` and `fjordur` — anti-fold assertions) while ``_ABSENT_PROBES`` below is one global
# set. Those extra per-variant negatives are asserted by the test suite and NOT by this
# command; making them per-variant here is a separate change to ``_targets``.
# A variant with no entry here is still audited structurally; it simply has no positive probe.
_PRESENT_PROBES: dict[str, frozenset[str]] = {
    "english": frozenset({"qi", "za", "fe"}),
    "slovak": frozenset({"škola"}),
    "czech": frozenset({"domu", "knihy"}),
    "polish": frozenset({"domach", "książki"}),
    "afrikaans": frozenset({"die", "van", "more"}),
    "italian": frozenset({"casa", "citta", "perche"}),
    "dutch": frozenset({"kaas", "ijs", "dijk", "reeel"}),
    "german": frozenset({"haus", "strasse", "käse"}),
    "portuguese": frozenset({"casa", "nao", "coraçao"}),
    "danish": frozenset({"hus", "københavn", "cafe"}),
    "swedish": frozenset({"hus", "väg", "cafe"}),
    "icelandic": frozenset({"maður", "þú", "fjörður"}),
}
_ABSENT_PROBES = frozenset({"qxqxqxqxq"})
# An auxiliary two-tile allowlist is intentionally tiny (the shipped Slovak one has 103
# entries), so it is audited with its own floor instead of the dictionary floor.
_AUXILIARY_MIN_WORDS = 1


def _targets(
    variant: VariantDefinition,
) -> list[tuple[str, Path, int, frozenset[str]]]:
    targets: list[tuple[str, Path, int, frozenset[str]]] = [
        (
            "dictionary",
            variant.dictionary_path,
            DEFAULT_MIN_SURVIVING_WORDS,
            _PRESENT_PROBES.get(variant.slug, frozenset()),
        )
    ]
    two_tile = variant.two_tile_words_path
    if two_tile is not None:
        targets.append(("two_tile", two_tile, _AUXILIARY_MIN_WORDS, frozenset()))
    return targets


def _format(slug: str, label: str, audit: LexiconAudit) -> str:
    verdict = "ok" if audit.ok else "FAILED"
    line = (
        f"{slug} {label} {verdict} reason={audit.reason} "
        f"words={audit.surviving_words} duplicates={audit.duplicate_words} "
        f"non_nfc={audit.non_nfc_lines}"
    )
    if audit.missing_probes:
        line += f" missing_probes={','.join(audit.missing_probes)}"
    if audit.unexpected_probes:
        line += f" unexpected_probes={','.join(audit.unexpected_probes)}"
    return line


class Command(BaseCommand):
    help = (
        "Audit every installed variant's lexicon assets with the expensive whole-file "
        "tier. Read-only; exits non-zero when any asset fails."
    )

    def handle(self, *args: object, **options: object) -> None:
        variants = list_installed_variants()
        if not variants:
            raise CommandError("no installed variants found; nothing was audited")

        failures: list[str] = []
        audited = 0
        for variant in variants:
            for label, path, min_words, present in _targets(variant):
                audit = audit_lexicon(
                    path,
                    min_words=min_words,
                    expect_present=present,
                    expect_absent=_ABSENT_PROBES,
                )
                audited += 1
                self.stdout.write(_format(variant.slug, label, audit))
                if not audit.ok:
                    failures.append(f"{variant.slug}/{label}={audit.reason}")

        self.stdout.write(
            f"validate_lexicons: {audited} asset(s) audited, {len(failures)} failed"
        )
        if failures:
            raise CommandError("lexicon audit failed: " + ", ".join(failures))
