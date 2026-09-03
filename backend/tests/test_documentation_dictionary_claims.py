"""Mechanical guard: the PRD must name the dictionary this product actually ships.

For the whole life of the project ``libretiles_PRD.md`` named SOWPODS as the Tier-1
dictionary while the shipped Tier-1 asset was ``backend/assets/dicts/collins2019.txt``, and
published a word count (``172,823``) that matched no file in the tree. No test read those
prose claims, so the documentation and the product drifted apart silently. These two
assertions are the mechanical part of that fix: correcting the prose alone would leave the
same hole open for the next reader to fall into.

Two scope boundaries, both deliberate:

* ``D2`` reads the variant MANIFEST, never ``settings.PRIMARY_DICTIONARY_PATH``. That setting
  is repointable through the ``PRIMARY_DICTIONARY_FILE`` environment variable, so binding
  this guard to it would make the result depend on an operator's ``.env``.
* ⛔ whether the manifest's ``entry_count`` equals the real surviving word count of the
  lexicon is NOT re-checked here. ``test_lexicon_provenance.py`` P4 already owns that rule,
  and one claim gets one semantic owner.

Offline and cheap: standard library only, no Django database, no network, no subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRD_PATH = _REPO_ROOT / "libretiles_PRD.md"
_ENGLISH_MANIFEST_PATH = _REPO_ROOT / "backend" / "assets" / "variants" / "english.json"

# The dictionary this product does not ship. Matched case-insensitively because every
# occurrence the PRD carried was uppercase, and a case-sensitive grep therefore returned
# ZERO hits and read as proof of absence.
_UNSHIPPED_DICTIONARY = "sowpods"


def test_d1_prd_never_names_a_dictionary_the_product_does_not_ship() -> None:
    """``libretiles_PRD.md`` carries no case-insensitive occurrence of ``sowpods``."""
    prd_text = _PRD_PATH.read_text(encoding="utf-8")
    matched_lines = [
        number
        for number, line in enumerate(prd_text.splitlines(), start=1)
        if _UNSHIPPED_DICTIONARY in line.casefold()
    ]
    assert _UNSHIPPED_DICTIONARY not in prd_text.casefold(), (
        f"libretiles_PRD.md names {_UNSHIPPED_DICTIONARY!r} (case-insensitive) on line(s) "
        f"{matched_lines}; the shipped Tier-1 dictionary is "
        f"backend/assets/dicts/collins2019.txt (Collins Scrabble Words 2019)"
    )


def test_d2_prd_word_count_equals_the_english_manifest_entry_count() -> None:
    """The English word count the PRD publishes is the one ``english.json`` declares."""
    manifest = json.loads(_ENGLISH_MANIFEST_PATH.read_text(encoding="utf-8"))
    entry_count = manifest["lexicon_provenance"]["entry_count"]

    # Checked BEFORE formatting: a null or boolean manifest value must fail loudly here
    # rather than turn into a degenerate needle that trivially appears in the document.
    assert isinstance(entry_count, int) and not isinstance(entry_count, bool), (
        f"english.json lexicon_provenance.entry_count must be an int, got "
        f"{entry_count!r} ({type(entry_count).__name__})"
    )
    assert entry_count > 0, (
        f"english.json lexicon_provenance.entry_count must be positive, got {entry_count!r}"
    )

    published = f"{entry_count:,}"
    prd_text = _PRD_PATH.read_text(encoding="utf-8")
    assert published in prd_text, (
        f"libretiles_PRD.md does not publish the English word count {published} declared by "
        f"backend/assets/variants/english.json"
    )
