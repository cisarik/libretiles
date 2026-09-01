from typing import Any

from django.db import migrations, models


_GAME_STATE_MODELS = (
    ("game", "ChatMessage"),
    ("game", "Move"),
    ("game", "PlayerSlot"),
    ("game", "GameSession"),
    ("game", "ConsumedWsTicket"),
)


def refuse_if_game_state_present(apps: Any, schema_editor: Any) -> None:
    """Refuse schema change while any of the five game-state tables has a row.

    This is a refusal, never a deletion. Reverse uses the same guard so
    reversing after games exist is blocked rather than silently corrupting
    new-shape data. The trailing RunPython below exists so Django's last-to-first
    reverse order still refuses *before* undoing schema operations.
    """
    nonempty: list[str] = []
    for app_label, model_name in _GAME_STATE_MODELS:
        model = apps.get_model(app_label, model_name)
        count = int(model.objects.count())
        if count:
            nonempty.append(f"{model._meta.db_table}={count}")
    if nonempty:
        raise RuntimeError(
            "Refusing atomic-token schema change while game-state tables are "
            "non-empty (" + ", ".join(nonempty) + "). "
            "Run manage.py purge_legacy_game_state first."
        )


def default_structured_board() -> list[list[None]]:
    return [[None] * 15 for _ in range(15)]


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0007_consumedwsticket"),
    ]

    operations = [
        migrations.RunPython(refuse_if_game_state_present, refuse_if_game_state_present),
        migrations.RemoveField(
            model_name="gamesession",
            name="blanks",
        ),
        migrations.RemoveField(
            model_name="gamesession",
            name="bag_tiles",
        ),
        migrations.AddField(
            model_name="gamesession",
            name="bag_tiles",
            field=models.JSONField(
                default=list,
                help_text="Ordered remaining tile tokens",
            ),
        ),
        migrations.AlterField(
            model_name="gamesession",
            name="board_state",
            field=models.JSONField(
                default=default_structured_board,
                help_text="15x15 structured cell grid: null or {token, blank_as}",
            ),
        ),
        # Same refusal as operation 1. On reverse this runs first, so a non-empty
        # database cannot reach the schema undo steps.
        migrations.RunPython(refuse_if_game_state_present, refuse_if_game_state_present),
    ]
