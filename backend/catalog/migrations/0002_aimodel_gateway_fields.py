from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aimodel",
            name="provider",
            field=models.CharField(max_length=50),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="context_window",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="gateway_available",
            field=models.BooleanField(
                default=True,
                help_text="True when the model exists in the latest Vercel AI Gateway catalog sync.",
            ),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="gateway_managed",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, sync updates display name and description from Vercel AI Gateway.",
            ),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="max_tokens",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="model_type",
            field=models.CharField(blank=True, default="language", max_length=20),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="pricing",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="released_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="aimodel",
            name="tags",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
