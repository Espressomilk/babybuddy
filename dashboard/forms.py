import datetime
from datetime import timedelta

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from babybuddy.widgets import DateTimeInput
from core import models


class BottleFeedForm(forms.Form):
    BREAST_MILK = "breast milk"
    FORMULA = "formula"
    BOTH = "both"

    feed_type = forms.ChoiceField(
        choices=[
            (BREAST_MILK, _("Breast Milk")),
            (FORMULA, _("Formula")),
            (BOTH, _("Both")),
        ],
        initial=BREAST_MILK,
        widget=forms.HiddenInput(attrs={"id": "id_feed_type"}),
    )
    start = forms.DateTimeField(
        widget=DateTimeInput(),
    )
    amount_breast_milk = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Breast Milk (ml)"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "0",
                "step": "0.5",
                "id": "id_amount_breast_milk",
            }
        ),
    )
    amount_formula = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Formula (ml)"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "0",
                "step": "0.5",
                "id": "id_amount_formula",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )

    def __init__(self, *args, child=None, start=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.child = child
        if not self.is_bound:
            self.initial["start"] = start or timezone.localtime()

    def clean(self):
        cleaned_data = super().clean()
        feed_type = cleaned_data.get("feed_type")
        amount_bm = cleaned_data.get("amount_breast_milk")
        amount_f = cleaned_data.get("amount_formula")

        if feed_type in (self.BREAST_MILK, self.BOTH) and not amount_bm:
            self.add_error("amount_breast_milk", _("Please enter an amount."))
        if feed_type in (self.FORMULA, self.BOTH) and not amount_f:
            self.add_error("amount_formula", _("Please enter an amount."))

        return cleaned_data

    def save(self):
        from core.models import Feeding

        feed_type = self.cleaned_data["feed_type"]
        start = self.cleaned_data["start"]
        notes = self.cleaned_data.get("notes", "")
        instances = []

        if feed_type in (self.BREAST_MILK, self.BOTH):
            f = Feeding(
                child=self.child,
                start=start,
                end=start,
                type="breast milk",
                method="bottle",
                amount=self.cleaned_data.get("amount_breast_milk"),
                notes=notes,
            )
            f.save()
            instances.append(f)

        if feed_type in (self.FORMULA, self.BOTH):
            f = Feeding(
                child=self.child,
                start=start,
                end=start,
                type="formula",
                method="bottle",
                amount=self.cleaned_data.get("amount_formula"),
                notes=notes,
            )
            f.save()
            instances.append(f)

        return instances


class SleepNoteForm(forms.Form):
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )


class DiaperChangeQuickForm(forms.ModelForm):
    DIAPER_WET = "wet"
    DIAPER_SOLID = "solid"
    DIAPER_MIXED = "mixed"

    diaper_type = forms.ChoiceField(
        choices=[
            (DIAPER_WET, _("Wet")),
            (DIAPER_SOLID, _("Solid")),
            (DIAPER_MIXED, _("Mixed")),
        ],
        initial=DIAPER_WET,
        widget=forms.HiddenInput(attrs={"id": "id_diaper_type"}),
    )

    def __init__(self, *args, child=None, diaper_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        if child:
            self.fields["child"].initial = child
        if not self.is_bound:
            self.initial["time"] = timezone.localtime()
            if diaper_type in (self.DIAPER_WET, self.DIAPER_SOLID, self.DIAPER_MIXED):
                self.initial["diaper_type"] = diaper_type
            else:
                self.initial["diaper_type"] = self.DIAPER_WET

    def save(self, commit=True):
        instance = super().save(commit=False)
        diaper_type = self.cleaned_data.get("diaper_type")
        instance.wet = diaper_type in (self.DIAPER_WET, self.DIAPER_MIXED)
        instance.solid = diaper_type in (self.DIAPER_SOLID, self.DIAPER_MIXED)
        if commit:
            instance.save()
        return instance

    class Meta:
        model = models.DiaperChange
        fields = ["child", "time", "color", "notes"]
        widgets = {
            "child": forms.HiddenInput(),
            "time": DateTimeInput(),
            "color": forms.HiddenInput(attrs={"id": "id_color"}),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "id": "id_notes",
                    "placeholder": "",
                }
            ),
        }


class TummyTimeMilestoneForm(forms.Form):
    milestone = forms.CharField(
        required=False,
        label=_("Milestone"),
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_milestone",
                "placeholder": "",
            }
        ),
    )


class PumpCommitForm(forms.Form):
    start = forms.DateTimeField(
        required=False,
        label=_("Start time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_start"}),
    )
    end = forms.DateTimeField(
        required=False,
        label=_("End time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_end"}),
    )
    amount_left = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Left amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.5",
                "min": "0",
                "placeholder": "0",
                "id": "id_amount_left",
            }
        ),
    )
    amount_right = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Right amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "0.5",
                "min": "0",
                "placeholder": "0",
                "id": "id_amount_right",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )

    def __init__(self, *args, start=None, end=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start"].required = True
        self.fields["end"].required = True
        if not self.is_bound:
            if start:
                self.initial["start"] = start
            if end:
                self.initial["end"] = end

    def _make_aware(self, value):
        if value and timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_start(self):
        return self._make_aware(self.cleaned_data.get("start"))

    def clean_end(self):
        return self._make_aware(self.cleaned_data.get("end"))


class FeedCommitForm(forms.Form):
    BREAST_MILK = "breast milk"
    FORMULA = "formula"
    BOTH = "both"

    breast_start = forms.DateTimeField(
        required=False,
        label=_("Start time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_breast_start"}),
    )
    breast_end = forms.DateTimeField(
        required=False,
        label=_("End time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_breast_end"}),
    )
    bottle_start = forms.DateTimeField(
        required=False,
        label=_("Start time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_bottle_start"}),
    )
    bottle_end = forms.DateTimeField(
        required=False,
        label=_("End time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_bottle_end"}),
    )
    bottle_type = forms.ChoiceField(
        choices=[
            (BREAST_MILK, _("Breast Milk")),
            (FORMULA, _("Formula")),
            (BOTH, _("Both")),
        ],
        initial=BREAST_MILK,
        required=False,
        label=_("Bottle type"),
        widget=forms.HiddenInput(attrs={"id": "id_bottle_type"}),
    )
    bottle_amount_breast_milk = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Breast milk amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "any",
                "min": "0",
                "placeholder": "0",
                "id": "id_bottle_amount_breast_milk",
            }
        ),
    )
    bottle_amount_formula = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Formula amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "any",
                "min": "0",
                "placeholder": "0",
                "id": "id_bottle_amount_formula",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )

    def __init__(
        self,
        *args,
        has_breast=False,
        has_bottle=False,
        breast_start=None,
        breast_end=None,
        bottle_start=None,
        bottle_end=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.has_breast = has_breast
        self.has_bottle = has_bottle
        if has_breast:
            self.fields["breast_start"].required = True
            self.fields["breast_end"].required = True
        if has_bottle:
            self.fields["bottle_start"].required = True
            self.fields["bottle_end"].required = True
        if not self.is_bound:
            if breast_start:
                self.initial["breast_start"] = breast_start
            if breast_end:
                self.initial["breast_end"] = breast_end
            if bottle_start:
                self.initial["bottle_start"] = bottle_start
            if bottle_end:
                self.initial["bottle_end"] = bottle_end

    def _make_aware(self, value):
        if value and timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_breast_start(self):
        return self._make_aware(self.cleaned_data.get("breast_start"))

    def clean_breast_end(self):
        return self._make_aware(self.cleaned_data.get("breast_end"))

    def clean_bottle_start(self):
        return self._make_aware(self.cleaned_data.get("bottle_start"))

    def clean_bottle_end(self):
        return self._make_aware(self.cleaned_data.get("bottle_end"))

    def clean(self):
        cleaned_data = super().clean()
        bottle_type = cleaned_data.get("bottle_type") or self.BREAST_MILK
        amount_bm = cleaned_data.get("bottle_amount_breast_milk")
        amount_f = cleaned_data.get("bottle_amount_formula")

        if bottle_type == self.BOTH and not amount_bm and not amount_f:
            self.add_error(
                "bottle_amount_breast_milk", _("Please enter an amount.")
            )

        return cleaned_data


class FeedQuickForm(forms.Form):
    """Manually log a completed bottle feeding without running a timer.

    The end time defaults to the moment the form is opened (adjustable); the
    user must enter the start time. Bottle feeding only (breast milk / formula
    / both) -- breastfeeding is logged from the Breast Feed & Pump card.
    """

    BREAST_MILK = "breast milk"
    FORMULA = "formula"
    BOTH = "both"

    bottle_type = forms.ChoiceField(
        choices=[
            (BREAST_MILK, _("Breast Milk")),
            (FORMULA, _("Formula")),
            (BOTH, _("Both")),
        ],
        initial=BREAST_MILK,
        required=False,
        label=_("Bottle type"),
        widget=forms.HiddenInput(attrs={"id": "id_bottle_type"}),
    )
    start = forms.DateTimeField(
        label=_("Start time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_start"}),
    )
    end = forms.DateTimeField(
        label=_("End time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_end"}),
    )
    bottle_amount_breast_milk = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Breast milk amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "any",
                "min": "0",
                "placeholder": "0",
                "id": "id_bottle_amount_breast_milk",
            }
        ),
    )
    bottle_amount_formula = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Formula amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "any",
                "min": "0",
                "placeholder": "0",
                "id": "id_bottle_amount_formula",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )

    def __init__(self, *args, child=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.child = child
        if not self.is_bound:
            # Default both start and end to "now" so the start date already
            # matches the end date; the user can roll the time as needed.
            now = timezone.localtime().replace(second=0, microsecond=0, tzinfo=None)
            self.initial["end"] = now
            self.initial["start"] = now

    def _make_aware(self, value):
        if value and timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_start(self):
        return self._make_aware(self.cleaned_data.get("start"))

    def clean_end(self):
        return self._make_aware(self.cleaned_data.get("end"))

    def clean(self):
        cleaned_data = super().clean()
        bottle_type = cleaned_data.get("bottle_type") or self.BREAST_MILK
        amount_bm = cleaned_data.get("bottle_amount_breast_milk")
        amount_f = cleaned_data.get("bottle_amount_formula")

        if bottle_type == self.BOTH and not amount_bm and not amount_f:
            self.add_error("bottle_amount_breast_milk", _("Please enter an amount."))

        return cleaned_data

    def build_entries(self):
        """Return a list of unsaved bottle Feeding instances for the data."""
        from core.models import Feeding

        start = self.cleaned_data["start"]
        end = self.cleaned_data["end"]
        notes = self.cleaned_data.get("notes", "")
        bottle_type = self.cleaned_data.get("bottle_type") or self.BREAST_MILK
        amount_bm = self.cleaned_data.get("bottle_amount_breast_milk") or None
        amount_f = self.cleaned_data.get("bottle_amount_formula") or None

        if bottle_type == self.BOTH:
            specs = [("breast milk", amount_bm), ("formula", amount_f)]
        elif bottle_type == self.FORMULA:
            specs = [("formula", amount_f or amount_bm)]
        else:
            specs = [("breast milk", amount_bm or amount_f)]

        entries = []
        for entry_type, entry_amount in specs:
            entries.append(
                Feeding(
                    child=self.child,
                    start=start,
                    end=end,
                    type=entry_type,
                    method="bottle",
                    amount=entry_amount,
                    notes=notes,
                )
            )

        return entries


class BreastfeedForm(forms.ModelForm):
    # Both start and duration are set by JS before submit; kept hidden here.
    duration_minutes = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label=_("Duration (minutes)"),
        widget=forms.HiddenInput(attrs={"id": "id_duration_minutes"}),
    )

    def __init__(self, *args, child=None, **kwargs):
        super().__init__(*args, **kwargs)
        if child:
            self.fields["child"].initial = child
        self.fields["method"].widget = forms.HiddenInput(attrs={"id": "id_method"})
        self.fields["method"].required = True
        self.fields["start"].widget = forms.HiddenInput(attrs={"id": "id_start"})

    def clean_start(self):
        """
        JS always submits start as a UTC datetime string ('YYYY-MM-DD HH:MM:SS').
        Force Django to interpret it as UTC regardless of the user's active timezone,
        so the stored time is always correct even when the browser timezone differs
        from the BabyBuddy timezone setting.
        """
        value = self.cleaned_data.get("start")
        if value and timezone.is_naive(value):
            value = timezone.make_aware(value, datetime.timezone.utc)
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.type = "breast milk"
        duration = self.cleaned_data.get("duration_minutes") or 0
        instance.end = instance.start + timedelta(minutes=duration)
        if commit:
            instance.save()
        return instance

    class Meta:
        model = models.Feeding
        fields = ["child", "start", "method", "notes"]
        widgets = {
            "child": forms.HiddenInput(),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "id": "id_notes",
                    "placeholder": "",
                }
            ),
        }


class BreastfeedQuickForm(forms.Form):
    """Manually log a completed breastfeeding without running a timer.

    The user enters a left-side duration and a right-side duration (each defaults
    to 0, adjustable via the roller duration picker) plus an end time (defaults
    to the moment the form is opened). The start time is computed automatically
    as end - (left + right), and the breast method is inferred from which
    durations are non-zero.
    """

    LEFT = "left breast"
    RIGHT = "right breast"
    BOTH = "both breasts"

    left_minutes = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label=_("Left duration"),
        widget=forms.HiddenInput(
            attrs={"id": "id_left_minutes", "data-duration-roller": "1"}
        ),
    )
    right_minutes = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label=_("Right duration"),
        widget=forms.HiddenInput(
            attrs={"id": "id_right_minutes", "data-duration-roller": "1"}
        ),
    )
    start = forms.DateTimeField(
        label=_("Start time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_start"}),
    )
    end = forms.DateTimeField(
        label=_("End time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_end"}),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )

    def __init__(self, *args, child=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.child = child
        if not self.is_bound:
            now = timezone.localtime().replace(second=0, microsecond=0, tzinfo=None)
            self.initial["end"] = now
            self.initial["start"] = now
            self.initial["left_minutes"] = 0
            self.initial["right_minutes"] = 0

    def _make_aware(self, value):
        if value and timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_start(self):
        return self._make_aware(self.cleaned_data.get("start"))

    def clean_end(self):
        return self._make_aware(self.cleaned_data.get("end"))

    def clean(self):
        cleaned_data = super().clean()
        left = cleaned_data.get("left_minutes") or 0
        right = cleaned_data.get("right_minutes") or 0
        if left <= 0 and right <= 0:
            self.add_error(
                "left_minutes",
                _("Please enter a duration for at least one side."),
            )
        # The window between start and end must be long enough to contain the
        # active feeding time; any surplus is treated as rest during the feed.
        start = cleaned_data.get("start")
        end = cleaned_data.get("end")
        total = left + right
        if start and end:
            window = (end - start).total_seconds()
            if window + 1 < total * 60:
                self.add_error(
                    "start",
                    _(
                        "Start time is too late for the entered durations. "
                        "Move it earlier or shorten the durations."
                    ),
                )
        return cleaned_data

    def build_entry(self):
        """Return an unsaved breastfeeding Feeding instance for the data."""
        from core.models import Feeding

        left = self.cleaned_data.get("left_minutes") or 0
        right = self.cleaned_data.get("right_minutes") or 0

        if left > 0 and right > 0:
            method = self.BOTH
        elif right > 0:
            method = self.RIGHT
        else:
            method = self.LEFT

        end = self.cleaned_data["end"]
        # User-chosen start (defaults to end - total active time, adjustable
        # earlier to record rest during the feed).
        start = self.cleaned_data["start"]

        return Feeding(
            child=self.child,
            start=start,
            end=end,
            type="breast milk",
            method=method,
            duration_left=timedelta(minutes=left),
            duration_right=timedelta(minutes=right),
            notes=self.cleaned_data.get("notes", ""),
        )


class PumpQuickForm(forms.Form):
    """Manually log a completed pumping session without running a timer.

    The user enters a left-side duration and a right-side duration (each defaults
    to 0, adjustable via the roller duration picker) plus an end time (defaults
    to the moment the form is opened). The start time is computed automatically
    as end - (left + right). Amounts are entered per side and combined into the
    Pumping record's total amount.
    """

    left_minutes = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label=_("Left duration"),
        widget=forms.HiddenInput(
            attrs={"id": "id_left_minutes", "data-duration-roller": "1"}
        ),
    )
    right_minutes = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label=_("Right duration"),
        widget=forms.HiddenInput(
            attrs={"id": "id_right_minutes", "data-duration-roller": "1"}
        ),
    )
    start = forms.DateTimeField(
        label=_("Start time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_start"}),
    )
    end = forms.DateTimeField(
        label=_("End time"),
        widget=DateTimeInput(attrs={"step": 60, "id": "id_end"}),
    )
    amount_left = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Left amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "any",
                "min": "0",
                "placeholder": "0",
                "id": "id_amount_left",
            }
        ),
    )
    amount_right = forms.FloatField(
        min_value=0,
        required=False,
        label=_("Right amount"),
        widget=forms.NumberInput(
            attrs={
                "step": "any",
                "min": "0",
                "placeholder": "0",
                "id": "id_amount_right",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "id": "id_notes",
                "placeholder": "",
            }
        ),
    )

    def __init__(self, *args, child=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.child = child
        if not self.is_bound:
            now = timezone.localtime().replace(second=0, microsecond=0, tzinfo=None)
            self.initial["end"] = now
            self.initial["start"] = now
            self.initial["left_minutes"] = 0
            self.initial["right_minutes"] = 0

    def _make_aware(self, value):
        if value and timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_start(self):
        return self._make_aware(self.cleaned_data.get("start"))

    def clean_end(self):
        return self._make_aware(self.cleaned_data.get("end"))

    def clean(self):
        cleaned_data = super().clean()
        left = cleaned_data.get("left_minutes") or 0
        right = cleaned_data.get("right_minutes") or 0
        if left <= 0 and right <= 0:
            self.add_error(
                "left_minutes",
                _("Please enter a duration for at least one side."),
            )
        # Left and right pumping typically happen together, so the active
        # session length is the longer side; the window must be at least that
        # long, with any surplus treated as rest during the session.
        start = cleaned_data.get("start")
        end = cleaned_data.get("end")
        active = max(left, right)
        if start and end:
            window = (end - start).total_seconds()
            if window + 1 < active * 60:
                self.add_error(
                    "start",
                    _(
                        "Start time is too late for the entered durations. "
                        "Move it earlier or shorten the durations."
                    ),
                )
        return cleaned_data

    def build_entry(self):
        """Return an unsaved Pumping instance for the data."""
        from core.models import Pumping

        amount_left = self.cleaned_data.get("amount_left")
        amount_right = self.cleaned_data.get("amount_right")

        end = self.cleaned_data["end"]
        # User-chosen start (defaults to end - max(left, right) since the sides
        # are pumped together; adjustable earlier to record rest).
        start = self.cleaned_data["start"]

        return Pumping(
            child=self.child,
            start=start,
            end=end,
            amount=(amount_left or 0) + (amount_right or 0),
            amount_left=amount_left,
            amount_right=amount_right,
            notes=self.cleaned_data.get("notes", ""),
        )
