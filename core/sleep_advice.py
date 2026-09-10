# -*- coding: utf-8 -*-
"""Estimate when a child is next due to sleep.

The estimate is built from the child's own recent pattern -- the wake windows
that actually preceded their naps -- because every baby differs. Typical wake
windows for the child's age are used only as a fallback, when there is not yet
enough logged sleep for their own pattern to mean anything.
"""
import statistics
from datetime import timedelta

from django.utils import timezone

from core.models import Sleep, Timer

# Typical wake window by age, as (age in days at or below, minutes). These are
# the usual ranges quoted for infants; the midpoint of each is used.
AGE_WAKE_WINDOWS = [
    (30, 50),  # 0-1 month
    (60, 75),  # 1-2 months
    (90, 90),  # 2-3 months
    (120, 105),  # 3-4 months
    (180, 135),  # 4-6 months
    (270, 165),  # 6-9 months
    (365, 195),  # 9-12 months
    (545, 225),  # 12-18 months
    (730, 300),  # 18-24 months
]
DEFAULT_WAKE_WINDOW_MINUTES = 330

# How much history to learn from, and how many naps are needed before the
# child's own pattern is trusted over the age fallback.
LOOKBACK_DAYS = 14
MIN_SAMPLES = 5

# A gap outside these bounds is a logging artefact rather than a wake window.
MIN_WAKE_WINDOW = timedelta(minutes=15)
MAX_WAKE_WINDOW = timedelta(hours=6)
# Samples far above what is plausible for the age are dropped before averaging.
OUTLIER_FACTOR = 2.5

# How close to the suggested time counts as "due now" rather than "later".
DUE_SOON = timedelta(minutes=15)

# Past this much awake, sleep simply is not being logged: an infant has not
# really been up for a day. Saying "overdue by 40 hours" would be noise.
STALE_AFTER = timedelta(hours=12)

SLEEP_TIMER_NAMES = ["Sleep", "Nap"]

# A nap may be logged with the Sleep button rather than the Nap one, so fall
# back to the shape of the record: a short daytime sleep is a nap either way.
NAP_MAX_DURATION = timedelta(hours=4)
NAP_EARLIEST_HOUR = 6
NAP_LATEST_HOUR = 20


def is_nap(sleep):
    """Whether a sleep record should count as a nap for learning purposes."""
    if sleep.nap:
        return True
    if sleep.end - sleep.start >= NAP_MAX_DURATION:
        return False
    return NAP_EARLIEST_HOUR <= timezone.localtime(sleep.start).hour < NAP_LATEST_HOUR


def age_wake_window(child, on=None):
    """Typical wake window for the child's age."""
    if not child.birth_date:
        return timedelta(minutes=DEFAULT_WAKE_WINDOW_MINUTES)
    days = ((on or timezone.localdate()) - child.birth_date).days
    for limit, minutes in AGE_WAKE_WINDOWS:
        if days <= limit:
            return timedelta(minutes=minutes)
    return timedelta(minutes=DEFAULT_WAKE_WINDOW_MINUTES)


def observed_wake_windows(child, lookback_days=LOOKBACK_DAYS):
    """The wake windows that actually preceded this child's recent naps.

    Only naps count: the stretch before the night sleep is a bedtime, not a
    wake window, and would skew the estimate upwards.
    """
    since = timezone.now() - timedelta(days=lookback_days)
    # Reach back an extra day so a nap early in the window still has the sleep
    # before it available to measure from.
    sleeps = (
        Sleep.objects.filter(child=child, end__gte=since - timedelta(days=1))
        .order_by("start")
    )
    windows = []
    prev_end = None
    for sleep in sleeps:
        if (
            sleep.start >= since
            and prev_end
            and prev_end <= sleep.start
            and is_nap(sleep)
        ):
            gap = sleep.start - prev_end
            if MIN_WAKE_WINDOW <= gap <= MAX_WAKE_WINDOW:
                windows.append(gap)
        prev_end = max(prev_end, sleep.end) if prev_end else sleep.end
    return windows


def target_wake_window(child):
    """How long this child tends to stay awake before a nap.

    :returns: (timedelta, source, sample_count) where source is "personal" when
        the child's own naps were used and "age" when the fallback was.
    """
    baseline = age_wake_window(child)
    cap = baseline * OUTLIER_FACTOR
    windows = [w for w in observed_wake_windows(child) if w <= cap]
    if len(windows) >= MIN_SAMPLES:
        median = statistics.median(w.total_seconds() for w in windows)
        return timedelta(seconds=median), "personal", len(windows)
    return baseline, "age", len(windows)


def suggest_next_sleep(child):
    """When the child is next due to sleep.

    :returns: a dict with the suggestion and the state it is in:
        "asleep"   - sleeping now, so there is nothing to suggest
        "early"    - the suggested time is still comfortably ahead
        "due"      - within the next few minutes
        "overdue"  - the suggested time has passed
        "unknown"  - no sleep has been logged, so there is nothing to go on
    """
    now = timezone.now()
    target, source, samples = target_wake_window(child)
    result = {
        "target": target,
        "source": source,
        "samples": samples,
        "asleep": False,
        "state": "unknown",
        "awake_since": None,
        "suggested_at": None,
        "remaining": None,
    }

    timer = Timer.objects.filter(child=child, name__in=SLEEP_TIMER_NAMES).first()
    if timer:
        result.update({"asleep": True, "state": "asleep", "awake_since": timer.start})
        return result

    last_sleep = Sleep.objects.filter(child=child).order_by("-end").first()
    if not last_sleep or last_sleep.end > now:
        return result

    if now - last_sleep.end > STALE_AFTER:
        result.update({"state": "stale", "awake_since": last_sleep.end})
        return result

    suggested = last_sleep.end + target
    remaining = suggested - now
    if remaining > DUE_SOON:
        state = "early"
    elif remaining >= timedelta(0):
        state = "due"
    else:
        state = "overdue"

    result.update(
        {
            "state": state,
            "awake_since": last_sleep.end,
            "suggested_at": suggested,
            "remaining": remaining,
        }
    )
    return result
