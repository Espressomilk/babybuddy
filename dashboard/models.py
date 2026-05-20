from django.db import models

from core.models import Child


class PumpPending(models.Model):
    """Stopped-but-uncommitted pump timer sessions, shared across devices via DB."""

    child = models.ForeignKey(Child, on_delete=models.CASCADE)
    side = models.CharField(max_length=5)  # "left" or "right"
    start = models.DateTimeField()
    end = models.DateTimeField()

    class Meta:
        ordering = ["start"]
