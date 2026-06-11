# -*- coding: utf-8 -*-
import calendar
import datetime

from django import template
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from core import utils

register = template.Library()


@register.filter
def child_age_string(birth_date):
    """
    Format a Child's age precisely: days under one week, weeks + days under
    nine weeks, calendar months + days under two years, then years + months.
    :param birth_date: datetime or date instance
    :return: a string representation of time since `birth_date`.
    """
    if not birth_date:
        return ""
    try:
        birth = timezone.localtime(birth_date).date()
    except (AttributeError, ValueError):
        birth = birth_date.date() if hasattr(birth_date, "date") else birth_date
    today = timezone.localdate()
    days = (today - birth).days
    if days < 0:
        return ""

    def _days(count):
        return ngettext("%(count)s day", "%(count)s days", count) % {"count": count}

    if days < 7:
        return _days(days)
    if days < 63:
        weeks, rem = divmod(days, 7)
        result = ngettext("%(count)s week", "%(count)s weeks", weeks) % {
            "count": weeks
        }
        if rem:
            result += ", " + _days(rem)
        return result

    # Whole calendar months elapsed, plus exact remainder days from the
    # month anniversary (clamped for short months).
    months = (today.year - birth.year) * 12 + (today.month - birth.month)
    if today.day < min(birth.day, calendar.monthrange(today.year, today.month)[1]):
        months -= 1
    anchor_year = birth.year + (birth.month - 1 + months) // 12
    anchor_month = (birth.month - 1 + months) % 12 + 1
    anchor_day = min(birth.day, calendar.monthrange(anchor_year, anchor_month)[1])
    rem_days = (today - datetime.date(anchor_year, anchor_month, anchor_day)).days

    if months < 24:
        result = ngettext("%(count)s month", "%(count)s months", months) % {
            "count": months
        }
        if rem_days:
            result += ", " + _days(rem_days)
        return result
    years, rem_months = divmod(months, 12)
    result = ngettext("%(count)s year", "%(count)s years", years) % {"count": years}
    if rem_months:
        result += ", " + ngettext(
            "%(count)s month", "%(count)s months", rem_months
        ) % {"count": rem_months}
    return result


@register.filter
def duration_string(duration, precision="s"):
    """
    Format a duration (e.g. "2 hours, 3 minutes, 35 seconds").
    :param duration: a timedelta instance.
    :param precision: the level of precision to return (h for hours, m for
                      minutes, s for seconds)
    :returns: a string representation of the duration.
    """
    if not duration:
        return ""
    try:
        return utils.duration_string(duration, precision)
    except (ValueError, TypeError):
        return ""


@register.filter
def hours(duration):
    """
    Return the "hours" portion of a duration.
    :param duration: a timedelta instance.
    :returns: an integer representing the number of hours in duration.
    """
    if not duration:
        return 0
    try:
        h, m, s = utils.duration_parts(duration)
        return h
    except (ValueError, TypeError):
        return 0


@register.filter
def minutes(duration):
    """
    Return the "minutes" portion of a duration.
    :param duration: a timedelta instance.
    :returns: an integer representing the number of minutes in duration.
    """
    if not duration:
        return 0
    try:
        h, m, s = utils.duration_parts(duration)
        return m
    except (ValueError, TypeError):
        return 0


@register.filter
def seconds(duration):
    """
    Return the "seconds" portion of a duration.
    :param duration: a timedelta instance.
    :returns: an integer representing the number of seconds in duration.
    """
    if not duration:
        return 0
    try:
        h, m, s = utils.duration_parts(duration)
        return s
    except (ValueError, TypeError):
        return 0


@register.filter()
def dayssince(value, today=None):
    """
    Returns the days since passed datetime in a user friendly way. (e.g. today, yesterday, 2 days ago, ...)
    :param value: a date instance
    :param today: date to compare to (defaults to today)
    :returns: the formatted string
    """

    if today is None:
        today = timezone.localtime().date()

    delta = today - value
    days_ago = _("%(days_ago)s days ago") % {"days_ago": str(delta.days)}

    if delta < datetime.timedelta(days=1):
        return _("today")
    if delta < datetime.timedelta(days=2):
        return _("yesterday")

    # use standard timesince for anything beyond yesterday
    return days_ago


@register.filter
def deltasince(value, now=None):
    """
    Returns a timedelta representing the time since passed datetime
    :param value: a datetime instance
    :param now: datetime to compare to (defaults to now)
    :returns: a timedelta representing the elapsed time
    """
    if now is None:
        now = timezone.now()

    delta = now - value

    return delta
