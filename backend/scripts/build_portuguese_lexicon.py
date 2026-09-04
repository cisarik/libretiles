#!/usr/bin/env python3
"""Build the committed Portuguese lexicon from pinned LibreOffice hunspell pt_PT sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ THREE THINGS TO KNOW BEFORE EDITING THIS SCRIPT:

1. THE FOLD IS PARTIAL, like German's and unlike Afrikaans/Italian/Dutch. ``Ç`` is a separate
   TILE worth 3 points in the Portuguese edition, so it must SURVIVE, while every other
   diacritic folds. ``coração`` becomes ``coraçao``, NOT ``coracao``.

2. TWO ENCODINGS IN ONE UPSTREAM PACK. ``pt_PT.aff`` declares ``SET UTF-8`` and
   ``LICENSES.txt`` is UTF-8, but ``README_pt_PT.txt`` is ISO8859-1 and raises on a UTF-8 read.
   German's whole pack was latin-1; here it is mixed, which is why the encodings are named
   per file rather than once.

3. UPSTREAM CONTRADICTS ITSELF ABOUT THE LICENCE, and this script takes the specific,
   versioned statement. See ``SPDX_EXPRESSION``.
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
    f"{PINNED_COMMIT}/pt_PT"
)
# Established upstream: pt_PT/description.xml declares <version value="20.10.5.1" />.
PACK_VERSION = "20.10.5.1"
# ⛔ TWO UPSTREAM FILES DISAGREE, AND THE DISAGREEMENT IS RECORDED RATHER THAN SMOOTHED OVER:
#   README_pt_PT.txt  "All dictionary files and associated programs are currently covered by
#                      the (GPL/LGPL/MPL), by this order." and then, explicitly,
#                      "1. GPL Version 2  2. LGPL Version 2.1  3. MPL Version 1.1"
#   LICENSES.txt      under "Spellchecker", by different authors and with NO versions:
#                      "All dictionary files and associated programs are currently covered
#                       by the GPL and BSD licence"
# The README is the specific statement: it names the exact artifact class this script consumes
# AND pins three versions. It is also the same tri-licence shape the shipped Slovak lexicon
# already declares, so this expression is consistent with the house rather than invented here.
# ⛔ BSD is NOT claimed, precisely because only the vaguer of the two files mentions it. Both
# upstream files ship verbatim inside portuguese.LICENSE so a reader can check the conflict.
SPDX_EXPRESSION = "GPL-2.0-only OR LGPL-2.1-only OR MPL-1.1"
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
# ⛔ PER-FILE ENCODINGS. Measured: README_pt_PT.txt raises UnicodeDecodeError on UTF-8 at byte
# 0xE9 (the é of "José"), while LICENSES.txt decodes cleanly as UTF-8. Naming them separately
# is the only way a licence assertion can read the file it is asserting.
README_ENCODING = "iso8859-1"
LICENSES_ENCODING = "utf-8"
# Measured verbatim in pt_PT/README_pt_PT.txt at PINNED_COMMIT, decoded as latin-1. FOUR
# strings, because a tri-licence is not proved by one sentence: the grant plus each version.
LICENSE_SENTENCES: tuple[str, ...] = (
    "All dictionary files and associated programs are currently covered by "
    "the (GPL/LGPL/MPL), by this order.",
    "1. GPL Version 2",
    "2. LGPL Version 2.1",
    "3. MPL Version 1.1",
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ THE EDITION RULE, SOURCED AND PARTIAL. The Portuguese set is 120 tiles with THREE blanks,
# and its distribution note says: "While Ç is a separate tile, other diacritical marks are
# ignored." So ``ç`` is kept and every other mark folds.
# MEASURED at PINNED_COMMIT with hunspell 1.7.3:
#     4 321 825 unique expanded forms of playable shape
#     marked letters present: í 602 934 · á 505 997 · ã 108 132 · ó 61 062 · é 45 255 ·
#                             ê 26 672 · õ 21 575 · ú 15 492 · â 12 321 · ô 1 606 · î · à
#     4 119 831 unique forms after the rule, ZERO characters outside the tile faces remain,
#     and 137 997 words STILL CARRY a cedilla — which is what proves the fold stayed partial
# ⛔ A TOTAL fold would rewrite `coração` to `coracao`, which no Portuguese board can spell,
# and would destroy 137 997 playable words while every count-based gate stayed green.
KEEP_MARKED: frozenset[str] = frozenset({"ç"})

MIN_UNIQUE = 3_000_000
MAX_UNIQUE = 6_000_000

# Fail-closed post-condition. Six words, and TWO of them prove BOTH rules in a single token:
#   casa nada          plain words — the expansion ran
#   nao portugues      FOLD witnesses, from `não` and `português`
#   coraçao açao       DUAL witnesses, from `coração` and `ação`: the cedilla was KEPT and the
#                      tilde was FOLDED, in the same word. A total fold turns these into
#                      `coracao`/`acao` and the gate fails; a fold that never ran leaves
#                      `coração`/`ação` and the gate fails. Only the correct partial rule passes.
REQUIRED_WORDS: tuple[str, ...] = ("casa", "nada", "nao", "portugues", "coraçao", "açao")
FORBIDDEN_WORD = "qxqxqxqxq"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "portuguese.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "portuguese.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("pt_PT.dic", "9d90cfd9fb15312db71fbe46c11f871df67684dae7c218ab270142e7ae68c377"),
    ("pt_PT.aff", "975a209fcc892cb382fa5f34a28c391a39668661ce373ae071287809c5fcae24"),
    ("LICENSES.txt", "d2c1cfe2e2dd81c651aec3fda5d1b4b4e7679b9e04f8cdc37586e521837384d1"),
    ("README_pt_PT.txt", "36de7d88a406a4947bf646a64145f00827566808988632e3df969aa95776060c"),
    ("description.xml", "367cea11a1c4ccde5a5e0a37c8e6d8f7e0b0979e2721fa90e233ea2bc10e81fd"),
)

_LEXICON_HEADER = (
    "# Portuguese playable lexicon expanded from hunspell pt_PT "
    f"(LibreOffice dictionaries pt_PT @ {PINNED_COMMIT}).\n"
    "# The Portuguese edition has a separate C-cedilla TILE and ignores every other\n"
    "# diacritical mark, so:\n"
    "#   * c-cedilla is PRESERVED, because it has its own tile worth 3 points;\n"
    "#   * every other marked letter is folded to its base letter.\n"
    "# So this file lists playable TILE SEQUENCES: 'coracao' with a cedilla on the C and a\n"
    "# plain final 'ao' is here; neither the fully accented nor the fully plain spelling is.\n"
    "# European Portuguese (pt_PT). Brazilian Portuguese is a separate upstream pack.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Portuguese (pt_PT) dictionary pack version {PACK_VERSION}"

# ⛔ BOTH upstream documents are embedded, in this order, precisely BECAUSE they disagree about
# the licence. Shipping only the one this script relies on would hide the conflict.
_ATTRIBUTION = (
    "Portuguese lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries pt_PT at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file, preserving c-cedilla\n"
    "because it has its own tile, and folding every other marked letter; see the lexicon\n"
    "header for why.\n"
    "\n"
    "NOTE ON THE LICENCE: the two upstream documents below do not agree. README_pt_PT.txt\n"
    "states that all dictionary files are covered by GPL 2 / LGPL 2.1 / MPL 1.1 in that\n"
    "order; LICENSES.txt says, without versions, 'the GPL and BSD licence'. The SPDX\n"
    "expression above follows the README because it is the specific, versioned statement\n"
    "about the dictionary files themselves. BSD is deliberately not claimed. Both documents\n"
    "are reproduced in full so the conflict is visible rather than resolved silently.\n"
    "\n"
    "--- upstream README_pt_PT.txt ---\n"
    "\n"
)

_LICENSES_SECTION = "\n--- upstream LICENSES.txt ---\n\n"
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

    pt_PT.aff happens to declare it on line 1, but the scan is still the general one: comments
    and blank lines are skipped, because three of this script's siblings do not.
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
    """Every string in ``LICENSE_SENTENCES`` must be present in the README. All four.

    ⛔ Read as ISO8859-1. A UTF-8 read raises on the ``é`` of "José" before it can assert
    anything, which would look like a licence failure and be an encoding failure.
    """
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
    """Rewrite one form as the tile faces the Portuguese edition can place. PARTIAL by design.

    ``ç`` has its own tile and is kept; every other marked letter is decomposed and stripped.
    So ``coração`` becomes ``coraçao`` — cedilla kept, tilde folded — which is exactly what a
    Portuguese board can spell.

    ⛔ The per-character loop is the point, not an optimisation target: stripping marks from the
    whole word first would leave no way to tell a folded ``c`` from an original one.
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
    with raw_path.open(encoding=WORD_ENCODING, errors="strict") as handle:
        for line in handle:
            word = unicodedata.normalize("NFC", line.strip()).casefold()
            if not (word.isalpha() and len(word) >= 2):
                continue
            candidate = _to_tile_faces(word)
            if candidate != word:
                rewritten += 1
            if not (candidate.isalpha() and len(candidate) >= 2):
                continue
            unique.add(candidate)
    count = len(unique)
    cedillas = sum(1 for word in unique if any(mark in word for mark in KEEP_MARKED))
    print(f"unique_words={count} rewritten={rewritten} words_keeping_a_cedilla={cedillas}")
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if cedillas == 0:
        print(
            "ERROR not one finished word carries a cedilla. Measured at "
            f"{PINNED_COMMIT} there are 137 997, so zero means the fold became TOTAL and "
            "destroyed every ç — which is a 3-point tile in this edition.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    _require_word_gate(unique)
    return sorted(unique)


def _require_word_gate(words: set[str]) -> None:
    """Fail closed unless every required word survived and the forbidden one did not.

    ⛔ A POST-CONDITION of the build. ``coraçao`` and ``açao`` are in the required set because
    each fails under BOTH wrong rules: a total fold produces ``coracao``, and no fold at all
    leaves ``coração``. Only the correct partial rule yields the required form.
    """
    missing = [word for word in REQUIRED_WORDS if word not in words]
    if missing:
        print(
            f"ERROR required word(s) absent from the finished lexicon: {missing}. "
            "'nao' and 'portugues' prove the fold ran; 'coraçao' and 'açao' prove it stayed "
            "PARTIAL, since a total fold would spell them without the cedilla and no fold at "
            "all would leave the tilde — so which ones are missing says which rule failed.",
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


def _write_license(path: Path, readme: Path, licenses: Path) -> None:
    """⛔ Read the README as latin-1 and LICENSES.txt as UTF-8; write one UTF-8 asset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        readme.read_text(encoding=README_ENCODING)
        + _LICENSES_SECTION
        + licenses.read_text(encoding=LICENSES_ENCODING)
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
        default=Path("/tmp/libretiles-portuguese-lexicon"),
        help="Directory for pinned .dic/.aff/licence/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-portuguese-unmunch.stdout"),
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
    _require_affix_encoding(paths["pt_PT.aff"])
    _require_license_sentences(paths["README_pt_PT.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["pt_PT.dic"], paths["pt_PT.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["README_pt_PT.txt"], paths["LICENSES.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
