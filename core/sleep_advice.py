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

# Recommended total sleep per 24 hours by age, as (age in days at or below,
# min hours, max hours).
AGE_TOTAL_SLEEP = [
    (90, 14, 17),  # 0-3 months
    (365, 12, 16),  # 4-12 months
    (730, 11, 14),  # 1-2 years
]
DEFAULT_TOTAL_SLEEP = (10, 13)

# How far the sleep budget may pull the wake window either way.
MIN_PACE_FACTOR = 0.8
MAX_PACE_FACTOR = 1.2

# Failed settles bound the estimate rather than setting it. Quantiles, not the
# extremes, so a single bad afternoon cannot dictate the answer; the margins
# then aim inside the failing region rather than at its edge.
CEILING_QUANTILE = 0.25  # low end of the windows that ended overtired
FLOOR_QUANTILE = 0.75  # high end of the windows that ended wide awake
BOUND_MARGIN_DOWN = 0.9
BOUND_MARGIN_UP = 1.1
# Failed settles bound the estimate only once they repeat; one is an anecdote.
MIN_BOUND_SAMPLES = 3

# How much history to learn from, and how many naps are needed before the
# child's own pattern is trusted over the age fallback.
LOOKBACK_DAYS = 14
MIN_SAMPLES = 5

# A gap longer than this is a logging artefact rather than a wake window.
MAX_WAKE_WINDOW = timedelta(hours=6)
# A sleep starting within this fraction of the typical window for the age is a
# resettle -- the same nap broken and restarted, say on a failed transfer --
# not a new nap after a wake window. How the resettle went says nothing about
# the gap before it, so it is left out of both the estimate and its bounds.
RESETTLE_FRACTION = 0.5
# Samples far above what is plausible for the age are dropped before averaging.
OUTLIER_FACTOR = 2.5
# Whatever the feedback and the sleep budget say, never suggest less than this
# fraction of the typical window for the age.
MIN_TARGET_FRACTION = 0.5

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


def observed_wake_windows(child, lookback_days=LOOKBACK_DAYS, with_sleep=False):
    """The wake windows that actually preceded this child's recent naps.

    Only naps count: the stretch before the night sleep is a bedtime, not a
    wake window, and would skew the estimate upwards. Resettles do not count
    either: a nap restarted minutes after it broke is still that nap.

    :param with_sleep: return (window, sleep) pairs instead of just windows, so
        callers can weigh each window by how that sleep went.
    """
    since = timezone.now() - timedelta(days=lookback_days)
    min_gap = age_wake_window(child) * RESETTLE_FRACTION
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
            if min_gap <= gap <= MAX_WAKE_WINDOW:
                windows.append((gap, sleep) if with_sleep else gap)
        prev_end = max(prev_end, sleep.end) if prev_end else sleep.end
    return windows


def age_total_sleep(child, on=None):
    """Recommended total sleep per 24 hours for the child's age, in hours."""
    if not child.birth_date:
        return DEFAULT_TOTAL_SLEEP
    days = ((on or timezone.localdate()) - child.birth_date).days
    for limit, low, high in AGE_TOTAL_SLEEP:
        if days <= limit:
            return low, high
    return DEFAULT_TOTAL_SLEEP


def sleep_in_last_24h(child, now=None):
    """How much the child has slept in the last 24 hours.

    A rolling window rather than "today", which would otherwise reset in the
    middle of the night sleep and read as a huge deficit every morning.
    """
    now = now or timezone.now()
    since = now - timedelta(hours=24)
    total = timedelta()
    for sleep in Sleep.objects.filter(child=child, end__gt=since, start__lt=now):
        total += min(sleep.end, now) - max(sleep.start, since)
    return total


def pace_factor(child, now=None):
    """Scale the wake window by how the last 24 hours compare to the target.

    Behind on sleep means offering the next one sooner; comfortably ahead means
    it can wait. Returns (factor, slept, low, high).
    """
    low, high = age_total_sleep(child)
    slept = sleep_in_last_24h(child, now)
    hours = slept.total_seconds() / 3600
    if hours < low:
        factor = max(MIN_PACE_FACTOR, hours / low) if low else 1.0
    elif hours > high:
        factor = min(MAX_PACE_FACTOR, hours / high) if high else 1.0
    else:
        factor = 1.0
    return factor, slept, low, high


def _settled_well(sleep):
    return sleep.settling in Sleep.SETTLED_WELL


def _quantile(values, q):
    """A quantile that also works for one or two samples."""
    ordered = sorted(v.total_seconds() for v in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return timedelta(seconds=ordered[0])
    index = q * (len(ordered) - 1)
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    seconds = ordered[low] + (ordered[high] - ordered[low]) * (index - low)
    return timedelta(seconds=seconds)


def training_windows(child):
    """Wake windows to anchor the estimate on, preferring the ones that worked.

    :returns: (windows, basis)
    """
    pairs = observed_wake_windows(child, with_sleep=True)
    baseline = age_wake_window(child)
    cap = baseline * OUTLIER_FACTOR
    pairs = [(w, s) for w, s in pairs if w <= cap]

    settled = [w for w, s in pairs if _settled_well(s)]
    if len(settled) >= MIN_SAMPLES:
        return settled, "settled"

    # No feedback yet: naps that at least lasted are a weaker proxy for the
    # same thing.
    durations = [(s.end - s.start) for _, s in pairs]
    if durations:
        median_nap = timedelta(
            seconds=statistics.median(d.total_seconds() for d in durations)
        )
        restorative = [w for w, s in pairs if (s.end - s.start) >= median_nap]
        if len(restorative) >= MIN_SAMPLES:
            return restorative, "restorative"

    return [w for w, _ in pairs], "all"


def feedback_bounds(child):
    """Bounds on the wake window implied by settles that went badly.

    A settle that failed says which way the window was wrong, which is useful
    even though it says nothing about the right value: going down overtired
    means the window ran long, going down wide awake means it was cut short.
    Requiring a few of them, and taking a quantile rather than the extreme,
    keeps one bad afternoon from dictating the answer.

    :returns: (ceiling, floor), either of which may be None.
    """
    baseline = age_wake_window(child)
    cap = baseline * OUTLIER_FACTOR
    pairs = [
        (w, s) for w, s in observed_wake_windows(child, with_sleep=True) if w <= cap
    ]
    too_long = [w for w, s in pairs if s.settling == Sleep.SETTLING_TOO_LONG]
    too_short = [w for w, s in pairs if s.settling == Sleep.SETTLING_TOO_SHORT]

    ceiling = (
        _quantile(too_long, CEILING_QUANTILE)
        if len(too_long) >= MIN_BOUND_SAMPLES
        else None
    )
    floor = (
        _quantile(too_short, FLOOR_QUANTILE)
        if len(too_short) >= MIN_BOUND_SAMPLES
        else None
    )
    # Aim inside the failing region rather than right at its edge.
    if ceiling:
        ceiling = ceiling * BOUND_MARGIN_DOWN
    if floor:
        floor = floor * BOUND_MARGIN_UP
    return ceiling, floor


def target_wake_window(child):
    """How long this child should stay awake before the next nap.

    An anchor from the settles that worked, then corrected by the ones that did
    not: every piece of feedback moves the estimate, successes by saying what
    the value is and failures by saying which side of it they were on.

    :returns: (timedelta, source, sample_count)
    """
    baseline = age_wake_window(child)
    windows, basis = training_windows(child)
    if len(windows) >= MIN_SAMPLES:
        target = timedelta(
            seconds=statistics.median(w.total_seconds() for w in windows)
        )
        samples = len(windows)
    else:
        target, basis, samples = baseline, "age", len(windows)

    ceiling, floor = feedback_bounds(child)
    if ceiling and floor and floor > ceiling:
        # Contradictory evidence: sit between the two rather than obeying
        # whichever was applied last.
        target = timedelta(seconds=(floor + ceiling).total_seconds() / 2)
        basis = basis + "+bounded"
    else:
        if floor and target < floor:
            target, basis = floor, basis + "+raised"
        if ceiling and target > ceiling:
            target, basis = ceiling, basis + "+capped"

    minimum = baseline * MIN_TARGET_FRACTION
    if target < minimum:
        target, basis = minimum, basis + "+floored"
    return target, basis, samples


def _paced(child, base, factor):
    """The wake window nudged by the sleep budget, but never outside what is
    plausible for the age."""
    baseline = age_wake_window(child)
    target = timedelta(seconds=base.total_seconds() * factor)
    return min(
        max(target, baseline * MIN_TARGET_FRACTION), baseline * OUTLIER_FACTOR
    )


def suggestion_for(child, sleep_start):
    """What would have been suggested for a sleep starting at this moment.

    Recorded against the sleep as it is saved, so the gap between the advice
    and what the caregiver actually did can be measured later. Call this before
    saving, while the previous sleep is still the most recent one.
    """
    previous = (
        Sleep.objects.filter(child=child, end__lte=sleep_start).order_by("-end").first()
    )
    if not previous:
        return None
    base, _, _ = target_wake_window(child)
    factor = pace_factor(child, now=sleep_start)[0]
    return previous.end + _paced(child, base, factor)


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
    base, source, samples = target_wake_window(child)
    factor, slept_24h, low, high = pace_factor(child, now)
    target = _paced(child, base, factor)
    result = {
        "target": target,
        "base_target": base,
        "source": source,
        "samples": samples,
        "pace": ("behind" if factor < 1 else "ahead" if factor > 1 else "on_track"),
        "slept_24h": slept_24h,
        "recommended_low": low,
        "recommended_high": high,
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
