import core.models
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0040_milk_stash"),
    ]

    operations = [
        migrations.CreateModel(
            name="Procedure",
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
                (
                    "name",
                    models.CharField(
                        max_length=255,
                        verbose_name="Procedure Name",
                    ),
                ),
                (
                    "date",
                    models.DateTimeField(
                        default=django.utils.timezone.localtime,
                        verbose_name="Date",
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, null=True, verbose_name="Notes"),
                ),
                (
                    "child",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="procedure",
                        to="core.child",
                        verbose_name="Child",
                    ),
                ),
                (
                    "tags",
                    core.models.TaggableManager(
                        blank=True,
                        help_text="A comma-separated list of tags.",
                        through="core.Tagged",
                        to="core.Tag",
                        verbose_name="Tags",
                    ),
                ),
            ],
            options={
                "verbose_name": "Procedure",
                "verbose_name_plural": "Procedures",
                "ordering": ["-date"],
                "default_permissions": ("view", "add", "change", "delete"),
            },
        ),
    ]
