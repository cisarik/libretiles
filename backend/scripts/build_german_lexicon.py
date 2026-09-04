#!/usr/bin/env python3
"""Build the committed German lexicon from pinned LibreOffice hunspell de_DE_frami sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ TWO THINGS MAKE THIS SCRIPT DIFFERENT FROM ITS SIBLINGS, AND BOTH ARE MEASURED:

1. THE UPSTREAM IS ISO8859-1, NOT UTF-8. ``de_DE_frami.aff`` declares ``SET ISO8859-1``, so
   ``unmunch`` emits latin-1 bytes and ``README_de_DE_frami.txt`` is latin-1 too. Decoding
   either as UTF-8 produces mojibake in a shipped asset. This is the exact hazard
   build_czech_lexicon.py's encoding comment warned the next language about, and German is
   that next language.

2. THE FOLD IS PARTIAL, NOT TOTAL. Afrikaans, Italian and Dutch fold every marked letter
   because none of them has a tile. German has Ä, Ö and Ü TILES — at 6, 8 and 6 points — so
   those three must SURVIVE, while é ñ á ç ê à â è must fold. See ``_to_tile_faces``.

⚠ And one thing that needs NO rule at all: ``ß``. Python's ``str.casefold()`` implements full
Unicode case folding, so ``'ß'.casefold() == 'ss'`` already. The German edition has no ß tile
and spells the sound SS, so the default casefold in ``_filter_words`` is exactly right and no
special mapping is needed. MEASURED: zero ß survives into the finished lexicon.
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
    f"{PINNED_COMMIT}/de"
)
# Established upstream: de/description.xml declares <version value="2017.01.12" />.
PACK_VERSION = "2017.01.12"
# ⛔ A DUAL LICENCE, like Dutch but a different shape. README_de_DE_frami.txt states, in German:
# "Das Wörterbuch und alle enthaltenen Wortlisten sind lizenziert unter der GNU GPL, Version 2
# oder 3." — "Version 2 or 3", a choice between exactly those two, NOT "2 or later". So the
# expression is an OR of two -only identifiers rather than GPL-2.0-or-later, which would also
# grant version 4 if one ever existed.
SPDX_EXPRESSION = "GPL-2.0-only OR GPL-3.0-only"
# ⛔ NOT UTF-8, AND THAT IS THE POINT. de_DE_frami.aff line 13 declares SET ISO8859-1.
AFFIX_SET_LINE = b"SET ISO8859-1"
WORD_ENCODING = "iso8859-1"
# ⛔ The README is latin-1 as well; reading it as UTF-8 raises before it can be asserted.
README_ENCODING = "iso8859-1"
# Measured verbatim in de/README_de_DE_frami.txt at PINNED_COMMIT, decoded as latin-1.
LICENSE_SENTENCE = (
    "Das Wörterbuch und alle enthaltenen Wortlisten sind lizenziert unter der "
    "GNU GPL, Version 2 oder 3."
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ THE EDITION RULE, AND IT IS PARTIAL. The German set is 102 tiles over 29 letter kinds:
# A-Z plus Ä (6 points), Ö (8) and Ü (6). There is NO ß tile.
# So a marked letter that HAS a tile must be kept, and one that does not must fold.
# MEASURED at PINNED_COMMIT with hunspell 1.7.3, decoding as latin-1:
#     709 883 unique expanded forms of playable shape
#         223 of them (0.031%) carry a letter outside a-z + ä ö ü:
#             é 198 · ñ 11 · á 9 · ç 7 · ê 2 · à 2 · â 2 · è 1   — all loanwords
#     709 844 unique forms after the rule, ZERO characters outside the tile faces remain,
#     and 155 641 words STILL CARRY an umlaut, which is what proves the fold stayed partial
# ⛔ Do NOT replace this with the total fold used by Afrikaans, Italian and Dutch. A total fold
# would rewrite `käse` to `kase` and delete 155 641 playable words while every count-based gate
# stayed green.
KEEP_MARKED: frozenset[str] = frozenset({"ä", "ö", "ü"})
# ⛔ And nothing may survive that no tile bears. ß is covered by casefold, but asserting it is
# free and a silently changed expander would show up here.
FORBIDDEN_CHARS: tuple[str, ...] = ("ß",)

MIN_UNIQUE = 500_000
MAX_UNIQUE = 1_500_000

# Fail-closed post-condition covering FOUR distinct mechanisms, not four samples of one:
#   haus wasser   plain words — the expansion ran and latin-1 decoding worked
#   strasse       ß expanded by casefold, from `Straße`
#   käse über     UMLAUT PRESERVED — the fold stayed PARTIAL. Without these two the gate would
#                 pass a total fold that silently destroyed 155 641 words.
#   attache       folded from `attaché` — the fold still runs where there is no tile
REQUIRED_WORDS: tuple[str, ...] = ("haus", "wasser", "strasse", "käse", "über", "attache")
FORBIDDEN_WORD = "qxqxqxqxq"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "german.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "german.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("de_DE_frami.dic", "52d2484a70681386d979e958f2f828a976f0dcdaa680038f371bc70abcf7463a"),
    ("de_DE_frami.aff", "646bf3333ac69c23e9d794533ee5241d6f755c359e8fe10a648f87613743d594"),
    (
        "README_de_DE_frami.txt",
        "c141f4f79c428b7348b5012836f4ad3db4d124f288f15effc22696dc876512ae",
    ),
    ("description.xml", "cb7774b42d95117d8078c5bb38144226a1e5e19d535059ee5974e48738355d0d"),
)

_LEXICON_HEADER = (
    "# German playable lexicon expanded from hunspell de_DE_frami "
    f"(LibreOffice dictionaries de @ {PINNED_COMMIT}).\n"
    "# The German edition has A-Z plus AE-, OE- and UE-umlaut TILES and no eszett tile, so:\n"
    "#   * eszett is written 'ss' -- Unicode full case folding already does this;\n"
    "#   * a-umlaut, o-umlaut and u-umlaut are PRESERVED, because each has its own tile;\n"
    "#   * every other marked letter (loanword accents) is folded to its base letter.\n"
    "# So this file lists playable TILE SEQUENCES: 'strasse' and 'attache' are here,\n"
    "# 'kaese' is not -- 'k' + a-umlaut + 'se' is.\n"
    "# Compound words are not enumerated; unmunch expands affixes, not compounding.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice German dictionary pack version {PACK_VERSION}"

# ⛔ de/ has COPYING_GPLv2 and COPYING_GPLv3 as separate top-level files, but the GRANT is the
# sentence in README_de_DE_frami.txt, and that README is what names both versions. Embedding
# the two full licence texts would add ~55 kB of boilerplate that the SPDX expression already
# identifies, so the README is embedded and the SPDX expression carries the rest.
_ATTRIBUTION = (
    "German lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries de / de_DE_frami at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "Upstream is ISO8859-1 encoded; this file is UTF-8. The word list is derived by expanding\n"
    "the upstream affix file, letting Unicode case folding write eszett as 'ss', preserving\n"
    "a-, o- and u-umlaut because each has its own tile, and folding every other marked letter.\n"
    "The full GNU GPL v2 and v3 texts are not reproduced here; the SPDX expression above\n"
    "identifies them and upstream ships them as COPYING_GPLv2 and COPYING_GPLv3.\n"
    "\n"
    "--- upstream README_de_DE_frami.txt ---\n"
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

    ⛔ For German that directive is ``SET ISO8859-1``, at line 13, and asserting it is the whole
    defence against mojibake: ``unmunch`` emits bytes in the affix file's own encoding, and a
    silent UTF-8 default would turn every umlaut in a shipped word list into replacement
    characters. Comments and blank lines are skipped.
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
    text = _collapse_whitespace(readme_path.read_text(encoding=README_ENCODING))
    if _collapse_whitespace(LICENSE_SENTENCE) not in text:
        print(
            f"ERROR {readme_path.name} no longer states the GPL grant {LICENSE_SENTENCE!r}. "
            f"It is read as {README_ENCODING}; a UTF-8 read would also fail here, on the "
            "umlauts rather than on the licence.",
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


def _to_tile_faces(word: str) -> str:
    """Rewrite one form as the tile faces the German edition can place. PARTIAL by design.

    A marked letter that HAS a tile — ``ä``, ``ö``, ``ü`` — is kept exactly as it is. Every
    other marked letter is decomposed and stripped, so ``attaché`` becomes ``attache`` while
    ``käse`` stays ``käse``.

    ⛔ The per-character loop is not an optimisation target; it is the point. Stripping marks
    from the WHOLE word first and then trying to restore the umlauts would need a second pass
    that cannot tell a folded ``a`` from an original one.
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
    rewritten = 0
    # ⛔ errors="strict" against WORD_ENCODING. _require_affix_encoding has already asserted
    # SET ISO8859-1, so an undecodable byte here means the pinned pair changed underneath us.
    with raw_path.open(encoding=WORD_ENCODING, errors="strict") as handle:
        for line in handle:
            word = unicodedata.normalize("NFC", line.strip()).casefold()
            word = unicodedata.normalize("NFC", word)
            if not (word.isalpha() and len(word) >= 2):
                continue
            candidate = _to_tile_faces(word)
            if candidate != word:
                rewritten += 1
            if not (candidate.isalpha() and len(candidate) >= 2):
                continue
            unique.add(candidate)
    count = len(unique)
    umlauts = sum(1 for word in unique if any(mark in word for mark in KEEP_MARKED))
    print(f"unique_words={count} rewritten={rewritten} words_keeping_an_umlaut={umlauts}")
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if umlauts == 0:
        print(
            "ERROR not one finished word carries an umlaut. Measured at "
            f"{PINNED_COMMIT} there are 155 641, so zero means the fold became TOTAL and "
            "destroyed every ä, ö and ü — which are tiles in this edition.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed on a missing required word, a present control word, or a surviving eszett.

    ⛔ A POST-CONDITION of the build. ``käse`` and ``über`` are in the required set precisely
    so that a fold which became total fails here rather than shipping a lexicon that is the
    right SIZE and the wrong CONTENT.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. "
            "'strasse' proves case folding expanded eszett, 'käse' and 'über' prove the fold "
            "stayed PARTIAL, and 'attache' proves it still runs where there is no tile — so "
            "which ones are missing says which mechanism failed.",
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
    for char in FORBIDDEN_CHARS:
        survivors = [word for word in words if char in word]
        if survivors:
            print(
                f"ERROR {len(survivors)} finished word(s) still contain {char!r}, e.g. "
                f"{sorted(survivors)[:3]}. No tile bears it, so those words are unplayable.",
                file=sys.stderr,
            )
            raise SystemExit(1)
    print(
        f"word gate {len(REQUIRED_WORDS)}/{len(REQUIRED_WORDS)} present, control absent, "
        "no surviving eszett"
    )


def _write_lexicon(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_LEXICON_HEADER)
        handle.write("\n".join(words))
        handle.write("\n")
    print(f"wrote {path} lines={len(words)} bytes={path.stat().st_size}")


def _write_license(path: Path, readme: Path) -> None:
    """⛔ Read latin-1, write UTF-8. The committed asset is UTF-8 like every other one here."""
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
        default=Path("/tmp/libretiles-german-lexicon"),
        help="Directory for pinned .dic/.aff/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-german-unmunch.stdout"),
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
    _require_affix_encoding(paths["de_DE_frami.aff"])
    _require_license_sentence(paths["README_de_DE_frami.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["de_DE_frami.dic"], paths["de_DE_frami.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["README_de_DE_frami.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
