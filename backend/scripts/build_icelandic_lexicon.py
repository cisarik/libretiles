#!/usr/bin/env python3
"""Build the committed Icelandic lexicon from pinned LibreOffice hunspell is sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⭐ THIS IS THE SIMPLEST SCRIPT IN THE FAMILY, AND THAT IS A MEASURED RESULT RATHER THAN LUCK:
Icelandic needs NO TILE-FACE REWRITE AT ALL — the first such language since Polish. Every one of
the ten non-ASCII letters its lexicon uses has its own tile:

    ð 69 668 · ó 34 348 · á 26 191 · æ 24 749 · ö 23 294 · í 19 912 · ú 13 964 · þ 8 883 ·
    ý 6 450 · é 6 108        all of them are tiles in the 2016 edition

So there is no ``_to_tile_faces`` here. There is only a SHAPE FILTER, and it drops 77 loanword
forms containing c, w, z or q — letters that are not part of the Icelandic alphabet and have no
tile. ⛔ Do NOT add a diacritic fold to this script by analogy with its siblings: folding ``ð``
to ``d`` or ``á`` to ``a`` would destroy well over a hundred thousand playable words.
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
    f"{PINNED_COMMIT}/is"
)
# Established upstream: is/description.xml declares <version value="2016.03.13" />.
PACK_VERSION = "2016.03.13"
# ⛔ A MIXED-PROVENANCE ASSET, and the expression follows the MORE RESTRICTIVE component.
# is/license.txt states two things about the material inside is.dic:
#   "The wordlist was developed by Orðabók Háskólans … and was released into the public domain.
#    Further modifications to the wordlist are also released into the public domain."
#   "The thesaurus and words in the spell checker with additional morphological information are
#    from the Icelandic Wiktionary Project … under a Creative Commons Attribution-ShareAlike 3.0
#    Unported license (CC BY-SA 3.0)."
# The two are INDISTINGUISHABLE inside the shipped .dic, so the derived word list must be treated
# as CC BY-SA 3.0: share-alike propagates, while public-domain material imposes nothing. Claiming
# public domain for the whole would under-state an obligation that actually exists.
# ⚠ Unlike Norwegian, this is DETERMINATE — both components are named and both licences are named
# with versions — so it is shippable rather than a blocker.
SPDX_EXPRESSION = "CC-BY-SA-3.0"
# ⛔ NOT a line-1 test: is.aff opens with a comment and its SET is line 2.
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
LICENSE_ENCODING = "utf-8"
# Measured verbatim in is/license.txt at PINNED_COMMIT. BOTH statements, because the SPDX
# expression above is a consequence of the two together: if either disappears, the reasoning
# behind the claim no longer holds and this must fail rather than keep asserting it.
LICENSE_SENTENCES: tuple[str, ...] = (
    "was released into the public domain",
    "Creative Commons Attribution-ShareAlike 3.0 Unported license (CC BY-SA 3.0)",
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ THE ICELANDIC ALPHABET, ALL 32 LETTERS, AND IT EQUALS THE TILE SET EXACTLY.
# 2016 Tinderbox edition under Mattel licence: 104 tiles over these same 32 kinds, so there is
# no letter without a tile and no tile outside the alphabet — perfect equality in both
# directions, which only Italian has otherwise achieved.
# MEASURED at PINNED_COMMIT with hunspell 1.7.3: 200 259 unique expanded forms of playable
# shape, of which 77 contain a letter OUTSIDE this alphabet — c 38, w 19, z 19, q 2, all in
# loanwords and foreign proper names such as `azerbaijaníska`. Those 77 are DROPPED, because no
# Icelandic tile bears any of the four and a lexicon of playable tile sequences must not contain
# sequences no tile set can spell.
TILE_FACE_RE = re.compile(r"\A[aábdðeéfghiíjklmnoóprstuúvxyýþæö]+\Z")
MAX_SHAPE_DROPS = 500
# Danish measured eleven lines this expander truncated mid-character. Icelandic measures ZERO,
# and the guard stays either way, because the defect is in the TOOL and not in the language.
MAX_UNDECODABLE_LINES = 100

MIN_UNIQUE = 120_000
MAX_UNIQUE = 400_000

# Fail-closed post-condition. SIX words chosen so that between them they exercise SIX of the ten
# non-ASCII tiles, which is what proves no fold crept in:
#   maður      ð      the most common one, 69 668 forms
#   ísland     í
#   þú         þ      and it is two letters long, so the length floor is exercised too
#   fjörður    ö and ð
#   æði        æ
#   góður      ó and ð
# ⛔ Every one of these becomes a DIFFERENT word under a diacritic fold — `madur`, `island`,
# `thu`/`u`, `fjordur`, `aedi`, `godur` — so a fold added by analogy fails this gate immediately.
REQUIRED_WORDS: tuple[str, ...] = ("maður", "ísland", "þú", "fjörður", "æði", "góður")
FORBIDDEN_WORD = "qxqxqxqxq"
# ⛔ And the artefacts a fold would produce. If any appears, somebody added a rewrite.
FORBIDDEN_FOLD_ARTEFACTS: tuple[str, ...] = ("madur", "island", "fjordur", "godur")

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "icelandic.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "icelandic.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("is.dic", "8447594fd7eb1d6d43725c4ca49b00d3f00c4c4f3ac2f2b6dfe3f56eb211d280"),
    ("is.aff", "0168050c64a369c55b5aeb61f9dfe484d2aa7512d78bb3fa36779ea24b467c50"),
    ("license.txt", "a852be66ff244eb15563a39631e7d4663811ee8e5d66682e653a989e57cd13fe"),
    ("description.xml", "0d80c9b4fdacd772ba155208d1812d0f04d78c43c9c1fb6392a350c269a9c715"),
)

# ⚠ THREE Icelandic distributions exist and the manifest ships ONE of them. The 2016 Tinderbox
# set is the Mattel-licensed SCRABBLE edition, so it is what ships — consistent with every other
# variant here, which ships the current official edition. `Krafla` (100 tiles) is explicitly
# "independent of the Scrabble brand" although it is sanctioned by Iceland's clubs for
# tournaments and the national championship, and a pre-2016 104-tile set also exists. Both are
# C5 ruleset candidates, recorded rather than shipped.
_LEXICON_HEADER = (
    "# Icelandic playable lexicon expanded from hunspell is "
    f"(LibreOffice dictionaries is @ {PINNED_COMMIT}).\n"
    "# NO tile-face rewrite is applied, and that is deliberate: every non-ASCII letter this\n"
    "# language uses -- eth, thorn, ae-ligature, o-umlaut and the six accented vowels -- has\n"
    "# its own tile in the Icelandic edition, so folding any of them would destroy playable\n"
    "# words rather than enable them.\n"
    "# The only filter is by SHAPE: 77 loanword forms containing c, w, z or q are dropped,\n"
    "# because those four are not Icelandic letters and no tile bears them.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Icelandic dictionary pack version {PACK_VERSION}"

_ATTRIBUTION = (
    "Icelandic lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries is at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file and dropping any form\n"
    "containing a letter outside the 32-letter Icelandic alphabet. No diacritic is folded.\n"
    "\n"
    "NOTE ON THE LICENCE: the upstream licence below describes a MIXED-PROVENANCE asset. The\n"
    "base wordlist was released into the public domain by Orðabók Háskólans, while words\n"
    "carrying additional morphological information come from the Icelandic Wiktionary Project\n"
    "under CC BY-SA 3.0. The two are indistinguishable inside the shipped dictionary, so the\n"
    "SPDX expression above follows the more restrictive component: share-alike propagates,\n"
    "public-domain material imposes nothing. Claiming public domain for the whole would\n"
    "under-state a real obligation.\n"
    "\n"
    "--- upstream license.txt ---\n"
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
    """The affix file's FIRST ``SET`` directive must be the encoding this script decodes with."""
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
    """Both statements must be present; the SPDX expression is a consequence of the pair."""
    text = _collapse_whitespace(license_path.read_text(encoding=LICENSE_ENCODING))
    missing = [
        sentence for sentence in LICENSE_SENTENCES if _collapse_whitespace(sentence) not in text
    ]
    if missing:
        print(
            f"ERROR {license_path.name} no longer states {missing!r}. The manifest claims "
            f"{SPDX_EXPRESSION} as a CONSEQUENCE of the public-domain base plus the CC BY-SA "
            "morphological additions, so if either statement disappears the reasoning behind "
            "the claim no longer holds and it must not keep being asserted.",
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


def _filter_words(raw_path: Path) -> list[str]:
    """Casefold, NFC, keep what the tile faces can spell. ⛔ NO tile-face rewrite — see module docstring."""
    unique: set[str] = set()
    dropped: set[str] = set()
    undecodable = 0
    with raw_path.open("rb") as handle:
        for raw_line in handle:
            try:
                text = raw_line.decode(WORD_ENCODING)
            except UnicodeDecodeError:
                undecodable += 1
                continue
            word = unicodedata.normalize("NFC", text.strip()).casefold()
            word = unicodedata.normalize("NFC", word)
            if not (word.isalpha() and len(word) >= 2):
                continue
            if TILE_FACE_RE.match(word) is None:
                dropped.add(word)
                continue
            unique.add(word)
    count = len(unique)
    non_ascii = sum(1 for word in unique if any(ord(ch) > 127 for ch in word))
    print(
        f"unique_words={count} words_with_a_non_ascii_tile={non_ascii} "
        f"dropped_by_shape={len(dropped)} undecodable_lines={undecodable}"
    )
    if undecodable > MAX_UNDECODABLE_LINES:
        print(
            f"ERROR {undecodable} emitted lines could not be decoded as {WORD_ENCODING}, above "
            f"the bound {MAX_UNDECODABLE_LINES}. Measured at {PINNED_COMMIT} there are ZERO.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if non_ascii == 0:
        print(
            "ERROR not one finished word carries a non-ASCII letter. Icelandic uses ten of "
            "them and every one is a TILE, so zero means a fold was introduced and well over "
            "a hundred thousand playable words have been destroyed.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if len(dropped) > MAX_SHAPE_DROPS:
        print(
            f"ERROR the shape filter dropped {len(dropped)} distinct forms, above the bound "
            f"{MAX_SHAPE_DROPS}. Measured at {PINNED_COMMIT} it drops 77 — loanwords carrying "
            f"c, w, z or q. Sample: {sorted(dropped)[:5]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed on a missing required word, the control word, or any fold artefact.

    ⛔ ``FORBIDDEN_FOLD_ARTEFACTS`` is what makes "no fold" an assertion rather than a comment.
    Every required word here changes under a diacritic fold, and every forbidden one is what a
    fold would produce, so the two lists catch the same mistake from both directions.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. Each one "
            "carries a non-ASCII Icelandic TILE, so a missing one most likely means a "
            "diacritic fold was introduced — which this language must not have.",
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
    artefacts = [word for word in FORBIDDEN_FOLD_ARTEFACTS if word in words]
    if artefacts:
        print(
            f"ERROR fold artefact(s) present: {artefacts}. Those are what `maður`, `ísland`, "
            "`fjörður` and `góður` become under a diacritic fold. Icelandic tiles bear eth, "
            "thorn and the accented vowels, so no fold belongs in this script.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        f"word gate {len(REQUIRED_WORDS)}/{len(REQUIRED_WORDS)} present, control absent, "
        "no fold artefacts"
    )


def _write_lexicon(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_LEXICON_HEADER)
        handle.write("\n".join(words))
        handle.write("\n")
    print(f"wrote {path} lines={len(words)} bytes={path.stat().st_size}")


def _write_license(path: Path, license_file: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = license_file.read_text(encoding=LICENSE_ENCODING) + _LICENSE_TRAILER
    path.write_text(_ATTRIBUTION + body, encoding="utf-8")
    print(f"wrote {path} bytes={path.stat().st_size}")


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, as a seam so a test can inspect it without running anything."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/libretiles-icelandic-lexicon"),
        help="Directory for pinned .dic/.aff/licence/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-icelandic-unmunch.stdout"),
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
    _require_affix_encoding(paths["is.aff"])
    _require_license_sentences(paths["license.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["is.dic"], paths["is.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["license.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
