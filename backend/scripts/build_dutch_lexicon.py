#!/usr/bin/env python3
"""Build the committed Dutch lexicon from pinned LibreOffice hunspell nl_NL (OpenTaal) sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ THIS SCRIPT APPLIES TWO EDITION RULES, NOT ONE, AND THE FIRST IS THE IMPORTANT ONE:
  1. the IJ LIGATURE ``ĳ`` (U+0133) is expanded to ``ij``, because the Dutch edition dropped
     its IJ tile in March 1998 and now spells the sound with an I tile and a J tile;
  2. diacritics are folded to their base letter.
Without rule 1 the Dutch words for dike, iron, ice and freedom could not be played AT ALL.
See ``_to_tile_faces`` for the measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PINNED_COMMIT = "75f5dff8c972fff4a32e4ea8434722c277f02a3f"
UPSTREAM_BASE = (
    "https://raw.githubusercontent.com/LibreOffice/dictionaries/"
    f"{PINNED_COMMIT}/nl_NL"
)
# Established upstream: nl_NL/description.xml declares <version value="2.0.0" />. ⚠ Note the
# shape differs from its siblings, which use dated pack versions like "2021.07" — OpenTaal
# versions its own way and this script must not normalize it.
PACK_VERSION = "2.0.0"
# ⛔ A DUAL LICENCE, AND THE ONLY ONE IN THIS REPOSITORY SO FAR. license_en_EN.txt §6 offers
# the files "under the below, liberal licenses at the discretion of the user": A. BSD (revised
# version) and B. Creative Commons Attribution 3.0 unported. SPDX expresses user choice with
# OR, so this is an OR expression rather than a single identifier. Do not collapse it to one
# licence; the grant is genuinely either.
SPDX_EXPRESSION = "BSD-3-Clause OR CC-BY-3.0"
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
# ⛔ SENTENCES, PLURAL, and that is deliberate: a dual licence is not proved by one sentence.
# All three strings must be present, measured verbatim in nl_NL/license_en_EN.txt at
# PINNED_COMMIT: the availability grant, then each of the two named licences. If upstream ever
# drops one of the two options, this gate fails rather than silently over-claiming.
LICENSE_SENTENCES: tuple[str, ...] = (
    "the language files are freely available under the below, liberal licenses "
    "at the discretion of the user",
    "A. BSD (revised version):",
    "B. Creative Commons, Attribution 3.0 (unported)",
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ RULE 1 — THE IJ LIGATURE, and it is the reason this language needed care.
# The Dutch set is 102 tiles bearing plain Latin letters. Before March 1998 the Dutch edition
# had two ``Ĳ`` tiles worth 4 points; the modern edition has none and spells the sound with an
# I tile plus a J tile.
# ⚠ MEASURED: upstream nl_NL spells those words with U+0133 LATIN SMALL LIGATURE IJ, and NFD
# does NOT decompose it — a ligature is a compatibility mapping, not a base plus a combining
# mark. So a diacritic fold alone leaves 121 891 words unreachable. Measured at PINNED_COMMIT:
#     1 294 152 unique expanded forms of playable shape
#       131 694 (10.18%) carry a non a-z letter, of which 125 444 contain ``ĳ``
#     after the fold ALONE, 121 891 non a-z words would REMAIN
#     after ligature expansion AND fold: 1 293 086 forms, ZERO non a-z remain
# Verified absent before the transform and present after it: ``ijs``, ``dijk``, ``ijzer``,
# ``vrijheid``. Those are ordinary Dutch words; without rule 1 none of them is playable.
# ⛔ Mapped EXPLICITLY rather than via NFKD. NFKD would also rewrite unrelated compatibility
# characters, and an aggressive normalizer on a shipped word list is how a silent corruption
# enters. This mapping states exactly the edition rule and nothing else.
IJ_LIGATURES: dict[str, str] = {"\u0133": "ij", "\u0132": "IJ"}

# ⛔ RULE 2 — diacritics, same rule and same boundary as Afrikaans and Italian: legitimate only
# because every letter it touches is absent from the Dutch tile set. Measured contributors:
# ë 5694, ï 1907, é 1002, è 477, ö 344, ü 191, ê 135, ç 94, á 64, í 59, ó 56.
FOLD_DIACRITICS = True

MIN_UNIQUE = 800_000
MAX_UNIQUE = 2_500_000

# Fail-closed post-condition, THREE categories so no single failure mode can hide:
#   kaas water boek   plain words — the expansion ran at all
#   ijs dijk          LIGATURE witnesses — absent before rule 1, present after it
#   reeel             the folded form of ``reëel`` — a witness for rule 2
REQUIRED_WORDS: tuple[str, ...] = ("kaas", "water", "boek", "ijs", "dijk", "reeel")
FORBIDDEN_WORD = "qxqxqxqxq"
# ⛔ And one shape that must NOT survive: no finished word may still contain the ligature.
# A count- or size-based check cannot see a partially applied mapping; this can.
FORBIDDEN_CHARS: tuple[str, ...] = ("\u0133", "\u0132")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "dutch.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "dutch.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("nl_NL.dic", "24782020d0d0bd465270027f51443b752f8ddaecf7c612a225e8668e1746aa24"),
    ("nl_NL.aff", "0ee9233fe1c5785f9a803a05ac882e8363ac785c06fbd455af88ce0c0a57324b"),
    ("license_en_EN.txt", "1d3243be74045a177b0c8a9a4b4166053f5c8966cb01a559a3b427762425490d"),
    ("README_NL.txt", "5e080b0d6fad4d61b3403694bdc9ab40c725ed5523942170dc2a956c294ba91b"),
    ("description.xml", "140dee76de746b08d2e16026e9bbecbb14e5fed191b0df2a2fae3f8b7c01575c"),
)

# ⚠ Dutch DOES have a named language authority — the Nederlandse Taalunie, whose Spelling Seal
# of Approval the OpenTaal lemma list carries (license_en_EN.txt §4). But a spelling seal on a
# lemma list is not a tournament word list, so this header still says "Not an official
# tournament list." The seal belongs in the manifest's provenance, not in a claim of officialdom.
_LEXICON_HEADER = (
    "# Dutch playable lexicon expanded from hunspell nl_NL / OpenTaal "
    f"(LibreOffice dictionaries nl_NL @ {PINNED_COMMIT}).\n"
    "# Two edition rules are applied, so this file lists playable TILE SEQUENCES rather than\n"
    "# Dutch orthography:\n"
    "#   1. the IJ ligature is written as 'ij', because the modern Dutch edition dropped its\n"
    "#      IJ tile in 1998 and spells the sound with an I tile and a J tile;\n"
    "#   2. diacritics are folded to their base letter, because no tile bears one.\n"
    "# So 'ijs' and 'reeel' are here; the ligature and diaeresis spellings are not.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"OpenTaal / LibreOffice Dutch dictionary pack version {PACK_VERSION}"

# ⛔ nl_NL is the first language here with a STANDALONE licence file, so the primary embedded
# document is license_en_EN.txt rather than a README. README_NL.txt follows it for provenance,
# in the same two-document shape build_czech_lexicon.py uses for its two READMEs.
_ATTRIBUTION = (
    "Dutch lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries nl_NL (OpenTaal) at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file, writing the IJ ligature\n"
    "as 'ij', and folding diacritics; see the lexicon header for why. The upstream licence\n"
    "and README below carry the copyright statements and both licence options.\n"
    "\n"
    "--- upstream license_en_EN.txt ---\n"
    "\n"
)

_README_SECTION = "\n--- upstream README_NL.txt ---\n\n"
_LICENSE_TRAILER = "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_inside_assets(path: Path) -> bool:
    """True when ``path`` resolves inside ``backend/assets/``.

    Both sides are ``resolve()``d FIRST, so a relative path, a ``..`` traversal and a symlink
    all collapse to the same answer. A textual prefix test would let all three through.
    """
    resolved = path.resolve()
    assets = _ASSETS_ROOT.resolve()
    return resolved == assets or assets in resolved.parents


def require_check_dir_outside_assets(path: Path) -> Path:
    """Refuse a ``--check`` working directory inside the assets tree; return the resolved dir.

    ⛔ The committed asset is the comparison ORACLE, so a mode that reproduced into the assets
    tree would overwrite the file it claims to verify and then report agreement with itself.
    """
    resolved = path.resolve()
    if is_inside_assets(path):
        print(
            "ERROR refused by require_check_dir_outside_assets: --check work directory "
            f"{path} resolves to {resolved}, which is inside the read-only assets tree "
            f"{_ASSETS_ROOT.resolve()}. --check never writes under backend/assets/ because "
            "the committed asset is the comparison oracle; pass a directory outside it.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return resolved


def _require_expander(hunspell_bin: str) -> str:
    """Fail closed unless the host expander is exactly ``EXPECTED_EXPANDER``."""
    proc = subprocess.run(
        [hunspell_bin, "-vv"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    banner = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    first_line = banner.splitlines()[0] if banner else ""
    if proc.returncode != 0 or not banner:
        print(
            f"ERROR could not read the expander version: {hunspell_bin} -vv exited "
            f"{proc.returncode} with output {banner!r}. Expected {EXPECTED_EXPANDER}; an "
            "unverified expander is not a pass, because a different expander may produce a "
            "different word list.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if EXPECTED_EXPANDER.casefold() not in banner.casefold():
        print(
            f"ERROR expander mismatch: found {first_line!r}, expected {EXPECTED_EXPANDER}. "
            "A different expander may expand the same affix file into a DIFFERENT word "
            "list, and this script writes a shipped asset, so this is fatal rather than a "
            "warning. Upgrading hunspell must be a deliberate, visible decision.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"expander={EXPECTED_EXPANDER} confirmed: {first_line}")
    return first_line


def _compare_against_committed(pairs: tuple[tuple[Path, Path], ...]) -> int:
    """Print BOTH digests per artifact; return 0 only when every pair agrees."""
    mismatches = 0
    for reproduced, committed in pairs:
        got = _sha256_bytes(reproduced.read_bytes())
        expected = _sha256_bytes(committed.read_bytes()) if committed.is_file() else "<absent>"
        verdict = "IDENTICAL" if got == expected else "MISMATCH"
        if verdict != "IDENTICAL":
            mismatches += 1
        print(f"CHECK {committed.name} reproduced={got} committed={expected} {verdict}")
    if mismatches:
        print(f"ERROR --check found {mismatches} mismatching artifact(s)", file=sys.stderr)
        return 1
    print("CHECK all artifacts identical")
    return 0


def _collapse_whitespace(text: str) -> str:
    """Fold every run of whitespace to one space so a hard-wrapped sentence still matches."""
    return " ".join(text.split())


def _download(url: str, dest: Path) -> int:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 — pinned GitHub raw GET
            status = int(getattr(response, "status", 200))
            data = response.read()
    except HTTPError as exc:
        print(f"ERROR download {url} HTTP {exc.code}", file=sys.stderr)
        raise SystemExit(1) from exc
    except URLError as exc:
        print(f"ERROR download {url}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if status != 200:
        print(f"ERROR download {url} HTTP {status}", file=sys.stderr)
        raise SystemExit(1)
    dest.write_bytes(data)
    print(f"GET {url} -> {dest} status={status} bytes={len(data)}")
    return status


def _ensure_pinned_sources(cache_dir: Path, refresh: bool) -> dict[str, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, expected in PINNED_FILES:
        dest = cache_dir / name
        url = f"{UPSTREAM_BASE}/{name}"
        if refresh or not dest.is_file():
            _download(url, dest)
        else:
            print(f"cache hit {dest}")
        digest = _sha256_bytes(dest.read_bytes())
        print(f"SHA-256 {name} {digest}")
        if digest != expected:
            print(
                f"ERROR SHA-256 mismatch for {name}: got {digest} expected {expected}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        paths[name] = dest
    return paths


def _require_affix_encoding(aff_path: Path) -> None:
    """The affix file's FIRST ``SET`` directive must be the encoding this script decodes with.

    ⛔ Deliberately NOT a line-1 test: nl_NL.aff opens with comments and its ``SET UTF-8`` is
    line 11. Comments and blank lines are skipped.
    """
    found: bytes | None = None
    with aff_path.open("rb") as handle:
        for raw in handle:
            line = raw.rstrip(b"\r\n")
            if not line or line.startswith(b"#"):
                continue
            if line.startswith(b"SET"):
                found = line
                break
    if found != AFFIX_SET_LINE:
        print(
            f"ERROR {aff_path.name} first SET directive is {found!r}, expected "
            f"{AFFIX_SET_LINE!r}; unmunch output would not be {WORD_ENCODING}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"affix encoding {AFFIX_SET_LINE.decode('ascii')} -> decode as {WORD_ENCODING}")


def _require_license_sentences(license_path: Path) -> None:
    """Every string in ``LICENSE_SENTENCES`` must still be present. A dual licence needs all."""
    text = _collapse_whitespace(license_path.read_text(encoding="utf-8"))
    missing = [
        sentence for sentence in LICENSE_SENTENCES if _collapse_whitespace(sentence) not in text
    ]
    if missing:
        print(
            f"ERROR {license_path.name} no longer states {missing!r}. The manifest claims "
            f"{SPDX_EXPRESSION}, which asserts BOTH options, so a missing option means the "
            "claim would over-reach.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"licence assertions: {len(LICENSE_SENTENCES)}/{len(LICENSE_SENTENCES)} present")


def _require_pack_version(description_path: Path) -> None:
    text = description_path.read_text(encoding="utf-8")
    needle = f'<version value="{PACK_VERSION}"'
    if needle not in text:
        print(
            f"ERROR {description_path.name} does not declare {needle}; the attribution "
            f"line {_VERSION_LINE!r} would be wrong",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"pack version asserted upstream: {PACK_VERSION}")


def _run_unmunch(unmunch_bin: str, dic_path: Path, aff_path: Path, raw_path: Path) -> int:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("wb") as stdout_file:
        proc = subprocess.run(
            [unmunch_bin, str(dic_path), str(aff_path)],
            stdout=stdout_file,
            stderr=subprocess.PIPE,
            check=False,
        )
    stderr_text = proc.stderr.decode("utf-8", errors="replace")
    if stderr_text:
        # Hunspell prints `parsing line:` for .aff comments; that is not failure.
        print(stderr_text, file=sys.stderr, end="")
    print(f"unmunch exit={proc.returncode} raw={raw_path} bytes={raw_path.stat().st_size}")
    if proc.returncode != 0:
        print("ERROR unmunch exited nonzero", file=sys.stderr)
        raise SystemExit(proc.returncode)
    if raw_path.stat().st_size == 0:
        print("ERROR unmunch produced empty stdout", file=sys.stderr)
        raise SystemExit(1)
    return proc.returncode


def _to_tile_faces(word: str) -> str:
    """Rewrite one upstream form as the tile faces the Dutch edition can actually place.

    Rule 1 first, then rule 2, and the ORDER MATTERS: expanding the ligature can only produce
    ``i`` and ``j``, which carry no marks, so folding afterwards is a no-op on that output —
    whereas folding first would leave the ligature untouched and rule 1 would then have to run
    on already-folded text for no benefit. Doing rule 1 first keeps each rule's effect
    independently observable, which is what makes the three-category word gate meaningful.
    """
    expanded = "".join(IJ_LIGATURES.get(ch, ch) for ch in word)
    if not FOLD_DIACRITICS:
        return unicodedata.normalize("NFC", expanded)
    decomposed = unicodedata.normalize("NFD", expanded)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def _filter_words(raw_path: Path) -> list[str]:
    unique: set[str] = set()
    rewritten = 0
    ligature_inputs = 0
    with raw_path.open(encoding=WORD_ENCODING, errors="strict") as handle:
        for line in handle:
            word = unicodedata.normalize("NFC", line.strip()).casefold()
            if not (word.isalpha() and len(word) >= 2):
                continue
            if any(ligature in word for ligature in IJ_LIGATURES):
                ligature_inputs += 1
            candidate = _to_tile_faces(word)
            if candidate != word:
                rewritten += 1
            if not (candidate.isalpha() and len(candidate) >= 2):
                continue
            unique.add(candidate)
    count = len(unique)
    print(f"unique_words={count} rewritten={rewritten} ligature_inputs={ligature_inputs}")
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if ligature_inputs == 0:
        print(
            "ERROR the upstream expansion contained NO IJ ligature. Measured at "
            f"{PINNED_COMMIT} it contains 125 444 such forms, so zero means the pinned pair "
            "or the expander changed and rule 1 is now silently unnecessary — which would "
            "also mean this lexicon is not the one that was verified.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed on a missing required word, a present control word, or a surviving ligature.

    ⛔ A POST-CONDITION of the build. Word COUNT and file SIZE cannot see a mapping that
    stopped working; two ligature witnesses, one fold witness and a character scan can.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. 'ijs' and "
            "'dijk' are LIGATURE witnesses and 'reeel' is a FOLD witness, so which ones are "
            "missing says which rule failed.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if FORBIDDEN_WORD in words:
        print(
            f"ERROR the forbidden control word {FORBIDDEN_WORD!r} is present; the gate is "
            "asserting against a set that contains everything and therefore proves nothing",
            file=sys.stderr,
        )
        raise SystemExit(1)
    for ligature in FORBIDDEN_CHARS:
        survivors = [word for word in words if ligature in word]
        if survivors:
            print(
                f"ERROR {len(survivors)} finished word(s) still contain {ligature!r}, e.g. "
                f"{sorted(survivors)[:3]}. No tile bears that character, so those words "
                "would be unplayable.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    print(f"word gate {len(REQUIRED_WORDS)}/{len(REQUIRED_WORDS)} present, control absent, "
          "no surviving ligature")


def _write_lexicon(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_LEXICON_HEADER)
        handle.write("\n".join(words))
        handle.write("\n")
    print(f"wrote {path} lines={len(words)} bytes={path.stat().st_size}")


def _write_license(path: Path, license_file: Path, readme: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        license_file.read_text(encoding="utf-8")
        + _README_SECTION
        + readme.read_text(encoding="utf-8")
        + _LICENSE_TRAILER
    )
    path.write_text(_ATTRIBUTION + body, encoding="utf-8")
    print(f"wrote {path} bytes={path.stat().st_size}")


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, as a seam so a test can inspect it without running anything."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/libretiles-dutch-lexicon"),
        help="Directory for pinned .dic/.aff/licence/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-dutch-unmunch.stdout"),
        help="Temporary unmunch stdout (not committed)",
    )
    parser.add_argument("--output-dict", type=Path, default=_DEFAULT_DICT)
    parser.add_argument("--output-license", type=Path, default=_DEFAULT_LICENSE)
    parser.add_argument("--refresh", action="store_true", help="Re-download pinned sources")
    parser.add_argument("--unmunch", default="unmunch")
    parser.add_argument("--hunspell", default="hunspell")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Re-verify only: reproduce into --check-dir, compare SHA-256 against the "
        "committed asset, and write NOTHING under backend/assets/",
    )
    parser.add_argument(
        "--check-dir",
        type=Path,
        default=None,
        help="REQUIRED with --check: working directory for the reproduction. It has no "
        "default on purpose, and it must resolve outside backend/assets/",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    unmunch_bin = shutil.which(args.unmunch)
    if unmunch_bin is None:
        print(f"ERROR unmunch not found: {args.unmunch}", file=sys.stderr)
        return 1
    print(f"unmunch={unmunch_bin}")

    hunspell_bin = shutil.which(args.hunspell)
    if hunspell_bin is None:
        print(
            f"ERROR hunspell not found: {args.hunspell}. The expander version cannot be "
            "verified, and an unverified expander is a failure rather than a pass.",
            file=sys.stderr,
        )
        return 1
    _require_expander(hunspell_bin)

    output_dict = args.output_dict
    output_license = args.output_license
    raw_out = args.raw_out
    if args.check:
        if args.check_dir is None:
            print(
                "ERROR --check requires --check-dir DIRECTORY. It has no default because "
                "the only default it could have would sit under backend/assets/, which is "
                "exactly where --check must never write.",
                file=sys.stderr,
            )
            return 2
        work_dir = require_check_dir_outside_assets(args.check_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dict = work_dir / _DEFAULT_DICT.name
        output_license = work_dir / _DEFAULT_LICENSE.name
        raw_out = work_dir / "unmunch.stdout"
        print(
            f"--check reproducing into {work_dir}; comparing against {args.output_dict} "
            f"and {args.output_license} (both read-only in this mode)"
        )

    paths = _ensure_pinned_sources(args.cache_dir, refresh=args.refresh)
    _require_affix_encoding(paths["nl_NL.aff"])
    _require_license_sentences(paths["license_en_EN.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["nl_NL.dic"], paths["nl_NL.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["license_en_EN.txt"], paths["README_NL.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
