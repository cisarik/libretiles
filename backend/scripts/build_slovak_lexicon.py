#!/usr/bin/env python3
"""Build the committed Slovak lexicon from pinned LibreOffice hunspell-sk sources.

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
    f"{PINNED_COMMIT}/sk_SK"
)
HUNSPELL_SK_VERSION = "2.4.8"
SPDX_EXPRESSION = "GPL-2.0-only OR LGPL-2.1-only OR MPL-1.1"
MIN_UNIQUE = 80_000
MAX_UNIQUE = 5_000_000

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DICT = _BACKEND_ROOT / "assets" / "dicts" / "slovak.txt"
_DEFAULT_LICENSE = _BACKEND_ROOT / "assets" / "dicts" / "slovak.LICENSE"

PINNED_FILES: tuple[tuple[str, str], ...] = (
    ("sk_SK.dic", "3e3dbd5c6af8431a3a47652c69692f3f86d0cd82deb4418e49a057a33ef56063"),
    ("sk_SK.aff", "af67bbe8ea9dea74968ec01acd266b3f74177ca087ee6eb7898c576e0aef7a3d"),
    ("LICENSE.txt", "dc06f891b13dcb6fe1ede36c0c9020f0e57e6777aca951ecaceefa95a19d7cfc"),
    ("README_en.txt", "a36af75654ae6e65614f7821b2c401ea1f3b4adfdcba9b59efcb1a06c96df14d"),
)

_LEXICON_HEADER = (
    "# Slovak playable lexicon expanded from hunspell-sk "
    f"(LibreOffice dictionaries sk_SK @ {PINNED_COMMIT}).\n"
    "# Not an official SSS tournament list.\n"
)

_ATTRIBUTION = (
    "Slovak lexicon for Libre Tiles\n"
    f"Source: LibreOffice dictionaries sk_SK at commit {PINNED_COMMIT}\n"
    f"hunspell-sk v{HUNSPELL_SK_VERSION}\n"
    f"SPDX-License-Identifier: {SPDX_EXPRESSION}\n"
    "\n"
    "--- upstream LICENSE.txt ---\n"
    "\n"
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _require_tri_license(readme_path: Path) -> None:
    text = readme_path.read_text(encoding="utf-8")
    has_gpl = "GPL" in text
    has_lgpl = "LGPL" in text or "Lesser General Public License" in text
    has_mpl = "MPL" in text
    if not (has_gpl and has_lgpl and has_mpl):
        print(
            "ERROR README_en.txt missing tri-license sentence "
            f"(GPL={has_gpl} LGPL={has_lgpl} MPL={has_mpl})",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _run_unmunch(unmunch_bin: str, dic_path: Path, aff_path: Path, raw_path: Path) -> int:
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
    with raw_path.open(encoding="utf-8", errors="strict") as handle:
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


def _write_license(path: Path, upstream_license: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = upstream_license.read_text(encoding="utf-8")
    path.write_text(_ATTRIBUTION + body, encoding="utf-8")
    print(f"wrote {path} bytes={path.stat().st_size}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/libretiles-slovak-lexicon"),
        help="Directory for pinned .dic/.aff/LICENSE/README downloads",
    )
    parser.add_argument(
        "--raw-out",
        type=Path,
        default=Path("/tmp/libretiles-slovak-unmunch.stdout"),
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
    _require_tri_license(paths["README_en.txt"])
    _run_unmunch(unmunch_bin, paths["sk_SK.dic"], paths["sk_SK.aff"], args.raw_out)
    words = _filter_words(args.raw_out)
    _write_lexicon(args.output_dict, words)
    _write_license(args.output_license, paths["LICENSE.txt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
