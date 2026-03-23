from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="gamesession",
            name="current_turn_slot",
            field=models.IntegerField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="gamesession",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_messages", to="game.gamesession"),
                ),
                (
                    "user",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="game_chat_messages", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "db_table": "game_chat_message",
            },
        ),
    ]
