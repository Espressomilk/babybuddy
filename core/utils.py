# -*- coding: utf-8 -*-
import datetime
import random

from django.utils import timezone
from django.utils.translation import ngettext

random.seed()

COLORS = [
    "#ff0000",
    "#00ff00",
    "#0000ff",
    "#ff00ff",
    "#ffff00",
    "#00ffff",
    "#ff7f7f",
    "#7fff7f",
    "#7f7fff",
    "#ff7fff",
    "#ffff7f",
    "#7fffff",
    "#7f0000",
    "#007f00",
    "#00007f",
    "#7f007f",
    "#7f7f00",
    "#007f7f",
]


def duration_string(duration, precision="s"):
    """Format hours, minutes and seconds as a human-friendly string (e.g. "2
    hours, 25 minutes, 31 seconds") with precision to h = hours, m = minutes or
    s = seconds.
    """
    h, m, s = duration_parts(duration)

    duration = ""
    if h > 0:
        duration = ngettext("%(hours)s hour", "%(hours)s hours", h) % {"hours": h}
    if m >= 0 and precision != "h":
        if duration != "":
            duration += ", "
        duration += ngettext("%(minutes)s minute", "%(minutes)s minutes", m) % {
            "minutes": m
        }
    if s > 0 and precision != "h" and precision != "m":
        if duration != "":
            duration += ", "
        duration += ngettext("%(seconds)s second", "%(seconds)s seconds", s) % {
            "seconds": s
        }

    return duration


def duration_parts(duration):
    """Get hours, minutes and seconds from a timedelta."""
    if not isinstance(duration, timezone.timedelta):
        raise TypeError("Duration provided must be a timedetla")
    h, remainder = divmod(duration.seconds, 3600)
    h += duration.days * 24
    m, s = divmod(remainder, 60)
    return h, m, s


def random_color():
    return COLORS[random.randrange(0, len(COLORS))]


def timezone_aware_duration(
    start: timezone.datetime, end: timezone.datetime
) -> datetime.timedelta:
    """
    Calculate a duration between timezone aware dates in UTC. This accounts for DST changes between dates.
    """
    utc = datetime.timezone.utc
    return end.astimezone(utc) - start.astimezone(utc)


# Maximum gap (end of one feeding to the start of the next) for two feedings to
# count as part of the same feeding session. This groups a "triple feeding"
# (breast feed + top-up bottle(s)) into a single session for frequency and
# interval statistics.
FEEDING_SESSION_GAP = datetime.timedelta(minutes=30)


def group_feeding_sessions(instances, gap=FEEDING_SESSION_GAP):
    """
    Group an ordered sequence of Feeding instances into feeding sessions.

    Consecutive feedings separated by less than ``gap`` (measured from the end
    of one feeding to the start of the next) are treated as a single session,
    so that e.g. a breast feed immediately followed by a top-up bottle counts
    as one feeding rather than several.

    :param instances: Feeding instances ordered by ``start``.
    :param gap: maximum end-to-start gap to merge into one session.
    :returns: a list of ``{"start", "end", "feedings"}`` dicts, one per session,
        where ``start`` is the first feeding's start, ``end`` is the latest end,
        and ``feedings`` is the list of member Feeding instances.
    """
    sessions = []
    for instance in instances:
        if sessions and (instance.start - sessions[-1]["end"]) < gap:
            sessions[-1]["feedings"].append(instance)
            if instance.end > sessions[-1]["end"]:
                sessions[-1]["end"] = instance.end
        else:
            sessions.append(
                {
                    "start": instance.start,
                    "end": instance.end,
                    "feedings": [instance],
                }
            )
    return sessions


# Feeding types that consume stored breast milk when given by bottle.
BREAST_MILK_BOTTLE_TYPES = ["breast milk", "fortified breast milk"]


def milk_stash_status(child):
    """
    Compute the current breast milk stash for a child.

    Balances start from the most recent ``MilkStashCalibration`` (or zero if
    none exists). Pumpings recorded since then add to the location stored to;
    bottle feedings of (fortified) breast milk since then draw from the fridge.

    The storage suggestion compares the fridge balance against the projected
    bottle breast-milk consumption for the next 24 hours (average of the past
    3 days): if the fridge already covers it, new milk should go to the
    freezer (fridge milk should be consumed within 24 hours).

    :returns: dict with ``fridge``, ``freezer`` (floats, ml, clamped at 0),
        ``needs_calibration`` (True when a computed balance went negative or
        no calibration exists yet), ``suggestion`` ("fridge"/"freezer"),
        ``daily_need`` (projected 24h bottle breast-milk consumption, ml) and
        ``calibrated_at`` (datetime or None).
    """
    from django.db.models import Sum

    from core import models

    calibration = (
        models.MilkStashCalibration.objects.filter(child=child)
        .order_by("-time")
        .first()
    )
    if calibration:
        fridge = calibration.fridge_amount
        freezer = calibration.freezer_amount
        since = calibration.time
    else:
        fridge = 0.0
        freezer = 0.0
        since = None

    pumpings = models.Pumping.objects.filter(child=child)
    feedings = models.Feeding.objects.filter(
        child=child, method="bottle", type__in=BREAST_MILK_BOTTLE_TYPES
    )
    if since:
        # Milk enters storage when the pumping session ends; anchor on end so
        # a session in progress while calibrating is still counted after.
        pumpings = pumpings.filter(end__gt=since)
        feedings = feedings.filter(start__gt=since)

    def _sum(queryset, field):
        return queryset.aggregate(total=Sum(field))["total"] or 0.0

    fridge += _sum(pumpings.filter(storage="fridge"), "amount")
    freezer += _sum(pumpings.filter(storage="freezer"), "amount")
    fridge -= _sum(feedings, "amount")

    needs_calibration = calibration is None or fridge < 0 or freezer < 0
    fridge = max(fridge, 0.0)
    freezer = max(freezer, 0.0)

    # Projected consumption for the next 24h: average daily bottle
    # breast-milk amount over the past 3 days.
    now = timezone.now()
    recent = models.Feeding.objects.filter(
        child=child,
        method="bottle",
        type__in=BREAST_MILK_BOTTLE_TYPES,
        start__gte=now - datetime.timedelta(days=3),
    )
    daily_need = _sum(recent, "amount") / 3.0

    # Fridge only when there is upcoming consumption it does not yet cover;
    # otherwise freezer (including when no bottle feeds happen at all, since
    # fridge milk would expire unused).
    suggestion = "fridge" if daily_need > 0 and fridge < daily_need else "freezer"

    return {
        "fridge": fridge,
        "freezer": freezer,
        "needs_calibration": needs_calibration,
        "suggestion": suggestion,
        "daily_need": daily_need,
        "calibrated_at": calibration.time if calibration else None,
    }
