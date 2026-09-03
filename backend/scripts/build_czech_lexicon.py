#!/usr/bin/env python3
"""Build the committed Czech lexicon from pinned LibreOffice hunspell-cs sources.

Not imported by Django. Host tool: /usr/bin/unmunch. No Poetry/npm dependency.
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
    f"{PINNED_COMMIT}/cs_CZ"
)
# Established upstream, not copied from the committed asset: cs_CZ/description.xml
# declares ``<version value="2021.07" />``. ``_require_pack_version`` asserts it, so a
# future pack bump fails loudly here instead of silently contradicting czech.LICENSE.
PACK_VERSION = "2021.07"
# ⛔ Czech is GPL ONLY. Do not copy the Slovak tri-licence assertion: sk_SK ships a
# GPL/LGPL/MPL grant, cs_CZ does not, and demanding LGPL or MPL here would always fail.
SPDX_EXPRESSION = "GPL-2.0-only"
# ⛔ ENCODING IS NAMED AND ASSERTED, NEVER DEFAULTED. ``unmunch`` emits bytes in the affix
# file's own encoding. cs_CZ.aff line 1 is ``SET UTF-8``; pl_PL.aff declares
# ``SET ISO8859-2``. A silent default is how that difference becomes mojibake in the next
# language, so ``_require_affix_encoding`` pins the declaration byte-for-byte.
AFFIX_SET_LINE = b"SET UTF-8"
WORD_ENCODING = "utf-8"
# Measured verbatim in cs_CZ/README_en.txt at PINNED_COMMIT (line 19).
LICENSE_SENTENCE = "This dictionary is licensed under the GNU/GPL license."
# ⛔ THE EXPANDER IS PINNED, AND A MISMATCH IS FATAL. ``unmunch`` prints no version of its
# own — measured, it prints only "correct syntax is: unmunch dic_file affix_file" — so the
# identity comes from ``hunspell -vv``, which prints
# "@(#) International Ispell Version 3.2.06 (but really Hunspell 1.7.3)".
# A different expander may expand the same affix file into a DIFFERENT word list, and this
# script writes a shipped asset, so ``_require_expander`` exits non-zero rather than warning.
# A warning on a tool that writes a shipped asset is the same as no check at all.
# ⛔ Keep this value IDENTICAL in all three build scripts; test P13 asserts exactly that.
EXPECTED_EXPANDER = "hunspell 1.7.3"
MIN_UNIQUE = 80_000
MAX_UNIQUE = 5_000_000

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_ROOT = _BACKEND_ROOT / "assets"
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "czech.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "czech.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("cs_CZ.dic", "d8e8c88c006fdae72dac8c85df11b0c99a773e05a4ab0fcbe92244876668ca74"),
    ("cs_CZ.aff", "7ecb20620ecd46ebd9c36f3f33e69dd4eda385cba5b2bb4e6bc396d910e297f7"),
    ("README_en.txt", "0fe6d017aa91ffb58146d19160f8207900cc0c49d5fffef0b1a7d3a364cb29bd"),
    ("README_cs.txt", "24d1d07409b62e8e6f0ee114991d4749d3e97b05ea19feca835916af67312720"),
    ("description.xml", "7d87b3603858558b8a288d72c9d1c5db416c7100d94f7ad597331bd50da5a675"),
)

# ⛔ Czech says "Not an official tournament list." with NO national authority named, while
# build_slovak_lexicon.py says "Not an official SSS tournament list.". Slovak has a named
# authority and Czech does not. Do not normalize the two.
_LEXICON_HEADER = (
    "# Czech playable lexicon expanded from hunspell-cs "
    f"(LibreOffice dictionaries cs_CZ @ {PINNED_COMMIT}).\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"LibreOffice Czech dictionary pack version {PACK_VERSION}"

# ⛔ cs_CZ has NO LICENSE.txt — its licence text lives in the READMEs, which is why this
# block says ``--- upstream README_en.txt ---`` where build_slovak_lexicon.py:52 says
# ``--- upstream LICENSE.txt ---``. Do not "fix" that difference.
_ATTRIBUTION = (
    "Czech lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries cs_CZ at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "--- upstream README_en.txt ---\n"
    "\n"
)

# Measured against the committed czech.LICENSE: BOTH upstream READMEs are embedded
# verbatim, separated by exactly these 33 bytes, and the file ends with ONE extra newline
# after the native README. Each of those three details is a byte of the oracle.
_NATIVE_README_SECTION = "\n--- upstream README_cs.txt ---\n\n"
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
    """The affix file must still declare the encoding this script decodes unmunch with."""
    with aff_path.open("rb") as handle:
        first_line = handle.readline().rstrip(b"\r\n")
    if first_line != AFFIX_SET_LINE:
        print(
            f"ERROR {aff_path.name} declares {first_line!r}, expected {AFFIX_SET_LINE!r}; "
            f"unmunch output would not be {WORD_ENCODING}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"affix encoding {AFFIX_SET_LINE.decode('ascii')} -> decode as {WORD_ENCODING}")


def _require_license_sentence(readme_path: Path) -> None:
    text = _collapse_whitespace(readme_path.read_text(encoding="utf-8"))
    if LICENSE_SENTENCE not in text:
        print(
            f"ERROR {readme_path.name} no longer states the GPL grant "
            f"{LICENSE_SENTENCE!r}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"licence sentence asserted: {LICENSE_SENTENCE}")


def _require_pack_version(description_path: Path) -> None:
    text = description_path.read_text(encoding="utf-8")
    needle = f'<version value="{PACK_VERSION}" />'
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
    unique: set[str] = set()
    with raw_path.open(encoding=WORD_ENCODING, errors="strict") as handle:
        for line in handle:
            word = unicodedata.normalize("NFC", line.strip()).casefold()
            if word.isalpha() and len(word) >= 2:
                unique.add(word)
    count = len(unique)
    print(f"unique_words={count}")
    if count < MIN_UNIQUE or count > MAX_UNIQUE:
        print(
            f"ERROR unique count {count} outside [{MIN_UNIQUE}, {MAX_UNIQUE}]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return sorted(unique)


def _write_lexicon(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_LEXICON_HEADER)
        handle.write("\n".join(words))
        handle.write("\n")
    print(f"wrote {path} lines={len(words)} bytes={path.stat().st_size}")


def _write_license(path: Path, english_readme: Path, native_readme: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        english_readme.read_text(encoding="utf-8")
        + _NATIVE_README_SECTION
        + native_readme.read_text(encoding="utf-8")
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
        default=Path("/tmp/libretiles-czech-lexicon"),
        help="Directory for pinned .dic/.aff/README/description downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-czech-unmunch.stdout"),
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
    _require_affix_encoding(paths["cs_CZ.aff"])
    _require_license_sentence(paths["README_en.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["cs_CZ.dic"], paths["cs_CZ.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["README_en.txt"], paths["README_cs.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
