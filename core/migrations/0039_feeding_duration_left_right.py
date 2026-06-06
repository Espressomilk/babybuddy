# Generated for per-side breastfeeding duration tracking.
import datetime

from django.db import migrations, models


def backfill_sides(apps, schema_editor):
    """Populate per-side durations for existing breastfeeding entries.

    No per-side detail exists for historical data, so "both breasts" is split
    evenly; single-side methods attribute the whole duration to that side.
    """
    Feeding = apps.get_model("core", "Feeding")
    breast = Feeding.objects.filter(
        method__in=("left breast", "right breast", "both breasts")
    )
    for feeding in breast.iterator():
        if feeding.duration_left is not None or feeding.duration_right is not None:
            continue
        total = feeding.duration or datetime.timedelta()
        if feeding.method == "both breasts":
            half = total / 2
            feeding.duration_left = half
            feeding.duration_right = half
        elif feeding.method == "left breast":
            feeding.duration_left = total
            feeding.duration_right = datetime.timedelta()
        else:  # right breast
            feeding.duration_left = datetime.timedelta()
            feeding.duration_right = total
        feeding.save(update_fields=["duration_left", "duration_right"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_pumping_amount_left_amount_right"),
    ]

    operations = [
        migrations.AddField(
            model_name="feeding",
            name="duration_left",
            field=models.DurationField(
                blank=True, null=True, verbose_name="Left duration"
            ),
        ),
        migrations.AddField(
            model_name="feeding",
            name="duration_right",
            field=models.DurationField(
                blank=True, null=True, verbose_name="Right duration"
            ),
        ),
        migrations.RunPython(backfill_sides, noop),
    ]
