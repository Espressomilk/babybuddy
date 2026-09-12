import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_sleep_settling"),
        ("dashboard", "0003_feedpending"),
    ]

    operations = [
        migrations.CreateModel(
            name="SleepSettlingDraft",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("settling", models.CharField(max_length=255)),
                (
                    "timer",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="settling_draft",
                        to="core.timer",
                    ),
                ),
            ],
        ),
    ]
