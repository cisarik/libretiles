from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditbalance",
            name="balance",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="amount",
            field=models.DecimalField(decimal_places=6, max_digits=12),
        ),
    ]
