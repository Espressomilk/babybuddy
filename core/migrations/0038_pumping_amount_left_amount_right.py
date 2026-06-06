# Generated for per-side pumping amount tracking.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_vaccine"),
    ]

    operations = [
        migrations.AddField(
            model_name="pumping",
            name="amount_left",
            field=models.FloatField(
                blank=True, null=True, verbose_name="Left amount"
            ),
        ),
        migrations.AddField(
            model_name="pumping",
            name="amount_right",
            field=models.FloatField(
                blank=True, null=True, verbose_name="Right amount"
            ),
        ),
    ]
