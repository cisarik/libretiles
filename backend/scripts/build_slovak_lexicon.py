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


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, as a seam so a test can inspect it without running anything."""
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
    _require_tri_license(paths["README_en.txt"])
    _run_unmunch(unmunch_bin, paths["sk_SK.dic"], paths["sk_SK.aff"], raw_out)
    words = _filter_words(raw_out)
    _write_lexicon(output_dict, words)
    _write_license(output_license, paths["LICENSE.txt"])
    if args.check:
        return _compare_against_committed(
            ((output_dict, args.output_dict), (output_license, args.output_license))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
