from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0002_multiplayer_chat_and_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="gamesession",
            name="total_cost_usd",
            field=models.DecimalField(decimal_places=6, default=Decimal("0"), max_digits=12),
        ),
    ]
