#!/usr/bin/env python3
"""Build the committed Afrikaans lexicon from pinned LibreOffice hunspell af_ZA sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ THIS SCRIPT DIFFERS FROM ITS THREE SIBLINGS IN ONE MATERIAL WAY, AND IT IS DELIBERATE:
it FOLDS DIACRITICS at build time. See ``_fold_diacritics`` and ``FOLD_DIACRITICS`` below for
the sourced reason, the measurement, and the boundary of where that technique is legitimate.
Do NOT copy the folding into a language whose edition treats an accented letter as a distinct
letter with its own tile — Slovak ``Á``, Czech ``Í`` and German ``Ä`` are all such letters, and
folding them would destroy playable words.
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
    f"{PINNED_COMMIT}/af_ZA"
)
# Established upstream, not copied from the committed asset: af_ZA/description.xml declares
# ``<version value="2024.02.13" />``. ``_require_pack_version`` asserts it, so a future pack
# bump fails loudly here instead of silently contradicting afrikaans.LICENSE.
PACK_VERSION = "2024.02.13"
# ⛔ CONSERVATIVE ON PURPOSE. README_af_ZA.txt section 5 says "This software is released under
# the LGPL" and embeds "GNU LESSER GENERAL PUBLIC LICENSE Version 2.1, February 1999" verbatim.
# It does NOT carry an explicit "or (at your option) any later version" grant for this work, so
# the honest expression is -only rather than -or-later. Do not widen it to look tidier; the
# whole README, licence text included, ships as afrikaans.LICENSE so a reader can check.
SPDX_EXPRESSION = "LGPL-2.1-only"
# ⛔ ENCODING IS NAMED AND ASSERTED, NEVER DEFAULTED — and the assertion here is NOT the
# line-1 test its three siblings use. MEASURED: cs_CZ.aff, pl_PL.aff and sk_SK.aff open with
# their ``SET`` directive, but af_ZA.aff line 1 is
#     ``# af_ZA.aff - Afrikaans (af) affix file for use in hunspell``
# and ``SET UTF-8`` is line 31. A line-1 test would have failed on a perfectly correct affix
# file. So this script asserts the FIRST ``SET`` directive instead, which is the thing that
# actually governs unmunch's output encoding.
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
# Measured verbatim in af_ZA/README_af_ZA.txt at PINNED_COMMIT (lines 167-168, hard-wrapped;
# ``_collapse_whitespace`` is why the wrap does not matter).
LICENSE_SENTENCE = (
    "This software is released under the LGPL which is included here for your information."
)
# ⛔ THE EXPANDER IS PINNED, AND A MISMATCH IS FATAL. ``unmunch`` prints no version of its own,
# so the identity comes from ``hunspell -vv``. A different expander may expand the same affix
# file into a DIFFERENT word list, and this script writes a shipped asset.
# ⛔ Keep this value IDENTICAL in all ELEVEN build scripts; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ THE ONE RULE THAT MAKES THIS LANGUAGE PLAYABLE, AND IT IS SOURCED.
# The Afrikaans Scrabble edition ships 102 tiles bearing PLAIN LATIN LETTERS ONLY, and its
# distribution note states that diacritical marks are ignored. Afrikaans orthography, however,
# uses ë ê ï é ö ô á ó è ú û ü ý í ä ò ñ à â freely.
#
# MEASURED at PINNED_COMMIT with hunspell 1.7.3:
#     148 601 unique expanded forms of playable shape
#       4 614 of them (3.10%) contain at least one non a-z letter
#     folding those 4 614 yields 4 280 NEW forms and 314 that already existed
#     148 267 unique forms after folding, and ZERO non a-z letters remain
#
# Without folding, those 4 614 words sit in the lexicon and can never be played, because no
# tile bears ``ë``: ``môre`` (tomorrow), ``aangelê``, ``reël`` would all be unreachable, and a
# player spelling MORE, AANGELE or REEL would be told the word is invalid. Folding at BUILD
# time is what makes the asset answer the only question the board can ask — "is this sequence
# of tile faces a word" — and it needs no engine branch, no manifest field, and no capability.
#
# ⛔ THE BOUNDARY, and it is the important half. Build-time folding is legitimate ONLY when the
# fold is TOTAL for the edition: every accented letter must be absent from the tile set AND
# treated as its base letter by the edition's own rules. It is WRONG for Slovak (``A`` and
# ``Á`` are separate tiles), wrong for Czech, and wrong for German (``Ä`` is not ``A`` even
# though ``ß`` expands to ``SS``). Those cases need a variant-declared normalization rule, not
# a folded asset. Adding folding to a language because "it worked for Afrikaans" would silently
# delete playable words.
FOLD_DIACRITICS = True

MIN_UNIQUE = 100_000
MAX_UNIQUE = 400_000

# Fail-closed post-condition. Six words that MUST survive into the finished lexicon, chosen so
# that the set proves three different things rather than six times the same thing:
#   die en van   ordinary high-frequency Afrikaans words — the expansion ran at all
#   more         the folded form of ``môre``; absent unless folding worked
#   aangele      the folded form of ``aangelê``; a second, differently-accented witness
#   reel         the folded form of ``reël``; a third, with a diaeresis rather than a circumflex
# ⛔ Three of the six are folded forms on purpose. A gate made only of plain words would pass
# even if FOLD_DIACRITICS silently became a no-op.
REQUIRED_WORDS: tuple[str, ...] = ("die", "en", "van", "more", "aangele", "reel")
# And one word that must NOT be there, so the gate cannot pass by asserting against everything.
FORBIDDEN_WORD = "qxqxqxqxq"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "afrikaans.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "afrikaans.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("af_ZA.dic", "8d806f90146059ea18b49c2352d188bd27dcc571a06815794facaa176aa5a5de"),
    ("af_ZA.aff", "fdfcdd04d700fc4ac94be63930167fa942ee5ffb471b52a6f4e0c68362dd63d2"),
    ("README_af_ZA.txt", "e00c86cb0a1c0499380770750f545b5d0308d6cb35d25014cef6891c2fe5f255"),
    ("description.xml", "a50112d68ca165827d094a5be7e085d03fa685824d7ed56a5c2a971bdd1b59e7"),
)

# ⛔ af_ZA names NO national language authority for a tournament word list, so this header says
# "Not an official tournament list." with no authority named — the same wording as Czech, and
# deliberately NOT the Slovak wording, which names SSS. Do not normalize the three.
# The folding note is part of the header because a reader comparing this file to an Afrikaans
# dictionary must be told immediately why ``more`` appears and ``môre`` does not.
_LEXICON_HEADER = (
    "# Afrikaans playable lexicon expanded from hunspell af_ZA "
    f"(LibreOffice dictionaries af_ZA @ {PINNED_COMMIT}).\n"
    "# Diacritics are FOLDED to their base letter, because the Afrikaans Scrabble edition\n"
    "# bears plain Latin tiles only and ignores diacritical marks. So this file lists\n"
    "# playable TILE SEQUENCES, not Afrikaans orthography: 'more' is here, 'more' with a\n"
    "# circumflex is not.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Afrikaans dictionary pack version {PACK_VERSION}"

# ⛔ af_ZA has NO standalone LICENSE file — its licence text lives INSIDE README_af_ZA.txt,
# whose section 5 embeds the complete LGPL 2.1. That is why this block says
# ``--- upstream README_af_ZA.txt ---`` where build_slovak_lexicon.py says
# ``--- upstream LICENSE.txt ---``. It is also why there is only ONE embedded document here,
# where build_czech_lexicon.py embeds two READMEs. Do not "fix" either difference.
_ATTRIBUTION = (
    "Afrikaans lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries af_ZA at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file and then folding\n"
    "diacritics to their base letters; see the lexicon header for why. The upstream\n"
    "README below carries the copyright statements and the full LGPL 2.1 text.\n"
    "\n"
    "--- upstream README_af_ZA.txt ---\n"
    "\n"
)

_LICENSE_TRAILER = "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_inside_assets(path: Path) -> bool:
    """True when ``path`` resolves inside ``backend/assets/``.

    Both sides are ``resolve()``d FIRST, so a relative path, a ``..`` traversal and a symlink
    whose own name looks harmless all collapse to the same answer. A textual prefix test
    would let every one of those three straight through.
    """
    resolved = path.resolve()
    assets = _ASSETS_ROOT.resolve()
    return resolved == assets or assets in resolved.parents


def require_check_dir_outside_assets(path: Path) -> Path:
    """Refuse a ``--check`` working directory inside the assets tree; return the resolved dir.

    ⛔ This is the guard the whole ``--check`` mode exists for. The committed asset is the
    comparison ORACLE, so a mode that reproduced into the assets tree would overwrite the
    very file it claims to verify and then report agreement with itself.
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

    ⛔ Deliberately NOT a line-1 test. MEASURED: af_ZA.aff line 1 is a comment and its
    ``SET UTF-8`` is line 31, whereas cs_CZ.aff, pl_PL.aff and sk_SK.aff all open with their
    ``SET`` directive. Asserting line 1 here would reject a correct affix file. Comments and
    blank lines are skipped; the first ``SET`` line found is the one that governs ``unmunch``
    output, so it is the one that must match.
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


def _require_license_sentence(readme_path: Path) -> None:
    text = _collapse_whitespace(readme_path.read_text(encoding="utf-8"))
    if LICENSE_SENTENCE not in text:
        print(
            f"ERROR {readme_path.name} no longer states the LGPL grant {LICENSE_SENTENCE!r}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"licence sentence asserted: {LICENSE_SENTENCE}")


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


def _fold_diacritics(word: str) -> str:
    """Strip combining marks: ``môre`` -> ``more``, ``reël`` -> ``reel``.

    NFD splits a precomposed letter into base plus combining mark; dropping every ``Mn``
    (non-spacing mark) leaves the base. The result is re-normalized to NFC by the caller, so
    the finished asset is NFC exactly like its three siblings and ``validate_lexicons``
    reports ``non_nfc=0``.

    ⚠ This is a TOTAL fold, not a table of special cases, and that is only correct because
    every letter it touches is absent from the Afrikaans tile set. A language with an accented
    TILE must never route through here.
    """
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _filter_words(raw_path: Path) -> list[str]:
    unique: set[str] = set()
    folded_count = 0
    with raw_path.open(encoding=WORD_ENCODING, errors="strict") as handle:
        for line in handle:
            word = unicodedata.normalize("NFC", line.strip()).casefold()
            if not (word.isalpha() and len(word) >= 2):
                continue
            if FOLD_DIACRITICS:
                candidate = unicodedata.normalize("NFC", _fold_diacritics(word))
                if candidate != word:
                    folded_count += 1
                word = candidate
                # Re-check shape: folding cannot introduce a non-letter, but a word that was
                # only alphabetic BECAUSE of its marks would be caught here rather than
                # silently shipped.
                if not (word.isalpha() and len(word) >= 2):
                    continue
            unique.add(word)
    count = len(unique)
    print(f"unique_words={count} folded_inputs={folded_count}")
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed unless every required word survived and the forbidden one did not.

    ⛔ This is a POST-CONDITION of the build, not a test somebody may forget to run. A build
    that silently produced a lexicon missing ``more`` — the folded ``môre`` — would ship an
    Afrikaans variant in which a common word cannot be played, and every mechanical gate in
    the repository would stay green, because word COUNT and file SIZE cannot see it.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. Three of "
            "the six are FOLDED forms, so this most likely means the diacritic fold did not "
            "run.",
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
    body = readme.read_text(encoding="utf-8") + _LICENSE_TRAILER
    path.write_text(_ATTRIBUTION + body, encoding="utf-8")
    print(f"wrote {path} bytes={path.stat().st_size}")


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, as a seam so a test can inspect it without running anything."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/libretiles-afrikaans-lexicon"),
        help="Directory for pinned .dic/.aff/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-afrikaans-unmunch.stdout"),
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
    _require_affix_encoding(paths["af_ZA.aff"])
    _require_license_sentence(paths["README_af_ZA.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["af_ZA.dic"], paths["af_ZA.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["README_af_ZA.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
