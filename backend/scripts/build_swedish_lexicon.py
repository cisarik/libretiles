#!/usr/bin/env python3
"""Build the committed Swedish lexicon from pinned LibreOffice hunspell sv_SE sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ THE RULE HERE HAS A CARVE-OUT INSIDE A CARVE-OUT, AND IT IS SOURCED. The Swedish edition's
distribution note says: "Å, Ä and Ö have separate tiles as these are considered separate letters
in the Swedish alphabet; other diacritics like that on É are ignored (EXCEPT Ü). Ü and Æ require
a blank, and as of 2010 only occur in one and three playable words respectively."

So there are three classes, not two:
  Å Ä Ö    have tiles  -> KEPT, and they are tile faces
  Ü        NO tile, but the edition does NOT ignore it -> NOT folded, and therefore DROPPED by
           the shape filter, because no tile and no derivable blank target can produce it
  É è á ç… NO tile and the edition DOES ignore them -> FOLDED to the base letter
⚠ Folding Ü would make `müsli` playable as MUSLI. That is a rule this edition does not have, and
it is exactly the kind of quiet over-generosity a word count cannot see.
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
    f"{PINNED_COMMIT}/sv_SE"
)
# Established upstream: sv_SE/description.xml declares <version value="2.40" />. ⚠ Like Dutch's
# "2.0.0" and unlike the dated packs, this maintainer versions his own way. Do not normalize it.
PACK_VERSION = "2.40"
# ⛔ A SINGLE licence, and the cleanest statement of any language here: LICENSE_en_US.txt says
# "This dictionary is made available subject to the terms of GNU Lesser General Public License
# Version 3." No "or later", so -only. One maintainer, one grant, no ambiguity.
SPDX_EXPRESSION = "LGPL-3.0-only"
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
README_ENCODING = "utf-8"
# Measured verbatim in sv_SE/LICENSE_en_US.txt at PINNED_COMMIT.
LICENSE_SENTENCES: tuple[str, ...] = (
    "This dictionary is made available subject to the terms of "
    "GNU Lesser General Public License Version 3.",
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ NOT FOLDED. Å Ä Ö because they are tiles; Ü because the sourced note explicitly exempts it
# from the "diacritics are ignored" rule. Ü then fails the tile-face filter below and its words
# are dropped, which is the faithful outcome: the note says Ü "requires a blank", and derived
# blank targets come from the tile set, so no blank can become Ü either.
# MEASURED at PINNED_COMMIT with hunspell 1.7.3:
#     823 327 unique expanded forms of playable shape
#     folded: é 3 574 · è 56 · á 47 · ç 33 · ć 27 · ó 25 · í 18 · â 10 and a tail
#     822 919 unique forms after the rule; 320 299 of them still carry å, ä or ö
KEEP_MARKED: frozenset[str] = frozenset({"å", "ä", "ö", "ü"})

# ⛔ THE SHAPE FILTER. Å Ä Ö are tile faces; Ü is not. Neither are æ, ø, ł or μ, which arrive
# with Danish, Norwegian and Polish proper names and are distinct letters that no fold touches.
# MEASURED: 155 distinct forms are dropped — ü 124 · ł 14 · æ 9 · ø 9 · μ 1 — for example
# `atatürk`, `bülow`, `bjørnson`, `jarosław`. A lexicon of playable tile sequences must not
# contain sequences no tile set can spell.
TILE_FACE_RE = re.compile(r"\A[a-zåäö]+\Z")
MAX_SHAPE_DROPS = 800
# Danish measured eleven truncated lines from the same expander. Swedish measured ZERO, but the
# bound is kept because the defect is in the TOOL, not in the language.
MAX_UNDECODABLE_LINES = 100

MIN_UNIQUE = 500_000
MAX_UNIQUE = 1_500_000

# Fail-closed post-condition over three mechanisms:
#   hus vatten bok   plain words — the expansion ran
#   väg sjö          PRESERVATION witnesses — ä and ö survived, so the fold stayed PARTIAL
#   cafe             FOLD witness, from `café`
REQUIRED_WORDS: tuple[str, ...] = ("hus", "vatten", "bok", "väg", "sjö", "cafe")
FORBIDDEN_WORD = "qxqxqxqxq"
# ⛔ And one word that must be ABSENT, which is the whole point of not folding Ü: if `musli`
# ever appears, Ü was folded and the lexicon now permits a play the edition does not.
FORBIDDEN_FOLD_ARTEFACT = "musli"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "swedish.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "swedish.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("sv_SE.dic", "8bf485a6b0be30bd901d7acbdc1a8ee9c70471885b476f2e42eeba6fe2959bee"),
    ("sv_SE.aff", "b721c9d44bee912feb182b601a1bc2ae3e7dffef660f4130cf2751867488a9dd"),
    ("LICENSE_en_US.txt", "236df23d082b84cf68c70337c7e1739a106d78c133a2d6eb02bb5389f2ddefd3"),
    ("LICENSE_sv_SE.txt", "19a8bb060a50a0946aa33124608faf95ab215259b8b96b9f797b18a5ffa41599"),
    ("description.xml", "53c8c21813afc8982a7593109a43d601154d1d55850cdc3f1378765d151b7493"),
)

_LEXICON_HEADER = (
    "# Swedish playable lexicon expanded from hunspell sv_SE "
    f"(LibreOffice dictionaries sv_SE @ {PINNED_COMMIT}).\n"
    "# The Swedish edition has A-ring, A-umlaut and O-umlaut TILES because they are separate\n"
    "# letters of the alphabet, and ignores other diacritics EXCEPT U-umlaut, so:\n"
    "#   * a-ring, a-umlaut and o-umlaut are PRESERVED;\n"
    "#   * every other marked letter is folded to its base letter -- except u-umlaut, which\n"
    "#     the edition does NOT ignore and no tile bears, so its words are dropped;\n"
    "#   * a word containing any other letter no tile bears is dropped for the same reason.\n"
    "# So 'cafe' is here and 'muesli' is not, in either spelling.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Swedish dictionary pack version {PACK_VERSION}"

# ⛔ BOTH licence files are embedded: the English one carries the grant this build asserts, and
# the Swedish one is the maintainer's own wording of the same grant. Neither is redundant —
# shipping only the English text would drop the author's original statement.
_ATTRIBUTION = (
    "Swedish lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries sv_SE at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file, preserving the three\n"
    "Swedish letters that have their own tiles, folding every other marked letter except\n"
    "u-umlaut, and dropping any form that still contains a letter no Swedish tile bears;\n"
    "see the lexicon header for why.\n"
    "\n"
    "--- upstream LICENSE_en_US.txt ---\n"
    "\n"
)

_NATIVE_LICENSE_SECTION = "\n--- upstream LICENSE_sv_SE.txt ---\n\n"
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
    """Every string in ``LICENSE_SENTENCES`` must still be present in the upstream licence."""
    text = _collapse_whitespace(license_path.read_text(encoding=README_ENCODING))
    missing = [
        sentence for sentence in LICENSE_SENTENCES if _collapse_whitespace(sentence) not in text
    ]
    if missing:
        print(
            f"ERROR {license_path.name} no longer states {missing!r}. The manifest claims "
            f"{SPDX_EXPRESSION}, so a missing statement means the claim would over-reach.",
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
    """Rewrite one form as the tile faces the Swedish edition can place. PARTIAL by design.

    Anything in ``KEEP_MARKED`` is left alone; everything else is decomposed and stripped.
    ``café`` becomes ``cafe``; ``väg`` keeps its ``ä``; ``müsli`` keeps its ``ü`` and is then
    dropped by the shape filter, because the edition does not ignore that letter and no tile
    bears it.

    ⛔ The per-character loop is the point: ``å`` decomposes to ``a``, so stripping marks from
    the whole word first would leave no way to tell a folded ``a`` from an original one.
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
    # ⛔ BYTES, decoded line by line and strictly. Danish measured eleven lines this expander
    # truncated mid-character; Swedish measures zero, and the guard stays either way.
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
    keepers = sum(1 for word in unique if any(mark in word for mark in "åäö"))
    print(
        f"unique_words={count} rewritten={rewritten} words_keeping_aa_ae_or_oe={keepers} "
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
    if keepers == 0:
        print(
            "ERROR not one finished word carries å, ä or ö. Measured at "
            f"{PINNED_COMMIT} there are 320 299, so zero means the fold became TOTAL and "
            "destroyed every one of them — all three are tiles in this edition.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if len(dropped) > MAX_SHAPE_DROPS:
        print(
            f"ERROR the shape filter dropped {len(dropped)} distinct forms, above the bound "
            f"{MAX_SHAPE_DROPS}. Measured at {PINNED_COMMIT} it drops 155 — ü 124, ł 14, æ 9, "
            "ø 9, μ 1, mostly foreign proper names. A jump means the fold stopped working and "
            f"the filter is now hiding it. Sample: {sorted(dropped)[:5]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed on a missing required word, a present control word, or a folded ``ü``.

    ⛔ ``FORBIDDEN_FOLD_ARTEFACT`` is the assertion that makes the Ü carve-out real. If ``musli``
    appears, ``ü`` was folded to ``u`` and the lexicon now permits a play the Swedish edition
    does not have — and no word count, file size or digest would tell anyone.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. "
            "'väg' and 'sjö' prove the fold stayed PARTIAL; 'cafe' proves it ran at all.",
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
    if FORBIDDEN_FOLD_ARTEFACT in words:
        print(
            f"ERROR {FORBIDDEN_FOLD_ARTEFACT!r} is present, which means ü was FOLDED to u. The "
            "sourced Swedish rule ignores other diacritics EXCEPT ü, so that fold would make a "
            "word playable that the edition requires a blank for. Remove ü from the fold.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(
        f"word gate {len(REQUIRED_WORDS)}/{len(REQUIRED_WORDS)} present, control absent, "
        "ü not folded"
    )


def _write_lexicon(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_LEXICON_HEADER)
        handle.write("\n".join(words))
        handle.write("\n")
    print(f"wrote {path} lines={len(words)} bytes={path.stat().st_size}")


def _write_license(path: Path, english: Path, native: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        english.read_text(encoding=README_ENCODING)
        + _NATIVE_LICENSE_SECTION
        + native.read_text(encoding=README_ENCODING)
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
        default=Path("/tmp/libretiles-swedish-lexicon"),
        help="Directory for pinned .dic/.aff/licence/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-swedish-unmunch.stdout"),
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
    _require_affix_encoding(paths["sv_SE.aff"])
    _require_license_sentences(paths["LICENSE_en_US.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["sv_SE.dic"], paths["sv_SE.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["LICENSE_en_US.txt"], paths["LICENSE_sv_SE.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
