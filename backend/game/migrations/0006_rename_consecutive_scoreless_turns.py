from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0005_remove_money_state"),
    ]

    operations = [
        migrations.RenameField(
            model_name="gamesession",
            old_name="consecutive_passes",
            new_name="consecutive_scoreless_turns",
        ),
    ]
