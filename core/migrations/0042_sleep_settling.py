from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0041_procedure"),
    ]

    operations = [
        migrations.AddField(
            model_name="sleep",
            name="settling",
            field=models.CharField(
                blank=True,
                choices=[
                    ("self_settled", "Self-settled"),
                    ("easy", "Settled easily"),
                    ("fussy", "Fussy"),
                    ("overtired", "Overtired, crying"),
                    ("wired", "Wired, not tired"),
                ],
                default="",
                max_length=255,
                verbose_name="Settling",
            ),
        ),
        migrations.AddField(
            model_name="sleep",
            name="suggested_start",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                null=True,
                verbose_name="Suggested start time",
            ),
        ),
    ]
