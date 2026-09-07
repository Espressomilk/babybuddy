from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("babybuddy", "0036_settings_bottle_amount_roller_step"),
    ]

    operations = [
        migrations.AddField(
            model_name="settings",
            name="dashboard_triple_feeding",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Show the last breast feed, bottle (breast milk) and bottle "
                    "(formula) separately on the Last Feeding card. When off, the "
                    "card shows only the most recent feeding."
                ),
                verbose_name="Triple feeding card",
            ),
        ),
    ]
