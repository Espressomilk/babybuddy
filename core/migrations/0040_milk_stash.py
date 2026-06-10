import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0039_feeding_duration_left_right"),
    ]

    operations = [
        migrations.AddField(
            model_name="pumping",
            name="storage",
            field=models.CharField(
                blank=True,
                choices=[("fridge", "Fridge"), ("freezer", "Freezer")],
                default="",
                max_length=255,
                verbose_name="Storage",
            ),
        ),
        migrations.CreateModel(
            name="MilkStashCalibration",
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
                ("fridge_amount", models.FloatField(verbose_name="Fridge amount")),
                ("freezer_amount", models.FloatField(verbose_name="Freezer amount")),
                (
                    "time",
                    models.DateTimeField(
                        default=django.utils.timezone.localtime, verbose_name="Time"
                    ),
                ),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="milk_stash_calibrations",
                        to="core.child",
                        verbose_name="Child",
                    ),
                ),
            ],
            options={
                "verbose_name": "Milk Stash Calibration",
                "verbose_name_plural": "Milk Stash Calibrations",
                "ordering": ["-time"],
                "default_permissions": ("view", "add", "change", "delete"),
            },
        ),
    ]
