import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_medication"),
        ("dashboard", "0002_alter_pumppending_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="FeedPending",
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
                ("side", models.CharField(max_length=10)),
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
