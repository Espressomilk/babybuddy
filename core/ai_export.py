# -*- coding: utf-8 -*-
"""A plain-text export of a child's recent log, for pasting into an AI chat.

The data is written in English -- compact, unambiguous, and read equally well
by any model -- and only the instruction at the top follows the user's
language, which is what steers the language of the reply. Only the first name
and age go out: no last name or birth date.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone, translation
from django.utils.translation import gettext as _

from core.models import (
    BMI,
    DiaperChange,
    Feeding,
    HeadCircumference,
    Height,
    Medication,
    Note,
    Procedure,
    Pumping,
    Sleep,
    Temperature,
    TummyTime,
    Vaccine,
    Weight,
)
from core.sleep_advice import is_nap
from core.timeline import BREAST_METHODS

GROWTH = (
    (Weight, "weight", "weight"),
    (Height, "height", "height"),
    (HeadCircumference, "head_circumference", "head circumference"),
    (BMI, "bmi", "BMI"),
)


def _dur(delta):
    """Compact duration, e.g. "3h05m", "3h" or "45m"."""
    minutes = max(int(delta.total_seconds() // 60), 0) if delta else 0
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return "%dh%02dm" % (hours, minutes)
    if hours:
        return "%dh" % hours
    return "%dm" % minutes


def _num(value):
    """80.0 -> "80", 37.25 -> "37.25"."""
    return ("%.2f" % value).rstrip("0").rstrip(".")


def _clean(text):
    """Notes on one line, so each event stays one line."""
    return " ".join(str(text).split())


def _clock(dt, day):
    """Local time of day, marked when it falls on another day than the heading."""
    local = timezone.localtime(dt)
    text = local.strftime("%H:%M")
    offset = (local.date() - day).days
    if offset:
        text += "(%+dd)" % offset
    return text


def _with_notes(line, notes):
    return "%s; notes: %s" % (line, _clean(notes)) if notes else line


def build_export(child, days, now=None):
    """The child's last `days` days, today included, as pasteable text."""
    now = now or timezone.now()
    preamble = _(
        "Below is my baby's recent log, exported from the baby tracking app "
        "Baby Buddy. Times are local. Please answer my questions from this "
        "data; if something is not in the data, say so rather than guess."
    )
    with translation.override("en"):
        body = _render(child, days, now)
    return "%s\n\n%s" % (preamble, body)


def _render(child, days, now):
    today = timezone.localdate(now)
    first_day = today - timedelta(days=days - 1)
    day_list = [first_day + timedelta(days=i) for i in range(days)]
    bounds = {
        day: timezone.make_aware(datetime.combine(day, time.min)) for day in day_list
    }
    since = bounds[first_day]

    log = {day: [] for day in day_list}
    summary = {
        day: {
            "sleep": timedelta(),
            "naps": 0,
            "nap_time": timedelta(),
            "feeds": 0,
            "milk": 0.0,
            "breast": timedelta(),
            "wet": 0,
            "solid": 0,
            "pumped": 0.0,
            "tummy": timedelta(),
        }
        for day in day_list
    }

    def day_of(dt):
        # Anything that began before the range is listed on its first day.
        return max(timezone.localtime(dt).date(), first_day)

    def add(dt, line):
        log[day_of(dt)].append((dt, line))

    for sleep in Sleep.objects.filter(child=child, end__gt=since, start__lt=now):
        day = day_of(sleep.start)
        nap = is_nap(sleep)
        line = "%s–%s sleep %s (%s)" % (
            _clock(sleep.start, day),
            _clock(sleep.end, day),
            _dur(sleep.end - sleep.start),
            "nap" if nap else "night",
        )
        if sleep.settling:
            line += "; settling: %s" % sleep.get_settling_display()
        add(sleep.start, _with_notes(line, sleep.notes))
        # Sleep per calendar day, split at midnight.
        for d in day_list:
            day_end = bounds[d] + timedelta(days=1)
            overlap = min(sleep.end, day_end, now) - max(sleep.start, bounds[d])
            if overlap > timedelta(0):
                summary[d]["sleep"] += overlap
        if nap and sleep.start >= since:
            summary[day]["naps"] += 1
            summary[day]["nap_time"] += sleep.end - sleep.start

    for feeding in Feeding.objects.filter(child=child, start__gte=since, start__lt=now):
        day = day_of(feeding.start)
        parts = [feeding.get_type_display(), feeding.get_method_display().lower()]
        if feeding.amount:
            parts.append("%s ml" % _num(feeding.amount))
        if feeding.method in BREAST_METHODS:
            sides = []
            if feeding.duration_left:
                sides.append("L %s" % _dur(feeding.duration_left))
            if feeding.duration_right:
                sides.append("R %s" % _dur(feeding.duration_right))
            length = _dur(feeding.end - feeding.start)
            parts.append("%s (%s)" % (length, " ".join(sides)) if sides else length)
        line = "%s–%s feeding: %s" % (
            _clock(feeding.start, day),
            _clock(feeding.end, day),
            ", ".join(parts),
        )
        add(feeding.start, _with_notes(line, feeding.notes))
        stats = summary[day]
        stats["feeds"] += 1
        if feeding.amount and feeding.method in ("bottle",) + BREAST_METHODS:
            stats["milk"] += feeding.amount
        if feeding.method in BREAST_METHODS:
            stats["breast"] += feeding.end - feeding.start

    for change in DiaperChange.objects.filter(child=child, time__gte=since, time__lt=now):
        day = day_of(change.time)
        kinds = [k for k, on in (("wet", change.wet), ("solid", change.solid)) if on]
        line = "%s diaper: %s" % (_clock(change.time, day), "+".join(kinds) or "dry")
        if change.color:
            line += ", %s" % change.get_color_display().lower()
        add(change.time, _with_notes(line, change.notes))
        summary[day]["wet"] += int(change.wet)
        summary[day]["solid"] += int(change.solid)

    for pumping in Pumping.objects.filter(child=child, start__gte=since, start__lt=now):
        day = day_of(pumping.start)
        line = "%s–%s pumped %s ml" % (
            _clock(pumping.start, day),
            _clock(pumping.end, day),
            _num(pumping.amount),
        )
        if pumping.amount_left or pumping.amount_right:
            line += " (L %s, R %s)" % (
                _num(pumping.amount_left or 0),
                _num(pumping.amount_right or 0),
            )
        if pumping.storage:
            line += ", to %s" % pumping.get_storage_display().lower()
        add(pumping.start, _with_notes(line, pumping.notes))
        summary[day]["pumped"] += pumping.amount

    for tummy in TummyTime.objects.filter(child=child, start__gte=since, start__lt=now):
        day = day_of(tummy.start)
        line = "%s–%s tummy time %s" % (
            _clock(tummy.start, day),
            _clock(tummy.end, day),
            _dur(tummy.end - tummy.start),
        )
        if tummy.milestone:
            line += "; milestone: %s" % _clean(tummy.milestone)
        add(tummy.start, line)
        summary[day]["tummy"] += tummy.end - tummy.start

    for reading in Temperature.objects.filter(
        child=child, time__gte=since, time__lt=now
    ):
        line = "%s temperature %s" % (
            _clock(reading.time, day_of(reading.time)),
            _num(reading.temperature),
        )
        add(reading.time, _with_notes(line, reading.notes))

    for dose in Medication.objects.filter(child=child, time__gte=since, time__lt=now):
        what = [dose.name]
        if dose.dosage is not None:
            what.append(_num(dose.dosage))
        if dose.dosage_unit:
            what.append(dose.dosage_unit)
        line = "%s medication: %s" % (_clock(dose.time, day_of(dose.time)), " ".join(what))
        add(dose.time, _with_notes(line, dose.notes))

    for model, label in ((Vaccine, "vaccine"), (Procedure, "procedure")):
        for event in model.objects.filter(child=child, date__gte=since, date__lt=now):
            line = "%s %s: %s" % (_clock(event.date, day_of(event.date)), label, event.name)
            add(event.date, _with_notes(line, event.notes))

    for note in Note.objects.filter(child=child, time__gte=since, time__lt=now):
        add(note.time, "%s note: %s" % (_clock(note.time, day_of(note.time)), _clean(note.note)))

    # Growth is sparse, so include the last measurement before the range too.
    growth = []
    for model, field, label in GROWTH:
        entries = list(
            model.objects.filter(child=child, date__gte=first_day).order_by("date")
        )
        before = (
            model.objects.filter(child=child, date__lt=first_day).order_by("-date").first()
        )
        if before:
            entries.insert(0, before)
        for entry in entries:
            growth.append(
                (entry.date, "%s %s %s" % (entry.date.isoformat(), label, _num(getattr(entry, field))))
            )
    growth.sort(key=lambda item: item[0])

    age = (today - child.birth_date).days
    lines = [
        "# Baby Buddy log: %s" % child.first_name,
        "Exported: %s (%s)"
        % (
            timezone.localtime(now).strftime("%Y-%m-%d %H:%M"),
            timezone.get_current_timezone_name(),
        ),
        "Age: %d days (%d weeks %d days)" % (age, age // 7, age % 7),
        "Range: %s to %s (%d days; the last day is partial)"
        % (first_day.isoformat(), today.isoformat(), days),
        "Amounts are as entered in the app; volumes in ml. A nap is a sleep "
        "logged as a nap, or one under 4h starting 06:00-20:00. Daily sleep is "
        "the total within that calendar day.",
        "",
    ]
    if growth:
        lines.append("## Growth")
        lines += [line for _date, line in growth]
        lines.append("")

    lines += [
        "## Daily summary",
        "| Date | Sleep | Naps | Feeds | Milk ml | Breast | Wet | Solid | Pumped ml | Tummy |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for d in day_list:
        stats = summary[d]
        lines.append(
            "| %s | %s | %d (%s) | %d | %s | %s | %d | %d | %s | %s |"
            % (
                d.strftime("%m-%d %a"),
                _dur(stats["sleep"]),
                stats["naps"],
                _dur(stats["nap_time"]),
                stats["feeds"],
                _num(stats["milk"]),
                _dur(stats["breast"]),
                stats["wet"],
                stats["solid"],
                _num(stats["pumped"]),
                _dur(stats["tummy"]),
            )
        )

    lines += ["", "## Log"]
    for d in day_list:
        lines.append("### %s" % d.strftime("%Y-%m-%d %a"))
        entries = sorted(log[d], key=lambda item: item[0])
        lines += [line for _dt, line in entries] or ["(nothing logged)"]
    return "\n".join(lines)
