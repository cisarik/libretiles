#!/usr/bin/env python3
"""Build the committed Italian lexicon from pinned LibreOffice hunspell it_IT sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.

⛔ LIKE build_afrikaans_lexicon.py AND FOR THE SAME SOURCED REASON, this script FOLDS
DIACRITICS at build time: the Italian edition bears plain Latin tiles and its distribution note
states that diacritic marks are ignored. Do NOT copy the fold into Slovak, Czech, Polish or a
future German — there an accented letter has its own tile and folding would delete playable
words. See ``_fold_diacritics``.
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
    f"{PINNED_COMMIT}/it_IT"
)
# Established upstream: it_IT/description.xml declares <version value="2020.11.07" />.
PACK_VERSION = "2020.11.07"
# ⛔ GPL 3, and -only rather than -or-later. README_it_IT.txt states "the terms and conditions
# of the GNU General Public License (GPL), version 3" and the embedded grant reads "under the
# terms of the GNU General Public License, version 3, as published by the Free Software
# Foundation" with NO "or (at your option) any later version" clause. Do not widen it.
SPDX_EXPRESSION = "GPL-3.0-only"
# ⛔ NOT a line-1 test: it_IT.aff opens with comments and its SET is line 39. The first SET
# directive is what governs unmunch's output encoding, so that is what is asserted.
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
# Measured verbatim in it_IT/README_it_IT.txt at PINNED_COMMIT. ⚠ "extensione" is upstream's
# own typo and is quoted EXACTLY. A tidied quotation would never match and the licence gate
# would fail on a correct file.
LICENSE_SENTENCE = (
    "The extensione is released under the terms and conditions of the "
    "GNU General Public License (GPL), version 3."
)
# ⛔ Keep IDENTICAL in every build script; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"

# ⛔ THE EDITION RULE, SOURCED. The Italian set is 120 tiles bearing plain Latin letters, and
# its distribution note says diacritic marks are ignored.
# MEASURED at PINNED_COMMIT with hunspell 1.7.3:
#     3 135 500 unique expanded forms of playable shape
#        34 114 of them (1.09%) carry a non a-z letter: ò 13414, é 10527, à 9333, ì 724,
#                è 58, ù 56, ç 1, â 1, ô 1
#     3 128 429 unique forms after folding, and ZERO non a-z letters remain
# Without folding, CITTA, PERCHE, SARA and PIU could never be played while `città`, `perché`,
# `sarà` and `più` sat unplayable in the lexicon.
FOLD_DIACRITICS = True

MIN_UNIQUE = 2_000_000
MAX_UNIQUE = 5_000_000

# Fail-closed post-condition. Three plain words prove the expansion ran; three FOLDED forms
# prove the fold ran. A gate of plain words only would pass if FOLD_DIACRITICS became a no-op.
REQUIRED_WORDS: tuple[str, ...] = ("casa", "libro", "acqua", "citta", "perche", "piu")
FORBIDDEN_WORD = "qxqxqxqxq"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "italian.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "italian.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("it_IT.dic", "bae1e3501dcd2a923669592493b3fde6c02aae7c7aab83bf5e5b49077e73dd64"),
    ("it_IT.aff", "951afaa19272f13555b8823e8bcf9ccf78f8fe1a07835bdfb912ab3e4d537c2b"),
    ("README_it_IT.txt", "34c3e93595cf3cf5f3afc9bc0d98eea12593750383f1e82ed1d3ca29f9681283"),
    ("description.xml", "b0013fc7ed461930d2aad43bcdd2761999936cd7ec949d6baa548484c5339891"),
)

# ⛔ No national authority is named for an Italian tournament list, so this header says
# "Not an official tournament list." with none named — like Czech and Afrikaans, and
# deliberately NOT like Slovak, which names SSS.
_LEXICON_HEADER = (
    "# Italian playable lexicon expanded from hunspell it_IT "
    f"(LibreOffice dictionaries it_IT @ {PINNED_COMMIT}).\n"
    "# Diacritics are FOLDED to their base letter, because the Italian Scrabble edition\n"
    "# bears plain Latin tiles only and ignores diacritic marks. So this file lists playable\n"
    "# TILE SEQUENCES, not Italian orthography: 'citta' is here, 'citta' with a grave accent\n"
    "# is not.\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Italian dictionary pack version {PACK_VERSION}"

# ⛔ it_IT's licence text lives INSIDE README_it_IT.txt, which embeds the full GPL 3 — so one
# embedded document, and the section marker names the README rather than a LICENSE.txt.
_ATTRIBUTION = (
    "Italian lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries it_IT at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "The word list is derived by expanding the upstream affix file and then folding\n"
    "diacritics to their base letters; see the lexicon header for why. The upstream\n"
    "README below carries the copyright statements and the full GPL 3 text.\n"
    "\n"
    "--- upstream README_it_IT.txt ---\n"
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

    ⛔ Deliberately NOT a line-1 test: it_IT.aff opens with a comment block and its
    ``SET UTF-8`` is line 39. Comments and blank lines are skipped.
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
            f"ERROR {readme_path.name} no longer states the GPL 3 grant {LICENSE_SENTENCE!r}",
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
    """Strip combining marks: ``città`` -> ``citta``, ``perché`` -> ``perche``.

    NFD splits a precomposed letter into base plus combining mark; dropping every ``Mn``
    (non-spacing mark) leaves the base. The caller re-normalizes to NFC, so the finished asset
    is NFC and ``validate_lexicons`` reports ``non_nfc=0``.

    ⚠ A TOTAL fold, correct only because every letter it touches is absent from the Italian
    tile set. A language with an accented TILE must never route through here.
    """
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _filter_words(raw_path: Path) -> list[str]:
    unique: set[str] = set()
    folded_count = 0
    # ⛔ errors="strict": it_IT.aff declares SET UTF-8 and _require_affix_encoding has already
    # asserted it, so any undecodable byte here means the pinned pair changed underneath us.
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

    ⛔ A POST-CONDITION of the build, not a test somebody may forget to run. Word COUNT and
    file SIZE cannot see a fold that stopped working; three folded witnesses can.
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
        default=Path("/tmp/libretiles-italian-lexicon"),
        help="Directory for pinned .dic/.aff/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-italian-unmunch.stdout"),
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
    _require_affix_encoding(paths["it_IT.aff"])
    _require_license_sentence(paths["README_it_IT.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["it_IT.dic"], paths["it_IT.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["README_it_IT.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
