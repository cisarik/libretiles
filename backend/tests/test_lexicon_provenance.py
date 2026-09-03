"""Lexicon provenance: every shipped lexicon declares where it came from, and can be rebuilt.

This module exists because of one measured fact at the previous baseline: ``backend/scripts/``
contained exactly ONE file, ``build_slovak_lexicon.py``, while ``czech.txt`` and
``polish.txt`` were shipped, playable and licence-documented — and reproducible from nothing
in this repository, because the script that produced them lived in ``/tmp`` and was never
committed. ``P3`` and ``P10`` are the assertions that make that state impossible to
re-enter: a lexicon claiming a build script must have one, and that script's pinned commit
and SPDX expression must agree with the manifest that claims them.

Two scope boundaries:

* the loader carries provenance and validates only its SHAPE
  (``variant_store._parse_provenance``). Every CONTENT rule — ``entry_count`` equals the
  real word count, ``license_file`` exists, ``build_script`` exists — is owned here, because
  a data problem must fail a test rather than fail process start-up.
* ⛔ the reproduction proof is NOT a test. That a build script regenerates its committed
  lexicon byte-identically is a one-time measurement whose evidence is a set of SHA-256
  digests in the Worker report. Nothing here runs ``unmunch`` or touches the network; the
  suite stays offline and fast.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from gamecore.assets import get_assets_path
from gamecore.lexicon_health import audit_lexicon
from gamecore.variant_store import (
    LexiconProvenance,
    VariantDefinition,
    VariantManifestError,
    _load_variant_from_path,
    list_installed_variants,
)

_INSTALLED = list_installed_variants()
_SLUGS = [variant.slug for variant in _INSTALLED]

# The seven declared keys, exactly. Not six, not eight: the point of a fixed shape is that
# a reviewer can read one object and know what is claimed.
_DECLARED_KEYS = frozenset(
    {
        "upstream",
        "upstream_commit",
        "expander",
        "entry_count",
        "spdx",
        "license_file",
        "build_script",
    }
)

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")

# The expander every shipped lexicon was built with, measured on the build host by two
# independent routes — ``hunspell -vv`` and the package owner of ``/usr/bin/unmunch``. Pinned
# here as well as inside each script so P13 can catch per-script drift.
_EXPECTED_EXPANDER = "hunspell 1.7.3"

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_DICTS_DIR = get_assets_path() / "dicts"
_VARIANTS_DIR = get_assets_path() / "variants"

_BLANK_ENTRY: dict[str, Any] = {"letter": "?", "count": 2, "points": 0}
_A_ENTRY: dict[str, Any] = {"letter": "A", "count": 98, "points": 1}


def _manifest_path(slug: str) -> Path:
    return _VARIANTS_DIR / f"{slug}.json"


def _raw_provenance(slug: str) -> Any:
    """The manifest as written on disk. The loader coerces, so shape rules read RAW JSON."""
    data = json.loads(_manifest_path(slug).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data.get("lexicon_provenance", "ABSENT")


def _provenance(variant: VariantDefinition) -> LexiconProvenance:
    assert variant.lexicon_provenance is not None, f"{variant.slug}: provenance did not load"
    return variant.lexicon_provenance


def _write_synthetic(tmp_path: Path, slug: str, **overrides: Any) -> Path:
    """A minimal loadable manifest.

    ``dictionary_file`` names a real lexicon because ``validate_dictionary_file`` runs
    before the provenance block is parsed: pointing at an absent lexicon would raise
    ``FileNotFoundError`` first and the intended ``VariantManifestError`` would never fire.
    """
    payload: dict[str, Any] = {
        "language": "Synthetic",
        "slug": slug,
        "dictionary_file": "collins2019.txt",
        "alphabet_order": ["A"],
        "letters": [_BLANK_ENTRY, _A_ENTRY],
    }
    payload.update(overrides)
    path = tmp_path / f"{slug}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _load_script(name: str) -> ModuleType:
    """Import a build script from its path, WITHOUT running it.

    ``backend/scripts/`` is not a package, so there is no importable dotted name. Executing
    the module body defines constants and functions only: no download, no ``unmunch``, no
    filesystem write. ⛔ Never call ``main()`` from a test.
    """
    path = _SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(f"_libretiles_build_script_{path.stem}", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Build scripts claimed by the shipped manifests, derived rather than hardcoded so a fifth
# language is covered the moment its manifest lands.
_SCRIPT_CLAIMS = [
    (variant.slug, variant.lexicon_provenance.build_script)
    for variant in _INSTALLED
    if variant.lexicon_provenance is not None
    and variant.lexicon_provenance.build_script is not None
]
_SCRIPT_IDS = [slug for slug, _ in _SCRIPT_CLAIMS]


# --- P1-P6: the shipped manifests -------------------------------------------------------


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_p1_provenance_is_present_with_exactly_the_seven_declared_keys(
    variant: VariantDefinition,
) -> None:
    raw = _raw_provenance(variant.slug)
    assert raw != "ABSENT", f"{variant.slug}.json declares no lexicon_provenance"
    assert isinstance(raw, dict), f"{variant.slug}: lexicon_provenance is {type(raw).__name__}"
    assert set(raw) == _DECLARED_KEYS, (
        f"{variant.slug}: lexicon_provenance keys {sorted(raw)} != {sorted(_DECLARED_KEYS)}"
    )
    assert variant.lexicon_provenance is not None


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_p2_declared_license_file_exists_beside_the_lexicon(variant: VariantDefinition) -> None:
    """A claimed licence file must be on disk next to the lexicon it covers.

    ``license_file`` is ``null`` for exactly one shipped variant, ENGLISH: Collins Scrabble
    Words ships with no licence file in-tree, and ``null`` is the honest value rather than
    an invented SPDX expression or a pointer to a file that does not exist.
    """
    license_file = _provenance(variant).license_file
    if license_file is None:
        assert variant.slug == "english", (
            f"{variant.slug}: license_file is null; only english is expected to lack one"
        )
        return
    assert Path(license_file).name == license_file, f"{variant.slug}: not a basename"
    path = _DICTS_DIR / license_file
    assert path.is_file(), f"{variant.slug}: declared license_file missing: {path}"
    assert path.stat().st_size > 0


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_p3_declared_build_script_exists_and_is_readable(variant: VariantDefinition) -> None:
    """⛔ The assertion that makes the Cooperator's directive mechanically true.

    "takto chcem aby boli stiahnute vsetky potrebne slovniky" — a lexicon that claims a
    build script must actually have one in this repository. English claims none and ships
    none, and that asymmetry is deliberate.
    """
    build_script = _provenance(variant).build_script
    if build_script is None:
        assert variant.slug == "english", (
            f"{variant.slug}: build_script is null; only english is expected to lack one"
        )
        return
    assert Path(build_script).name == build_script, f"{variant.slug}: not a basename"
    path = _SCRIPTS_DIR / build_script
    assert path.is_file(), f"{variant.slug}: declared build_script missing: {path}"
    assert path.read_text(encoding="utf-8").startswith("#!"), f"{variant.slug}: not a script"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_p4_entry_count_equals_the_real_surviving_word_count(
    variant: VariantDefinition,
) -> None:
    """The declared count is EXACT, over the whole file, using the canonical filter.

    ⛔ ONE FILTER. ``lexicon_health.audit_lexicon`` mirrors ``fastdict._read_words`` plus the
    two-code-point floor; re-deriving the filter here would be a fourth copy of it.

    ⛔ NOT SAMPLED. This reads the whole lexicon — four files, about 154 MB in total,
    measured at roughly 10 s of wall clock for the shipped set. It is deliberately NOT
    marked ``slow``: the project's ``slow`` marker is not excluded by default today, but a
    future ``-m "not slow"`` would silently stop verifying the one number in the manifest
    that a reader is most likely to trust.
    """
    declared = _provenance(variant).entry_count
    assert isinstance(declared, int), f"{variant.slug}: entry_count is not an integer"
    started = time.monotonic()
    audit = audit_lexicon(variant.dictionary_path)
    elapsed = time.monotonic() - started
    assert audit.surviving_words == declared, (
        f"{variant.slug}: manifest entry_count {declared} but "
        f"{variant.dictionary_file} carries {audit.surviving_words} surviving words "
        f"(audit reason={audit.reason}, {elapsed:.2f}s)"
    )


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_p5_spdx_is_a_single_line_string_when_declared(variant: VariantDefinition) -> None:
    """Shape only. Parsing SPDX syntax is a lawyer's job, not a test's."""
    spdx = _provenance(variant).spdx
    if spdx is None:
        assert variant.slug == "english", (
            f"{variant.slug}: spdx is null; only english is expected to lack one"
        )
        return
    assert spdx.strip() == spdx and spdx, f"{variant.slug}: {spdx!r}"
    assert "\n" not in spdx, f"{variant.slug}: spdx spans lines: {spdx!r}"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_p6_upstream_commit_is_a_full_lowercase_sha1_when_declared(
    variant: VariantDefinition,
) -> None:
    """An abbreviated or uppercase commit is not a pin; it is a hint."""
    commit = _provenance(variant).upstream_commit
    if commit is None:
        assert variant.slug == "english", (
            f"{variant.slug}: upstream_commit is null; only english is expected to lack one"
        )
        return
    assert _COMMIT_RE.fullmatch(commit) is not None, (
        f"{variant.slug}: upstream_commit {commit!r} is not 40 lowercase hex characters"
    )
    assert _provenance(variant).upstream, f"{variant.slug}: pinned commit with no upstream"


# --- P7, P8: the loader carries provenance without becoming brittle ---------------------


@pytest.mark.parametrize(
    "bad",
    ["LibreOffice dictionaries cs_CZ", ["cs_CZ"], 7, 3.5, None],
    ids=["string", "list", "integer", "float", "null"],
)
def test_p7_non_object_provenance_is_rejected_with_its_own_code(
    tmp_path: Path, bad: object
) -> None:
    """When declared, provenance is an OBJECT. Everything else is a manifest defect.

    An explicit ``null`` is included on purpose: it is a non-object, so it raises too. A
    variant that genuinely has no provenance OMITS the key, which is what P8 pins.
    """
    path = _write_synthetic(tmp_path, "p7", lexicon_provenance=bad)
    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == "malformed_provenance"


def test_p8_a_manifest_without_provenance_still_loads(tmp_path: Path) -> None:
    """The test that keeps the loader non-brittle.

    A future variant may legitimately arrive without provenance — a hand-authored tile set
    for a language with no upstream expander, for example. It must load and be playable;
    only the harness decides whether the shipped set is complete.
    """
    variant = _load_variant_from_path(_write_synthetic(tmp_path, "p8"))
    assert variant.lexicon_provenance is None
    assert variant.slug == "p8"
    assert variant.total_tiles == 100


def test_p8b_a_well_formed_provenance_object_loads_into_the_frozen_structure(
    tmp_path: Path,
) -> None:
    """Round-trip: the loader carries the seven declared values and freezes them."""
    declared: dict[str, Any] = {
        "upstream": "Synthetic upstream",
        "upstream_commit": "0" * 40,
        "expander": "unmunch (hunspell 1.7.3)",
        "entry_count": 4,
        "spdx": "GPL-2.0-only",
        "license_file": "czech.LICENSE",
        "build_script": "build_czech_lexicon.py",
    }
    variant = _load_variant_from_path(
        _write_synthetic(tmp_path, "p8b", lexicon_provenance=declared)
    )
    provenance = _provenance(variant)
    assert provenance == LexiconProvenance(**declared)
    with pytest.raises(FrozenInstanceError):
        provenance.entry_count = 5  # type: ignore[misc]


# --- P9, P10: the build scripts are import-safe and cannot drift from the manifests -----


@pytest.mark.parametrize(("slug", "script"), _SCRIPT_CLAIMS, ids=_SCRIPT_IDS)
def test_p9_build_scripts_are_import_safe(slug: str, script: str) -> None:
    """Importing a build script must define constants and nothing else.

    ⛔ No ``main()`` call, no ``unmunch``, no network. If importing one of these modules
    ever performs work, this test is where that shows up.
    """
    module = _load_script(script)
    assert isinstance(module.PINNED_COMMIT, str)
    assert _COMMIT_RE.fullmatch(module.PINNED_COMMIT) is not None
    assert isinstance(module.UPSTREAM_BASE, str)
    assert module.UPSTREAM_BASE.startswith(
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/"
    ), f"{script}: unexpected upstream base {module.UPSTREAM_BASE!r}"
    assert module.PINNED_COMMIT in module.UPSTREAM_BASE
    assert isinstance(module.SPDX_EXPRESSION, str) and module.SPDX_EXPRESSION
    assert isinstance(module.PINNED_FILES, tuple) and module.PINNED_FILES
    for entry in module.PINNED_FILES:
        assert isinstance(entry, tuple) and len(entry) == 2, f"{script}: {entry!r}"
        name, digest = entry
        assert isinstance(name, str) and name
        assert re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"{script}: {name} {digest!r}"
    names = [name for name, _ in module.PINNED_FILES]
    assert len(names) == len(set(names)), f"{script}: duplicate pinned file {names}"
    assert module.MIN_UNIQUE < module.MAX_UNIQUE


@pytest.mark.parametrize(("slug", "script"), _SCRIPT_CLAIMS, ids=_SCRIPT_IDS)
def test_p10_script_constants_agree_with_the_manifest_that_claims_them(
    slug: str, script: str
) -> None:
    """⛔ The assertion that stops a manifest and its build script drifting apart.

    That drift is the exact failure this whole exists to prevent for the NEXT language: a
    manifest claiming one SPDX expression while the script that regenerates the lexicon
    asserts another is a licence defect that nothing else in the repository would catch.
    """
    variant = next(item for item in _INSTALLED if item.slug == slug)
    provenance = _provenance(variant)
    module = _load_script(script)
    assert module.SPDX_EXPRESSION == provenance.spdx, (
        f"{slug}: {script} declares SPDX {module.SPDX_EXPRESSION!r} but the manifest says "
        f"{provenance.spdx!r}"
    )
    assert module.PINNED_COMMIT == provenance.upstream_commit, (
        f"{slug}: {script} pins {module.PINNED_COMMIT!r} but the manifest says "
        f"{provenance.upstream_commit!r}"
    )


def test_p10b_every_non_english_lexicon_has_a_committed_build_script() -> None:
    """The state this exchange changed, pinned as a test.

    At the previous baseline ``backend/scripts/`` held exactly one file and two of the three
    expanded lexicons were reproducible from nothing in this repository.
    """
    claimed = dict(_SCRIPT_CLAIMS)
    assert claimed == {
        "czech": "build_czech_lexicon.py",
        "polish": "build_polish_lexicon.py",
        "slovak": "build_slovak_lexicon.py",
    }, f"unexpected build-script claims: {claimed}"
    for script in claimed.values():
        assert (_SCRIPTS_DIR / script).is_file()


# --- P11-P13: `--check` mode, the assets-tree refusal, and the pinned expander -----------
#
# Two hazards compounded before this coverage existed, and either one alone stayed invisible
# to every gate: nothing asserted the host expander version, and nothing stopped a run from
# writing over a committed lexicon. A different hunspell plus one default-path run would have
# replaced a shipped word list silently. ``--check`` is the read-only re-verification route,
# and the guard below is what keeps it read-only.
#
# ⛔ Everything here is OFFLINE and subprocess-free: modules are imported, parsers are built
# but never parsed, guards are called directly. No ``main()``, no ``unmunch``, no
# ``hunspell``, no network.


@pytest.mark.parametrize(("slug", "script"), _SCRIPT_CLAIMS, ids=_SCRIPT_IDS)
def test_p11_check_mode_and_expander_pin_are_exposed(slug: str, script: str) -> None:
    """Each build script offers `--check`, demands an explicit directory, and pins hunspell."""
    module = _load_script(script)

    assert module.EXPECTED_EXPANDER == _EXPECTED_EXPANDER, (
        f"{script}: pins expander {module.EXPECTED_EXPANDER!r}, expected "
        f"{_EXPECTED_EXPANDER!r}"
    )
    assert callable(module.is_inside_assets), f"{script}: no is_inside_assets predicate"
    assert callable(module.require_check_dir_outside_assets), f"{script}: no refusal guard"

    parser = module.build_parser()
    help_text = parser.format_help()
    assert "--check" in help_text, f"{script}: no --check flag"
    assert "--check-dir" in help_text, f"{script}: --check has no explicit working-dir flag"
    assert parser.get_default("check") is False, f"{script}: --check is on by default"
    # ⛔ The load-bearing assertion of this test: --check must never pick a directory for the
    # caller, because the only directory it could pick is the one it must never write to.
    assert parser.get_default("check_dir") is None, (
        f"{script}: --check-dir carries default "
        f"{parser.get_default('check_dir')!r}; --check must require an explicit directory"
    )


@pytest.mark.parametrize(("slug", "script"), _SCRIPT_CLAIMS, ids=_SCRIPT_IDS)
def test_p12_the_assets_tree_refusal_guard_is_real(
    slug: str, script: str, tmp_path: Path
) -> None:
    """The one behavioural test of the hazard, and it needs no subprocess.

    Every candidate below resolves into ``backend/assets/`` by a different route — directly,
    one level deeper, through ``..``, through a CWD-relative path, and through a symlink whose
    own name looks harmless. ``resolve()`` before comparing is what makes all five equivalent;
    a textual prefix test would pass the last three straight through.
    """
    module = _load_script(script)
    assets = get_assets_path().resolve()

    refused: list[tuple[str, Path]] = [
        ("assets root itself", assets),
        ("inside assets/dicts", assets / "dicts"),
        ("deeper inside assets", assets / "dicts" / "nested" / "work"),
        ("dot-dot traversal", _SCRIPTS_DIR / ".." / "assets" / "dicts"),
        ("cwd-relative", Path(os.path.relpath(assets / "dicts", Path.cwd()))),
    ]
    decoy = tmp_path / "looks-like-a-safe-tmp-dir"
    decoy.symlink_to(assets / "dicts", target_is_directory=True)
    refused.append(("symlink into assets", decoy))

    for label, candidate in refused:
        assert module.is_inside_assets(candidate) is True, (
            f"{script}: {label} ({candidate}) was NOT recognised as inside the assets tree"
        )
        with pytest.raises(SystemExit) as caught:
            module.require_check_dir_outside_assets(candidate)
        assert caught.value.code not in (0, None), (
            f"{script}: {label} refused with exit code {caught.value.code!r}"
        )

    permitted = tmp_path / "work"
    assert module.is_inside_assets(permitted) is False
    assert module.require_check_dir_outside_assets(permitted) == permitted.resolve()


def test_p13_the_expander_constant_is_identical_across_all_three_scripts() -> None:
    """Per-script drift would let one language be built by a different tool than the others."""
    values = {script: _load_script(script).EXPECTED_EXPANDER for _, script in _SCRIPT_CLAIMS}
    assert len(values) == 3, f"expected three build scripts, found {sorted(values)}"
    assert set(values.values()) == {_EXPECTED_EXPANDER}, f"expander drift: {values}"


# --- P14, P15: nothing unclaimed may sit in the shipped dictionary directory --------------
#
# ``backend/assets/dicts/sowpods.txt`` sat in this repository for the whole life of the
# project claimed by NO manifest, carrying NO provenance, and audited by NOTHING:
# ``validate_lexicons`` walks the MANIFESTS, so a file that no manifest names is invisible to
# it by construction. It has since been deleted. P14 names that one file forever; P15 is the
# rule that makes the whole CLASS of defect impossible, which is the part that matters,
# because this directory is about to receive many more lexicons and their licence files.
#
# ⛔ Neither test reads Git history — the deleted blob deliberately survives there, which is
# exactly what made the deletion reversible — and neither greps the tree for that file's name.
# ``test_documentation_dictionary_claims.py`` owns the documentation claim and necessarily
# contains the name in order to forbid it.

# The manifest fields that CLAIM a file under ``assets/dicts/``. ⚠ ``build_script`` is NOT one
# of them: it names a file under ``backend/scripts/``, and P3 and P10b already own it.
_DIRECT_CLAIM_FIELDS = ("dictionary_file", "two_tile_words_file")
_PROVENANCE_CLAIM_FIELD = "license_file"


def _claimed_dictionary_filenames(variants_dir: Path) -> dict[str, list[str]]:
    """Map every ``assets/dicts/`` name a manifest CLAIMS to the manifests that claim it.

    ⛔ A RAW JSON scan, deliberately NOT ``list_installed_variants()``. That helper wraps each
    load in ``try/except Exception``, logs the failure and CONTINUES, so a manifest that fails
    to load contributes NO claims — and P15 would then report that manifest's perfectly
    legitimate lexicon and licence file as orphans, pointing the reader at the wrong files
    entirely. A raw scan sees the claim regardless of loader health, and loader health is
    owned by P1-P8 and ``variant_store``.

    Read defensively for the same reason: a missing key, a null, or a non-string value
    contributes no claim rather than raising, because P15's job is to find orphans, not to
    re-validate manifest shape. An unparseable manifest is the one exception — a tree where a
    manifest cannot be read is a tree where P15 cannot honestly claim anything.
    """
    claims: dict[str, list[str]] = {}
    for manifest in sorted(variants_dir.glob("*.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{manifest.name} is not parsable JSON: {exc}") from exc
        if not isinstance(data, dict):
            continue
        declared = [data.get(field) for field in _DIRECT_CLAIM_FIELDS]
        provenance = data.get("lexicon_provenance")
        if isinstance(provenance, dict):
            declared.append(provenance.get(_PROVENANCE_CLAIM_FIELD))
        for value in declared:
            if isinstance(value, str) and value:
                claims.setdefault(value, []).append(manifest.name)
    return claims


def test_p14_the_unclaimed_english_word_list_is_not_shipped() -> None:
    """The named absence. One file, one assertion, and the message says WHY it is unwanted."""
    orphan = _DICTS_DIR / "sowpods.txt"
    assert not orphan.exists(), (
        f"{orphan} is back. It is claimed by no manifest, so it carries no lexicon_provenance "
        f"and validate_lexicons — which walks the manifests — never audits it. The shipped "
        f"Tier-1 English list is collins2019.txt, claimed by english.json"
    )


def test_p15_every_present_dictionary_file_is_claimed_by_a_manifest() -> None:
    """ONE DIRECTION: a file that is PRESENT must be CLAIMED. Never the reverse.

    ⛔ Do not "tighten" this into "every claimed file is present". A future variant is already
    designed to claim a lexicon that is legitimately ABSENT from a fresh checkout: Hungarian's
    expansion is far past any committable size, so its committed build script generates the
    word list locally and that output stays out of Git. Until the local build runs,
    ``hungarian.json`` will claim a ``dictionary_file`` that does not exist, and fail-closed
    readiness reports the variant unavailable — ``gamecore/lexicon_health.py`` owns that, and
    it is correct behaviour rather than a test failure. The loader already enforces the
    alphabet invariant the same way round: every tile token must appear in ``alphabet_order``,
    while ``alphabet_order`` may legitimately carry letters that are not tiles (Slovak ``CH``).
    Reversing either direction fails on an asset that is deliberately shipped or deliberately
    planned.

    ⛔ NO EXEMPTION LIST — not for dotfiles, not for a README, not for ``.gitkeep``. An
    exemption list is precisely where the next orphan would hide. If an unclaimed file is ever
    genuinely needed here, that should cost a deliberate decision, and this test failing is
    that decision's trigger.
    """
    claims = _claimed_dictionary_filenames(_VARIANTS_DIR)
    present = sorted(path for path in _DICTS_DIR.iterdir() if path.is_file())
    orphans = [path.name for path in present if path.name not in claims]
    assert orphans == [], (
        f"unclaimed file(s) under {_DICTS_DIR}: {orphans}. Every file shipped there must be "
        f"claimed by an installed manifest through dictionary_file, two_tile_words_file, or "
        f"lexicon_provenance.license_file; an unclaimed asset carries no provenance and "
        f"validate_lexicons never audits it. Check the manifests as well: a renamed claim, a "
        f"claim written as a path rather than a basename, or a manifest that no longer parses "
        f"presents here as an orphan of the file it used to claim. Currently claimed: "
        f"{sorted(claims)}"
    )
