# -*- coding: utf-8 -*-
from datetime import timedelta

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from core.models import (
    DiaperChange,
    Feeding,
    Note,
    Sleep,
    TummyTime,
    Temperature,
    Medication,
)
from core.utils import duration_string

BREAST_METHODS = ("left breast", "right breast", "both breasts")


def _compact_duration(delta):
    """Short duration for the timeline's stat pill, e.g. "3h12m" or "45m"."""
    if delta is None:
        return None
    total = int(delta.total_seconds())
    if total < 0:
        return None
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return "%dh%dm" % (hours, minutes)
    if hours:
        return "%dh" % hours
    return "%dm" % minutes


def _amount_text(amount):
    """Format a feeding amount for the stat pill."""
    if not amount:
        return None
    value = round(float(amount), 2)
    if value == int(value):
        return "%d ml" % int(value)
    return ("%s ml" % value).rstrip("0").replace(".0 ", " ")


def _in_day(dt, min_date, max_date):
    """Whether a moment falls on the day being shown.

    Events are placed on the timeline of the day they actually happen, so an
    overnight sleep starting at 21:00 shows "fell asleep" on that day and
    "woke up" on the next one.
    """
    return min_date <= dt <= max_date


def get_summary(date, child=None):
    """
    Build a one-day totals summary for the timeline header.
    :param date: a DateTime instance for the day to be summarized.
    :param child: Child instance to filter results for (no filter if `None`).
    :returns: a dict with the day's breastfeeding duration, bottle-feeding
        amount, and wet / solid diaper counts.
    """
    min_date = date
    max_date = date.replace(hour=23, minute=59, second=59)

    feedings = Feeding.objects.filter(start__range=(min_date, max_date))
    diapers = DiaperChange.objects.filter(time__range=(min_date, max_date))
    if child:
        feedings = feedings.filter(child=child)
        diapers = diapers.filter(child=child)

    breast_total = (
        feedings.filter(method__in=BREAST_METHODS).aggregate(total=Sum("duration"))[
            "total"
        ]
        or timedelta()
    )
    # Milk total: bottles plus any amount recorded against a breast feed.
    bottle_amount = (
        feedings.filter(method__in=("bottle",) + BREAST_METHODS).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )

    return {
        "breastfeeding_duration": (
            duration_string(breast_total, "m") if breast_total else ""
        ),
        "bottle_amount": bottle_amount,
        "wet_count": diapers.filter(wet=True).count(),
        "solid_count": diapers.filter(solid=True).count(),
    }


def get_objects(date, child=None):
    """
    Create a time-sorted dictionary of all events for a child.
    :param date: a DateTime instance for the day to be summarized.
    :param child: Child instance to filter results for (no filter if `None`).
    :returns: a list of the day's events.
    """
    min_date = date
    max_date = date.replace(hour=23, minute=59, second=59)
    events = []

    _add_diaper_changes(min_date, max_date, events, child)
    _add_feedings(min_date, max_date, events, child)
    _add_medication(min_date, max_date, events, child)
    _add_sleeps(min_date, max_date, events, child)
    _add_tummy_times(min_date, max_date, events, child)
    _add_notes(min_date, max_date, events, child)
    _add_temperature_measurements(min_date, max_date, events, child)

    explicit_type_ordering = {"start": 0, "end": 1}
    events.sort(
        key=lambda x: (
            x["time"],
            explicit_type_ordering.get(x.get("type"), -1),
        ),
        reverse=True,
    )

    return events


def _add_tummy_times(min_date, max_date, events, child=None):
    instances = TummyTime.objects.filter(
        start__lte=max_date, end__gte=min_date
    ).order_by("-start")
    if child:
        instances = instances.filter(child=child)
    for instance in instances:
        details = []
        if instance.milestone:
            details.append(instance.milestone)
        edit_link = reverse("core:tummytime-update", args=[instance.id])
        if _in_day(instance.start, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.start),
                    "event": _("%(child)s started tummy time!")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "start",
                    "tags": instance.tags.all(),
                }
            )

        if _in_day(instance.end, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.end),
                    "event": _("%(child)s finished tummy time.")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "end",
                    "stat": _compact_duration(instance.duration),
                    "tags": instance.tags.all(),
                }
            )


def _add_sleeps(min_date, max_date, events, child=None):
    # Overlapping, not just starting: an overnight sleep belongs to both days,
    # contributing "fell asleep" to one and "woke up" to the next. Look back a
    # day so the first sleep has a previous wake to measure the window from.
    lookback = min_date - timedelta(days=1)
    instances = Sleep.objects.filter(start__lte=max_date, end__gte=lookback).order_by(
        "start"
    )
    if child:
        instances = instances.filter(child=child)
    # Keyed by child: the wake window is only meaningful within one child's
    # own stream, and the timeline can show every child at once.
    prev_ends = {}
    for instance in instances:
        prev_end = prev_ends.get(instance.child_id)
        wake_window = (
            _compact_duration(instance.start - prev_end)
            if prev_end and instance.start > prev_end
            else None
        )
        prev_ends[instance.child_id] = (
            max(prev_end, instance.end) if prev_end else instance.end
        )

        details = []
        if instance.notes:
            details.append(instance.notes)
        edit_link = reverse("core:sleep-update", args=[instance.id])
        if _in_day(instance.start, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.start),
                    "event": _("%(child)s fell asleep.")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "start",
                    "stat": wake_window,
                    "tags": instance.tags.all(),
                }
            )

        if _in_day(instance.end, min_date, max_date):
            events.append(
                {
                    "time": timezone.localtime(instance.end),
                    "event": _("%(child)s woke up.")
                    % {"child": instance.child.first_name},
                    "details": details,
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "end",
                    "stat": _compact_duration(instance.duration),
                    "tags": instance.tags.all(),
                }
            )


def _feeding_method_label(instance):
    """Return a human-readable label distinguishing the feeding method."""
    if instance.method in ("left breast", "right breast", "both breasts"):
        return _("Breast feed")
    if instance.method == "bottle":
        if instance.type == "breast milk":
            return _("Bottle (breast milk)")
        if instance.type == "formula":
            return _("Bottle (formula)")
    return instance.get_method_display()


def _add_feedings(min_date, max_date, events, child=None):
    # Look back a day so the first feeding shown has a previous one to measure
    # the gap from.
    lookback = min_date - timedelta(days=1)
    instances = Feeding.objects.filter(
        start__lte=max_date, end__gte=lookback
    ).order_by("start")
    if child:
        instances = instances.filter(child=child)
    # Keyed by child: the timeline can show every child at once, and the gap
    # since the last feeding is only meaningful within one child's own stream.
    prev_starts = {}
    for instance in instances:
        prev_start = prev_starts.get(instance.child_id)
        since_prev = (
            _compact_duration(instance.start - prev_start) if prev_start else None
        )
        prev_starts[instance.child_id] = instance.start

        details = [_feeding_method_label(instance)]
        if instance.notes:
            details.append(instance.notes)
        edit_link = reverse("core:feeding-update", args=[instance.id])

        base_object = {
            "time": timezone.localtime(instance.start),
            "details": details,
            "edit_link": edit_link,
            "model_name": instance.model_name,
            "tags": instance.tags.all(),
        }

        if instance.duration > timedelta(seconds=0):
            if _in_day(instance.start, min_date, max_date):
                events.append(
                    {
                        **base_object,
                        "event": _("%(child)s started feeding.")
                        % {"child": instance.child.first_name},
                        "type": "start",
                        "stat": since_prev,
                    }
                )
            if _in_day(instance.end, min_date, max_date):
                events.append(
                    {
                        **base_object,
                        "time": timezone.localtime(instance.end),
                        "event": _("%(child)s finished feeding.")
                        % {"child": instance.child.first_name},
                        "type": "end",
                        "stat": _amount_text(instance.amount),
                    }
                )
        elif _in_day(instance.start, min_date, max_date):
            events.append(
                {
                    **base_object,
                    "event": _("%(child)s had a feeding.")
                    % {"child": instance.child.first_name},
                    "stat": _amount_text(instance.amount) or since_prev,
                }
            )


def _add_diaper_changes(min_date, max_date, events, child):
    instances = DiaperChange.objects.filter(time__range=(min_date, max_date)).order_by(
        "-time"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances:
        contents = []
        if instance.wet:
            contents.append("💧")
        if instance.solid:
            contents.append("💩")
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s had a %(type)s diaper change.")
                % {
                    "child": instance.child.first_name,
                    "type": "".join(contents),
                },
                "edit_link": reverse("core:diaperchange-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.tags.all(),
            }
        )


def _add_medication(min_date, max_date, events, child):
    instances = Medication.objects.filter(time__range=(min_date, max_date)).order_by(
        "-time"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances:
        details = []
        if instance.notes:
            details.append(instance.notes)
        dosage = (
            str(instance.dosage) + " " + instance.get_dosage_unit_display()
            if instance.dosage
            else None
        )
        edit_link = reverse("core:medication-update", args=[instance.id])

        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s took %(medication)s.")
                % {
                    "child": instance.child.first_name,
                    "medication": instance.name,
                },
                "details": details,
                "edit_link": edit_link,
                "model_name": instance.model_name,
                "type": "start" if instance.next_dose_time else None,
                "stat": dosage,
                "tags": instance.tags.all(),
            }
        )
        if instance.next_dose_time:
            events.append(
                {
                    "time": timezone.localtime(instance.next_dose_time),
                    "event": _("%(child)s's %(medication)s dose wore off.")
                    % {
                        "child": instance.child.first_name,
                        "medication": instance.name,
                    },
                    "details": [],
                    "edit_link": edit_link,
                    "model_name": instance.model_name,
                    "type": "end",
                    "tags": instance.tags.all(),
                }
            )


def _add_notes(min_date, max_date, events, child):
    instances = Note.objects.filter(time__range=(min_date, max_date)).order_by("-time")
    if child:
        instances = instances.filter(child=child)
    for instance in instances:
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "details": [instance.note],
                "edit_link": reverse("core:note-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.tags.all(),
            }
        )


def _add_temperature_measurements(min_date, max_date, events, child):
    instances = Temperature.objects.filter(time__range=(min_date, max_date)).order_by(
        "-time"
    )
    if child:
        instances = instances.filter(child=child)
    for instance in instances:
        details = []
        if instance.notes:
            details.append(instance.notes)
        events.append(
            {
                "time": timezone.localtime(instance.time),
                "event": _("%(child)s had a temperature measurement.")
                % {
                    "child": instance.child.first_name,
                },
                "details": details,
                "stat": str(instance.temperature) if instance.temperature else None,
                "edit_link": reverse("core:temperature-update", args=[instance.id]),
                "model_name": instance.model_name,
                "tags": instance.tags.all(),
            }
        )
