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
MIN_UNIQUE = 80_000
MAX_UNIQUE = 5_000_000

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
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


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    unmunch_bin = shutil.which(args.unmunch)
    if unmunch_bin is None:
        print(f"ERROR unmunch not found: {args.unmunch}", file=sys.stderr)
        return 1
    print(f"unmunch={unmunch_bin}")

    paths = _ensure_pinned_sources(args.cache_dir, refresh=args.refresh)
    _require_affix_encoding(paths["cs_CZ.aff"])
    _require_license_sentence(paths["README_en.txt"])
    _require_pack_version(paths["description.xml"])
    _run_unmunch(unmunch_bin, paths["cs_CZ.dic"], paths["cs_CZ.aff"], args.raw_out)
    words = _filter_words(args.raw_out)
    _write_lexicon(args.output_dict, words)
    _write_license(args.output_license, paths["README_en.txt"], paths["README_cs.txt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
