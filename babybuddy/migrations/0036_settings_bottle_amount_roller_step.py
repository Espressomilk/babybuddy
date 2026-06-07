import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("babybuddy", "0035_alter_settings_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="settings",
            name="bottle_amount_roller_step",
            field=models.PositiveIntegerField(
                default=10,
                help_text=(
                    "The increment used by the amount wheel on the Save Bottle "
                    "Feeding page."
                ),
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Bottle amount step (ml)",
            ),
        ),
    ]
