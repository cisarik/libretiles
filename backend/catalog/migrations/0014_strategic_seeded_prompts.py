"""Refresh unmodified seeded AI prompt presets to strategic SEARCH_PROFILEs.

Forward updates ONLY seeded rows whose current text still matches the 0011
playable content (SHA-256 verified); an Admin-customized row is never
overwritten. Reverse restores the 0011 text for exactly the rows that forward
updated, so customized rows survive a full round trip untouched.
"""

import hashlib
import importlib

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_playable_0011 = importlib.import_module("catalog.migrations.0011_playable_seeded_prompts")

PRIOR_PROMPTS: dict[str, str] = _playable_0011.NEW_PROMPTS

NEW_PROMPTS: dict[str, str] = {
    "Initial": (
        "SEARCH PROFILE — Initial (balanced):\n"
        "Scan order: 1) check anchors adjacent to existing words and premium squares (TW/TL/DW), "
        "2) pick direction (ACROSS increases col, DOWN increases row), reuse existing board tiles without re-placing them, "
        "3) verify leave quality: keep a balanced mix of vowels and consonants, avoid duplicate tiles, and preserve blanks. "
        "With more than 7 bag tiles, play tighter defense when leading (+30); open lanes when trailing (-30). Validate your best candidate promptly."
    ),
    "Fast Search": (
        "SEARCH PROFILE — Fast Search (quick points):\n"
        "Find a high-scoring anchor quickly: target an anchor with an open span toward a premium square. "
        "Form a crisp, solid word using 3 to 5 rack tiles. Keep at least two vowels and two consonants for next turn. "
        "Avoid leaving Q, X, or lonely single vowels. Call validateMove immediately once found."
    ),
    "Short Hooks": (
        "SEARCH PROFILE — Short Hooks (extensions first):\n"
        "Inspect words already on the board: test prepending or appending 1 or 2 tiles to existing words (e.g. adding S, ED, ER, Y or language prefixes). "
        "Look for parallel plays that form multiple short cross-words simultaneously. "
        "Verify all perpendicular cross-words before playing. Count physical tiles carefully."
    ),
    "Grandmaster": (
        "SEARCH PROFILE — Grandmaster (strategic mastery):\n"
        "Master board control and leave equity: evaluate both turn score and opponent counter-threats. "
        "Leading by 30+ in midgame: close down open Triple Word (TW) lanes and reduce open anchors. "
        "Trailing by 30+: open explosive scoring lanes. In endgame (bag <= 7): track unseen tiles. "
        "When bag is empty: calculate exact out-play sequences to capture opponent leftover points."
    ),
}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def refresh_strategic_seeded_prompts(
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


def restore_0011_prompts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
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
        ("catalog", "0013_admin_provider_model_console"),
    ]

    operations = [
        migrations.RunPython(refresh_strategic_seeded_prompts, restore_0011_prompts),
    ]
