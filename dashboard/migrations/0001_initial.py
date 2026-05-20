import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0036_medication"),
    ]

    operations = [
        migrations.CreateModel(
            name="PumpPending",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("side", models.CharField(max_length=5)),
                ("start", models.DateTimeField()),
                ("end", models.DateTimeField()),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="core.child",
                    ),
                ),
            ],
            options={
                "ordering": ["start"],
            },
        ),
    ]
