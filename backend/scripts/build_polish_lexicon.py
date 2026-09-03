#!/usr/bin/env python3
"""Build the committed Polish lexicon from pinned LibreOffice hunspell-pl sources.

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
    f"{PINNED_COMMIT}/pl_PL"
)
# Established upstream, not copied from the committed asset: pl_PL/README_en.txt states
# "This version of the dictionary was generated on 2017-05-14" and points at
# http://www.sjp.pl/slownik/en/. ``_require_version_evidence`` asserts both halves.
UPSTREAM_GENERATED_ON = "2017-05-14"
UPSTREAM_SOURCE_HOST = "sjp.pl"
SPDX_EXPRESSION = "GPL-2.0-or-later OR LGPL-2.1-or-later OR MPL-1.1 OR Apache-2.0 OR CC-SA-1.0"
# ⛔ THE POLISH ENCODING TRAP, AND WHY THIS CONSTANT IS NAMED AND ASSERTED.
# ``unmunch`` emits bytes in the affix file's own encoding, and pl_PL.aff line 1 is
# ``SET ISO8859-2`` — NOT UTF-8 like cs_CZ and sk_SK. Every one of the 256 byte values is
# defined in ISO 8859-2, so a wrong encoding here cannot raise: it silently produces
# mojibake that a bounded prefix check may never see. Decode unmunch stdout as
# ISO 8859-2, then write the lexicon as UTF-8.
AFFIX_SET_LINE = b"SET ISO8859-2"
WORD_ENCODING = "iso8859-2"
# ⚠ The two upstream READMEs are UTF-8 even though the affix file is ISO 8859-2 (the
# maintainer's surname "Polaczyński" is UTF-8 in the raw bytes). Read them as UTF-8; the
# encoding above applies to unmunch output only.
README_ENCODING = "utf-8"
# Measured verbatim, hard-wrapped across pl_PL/README_en.txt lines 4-6 at PINNED_COMMIT.
LICENSE_SENTENCE = (
    "This dictionary for spell-checking Polish texts is licensed under GPL, LGPL, "
    "MPL (Mozilla Public License), Apache 2.0 and Creative Commons ShareAlike licenses"
)
MIN_UNIQUE = 80_000
MAX_UNIQUE = 5_000_000

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "polish.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "polish.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("pl_PL.dic", "215fd73aa47b11e7fdd2e4d655e9fe37be4acdae16ff833badcfdfce79110aad"),
    ("pl_PL.aff", "7c37b9bde78054e43365b488a13859094c88bc66664b5b7a7bb073626454b38e"),
    ("README_en.txt", "fb5f9b4a0643821cf88775c0932810c1cd05f236136c913e3eaf1e24806f3f44"),
    ("README_pl.txt", "ce3ad7ab1d3a8b767b8f7dcc870796fbda76bc7ad8cde22f6312b0cf86a5bd11"),
)

# ⛔ Polish says "Not an official tournament list." with NO national authority named, while
# build_slovak_lexicon.py says "Not an official SSS tournament list.". Slovak has a named
# authority and Polish does not. Do not normalize the two.
_LEXICON_HEADER = (
    "# Polish playable lexicon expanded from hunspell-pl "
    f"(LibreOffice dictionaries pl_PL @ {PINNED_COMMIT}).\n"
    "# Not an official tournament list.\n"
)

_VERSION_LINE = f"{UPSTREAM_SOURCE_HOST} / hunspell-pl generated {UPSTREAM_GENERATED_ON}"

# ⛔ pl_PL has NO LICENSE.txt — its licence text lives in the READMEs, which is why this
# block says ``--- upstream README_en.txt ---`` where build_slovak_lexicon.py:52 says
# ``--- upstream LICENSE.txt ---``. Do not "fix" that difference.
_ATTRIBUTION = (
    "Polish lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries pl_PL at commit {PINNED_COMMIT}\n"
    f"{_VERSION_LINE}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "--- upstream README_en.txt ---\n"
    "\n"
)

# Measured against the committed polish.LICENSE: BOTH upstream READMEs are embedded
# verbatim, separated by exactly these 33 bytes, and the file ends with ONE extra newline
# after the native README. Each of those three details is a byte of the oracle.
_NATIVE_README_SECTION = "\n--- upstream README_pl.txt ---\n\n"
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
    """⛔ Five licences, not three. Slovak's tri-licence assertion is the WRONG shape here."""
    text = _collapse_whitespace(readme_path.read_text(encoding=README_ENCODING))
    if LICENSE_SENTENCE not in text:
        print(
            f"ERROR {readme_path.name} no longer states the five-licence grant "
            f"{LICENSE_SENTENCE!r}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"licence sentence asserted: {LICENSE_SENTENCE}")


def _require_version_evidence(readme_path: Path) -> None:
    text = _collapse_whitespace(readme_path.read_text(encoding=README_ENCODING))
    needles = (f"generated on {UPSTREAM_GENERATED_ON}", UPSTREAM_SOURCE_HOST)
    missing = [needle for needle in needles if needle not in text]
    if missing:
        print(
            f"ERROR {readme_path.name} no longer evidences {missing}; the attribution "
            f"line {_VERSION_LINE!r} would be wrong",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"version line asserted upstream: {_VERSION_LINE}")


def _run_unmunch(unmunch_bin: str, dic_path: Path, aff_path: Path, raw_path: Path) -> int:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("wb") as stdout_file:
        proc = subprocess.run(
            [unmunch_bin, str(dic_path), str(aff_path)],
            stdout=stdout_file,
            stderr=subprocess.PIPE,
            check=False,
        )
    # ⚠ unmunch's own diagnostics are ISO 8859-2 here too, so decode them tolerantly:
    # a mojibake progress message must never mask a real nonzero exit.
    stderr_text = proc.stderr.decode(WORD_ENCODING, errors="replace")
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
        english_readme.read_text(encoding=README_ENCODING)
        + _NATIVE_README_SECTION
        + native_readme.read_text(encoding=README_ENCODING)
        + _LICENSE_TRAILER
    )
    path.write_text(_ATTRIBUTION + body, encoding="utf-8")
    print(f"wrote {path} bytes={path.stat().st_size}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/libretiles-polish-lexicon"),
        help="Directory for pinned .dic/.aff/README downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-polish-unmunch.stdout"),
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
    _require_affix_encoding(paths["pl_PL.aff"])
    _require_license_sentence(paths["README_en.txt"])
    _require_version_evidence(paths["README_en.txt"])
    _run_unmunch(unmunch_bin, paths["pl_PL.dic"], paths["pl_PL.aff"], args.raw_out)
    words = _filter_words(args.raw_out)
    _write_lexicon(args.output_dict, words)
    _write_license(args.output_license, paths["README_en.txt"], paths["README_pl.txt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
