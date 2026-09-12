from django.db import models

from core.models import Child, Timer


class PumpPending(models.Model):
    """Stopped-but-uncommitted pump timer sessions, shared across devices via DB."""

    child = models.ForeignKey(Child, on_delete=models.CASCADE)
    side = models.CharField(max_length=5)  # "left" or "right"
    start = models.DateTimeField()
    end = models.DateTimeField()

    class Meta:
        ordering = ["start"]


class SleepSettlingDraft(models.Model):
    """How a running sleep went down, answered before the timer is stopped.

    The answer describes the child on the way to sleep, so it is easiest to
    give while that is happening. Held against the timer -- and so removed with
    it -- and shared across devices via DB.
    """

    timer = models.OneToOneField(
        Timer, on_delete=models.CASCADE, related_name="settling_draft"
    )
    settling = models.CharField(max_length=255)


class FeedPending(models.Model):
    """Stopped-but-uncommitted feed timer sessions, shared across devices via DB."""

    child = models.ForeignKey(Child, on_delete=models.CASCADE)
    side = models.CharField(max_length=10)  # "left", "right", or "bottle"
    start = models.DateTimeField()
    end = models.DateTimeField()

    class Meta:
        ordering = ["start"]
