"""Refresh unmodified seeded AI prompt presets to advisory SEARCH_PROFILEs.

Forward updates ONLY seeded rows whose current text still matches the 0010
refreshed content (SHA-256 verified); an Admin-customized row is never
overwritten. Reverse restores the 0010 text for exactly the rows that forward
updated, so customized rows survive a full round trip untouched.
"""

import hashlib
import importlib

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_refresh_0010 = importlib.import_module("catalog.migrations.0010_refresh_seeded_prompts")

PRIOR_PROMPTS: dict[str, str] = _refresh_0010.NEW_PROMPTS

NEW_PROMPTS: dict[str, str] = {
    "Initial": (
        "SEARCH PROFILE — Initial (balanced):\n"
        "Scan order every turn: 1) hook squares and endings on existing words, "
        "2) parallel plays beside existing words, 3) reachable bonus squares "
        "(TL/DL/DW/TW). Choose by score PLUS leave quality, never raw score alone. "
        "Prefer leaves without duplicate letters and near three vowels / four consonants. "
        "Shed Q or J early unless a play gains clearly more. Spend your only blank only "
        "for roughly 20+ extra points or to play most of your rack."
    ),
    "Fast Search": (
        "SEARCH PROFILE — Fast Search (quick points):\n"
        "Find one solid placement quickly: prefer the highest-scoring legal play that "
        "still keeps at least two common consonants and two vowels for next turn. "
        "Take obvious bonus-square extensions when visible; skip deep hook hunting. "
        "Avoid leaves containing Q, J, X, or a single lonely vowel."
    ),
    "Short Hooks": (
        "SEARCH PROFILE — Short Hooks (affixes first):\n"
        "Before building long words, test the ends of existing words: adding S, ED, "
        "ING, ER, Y after them and RE, UN, OUT, IN before them — every candidate must "
        "be validated. Favor hook squares where one new tile both changes an old word "
        "and helps your main word. Then seek parallel plays forming two or three short "
        "cross-words at once."
    ),
    "Grandmaster": (
        "SEARCH PROFILE — Grandmaster (stronger judgment):\n"
        "Use the Initial scan order, then refine: weight rack leave heavily — protect "
        "blanks and the first S, keep balanced mixes, shed Q/J and duplicates even at "
        "small cost. Clearly ahead late: also close open triple-word lanes cheaply. "
        "Behind late: keep lanes usable. Empty bag: favor high-tile-count plays that "
        "finish cleanly."
    ),
}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def refresh_playable_seeded_prompts(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    prompt_model = apps.get_model("catalog", "AIPrompt")
    for name, new_text in NEW_PROMPTS.items():
        row = prompt_model.objects.filter(name=name).first()
        if row is None:
            continue
        if _text_hash(row.prompt) != _text_hash(PRIOR_PROMPTS[name]):
            # Admin-customized or otherwise diverged: never overwrite.
            continue
        row.prompt = new_text
        row.save(update_fields=["prompt"])


def restore_0010_prompts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    prompt_model = apps.get_model("catalog", "AIPrompt")
    for name, new_text in NEW_PROMPTS.items():
        row = prompt_model.objects.filter(name=name).first()
        if row is None:
            continue
        if _text_hash(row.prompt) != _text_hash(new_text):
            # Not updated by forward (customized or drifted): leave untouched.
            continue
        row.prompt = PRIOR_PROMPTS[name]
        row.save(update_fields=["prompt"])


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_refresh_seeded_prompts"),
    ]

    operations = [
        migrations.RunPython(refresh_playable_seeded_prompts, restore_0010_prompts),
    ]
