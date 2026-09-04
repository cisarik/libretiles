#!/usr/bin/env python3
"""Build the committed Danish lexicon from pinned LibreOffice hunspell da_DK sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ TWO RULES, AND THE SECOND ONE IS NEW TO THIS FAMILY OF SCRIPTS:

1. A PARTIAL FOLD, German's and Portuguese's shape. ``Æ``, ``Ø`` and ``Å`` are Danish TILES at
   4 points each, so they SURVIVE; every other marked letter folds. ``café`` -> ``cafe``,
   but ``København`` keeps its ``ø``.

2. A SHAPE FILTER. Some upstream forms contain letters that no Danish tile bears AND that no
   fold can remove, because they are distinct letters rather than marked ones: ``þ`` (thorn)
   and ``ð`` (eth), which arrive with Faroese and Icelandic proper names such as
   ``Þorhildur`` and ``Eyjafjörður``. Those words are DROPPED, because a lexicon of playable
   tile sequences must not contain sequences no tile set can spell. See ``TILE_FACE_RE``.
"""

from __future__ import annotations

import argparse
import hashlib
import re
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
    f"{PINNED_COMMIT}/da_DK"
)
# Established upstream: da_DK/description.xml declares <version value="2023.09.05" />.
PACK_VERSION = "2023.09.05"
# ⛔ A TRI-LICENCE, and README_da_DK.txt names THE EXACT FILES this script consumes:
#   "da_DK.dic, da_DK.aff, th_da_DK.dat, th_da_DK.idx: © 2020 Foreningen for frit
#    tilgængelige sprogværktøjer" … "These files are published under the following open source
#    licenses: GNU GPL version 2.0 / GNU LGPL version 2.1 / Mozilla MPL version 1.1"
# That is the strongest licence evidence of any language in this repository so far: the grant
# lists the artifacts by filename. It is also the same expression Slovak and Portuguese
# already declare, so the claim is consistent with the house.
SPDX_EXPRESSION = "GPL-2.0-only OR LGPL-2.1-only OR MPL-1.1"
# ⛔ NOT a line-1 test: da_DK.aff opens with a comment block and its SET is line 23.
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
README_ENCODING = "utf-8"
# Measured verbatim in da_DK/README_da_DK.txt at PINNED_COMMIT. FOUR strings: the grant that
# names the files, then each of the three licences with its version. A tri-licence is not
# proved by one sentence, and if upstream ever drops an option this fails rather than the
# manifest over-claiming.
LICENSE_SENTENCES: tuple[str, ...] = (
    "These files are published under the following open source licenses:",
    "GNU GPL version 2.0",
    "GNU LGPL version 2.1",
    "Mozilla MPL version 1.1",
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ RULE 1 — THE PARTIAL FOLD. The Danish set is 101 tiles over 28 letter kinds: A-Z without
# Q, plus Æ, Ø and Å at 4 points each. So those three must be kept and every other mark folds.
# MEASURED at PINNED_COMMIT with hunspell 1.7.3:
#     318 033 unique expanded forms of playable shape
#     marked letters that FOLD: é 769 · ü 352 · ö 256 · á 128 · ä 106 · ó 96 · í 71 · è 66 ·
#                               ë 49 and a long tail
#     76 208 finished words STILL CARRY an æ, ø or å — which is what proves the fold is partial
KEEP_MARKED: frozenset[str] = frozenset({"æ", "ø", "å"})

# ⛔ RULE 2 — THE SHAPE FILTER, and it exists because a fold cannot fix everything.
# ``þ`` and ``ð`` are distinct LETTERS, not marked ones, so NFD leaves them untouched and no
# Danish tile bears either. MEASURED: 106 finished forms still contain one — Faroese and
# Icelandic proper names like ``þorhildur``, ``eyjafjorður``, ``viðareiði``, ``sjurður``.
# A lexicon of playable tile sequences must not contain a sequence no tile set can spell, so
# those words are DROPPED rather than mangled into something that is not the word.
# ⚠ The bound is asserted below: a filter that suddenly drops thousands of words means the fold
# stopped working, and that must fail the build rather than quietly shrink the lexicon.
TILE_FACE_RE = re.compile(r"\A[a-zæøå]+\Z")
MAX_SHAPE_DROPS = 500

# ⛔ RULE 3, AND IT IS A TOOL DEFECT RATHER THAN A LANGUAGE RULE.
# ``unmunch`` TRUNCATES a long line at a fixed buffer size and will cut a multi-byte UTF-8
# character in half while doing it. MEASURED at PINNED_COMMIT: of 3 566 551 emitted lines,
# ELEVEN are not valid UTF-8, and every one is a truncated ``al:`` morphological-alias line —
# for example a line ending in the lead byte of ``å`` with its continuation byte opening the
# next line.
#
# ⛔ Neither obvious handling is acceptable:
#   errors="strict" on the whole stream  -> the build dies on 11 lines out of 3.5 million
#   errors="replace" on the whole stream -> real mojibake would be silently absorbed, and a
#                                          truncated tail such as b"\xa5lsans\xc3\xa6t" could
#                                          become a plausible-looking fake word
# So each line is decoded STRICTLY on its own, an undecodable line is SKIPPED and COUNTED, and
# the count is asserted against a bound. Eleven is tolerated and reported; a systematic
# encoding failure blows the bound and fails the build. That is the only version of this that
# neither lies nor breaks.
MAX_UNDECODABLE_LINES = 100

MIN_UNIQUE = 200_000
MAX_UNIQUE = 600_000

# Fail-closed post-condition over THREE mechanisms:
#   hus vand        plain words — the expansion ran
#   københavn små   PRESERVATION witnesses — ø and å survived, so the fold stayed PARTIAL
#   cafe alle       FOLD witnesses, from `café` and `allé`
REQUIRED_WORDS: tuple[str, ...] = ("hus", "vand", "københavn", "små", "cafe", "alle")
FORBIDDEN_WORD = "qxqxqxqxq"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "danish.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "danish.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("da_DK.dic", "dc7fd12bb56ef7a25a33ea7091e0f91617d74e7aee3ae6604fce52cf727f7370"),
    ("da_DK.aff", "e8da338675a6ddc85bdcff62e7cbdbb49fe27ce8d89c1f92950f6f9d448996ed"),
    ("README_da_DK.txt", "571a502baf46058f5d4c6cddf4b13db3f98251d0f4546bc16676d3707f48e7ed"),
    ("description.xml", "6f0919b4399cbabb06081827729c7c598b5dfea95cd84924d6083621337e1ed2"),
)

# ⚠ Danish DOES have a named authority behind the data — README_da_DK.txt states the dictionary
# is based on data from Det Danske Sprog- og Litteraturselskab. That is recorded in the
# manifest's provenance. It is NOT a tournament word list, so this header still says so.
_LEXICON_HEADER = (
    "# Danish playable lexicon expanded from hunspell da_DK (Stavekontrolden) "
    f"(LibreOffice dictionaries da_DK @ {PINNED_COMMIT}).\n"
    "# The Danish edition has AE-, OE- and AA-ligature/ring TILES at 4 points each and no Q\n"
    "# tile, so:\n"
    "#   * ae-ligature, o-slash and a-ring are PRESERVED, because each has its own tile;\n"
    "#   * every other marked letter is folded to its base letter;\n"
    "#   * a word still containing a letter no tile bears -- thorn or eth, which arrive with\n"
    "#     Faroese and Icelandic names -- is DROPPED, because no tile set can spell it.\n"
    "# So this file lists playable TILE SEQUENCES: 'cafe' and 'alle' are here, and\n"
    "# 'Koebenhavn' is spelled with the o-slash rather than 'oe'.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Danish dictionary pack version {PACK_VERSION}"

_ATTRIBUTION = (
    "Danish lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries da_DK (Stavekontrolden) at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file, preserving the three\n"
    "Danish letters that have their own tiles, folding every other marked letter, and\n"
    "dropping any form that still contains a letter no Danish tile bears; see the lexicon\n"
    "header for why. The upstream README below carries the copyright and the three licence\n"
    "options, and names the dictionary files it grants them for.\n"
    "\n"
    "--- upstream README_da_DK.txt ---\n"
    "\n"
)

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

    ⛔ Deliberately NOT a line-1 test: da_DK.aff opens with comments and its ``SET UTF-8`` is
    line 23. Comments and blank lines are skipped.
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


def _require_license_sentences(readme_path: Path) -> None:
    """Every string in ``LICENSE_SENTENCES`` must be present. A tri-licence needs all four."""
    text = _collapse_whitespace(readme_path.read_text(encoding=README_ENCODING))
    missing = [
        sentence for sentence in LICENSE_SENTENCES if _collapse_whitespace(sentence) not in text
    ]
    if missing:
        print(
            f"ERROR {readme_path.name} no longer states {missing!r}. The manifest claims "
            f"{SPDX_EXPRESSION}, which asserts all three options with those exact versions, "
            "so a missing statement means the claim would over-reach.",
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
    """Rewrite one form as the tile faces the Danish edition can place. PARTIAL by design.

    ``æ``, ``ø`` and ``å`` have their own tiles and are kept; every other marked letter is
    decomposed and stripped. ``café`` becomes ``cafe`` while ``københavn`` keeps its ``ø``.

    ⛔ The per-character loop is the point: stripping marks from the whole word first would
    leave no way to tell a folded ``a`` from an original one, and ``å`` decomposes to ``a``.
    """
    pieces: list[str] = []
    for char in word:
        if char in KEEP_MARKED:
            pieces.append(char)
            continue
        decomposed = unicodedata.normalize("NFD", char)
        pieces.append("".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn"))
    return unicodedata.normalize("NFC", "".join(pieces))


def _filter_words(raw_path: Path) -> list[str]:
    unique: set[str] = set()
    dropped: set[str] = set()
    rewritten = 0
    undecodable = 0
    # ⛔ Read BYTES and decode line by line, strictly. See MAX_UNDECODABLE_LINES for why this
    # is neither a whole-stream strict read nor a whole-stream replacing read.
    with raw_path.open("rb") as handle:
        for raw_line in handle:
            try:
                text = raw_line.decode(WORD_ENCODING)
            except UnicodeDecodeError:
                undecodable += 1
                continue
            word = unicodedata.normalize("NFC", text.strip()).casefold()
            if not (word.isalpha() and len(word) >= 2):
                continue
            candidate = _to_tile_faces(word)
            if candidate != word:
                rewritten += 1
            if not (candidate.isalpha() and len(candidate) >= 2):
                continue
            if TILE_FACE_RE.match(candidate) is None:
                dropped.add(candidate)
                continue
            unique.add(candidate)
    count = len(unique)
    keepers = sum(1 for word in unique if any(mark in word for mark in KEEP_MARKED))
    print(
        f"unique_words={count} rewritten={rewritten} "
        f"words_keeping_ae_oe_or_aa={keepers} dropped_by_shape={len(dropped)} "
        f"undecodable_lines={undecodable}"
    )
    if undecodable > MAX_UNDECODABLE_LINES:
        print(
            f"ERROR {undecodable} emitted lines could not be decoded as {WORD_ENCODING}, above "
            f"the bound {MAX_UNDECODABLE_LINES}. Measured at {PINNED_COMMIT} there are ELEVEN, "
            "all truncated morphological-alias lines. A larger number means the declared affix "
            "encoding and the real byte stream disagree, which would corrupt a shipped word "
            "list, so this fails rather than absorbing it.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if keepers == 0:
        print(
            "ERROR not one finished word carries æ, ø or å. Measured at "
            f"{PINNED_COMMIT} there are 76 208, so zero means the fold became TOTAL and "
            "destroyed every one of them — all three are 4-point tiles in this edition.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if len(dropped) > MAX_SHAPE_DROPS:
        print(
            f"ERROR the shape filter dropped {len(dropped)} distinct forms, above the bound "
            f"{MAX_SHAPE_DROPS}. Measured at {PINNED_COMMIT} it drops 106 — Faroese and "
            "Icelandic proper names carrying thorn or eth. A jump to thousands means the fold "
            "stopped working and the filter is now hiding it, so this fails rather than "
            "quietly shrinking the lexicon. Sample: "
            f"{sorted(dropped)[:5]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed unless every required word survived and the forbidden one did not.

    ⛔ A POST-CONDITION of the build. ``københavn`` and ``små`` are preservation witnesses:
    a total fold spells them ``kobenhavn`` and ``sma`` and this gate catches it. ``cafe`` and
    ``alle`` are fold witnesses: if the fold never ran they stay ``café`` and ``allé``.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. "
            "'københavn' and 'små' prove the fold stayed PARTIAL; 'cafe' and 'alle' prove it "
            "ran at all — so which ones are missing says which mechanism failed.",
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
    print(f"word gate {len(REQUIRED_WORDS)}/{len(REQUIRED_WORDS)} present, control absent")


def _write_lexicon(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_LEXICON_HEADER)
        handle.write("\n".join(words))
        handle.write("\n")
    print(f"wrote {path} lines={len(words)} bytes={path.stat().st_size}")


def _write_license(path: Path, readme: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = readme.read_text(encoding=README_ENCODING) + _LICENSE_TRAILER
    path.write_text(_ATTRIBUTION + body, encoding="utf-8")
    print(f"wrote {path} bytes={path.stat().st_size}")


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, as a seam so a test can inspect it without running anything."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/libretiles-danish-lexicon"),
        help="Directory for pinned .dic/.aff/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-danish-unmunch.stdout"),
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
    _require_affix_encoding(paths["da_DK.aff"])
    _require_license_sentences(paths["README_da_DK.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["da_DK.dic"], paths["da_DK.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["README_da_DK.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
