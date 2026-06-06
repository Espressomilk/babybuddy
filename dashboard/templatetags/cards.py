# -*- coding: utf-8 -*-
from django import template
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext as _

import collections

from core import models
from core.utils import duration_string, group_feeding_sessions

register = template.Library()


def _hide_empty(context):
    return context["request"].user.settings.dashboard_hide_empty


def _filter_data_age(context, keyword="end"):
    filter = {}
    if context["request"].user.settings.dashboard_hide_age:
        now = timezone.localtime()
        start_time = now - context["request"].user.settings.dashboard_hide_age
        filter[keyword + "__range"] = (start_time, now)
    return filter


@register.inclusion_tag("cards/diaperchange_last.html", takes_context=True)
def card_diaperchange_last(context, child):
    """
    Information about the most recent diaper change.
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Diaper Change instance.
    """
    instance = (
        models.DiaperChange.objects.filter(child=child)
        .filter(**_filter_data_age(context, "time"))
        .order_by("-time")
        .first()
    )
    empty = not instance

    return {
        "type": "diaperchange",
        "change": instance,
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/diaperchange_types.html", takes_context=True)
def card_diaperchange_types(context, child, date=None):
    """
    Creates a break down of wet and solid Diaper Change instances for the past
    seven days.
    :param child: an instance of the Child model.
    :param date: a datetime object for the day to filter.
    :returns: a dictionary with the wet/solid/empty statistics.
    """
    if not date:
        date = timezone.localtime()
    else:
        date = timezone.datetime.combine(date, timezone.localtime().min.time())
        date = timezone.make_aware(date)
    max_date = (date + timezone.timedelta(days=1)).replace(hour=0, minute=0, second=0)
    min_date = (max_date - timezone.timedelta(days=7)).replace(
        hour=0, minute=0, second=0
    )

    stats = {}
    for x in range(7):
        stats[x] = {"wet": 0.0, "solid": 0.0, "empty": 0.0, "changes": 0.0}

    instances = (
        models.DiaperChange.objects.filter(child=child)
        .filter(time__gt=min_date)
        .filter(time__lt=max_date)
        .order_by("-time")
    )
    empty = len(instances) == 0

    for instance in instances:
        key = (max_date - timezone.localtime(instance.time)).days
        stats[key]["changes"] += 1
        if instance.wet:
            stats[key]["wet"] += 1
        if instance.solid:
            stats[key]["solid"] += 1
        if not instance.wet and not instance.solid:
            stats[key]["empty"] += 1

    week_total = 0
    for key, info in stats.items():
        total = info["wet"] + info["solid"] + info["empty"]
        week_total += total
        if total > 0:
            stats[key]["wet_pct"] = info["wet"] / total * 100
            stats[key]["solid_pct"] = info["solid"] / total * 100
            stats[key]["empty_pct"] = info["empty"] / total * 100

    return {
        "type": "diaperchange",
        "stats": stats,
        "total": week_total,
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/breastfeeding.html", takes_context=True)
def card_breastfeeding(context, child, date=None):
    """
    Creates a break down of breasts used for breastfeeding, for the past
    seven days.
    :param child: an instance of the Child model.
    :param date: a datetime object for the day to filter.
    :returns: a dictionary with the statistics.
    """
    if date:
        date = timezone.datetime.combine(date, timezone.localtime().min.time())
        date = timezone.make_aware(date)
    else:
        date = timezone.localtime()

    max_date = (date + timezone.timedelta(days=1)).replace(hour=0, minute=0, second=0)
    min_date = (max_date - timezone.timedelta(days=7)).replace(
        hour=0, minute=0, second=0
    )

    instances = (
        models.Feeding.objects.filter(child=child)
        .filter(start__gt=min_date)
        .filter(start__lt=max_date)
        .filter(method__in=("left breast", "right breast", "both breasts"))
        .order_by("-start")
    )

    # Create a `stats` dictionary, keyed by day for the past 7 days.
    stats = {}
    for x in range(7):
        stats[x] = {}

    # Group feedings per day.
    per_day = collections.defaultdict(list)
    for instance in instances:
        key = (max_date - timezone.localtime(instance.start)).days
        per_day[key].append(instance)

    # Go through each day, set the stats dictionary for that day.
    for key, day_instances in per_day.items():
        left_count = 0
        right_count = 0
        left_duration = timezone.timedelta()
        right_duration = timezone.timedelta()
        for instance in day_instances:
            duration = instance.duration or timezone.timedelta()
            if instance.method == "both breasts":
                left_count += 1
                right_count += 1
            elif instance.method == "left breast":
                left_count += 1
            elif instance.method == "right breast":
                right_count += 1

            if (
                instance.duration_left is not None
                or instance.duration_right is not None
            ):
                # Stored per-side durations (exact for newer entries, even-split
                # backfill for older ones).
                left_duration += instance.duration_left or timezone.timedelta()
                right_duration += instance.duration_right or timezone.timedelta()
            elif instance.method == "both breasts":
                # Defensive fallback: split evenly when no per-side data exists.
                half = duration / 2
                left_duration += half
                right_duration += half
            elif instance.method == "left breast":
                left_duration += duration
            elif instance.method == "right breast":
                right_duration += duration

        left_secs = left_duration.total_seconds()
        right_secs = right_duration.total_seconds()
        total_secs = left_secs + right_secs
        if total_secs > 0:
            left_pct = round(100 * left_secs / total_secs)
            right_pct = 100 - left_pct
        else:
            # Fall back to count proportions when all durations are zero.
            total_count = left_count + right_count
            left_pct = (100 * left_count // total_count) if total_count else 50
            right_pct = 100 - left_pct

        stats[key] = {
            "count": len(day_instances),
            "duration": sum(
                (instance.duration for instance in day_instances),
                start=timezone.timedelta(),
            ),
            "left_count": left_count,
            "right_count": right_count,
            "left_duration": left_duration,
            "right_duration": right_duration,
            "left_pct": left_pct,
            "right_pct": right_pct,
        }

    return {
        "type": "feeding",
        "stats": stats,
        "total": len(instances),
        "empty": len(instances) == 0,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/feeding_recent.html", takes_context=True)
def card_feeding_recent(context, child, end_date=None):
    """
    Filters Feeding instances for a specific date and the 7 days before, broken
    down per day by the three "triple feeding" methods:
      - Breast feed: total duration and count.
      - Bottle (breast milk): total amount and count.
      - Bottle (formula): total amount and count.
    :param child: an instance of the Child model.
    :param end_date: a Date object for the day to filter.
    :returns: a dict with per-day, per-method totals and counts.
    """
    if not end_date:
        end_date = timezone.localtime()

    # push end_date to very end of that day
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=9999)
    # we need a datetime to use the range helper in the model
    start_date = end_date - timezone.timedelta(
        days=8
    )  # end of the -8th day so we get the FULL 7th day

    instances = models.Feeding.objects.filter(child=child).filter(
        start__range=[start_date, end_date]
    )

    def _new_methods():
        return [
            {
                "label": _("Breast feed"),
                "metric": "duration",
                "total": timezone.timedelta(),
                "count": 0,
            },
            {
                "label": _("Bottle (breast milk)"),
                "metric": "amount",
                "total": 0,
                "count": 0,
            },
            {
                "label": _("Bottle (formula)"),
                "metric": "amount",
                "total": 0,
                "count": 0,
            },
        ]

    # prepare the result list for the last 7 days
    dates = [end_date - timezone.timedelta(days=i) for i in range(8)]
    results = [
        {"date": d, "methods": _new_methods(), "count": 0} for d in dates
    ]

    # do one pass over the data and add it to the appropriate day
    for instance in instances:
        # convert to local tz and push feed_date to end so we're comparing apples to apples for the date
        feed_date = timezone.localtime(instance.end).replace(
            hour=23, minute=59, second=59, microsecond=9999
        )
        idx = (end_date - feed_date).days
        if idx < 0 or idx >= len(results):
            continue
        methods = results[idx]["methods"]
        if instance.method in ("left breast", "right breast", "both breasts"):
            methods[0]["total"] += instance.duration
            methods[0]["count"] += 1
        elif instance.method == "bottle" and instance.type == "breast milk":
            methods[1]["total"] += instance.amount or 0
            methods[1]["count"] += 1
        elif instance.method == "bottle" and instance.type == "formula":
            methods[2]["total"] += instance.amount or 0
            methods[2]["count"] += 1
        results[idx]["count"] += 1

    return {
        "feedings": results,
        "type": "feeding",
        "empty": len(instances) == 0,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/feeding_last.html", takes_context=True)
def card_feeding_last(context, child):
    """
    Information about the most recent feeding, broken down by the three methods
    used for "triple feeding": breast feed, bottle (breast milk) and bottle
    (formula).
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Feeding instances per method.
    """
    feedings = models.Feeding.objects.filter(child=child).filter(
        **_filter_data_age(context)
    )

    last_breast = (
        feedings.filter(
            method__in=("left breast", "right breast", "both breasts")
        )
        .order_by("-end")
        .first()
    )
    last_bottle_breast_milk = (
        feedings.filter(method="bottle", type="breast milk").order_by("-end").first()
    )
    last_bottle_formula = (
        feedings.filter(method="bottle", type="formula").order_by("-end").first()
    )

    triple = [
        {"label": _("Breast feed"), "feeding": last_breast},
        {"label": _("Bottle (breast milk)"), "feeding": last_bottle_breast_milk},
        {"label": _("Bottle (formula)"), "feeding": last_bottle_formula},
    ]

    # Retained for backwards compatibility (overall most recent feeding).
    instance = feedings.order_by("-end").first()
    empty = not instance

    return {
        "type": "feeding",
        "feeding": instance,
        "triple": triple,
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/feeding_last_method.html", takes_context=True)
def card_feeding_last_method(context, child):
    """
    Information about the three most recent feeding methods.
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Feeding instances.
    """
    instances = (
        models.Feeding.objects.filter(child=child)
        .filter(**_filter_data_age(context))
        .order_by("-end")[:3]
    )
    num_unique_methods = len({i.method for i in instances})
    empty = num_unique_methods <= 1

    # Results are reversed for carousel forward/back behavior.
    return {
        "type": "feeding",
        "feedings": list(reversed(instances)),
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/pumping_last.html", takes_context=True)
def card_pumping_last(context, child):
    """
    Information about the most recent pumping.
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Pumping instance.
    """
    instance = (
        models.Pumping.objects.filter(child=child)
        .filter(**_filter_data_age(context))
        .order_by("-end")
        .first()
    )
    empty = not instance

    return {
        "type": "pumping",
        "pumping": instance,
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/pumping_recent.html", takes_context=True)
def card_pumping_recent(context, child, end_date=None):
    """
    Filters Pumping instances to get total amount for a specific date and for 7 days before.
    :param child: an instance of the Child model.
    :param end_date: a Date object for the day to filter.
    :returns: a dict with count and total amount for the Pumping instances.
    """
    if not end_date:
        end_date = timezone.localtime()

    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=9999)
    start_date = end_date - timezone.timedelta(days=8)

    instances = models.Pumping.objects.filter(child=child).filter(
        start__range=[start_date, end_date]
    )

    dates = [end_date - timezone.timedelta(days=i) for i in range(8)]
    results = [{"date": d, "total": 0, "count": 0} for d in dates]

    for instance in instances:
        pump_date = timezone.localtime(instance.end).replace(
            hour=23, minute=59, second=59, microsecond=9999
        )
        idx = (end_date - pump_date).days
        result = results[idx]
        result["total"] += instance.amount if instance.amount is not None else 0
        result["count"] += 1

    return {
        "pumpings": results,
        "type": "pumping",
        "empty": len(instances) == 0,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/sleep_last.html", takes_context=True)
def card_sleep_last(context, child):
    """
    Information about the most recent sleep entry.
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Sleep instance.
    """
    instance = (
        models.Sleep.objects.filter(child=child)
        .filter(**_filter_data_age(context))
        .order_by("-end")
        .first()
    )
    empty = not instance

    return {
        "type": "sleep",
        "sleep": instance,
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/sleep_recent.html", takes_context=True)
def card_sleep_recent(context, child, end_date=None):
    """
    Filters sleeping instances to get total amount for a specific date and for 7 days before
    :param child: an instance of the Child model.
    :param end_date: a Date object for the day to filter.
    :returns: a dict with count and total amount for the sleeping instances.
    """
    if not end_date:
        end_date = timezone.localtime()

    # push end_date to very end of that day
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=9999)
    # we need a datetime to use the range helper in the model
    start_date = end_date - timezone.timedelta(
        days=8
    )  # end of the -8th day so we get the FULL 7th day

    instances = models.Sleep.objects.filter(child=child).filter(
        start__range=[start_date, end_date]
    ) | models.Sleep.objects.filter(child=child).filter(
        end__range=[start_date, end_date]
    )

    # prepare the result list for the last 7 days
    dates = [end_date - timezone.timedelta(days=i) for i in range(8)]
    results = [{"date": d, "total": timezone.timedelta(), "count": 0} for d in dates]

    # do one pass over the data and add it to the appropriate day
    for instance in instances:
        # convert to local tz and push feed_date to end so we're comparing apples to apples for the date
        start = timezone.localtime(instance.start)
        end = timezone.localtime(instance.end)
        sleep_start_date = start.replace(
            hour=23, minute=59, second=59, microsecond=9999
        )
        sleep_end_date = end.replace(hour=23, minute=59, second=59, microsecond=9999)
        start_idx = (end_date - sleep_start_date).days
        end_idx = (end_date - sleep_end_date).days
        # this is more complicated than feedings because we only want to capture the PORTION of sleep
        # that is a part of this day (e.g. starts sleep at 7PM and finished at 7AM = 5 hrs yesterday 7 hrs today)
        # (Assuming you have a unicorn sleeper. Congratulations)
        if start_idx == end_idx:  # if we're in the same day it's simple
            result = results[start_idx]
            result["total"] += end - start
            result["count"] += 1
        else:  # otherwise we need to split the time up
            midnight = end.replace(hour=0, minute=0, second=0)

            if 0 <= start_idx < len(results):
                result = results[start_idx]
                # only the portion that is today
                result["total"] += midnight - start
                result["count"] += 1

            if 0 <= end_idx < len(results):
                result = results[end_idx]
                # only the portion that is tomorrow
                result["total"] += end - midnight
                result["count"] += 1

    return {
        "sleeps": results,
        "type": "sleep",
        "empty": len(instances) == 0,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/sleep_naps_day.html", takes_context=True)
def card_sleep_naps_day(context, child, date=None):
    """
    Filters Sleep instances categorized as naps and generates statistics for a
    specific date.
    :param child: an instance of the Child model.
    :param date: a Date object for the day to filter.
    :returns: a dictionary of nap data statistics.
    """
    if not date:
        date = timezone.localtime().date()
    instances = models.Sleep.objects.filter(child=child, nap=True).filter(
        start__year=date.year, start__month=date.month, start__day=date.day
    ) | models.Sleep.objects.filter(child=child, nap=True).filter(
        end__year=date.year, end__month=date.month, end__day=date.day
    )
    empty = len(instances) == 0

    return {
        "type": "sleep",
        "total": instances.aggregate(Sum("duration"))["duration__sum"],
        "count": len(instances),
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/statistics.html", takes_context=True)
def card_statistics(context, child):
    """
    Statistics data for all models.
    :param child: an instance of the Child model.
    :returns: a list of dictionaries with "type", "stat" and "title" entries.
    """
    stats = []

    changes = _diaperchange_statistics(child)
    if changes:
        for item in changes:
            stats.append(
                {
                    "type": "duration",
                    "stat": item["btwn_average"],
                    "title": item["title"],
                }
            )

    feedings = _feeding_statistics(child)
    if feedings:
        for item in feedings:
            stats.append(
                {
                    "type": "duration",
                    "stat": item["btwn_average"],
                    "title": item["title"],
                }
            )

    for item in _feeding_amount_statistics(child):
        stats.append(item)

    naps = _nap_statistics(child)
    if naps:
        stats.append(
            {
                "type": "duration",
                "stat": naps["average"],
                "title": _("Average nap duration"),
            }
        )
        stats.append(
            {
                "type": "float",
                "stat": naps["avg_per_day"],
                "title": _("Average naps per day"),
            }
        )

    sleep = _sleep_statistics(child)
    if sleep:
        stats.append(
            {
                "type": "duration",
                "stat": sleep["average"],
                "title": _("Average sleep duration"),
            }
        )
        stats.append(
            {
                "type": "duration",
                "stat": sleep["btwn_average"],
                "title": _("Average awake duration"),
            }
        )

    weight = _weight_statistics(child)
    if weight:
        stats.append(
            {
                "type": "float",
                "stat": weight["change_weekly"],
                "title": _("Weight change per week"),
            }
        )

    height = _height_statistics(child)
    if height:
        stats.append(
            {
                "type": "float",
                "stat": height["change_weekly"],
                "title": _("Height change per week"),
            }
        )

    head_circumference = _head_circumference_statistics(child)
    if head_circumference:
        stats.append(
            {
                "type": "float",
                "stat": head_circumference["change_weekly"],
                "title": _("Head circumference change per week"),
            }
        )

    bmi = _bmi_statistics(child)
    if bmi:
        stats.append(
            {
                "type": "float",
                "stat": bmi["change_weekly"],
                "title": _("BMI change per week"),
            }
        )

    empty = len(stats) == 0

    return {"stats": stats, "empty": empty, "hide_empty": _hide_empty(context)}


def _diaperchange_statistics(child):
    """
    Averaged Diaper Change data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    changes = [
        {
            "start": timezone.localtime() - timezone.timedelta(days=3),
            "title": _("Diaper change frequency (past 3 days)"),
        },
        {
            "start": timezone.localtime() - timezone.timedelta(weeks=2),
            "title": _("Diaper change frequency (past 2 weeks)"),
        },
        {
            "start": None,
            "title": _("Diaper change frequency"),
        },
    ]
    for timespan in changes:
        timespan["btwn_total"] = timezone.timedelta(0)
        timespan["btwn_count"] = 0
        timespan["btwn_average"] = 0.0

    instances = models.DiaperChange.objects.filter(child=child).order_by("time")
    if len(instances) == 0:
        return False
    last_instance = None

    for instance in instances:
        if last_instance:
            for timespan in changes:
                last_time = timezone.localtime(last_instance.time)
                if timespan["start"] is None or last_time > timespan["start"]:
                    timespan["btwn_total"] += (
                        timezone.localtime(instance.time) - last_time
                    )
                    timespan["btwn_count"] += 1
        last_instance = instance

    for timespan in changes:
        if timespan["btwn_count"] > 0:
            timespan["btwn_average"] = timespan["btwn_total"] / timespan["btwn_count"]
    return changes


def _feeding_statistics(child):
    """
    Averaged Feeding data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    feedings = [
        {
            "start": timezone.localtime() - timezone.timedelta(days=3),
            "title": _("Feeding frequency (past 3 days)"),
        },
        {
            "start": timezone.localtime() - timezone.timedelta(weeks=2),
            "title": _("Feeding frequency (past 2 weeks)"),
        },
        {
            "start": None,
            "title": _("Feeding frequency"),
        },
    ]
    for timespan in feedings:
        timespan["btwn_total"] = timezone.timedelta(0)
        timespan["btwn_count"] = 0
        timespan["btwn_average"] = 0.0

    instances = models.Feeding.objects.filter(child=child).order_by("start")
    # Group consecutive feedings (e.g. a breast feed + top-up bottles) into
    # single feeding sessions so "frequency" reflects how often the baby feeds,
    # not how many sources each feeding used.
    sessions = group_feeding_sessions(instances)
    if len(sessions) == 0:
        return False
    last_session = None

    for session in sessions:
        if last_session:
            for timespan in feedings:
                start = timezone.localtime(session["start"])
                last_start = timezone.localtime(last_session["start"])
                last_end = timezone.localtime(last_session["end"])
                if timespan["start"] is None or last_start > timespan["start"]:
                    timespan["btwn_total"] += start - last_end
                    timespan["btwn_count"] += 1
        last_session = session

    for timespan in feedings:
        if timespan["btwn_count"] > 0:
            timespan["btwn_average"] = timespan["btwn_total"] / timespan["btwn_count"]
    return feedings


def _format_amount(value):
    """Format a feeding amount, dropping a trailing ``.0``."""
    value = round(value, 1)
    if value == int(value):
        return str(int(value))
    return "{:.1f}".format(value)


def _feeding_amount_statistics(child):
    """
    Average per-session feeding amounts: breastfeeding duration and bottle
    amount (all milk types), for yesterday / past 3 days / past 2 weeks.

    Feedings are grouped into sessions (a breast feed plus any top-up bottles
    counts as one session); each window's value is the per-session average
    across all sessions whose start falls in the window.

    :param child: an instance of the Child model.
    :returns: a list of {"type", "stat", "title"} dicts for the statistics card.
    """
    breast_methods = ("left breast", "right breast", "both breasts")
    now = timezone.localtime()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = [
        {
            "title": _("Feeding per session (yesterday)"),
            "start": today - timezone.timedelta(days=1),
            "end": today,
        },
        {
            "title": _("Feeding per session (past 3 days)"),
            "start": now - timezone.timedelta(days=3),
            "end": None,
        },
        {
            "title": _("Feeding per session (past 2 weeks)"),
            "start": now - timezone.timedelta(weeks=2),
            "end": None,
        },
    ]

    instances = models.Feeding.objects.filter(child=child).order_by("start")
    if len(instances) == 0:
        return []
    sessions = group_feeding_sessions(instances)

    results = []
    for window in windows:
        selected = []
        for session in sessions:
            start = timezone.localtime(session["start"])
            if start < window["start"]:
                continue
            if window["end"] is not None and start >= window["end"]:
                continue
            selected.append(session)
        if not selected:
            continue

        count = len(selected)
        breast_total = timezone.timedelta()
        bottle_total = 0.0
        for session in selected:
            for feeding in session["feedings"]:
                if feeding.method in breast_methods:
                    breast_total += (feeding.duration_left or timezone.timedelta())
                    breast_total += (feeding.duration_right or timezone.timedelta())
                elif feeding.method == "bottle":
                    bottle_total += feeding.amount or 0

        breast_avg = breast_total / count
        bottle_avg = bottle_total / count
        value = "🤱 {} · 🍼 {} ml".format(
            duration_string(breast_avg, "m"), _format_amount(bottle_avg)
        )
        results.append(
            {"type": "amount_combo", "stat": value, "title": window["title"]}
        )
    return results


def _nap_statistics(child):
    """
    Averaged nap data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    instances = models.Sleep.objects.filter(child=child, nap=True).order_by("start")
    if len(instances) == 0:
        return False
    naps = {
        "total": instances.aggregate(Sum("duration"))["duration__sum"],
        "count": instances.count(),
        "average": 0.0,
        "avg_per_day": 0.0,
    }
    if naps["count"] > 0:
        naps["average"] = naps["total"] / naps["count"]

    naps_avg = (
        instances.annotate(date=TruncDate("start"))
        .values("date")
        .annotate(naps_count=Count("id"))
        .order_by()
        .aggregate(Avg("naps_count"))
    )
    naps["avg_per_day"] = naps_avg["naps_count__avg"]

    return naps


def _sleep_statistics(child):
    """
    Averaged Sleep data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    instances = models.Sleep.objects.filter(child=child).order_by("start")
    if len(instances) == 0:
        return False

    sleep = {
        "total": instances.aggregate(Sum("duration"))["duration__sum"],
        "count": instances.count(),
        "average": 0.0,
        "btwn_total": timezone.timedelta(0),
        "btwn_count": instances.count() - 1,
        "btwn_average": 0.0,
    }

    last_instance = None
    for instance in instances:
        if last_instance:
            start = timezone.localtime(instance.start)
            last_end = timezone.localtime(last_instance.end)
            sleep["btwn_total"] += start - last_end
        last_instance = instance

    if sleep["count"] > 0:
        sleep["average"] = sleep["total"] / sleep["count"]
    if sleep["btwn_count"] > 0:
        sleep["btwn_average"] = sleep["btwn_total"] / sleep["btwn_count"]

    return sleep


def _weight_statistics(child):
    """
    Statistical weight data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    weight = {"change_weekly": 0.0}

    instances = models.Weight.objects.filter(child=child).order_by("-date")
    if len(instances) == 0:
        return False

    newest = instances.first()
    oldest = instances.last()

    if newest != oldest:
        weight_change = newest.weight - oldest.weight
        weeks = (newest.date - oldest.date).days / 7
        weight["change_weekly"] = weight_change / weeks

    return weight


def _height_statistics(child):
    """
    Statistical height data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    height = {"change_weekly": 0.0}

    instances = models.Height.objects.filter(child=child).order_by("-date")
    if len(instances) == 0:
        return False

    newest = instances.first()
    oldest = instances.last()

    if newest != oldest:
        height_change = newest.height - oldest.height
        weeks = (newest.date - oldest.date).days / 7
        height["change_weekly"] = height_change / weeks

    return height


def _head_circumference_statistics(child):
    """
    Statistical head circumference data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    head_circumference = {"change_weekly": 0.0}

    instances = models.HeadCircumference.objects.filter(child=child).order_by("-date")
    if len(instances) == 0:
        return False

    newest = instances.first()
    oldest = instances.last()

    if newest != oldest:
        hc_change = newest.head_circumference - oldest.head_circumference
        weeks = (newest.date - oldest.date).days / 7
        head_circumference["change_weekly"] = hc_change / weeks

    return head_circumference


def _bmi_statistics(child):
    """
    Statistical BMI data.
    :param child: an instance of the Child model.
    :returns: a dictionary of statistics.
    """
    bmi = {"change_weekly": 0.0}

    instances = models.BMI.objects.filter(child=child).order_by("-date")
    if len(instances) == 0:
        return False

    newest = instances.first()
    oldest = instances.last()

    if newest != oldest:
        bmi_change = newest.bmi - oldest.bmi
        weeks = (newest.date - oldest.date).days / 7
        bmi["change_weekly"] = bmi_change / weeks

    return bmi


@register.inclusion_tag("cards/timer_list.html", takes_context=True)
def card_timer_list(context, child=None):
    """
    Filters for currently active Timer instances, optionally by child.
    :param child: an instance of the Child model.
    :returns: a dictionary with a list of active Timer instances.
    """
    if child:
        # Get active instances for the selected child _or_ None (no child).
        instances = models.Timer.objects.filter(
            Q(child=child) | Q(child=None)
        ).order_by("-start")
    else:
        instances = models.Timer.objects.order_by("-start")
    empty = len(instances) == 0

    return {
        "type": "timer",
        "instances": list(instances),
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/tummytime_last.html", takes_context=True)
def card_tummytime_last(context, child):
    """
    Filters the most recent tummy time.
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Tummy Time instance.
    """
    instance = (
        models.TummyTime.objects.filter(child=child)
        .filter(**_filter_data_age(context))
        .order_by("-end")
        .first()
    )
    empty = not instance

    return {
        "type": "tummytime",
        "tummytime": instance,
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/tummytime_day.html", takes_context=True)
def card_tummytime_day(context, child, date=None):
    """
    Filters Tummy Time instances and generates statistics for a specific date.
    :param child: an instance of the Child model.
    :param date: a Date object for the day to filter.
    :returns: a dictionary of all Tummy Time instances and stats for date.
    """
    if not date:
        date = timezone.localtime().date()
    instances = models.TummyTime.objects.filter(
        child=child, end__year=date.year, end__month=date.month, end__day=date.day
    ).order_by("-end")
    empty = len(instances) == 0

    stats = {"total": timezone.timedelta(seconds=0), "count": instances.count()}
    for instance in instances:
        stats["total"] += timezone.timedelta(seconds=instance.duration.seconds)

    return {
        "type": "tummytime",
        "stats": stats,
        "instances": instances,
        "last": instances.first(),
        "empty": empty,
        "hide_empty": _hide_empty(context),
    }


@register.inclusion_tag("cards/medication_last.html", takes_context=True)
def card_medication_last(context, child):
    """
    Information about the most recent medication administration.
    :param child: an instance of the Child model.
    :returns: a dictionary with the most recent Medication instance.
    """
    instance = (
        models.Medication.objects.filter(child=child)
        .filter(**_filter_data_age(context, "time"))
        .select_related("child")
        .order_by("-time")
        .first()
    )

    return {
        "type": "medication",
        "medication": instance,
        "empty": not instance,
        "hide_empty": _hide_empty(context),
    }
