# -*- coding: utf-8 -*-
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic.base import TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, FormView

from babybuddy.mixins import LoginRequiredMixin, PermissionRequiredMixin
from core.models import BMI, Child, Feeding, HeadCircumference, Height, Medication, Pumping, Sleep, Temperature, Timer, TummyTime, Vaccine, Weight

from .forms import BottleFeedForm, BreastfeedForm, BreastfeedQuickForm, DiaperChangeQuickForm, FeedCommitForm, FeedQuickForm, PumpCommitForm, PumpQuickForm, SleepNoteForm, TummyTimeMilestoneForm
from .models import FeedPending, PumpPending


def _broadcast_track(child_slug):
    """Push a refresh signal to all WebSocket clients watching this child's track page."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        async_to_sync(get_channel_layer().group_send)(
            f"track_{child_slug}",
            {"type": "state.changed"},
        )
    except Exception:
        pass


class Dashboard(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get(self, request, *args, **kwargs):
        children = Child.objects.count()
        if children == 0:
            return HttpResponseRedirect(reverse("babybuddy:welcome"))
        elif children == 1:
            return HttpResponseRedirect(
                reverse("dashboard:dashboard-child", args={Child.objects.first().slug})
            )
        # Multiple children — go to last visited child's dashboard if known
        last_slug = request.session.get("last_child_slug")
        if last_slug and Child.objects.filter(slug=last_slug).exists():
            return HttpResponseRedirect(
                reverse("dashboard:dashboard-child", kwargs={"slug": last_slug})
            )
        return super(Dashboard, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        context["objects"] = Child.objects.all().order_by("last_name", "first_name", "id")
        return context


class ChildDashboard(PermissionRequiredMixin, DetailView):
    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/child.html"

    def get(self, request, *args, **kwargs):
        request.session["last_child_slug"] = kwargs["slug"]
        return super().get(request, *args, **kwargs)


class ChildTrack(PermissionRequiredMixin, DetailView):
    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/track.html"

    def get(self, request, *args, **kwargs):
        request.session["last_child_slug"] = kwargs["slug"]
        return super().get(request, *args, **kwargs)

    SLEEP_TIMER_NAMES = ["Sleep", "Nap"]
    PUMP_TIMER_NAMES = ["Pump Left", "Pump Right"]
    FEED_TIMER_NAMES = ["Feed Left", "Feed Right", "Feed Bottle"]
    TUMMY_TIMER_NAME = "Tummy Time"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        excluded = (
            self.SLEEP_TIMER_NAMES
            + self.PUMP_TIMER_NAMES
            + self.FEED_TIMER_NAMES
            + [self.TUMMY_TIMER_NAME]
        )
        ctx["active_timers"] = (
            Timer.objects.filter(child=self.object)
            .exclude(name__in=excluded)
            .order_by("start")
        )
        ctx["sleep_timer"] = (
            Timer.objects.filter(child=self.object, name__in=self.SLEEP_TIMER_NAMES)
            .first()
        )
        ctx["pump_left_timer"] = Timer.objects.filter(
            child=self.object, name="Pump Left"
        ).first()
        ctx["pump_right_timer"] = Timer.objects.filter(
            child=self.object, name="Pump Right"
        ).first()

        def _secs(qs):
            return sum(
                max(0, int((p.end - p.start).total_seconds())) for p in qs
            )

        def _dur(qs):
            total = _secs(qs)
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}"

        left_done = PumpPending.objects.filter(child=self.object, side="left")
        right_done = PumpPending.objects.filter(child=self.object, side="right")
        ctx["pending_pump"] = (
            PumpPending.objects.filter(child=self.object).exists() or None
        )
        ctx["pump_left_pending_duration"] = _dur(left_done) if left_done.exists() else None
        ctx["pump_right_pending_duration"] = _dur(right_done) if right_done.exists() else None
        ctx["pump_left_pending_seconds"] = _secs(left_done)
        ctx["pump_right_pending_seconds"] = _secs(right_done)

        # ── Feed (breast left/right + bottle) timers & pending ──
        ctx["feed_left_timer"] = Timer.objects.filter(
            child=self.object, name="Feed Left"
        ).first()
        ctx["feed_right_timer"] = Timer.objects.filter(
            child=self.object, name="Feed Right"
        ).first()
        ctx["feed_bottle_timer"] = Timer.objects.filter(
            child=self.object, name="Feed Bottle"
        ).first()
        feed_left_done = FeedPending.objects.filter(child=self.object, side="left")
        feed_right_done = FeedPending.objects.filter(child=self.object, side="right")
        feed_bottle_done = FeedPending.objects.filter(child=self.object, side="bottle")
        ctx["pending_feed"] = (
            FeedPending.objects.filter(child=self.object).exists() or None
        )
        ctx["feed_left_pending_duration"] = (
            _dur(feed_left_done) if feed_left_done.exists() else None
        )
        ctx["feed_right_pending_duration"] = (
            _dur(feed_right_done) if feed_right_done.exists() else None
        )
        ctx["feed_bottle_pending_duration"] = (
            _dur(feed_bottle_done) if feed_bottle_done.exists() else None
        )
        ctx["feed_left_pending_seconds"] = _secs(feed_left_done)
        ctx["feed_right_pending_seconds"] = _secs(feed_right_done)
        ctx["feed_bottle_pending_seconds"] = _secs(feed_bottle_done)

        ctx["tummy_timer"] = Timer.objects.filter(
            child=self.object, name=self.TUMMY_TIMER_NAME
        ).first()
        return ctx


class Track(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get(self, request, *args, **kwargs):
        children = Child.objects.count()
        if children == 0:
            return HttpResponseRedirect(reverse("babybuddy:welcome"))
        elif children == 1:
            return HttpResponseRedirect(
                reverse("dashboard:track-child", args={Child.objects.first().slug})
            )
        # Multiple children — go to last visited child's track page if known
        last_slug = request.session.get("last_child_slug")
        if last_slug and Child.objects.filter(slug=last_slug).exists():
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": last_slug})
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["objects"] = Child.objects.all().order_by("last_name", "first_name", "id")
        return context


class BreastfeedAdd(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("core.add_feeding",)
    form_class = BreastfeedForm
    template_name = "dashboard/breastfeed.html"

    def get_success_message(self, cleaned_data):
        return _("Breastfeeding entry added!")

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["child"] = self.get_child()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        timer_pk = self.request.GET.get("timer")
        if timer_pk:
            Timer.objects.filter(pk=timer_pk, child=self.get_child()).delete()
            _broadcast_track(self.kwargs["slug"])
        return response

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class SleepTimerStart(PermissionRequiredMixin, View):
    """Start (or replace) the single Sleep/Nap timer for a child."""

    permission_required = ("core.add_timer",)
    http_method_names = ["post"]

    SLEEP_TIMER_NAMES = ["Sleep", "Nap"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        sleep_type = request.POST.get("sleep_type", "sleep")
        name = "Nap" if sleep_type == "nap" else "Sleep"
        # Remove any existing sleep/nap timer before starting a fresh one
        Timer.objects.filter(child=child, name__in=self.SLEEP_TIMER_NAMES).delete()
        Timer.objects.create(child=child, user=request.user, name=name)
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class SleepTimerSave(PermissionRequiredMixin, View):
    """Directly save a sleep/nap entry from a running timer (no notes)."""

    permission_required = ("core.add_sleep",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        try:
            entry = Sleep(
                child=child,
                start=timer.start,
                end=timezone.now(),
                nap=(timer.name == "Nap"),
                notes="",
            )
            entry.full_clean()
            entry.save()
            timer.stop()
            messages.success(request, _("Sleep entry saved."))
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class SleepTimerNote(PermissionRequiredMixin, FormView):
    """Show a notes form before saving a sleep/nap entry from a running timer."""

    permission_required = ("core.add_sleep",)
    form_class = SleepNoteForm
    template_name = "dashboard/sleep_note.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_timer(self):
        return get_object_or_404(Timer, pk=self.kwargs["pk"], child=self.get_child())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        ctx["timer"] = self.get_timer()
        return ctx

    def form_valid(self, form):
        child = self.get_child()
        timer = self.get_timer()
        notes = form.cleaned_data.get("notes", "")
        try:
            entry = Sleep(
                child=child,
                start=timer.start,
                end=timezone.now(),
                nap=(timer.name == "Nap"),
                notes=notes,
            )
            entry.full_clean()
            entry.save()
            timer.stop()
            messages.success(self.request, _("Sleep entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
            )
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class TummyTimerStart(PermissionRequiredMixin, View):
    """Start (or replace) the single Tummy Time timer for a child."""

    permission_required = ("core.add_timer",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        Timer.objects.filter(child=child, name="Tummy Time").delete()
        Timer.objects.create(child=child, user=request.user, name="Tummy Time")
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class TummyTimerSave(PermissionRequiredMixin, View):
    """Directly save a tummy time entry from a running timer (no milestone)."""

    permission_required = ("core.add_tummytime",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        try:
            entry = TummyTime(
                child=child,
                start=timer.start,
                end=timezone.now(),
                milestone="",
            )
            entry.full_clean()
            entry.save()
            timer.stop()
            messages.success(request, _("Tummy time entry saved."))
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class TummyTimerNote(PermissionRequiredMixin, FormView):
    """Show a milestone form before saving a tummy time entry from a running timer."""

    permission_required = ("core.add_tummytime",)
    form_class = TummyTimeMilestoneForm
    template_name = "dashboard/tummytime_note.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_timer(self):
        return get_object_or_404(Timer, pk=self.kwargs["pk"], child=self.get_child())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        ctx["timer"] = self.get_timer()
        return ctx

    def form_valid(self, form):
        child = self.get_child()
        timer = self.get_timer()
        milestone = form.cleaned_data.get("milestone", "")
        try:
            entry = TummyTime(
                child=child,
                start=timer.start,
                end=timezone.now(),
                milestone=milestone,
            )
            entry.full_clean()
            entry.save()
            timer.stop()
            messages.success(self.request, _("Tummy time entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
            )
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class TimerUse(PermissionRequiredMixin, TemplateView):
    """Show options to log an activity from a running generic timer."""

    permission_required = ("core.view_timer",)
    template_name = "dashboard/timer_use.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        child = self.get_child()
        ctx["child"] = child
        ctx["timer"] = get_object_or_404(Timer, pk=self.kwargs["pk"], child=child)
        return ctx


class TimerUseSave(LoginRequiredMixin, View):
    """POST handler: save an activity directly from a timer; show a toast on conflict."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        activity = request.POST.get("activity")
        end = timezone.now()
        use_url = reverse(
            "dashboard:timer-use",
            kwargs={"slug": kwargs["slug"], "pk": kwargs["pk"]},
        )

        try:
            if activity in ("sleep", "nap"):
                if not request.user.has_perm("core.add_sleep"):
                    messages.error(request, _("Permission denied."))
                    return HttpResponseRedirect(use_url)
                entry = Sleep(
                    child=child,
                    start=timer.start,
                    end=end,
                    nap=(activity == "nap"),
                )
                entry.full_clean()
                entry.save()

            elif activity == "tummytime":
                if not request.user.has_perm("core.add_tummytime"):
                    messages.error(request, _("Permission denied."))
                    return HttpResponseRedirect(use_url)
                entry = TummyTime(child=child, start=timer.start, end=end)
                entry.full_clean()
                entry.save()

            else:
                messages.error(request, _("Unknown activity type."))
                return HttpResponseRedirect(use_url)

            timer.stop()
            _broadcast_track(kwargs["slug"])
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
            )

        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return HttpResponseRedirect(use_url)


class TimerStop(PermissionRequiredMixin, View):
    """Stop (delete) a running Timer and return to the Track page."""

    permission_required = ("core.delete_timer",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        timer.stop()
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class PumpTimerToggle(PermissionRequiredMixin, View):
    """Start or stop a pump timer for left, right, or both sides."""

    permission_required = ("core.add_timer",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        side = kwargs["side"]  # "left", "right", "both"
        now = timezone.now()

        if side == "both":
            running = list(
                Timer.objects.filter(child=child, name__in=["Pump Left", "Pump Right"])
            )
            if running:
                for timer in running:
                    side_label = "left" if timer.name == "Pump Left" else "right"
                    PumpPending.objects.create(
                        child=child, side=side_label, start=timer.start, end=now
                    )
                    timer.stop()
            else:
                for name in ["Pump Left", "Pump Right"]:
                    Timer.objects.create(child=child, user=request.user, name=name)
        else:
            name = "Pump Left" if side == "left" else "Pump Right"
            timer = Timer.objects.filter(child=child, name=name).first()
            if timer:
                PumpPending.objects.create(
                    child=child, side=side, start=timer.start, end=now
                )
                timer.stop()
            else:
                Timer.objects.create(child=child, user=request.user, name=name)

        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class PumpCommit(PermissionRequiredMixin, FormView):
    """Stop any running pump timers, then let the user enter amounts and save."""

    permission_required = ("core.add_pumping",)
    form_class = PumpCommitForm
    template_name = "dashboard/pump_commit.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def _stop_running_timers(self, child):
        """Stop any running pump timers and persist them as PumpPending rows."""
        now = timezone.now()
        for name, side_label in [("Pump Left", "left"), ("Pump Right", "right")]:
            timer = Timer.objects.filter(child=child, name=name).first()
            if timer:
                PumpPending.objects.create(
                    child=child, side=side_label, start=timer.start, end=now
                )
                timer.stop()

    def dispatch(self, request, *args, **kwargs):
        child = self.get_child()
        self._stop_running_timers(child)
        if not PumpPending.objects.filter(child=child).exists():
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
            )
        return super().dispatch(request, *args, **kwargs)

    def _duration_str(self, qs):
        total = sum(max(0, int((p.end - p.start).total_seconds())) for p in qs)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}"

    def _bounds(self, qs):
        """Return (start, end) for a queryset as naive local datetimes (minute
        precision) suitable for prefilling datetime-local inputs."""
        items = list(qs)
        if not items:
            return None, None
        start = timezone.localtime(min(p.start for p in items)).replace(
            second=0, microsecond=0, tzinfo=None
        )
        end = timezone.localtime(max(p.end for p in items)).replace(
            second=0, microsecond=0, tzinfo=None
        )
        return start, end

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        child = self.get_child()
        pending = PumpPending.objects.filter(child=child)
        start, end = self._bounds(pending)
        kwargs.update({"start": start, "end": end})
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        child = self.get_child()
        left = PumpPending.objects.filter(child=child, side="left")
        right = PumpPending.objects.filter(child=child, side="right")
        ctx["child"] = child
        ctx["has_left"] = left.exists()
        ctx["has_right"] = right.exists()
        ctx["left_duration"] = self._duration_str(left) if left.exists() else None
        ctx["right_duration"] = self._duration_str(right) if right.exists() else None
        return ctx

    def form_valid(self, form):
        child = self.get_child()
        pending = PumpPending.objects.filter(child=child)
        left = pending.filter(side="left")
        right = pending.filter(side="right")

        amount_left = form.cleaned_data.get("amount_left") or 0
        amount_right = form.cleaned_data.get("amount_right") or 0
        notes = form.cleaned_data.get("notes", "")

        start = form.cleaned_data.get("start")
        end = form.cleaned_data.get("end")
        # Only attribute a side's amount if that side actually had a timer.
        side_left = amount_left if left.exists() else None
        side_right = amount_right if right.exists() else None
        amount = (side_left or 0) + (side_right or 0)

        try:
            entry = Pumping(
                child=child,
                start=start,
                end=end,
                amount=amount,
                amount_left=side_left,
                amount_right=side_right,
                notes=notes,
            )
            entry.full_clean()
            entry.save()
            pending.delete()
            messages.success(self.request, _("Pumping entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
            )
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class PumpSideDiscard(PermissionRequiredMixin, View):
    """Delete a single running pump timer without saving to pending (full reset)."""

    permission_required = ("core.delete_timer",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        side = kwargs["side"]  # "left" or "right"
        name = "Pump Left" if side == "left" else "Pump Right"
        Timer.objects.filter(child=child, name=name).delete()
        PumpPending.objects.filter(child=child, side=side).delete()
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class PumpPendingDiscard(PermissionRequiredMixin, View):
    """Discard all pending pump data and stop any running pump timers."""

    permission_required = ("core.add_pumping",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        Timer.objects.filter(child=child, name__in=["Pump Left", "Pump Right"]).delete()
        PumpPending.objects.filter(child=child).delete()
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


FEED_TIMER_BY_SIDE = {
    "left": "Feed Left",
    "right": "Feed Right",
    "bottle": "Feed Bottle",
}


class FeedTimerToggle(PermissionRequiredMixin, View):
    """Start or stop a feed timer for the left breast, right breast, or bottle."""

    permission_required = ("core.add_timer",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        side = kwargs["side"]  # "left", "right", "bottle"
        name = FEED_TIMER_BY_SIDE.get(side)
        if not name:
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
            )
        now = timezone.now()
        timer = Timer.objects.filter(child=child, name=name).first()
        if timer:
            FeedPending.objects.create(
                child=child, side=side, start=timer.start, end=now
            )
            timer.stop()
        else:
            Timer.objects.create(child=child, user=request.user, name=name)
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class FeedCommit(PermissionRequiredMixin, FormView):
    """Stop any running feed timers, then let the user review and save feedings."""

    permission_required = ("core.add_feeding",)
    form_class = FeedCommitForm
    template_name = "dashboard/feed_commit.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def _stop_running_timers(self, child):
        """Stop any running feed timers and persist them as FeedPending rows."""
        now = timezone.now()
        for side, name in FEED_TIMER_BY_SIDE.items():
            timer = Timer.objects.filter(child=child, name=name).first()
            if timer:
                FeedPending.objects.create(
                    child=child, side=side, start=timer.start, end=now
                )
                timer.stop()

    def dispatch(self, request, *args, **kwargs):
        child = self.get_child()
        self._stop_running_timers(child)
        if not FeedPending.objects.filter(child=child).exists():
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
            )
        return super().dispatch(request, *args, **kwargs)

    def _bounds(self, qs):
        """Return (start, end) for a queryset as naive local datetimes (minute
        precision) suitable for prefilling datetime-local inputs."""
        items = list(qs)
        if not items:
            return None, None
        start = timezone.localtime(min(p.start for p in items)).replace(
            second=0, microsecond=0, tzinfo=None
        )
        end = timezone.localtime(max(p.end for p in items)).replace(
            second=0, microsecond=0, tzinfo=None
        )
        return start, end

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        child = self.get_child()
        pending = FeedPending.objects.filter(child=child)
        breast = pending.filter(side__in=["left", "right"])
        bottle = pending.filter(side="bottle")
        breast_start, breast_end = self._bounds(breast)
        bottle_start, bottle_end = self._bounds(bottle)
        kwargs.update(
            {
                "has_breast": breast.exists(),
                "has_bottle": bottle.exists(),
                "breast_start": breast_start,
                "breast_end": breast_end,
                "bottle_start": bottle_start,
                "bottle_end": bottle_end,
            }
        )
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        child = self.get_child()
        left = FeedPending.objects.filter(child=child, side="left")
        right = FeedPending.objects.filter(child=child, side="right")
        bottle = FeedPending.objects.filter(child=child, side="bottle")
        ctx["child"] = child
        ctx["has_left"] = left.exists()
        ctx["has_right"] = right.exists()
        ctx["has_bottle"] = bottle.exists()
        ctx["has_breast"] = left.exists() or right.exists()
        return ctx

    def form_valid(self, form):
        child = self.get_child()
        pending = FeedPending.objects.filter(child=child)
        left = pending.filter(side="left")
        right = pending.filter(side="right")
        bottle = pending.filter(side="bottle")

        notes = form.cleaned_data.get("notes", "")
        created = []

        try:
            # ── Breastfeeding entry (left and/or right combined) ──
            breast = list(left) + list(right)
            if breast:
                if left.exists() and right.exists():
                    method = "both breasts"
                elif left.exists():
                    method = "left breast"
                else:
                    method = "right breast"
                # Exact per-side durations from the individual timer sessions.
                left_dur = sum(
                    (p.end - p.start for p in left), timezone.timedelta()
                )
                right_dur = sum(
                    (p.end - p.start for p in right), timezone.timedelta()
                )
                entry = Feeding(
                    child=child,
                    start=form.cleaned_data.get("breast_start"),
                    end=form.cleaned_data.get("breast_end"),
                    type="breast milk",
                    method=method,
                    duration_left=left_dur,
                    duration_right=right_dur,
                    notes=notes,
                )
                entry.full_clean()
                created.append(entry)

            # ── Bottle feeding entry/entries ──
            if bottle.exists():
                bottle_type = form.cleaned_data.get("bottle_type") or "breast milk"
                bottle_start = form.cleaned_data.get("bottle_start")
                bottle_end = form.cleaned_data.get("bottle_end")
                amount_bm = form.cleaned_data.get("bottle_amount_breast_milk") or None
                amount_f = form.cleaned_data.get("bottle_amount_formula") or None

                if bottle_type == "both":
                    # Two separate entries: breast milk + formula.
                    bottle_entries = [
                        ("breast milk", amount_bm),
                        ("formula", amount_f),
                    ]
                elif bottle_type == "formula":
                    bottle_entries = [("formula", amount_f or amount_bm)]
                else:
                    bottle_entries = [("breast milk", amount_bm or amount_f)]

                for entry_type, entry_amount in bottle_entries:
                    entry = Feeding(
                        child=child,
                        start=bottle_start,
                        end=bottle_end,
                        type=entry_type,
                        method="bottle",
                        amount=entry_amount,
                        notes=notes,
                    )
                    entry.full_clean()
                    created.append(entry)

            for entry in created:
                entry.save()
            pending.delete()
            messages.success(self.request, _("Feeding entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(
                reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
            )
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class FeedSideDiscard(PermissionRequiredMixin, View):
    """Delete a single feed timer/side without saving (full reset for that side)."""

    permission_required = ("core.delete_timer",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        side = kwargs["side"]  # "left", "right", "bottle"
        name = FEED_TIMER_BY_SIDE.get(side)
        if name:
            Timer.objects.filter(child=child, name=name).delete()
            FeedPending.objects.filter(child=child, side=side).delete()
            _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class FeedPendingDiscard(PermissionRequiredMixin, View):
    """Discard all pending feed data and stop any running feed timers."""

    permission_required = ("core.add_feeding",)
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        child = get_object_or_404(Child, slug=kwargs["slug"])
        Timer.objects.filter(
            child=child, name__in=list(FEED_TIMER_BY_SIDE.values())
        ).delete()
        FeedPending.objects.filter(child=child).delete()
        _broadcast_track(kwargs["slug"])
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class FeedQuickAdd(PermissionRequiredMixin, FormView):
    """Manually log a completed bottle feeding without running a timer.

    The end time is prefilled with the current time (adjustable); the user
    enters the start time. Bottle feeding only (breast milk / formula / both) --
    breastfeeding is logged from the Breast Feed & Pump card.
    """

    permission_required = ("core.add_feeding",)
    form_class = FeedQuickForm
    template_name = "dashboard/feed_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["child"] = self.get_child()
        settings = getattr(self.request.user, "settings", None)
        kwargs["roller_step"] = getattr(settings, "bottle_amount_roller_step", 10)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def form_valid(self, form):
        try:
            entries = form.build_entries()
            for entry in entries:
                entry.full_clean()
            for entry in entries:
                entry.save()
            messages.success(self.request, _("Feeding entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(self.get_success_url())
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class BreastfeedQuickAdd(PermissionRequiredMixin, FormView):
    """Manually log a completed breastfeeding without running a timer.

    Mirrors FeedQuickAdd (the bottle Quick Log): start/end roller time inputs
    prefilled to "now", plus a side selector.
    """

    permission_required = ("core.add_feeding",)
    form_class = BreastfeedQuickForm
    template_name = "dashboard/breastfeed_quick_add.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["child"] = self.get_child()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def form_valid(self, form):
        try:
            entry = form.build_entry()
            entry.full_clean()
            entry.save()
            messages.success(self.request, _("Breastfeeding entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(self.get_success_url())
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class PumpQuickAdd(PermissionRequiredMixin, FormView):
    """Manually log a completed pumping session without running a timer.

    Mirrors FeedQuickAdd (the bottle Quick Log): start/end roller time inputs
    prefilled to "now", plus an amount stepper.
    """

    permission_required = ("core.add_pumping",)
    form_class = PumpQuickForm
    template_name = "dashboard/pump_quick_add.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["child"] = self.get_child()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def form_valid(self, form):
        try:
            entry = form.build_entry()
            entry.full_clean()
            entry.save()
            messages.success(self.request, _("Pumping entry saved."))
            _broadcast_track(self.kwargs["slug"])
            return HttpResponseRedirect(self.get_success_url())
        except ValidationError as e:
            for msg in e.messages:
                form.add_error(None, msg)
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class QuickPumpSave(PermissionRequiredMixin, View):
    """Show a streamlined pumping form seeded from a generic timer; save on POST."""

    permission_required = ("core.add_pumping",)
    template_name = "dashboard/pump_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        child = self.get_child()
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        return render(request, self.template_name, {"child": child, "timer": timer})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        try:
            amount = float(request.POST.get("amount") or 0)
        except (ValueError, TypeError):
            amount = 0
        notes = request.POST.get("notes", "").strip()
        end = timezone.now()
        try:
            entry = Pumping(
                child=child,
                start=timer.start,
                end=end,
                amount=amount,
                notes=notes,
            )
            entry.full_clean()
            entry.save()
            timer.stop()
            messages.success(request, _("Pumping entry saved."))
            _broadcast_track(kwargs["slug"])
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class QuickBreastfeedSave(PermissionRequiredMixin, View):
    """Show a streamlined breastfeed form seeded from a generic timer; save on POST."""

    permission_required = ("core.add_feeding",)
    template_name = "dashboard/breastfeed_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        child = self.get_child()
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        return render(request, self.template_name, {"child": child, "timer": timer})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        timer = get_object_or_404(Timer, pk=kwargs["pk"], child=child)
        method = request.POST.get("method", "")
        notes = request.POST.get("notes", "").strip()
        valid_methods = {"left breast", "right breast", "both breasts"}
        if method not in valid_methods:
            messages.error(request, _("Please select a side."))
            return render(request, self.template_name, {"child": child, "timer": timer})
        end = timezone.now()
        try:
            entry = Feeding(
                child=child,
                start=timer.start,
                end=end,
                type="breast milk",
                method=method,
                notes=notes,
            )
            entry.full_clean()
            entry.save()
            timer.stop()
            messages.success(request, _("Breastfeeding entry saved."))
            _broadcast_track(kwargs["slug"])
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
        return HttpResponseRedirect(
            reverse("dashboard:track-child", kwargs={"slug": kwargs["slug"]})
        )


class DiaperChangeAdd(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("core.add_diaperchange",)
    form_class = DiaperChangeQuickForm
    template_name = "dashboard/diaper.html"

    def get_success_message(self, cleaned_data):
        return _("Diaper change added!")

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["child"] = self.get_child()
        kwargs["diaper_type"] = self.request.GET.get("type", "wet")
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class BottleFeedAdd(PermissionRequiredMixin, FormView):
    permission_required = ("core.add_feeding",)
    form_class = BottleFeedForm
    template_name = "dashboard/bottlefeed.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        child = self.get_child()
        kwargs["child"] = child
        # When launched from a (quick) timer, seed the start time from the
        # timer's start so the feeding is recorded at the time it began,
        # not the moment the form happened to be opened.
        timer_pk = self.request.GET.get("timer")
        if timer_pk:
            timer = Timer.objects.filter(pk=timer_pk, child=child).first()
            if timer:
                kwargs["start"] = timezone.localtime(timer.start)
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Bottle feeding entry added!"))
        timer_pk = self.request.GET.get("timer")
        if timer_pk:
            Timer.objects.filter(pk=timer_pk, child=self.get_child()).delete()
            _broadcast_track(self.kwargs["slug"])
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})


class HealthTempQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_temperature",)
    template_name = "dashboard/health_temp_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        raw = request.POST.get("temperature", "").strip()
        unit = request.POST.get("unit", "F").strip()
        notes = request.POST.get("notes", "").strip()
        try:
            val = float(raw)
            val_c = (val - 32) * 5 / 9 if unit == "F" else val
            entry = Temperature(child=child, temperature=val_c, time=timezone.now(), notes=notes or None)
            entry.full_clean()
            entry.save()
            messages.success(request, _("Temperature recorded."))
        except (ValueError, ValidationError) as e:
            msgs = e.messages if hasattr(e, "messages") else [str(e)]
            for m in msgs:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]}))


class HealthHub(PermissionRequiredMixin, View):
    permission_required = ("core.view_temperature",)
    template_name = "dashboard/health_hub_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})


class HealthBMIQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_bmi",)
    template_name = "dashboard/health_bmi_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        raw = request.POST.get("bmi", "").strip()
        notes = request.POST.get("notes", "").strip()
        try:
            entry = BMI(child=child, bmi=float(raw), date=timezone.localdate(), notes=notes or None)
            entry.full_clean()
            entry.save()
            messages.success(request, _("BMI recorded."))
        except (ValueError, ValidationError) as e:
            msgs = e.messages if hasattr(e, "messages") else [str(e)]
            for m in msgs:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:health-hub", kwargs={"slug": self.kwargs["slug"]}))


class HealthHeadCircQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_headcircumference",)
    template_name = "dashboard/health_headcirc_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        raw = request.POST.get("head_circumference", "").strip()
        unit = request.POST.get("unit", "cm").strip()
        notes = request.POST.get("notes", "").strip()
        try:
            val = float(raw)
            val_cm = val if unit == "cm" else val * 2.54
            entry = HeadCircumference(child=child, head_circumference=round(val_cm, 2), date=timezone.localdate(), notes=notes or None)
            entry.full_clean()
            entry.save()
            messages.success(request, _("Head circumference recorded."))
        except (ValueError, ValidationError) as e:
            msgs = e.messages if hasattr(e, "messages") else [str(e)]
            for m in msgs:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:health-hub", kwargs={"slug": self.kwargs["slug"]}))


class HealthHeightQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_height",)
    template_name = "dashboard/health_height_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        raw = request.POST.get("height", "").strip()
        unit = request.POST.get("unit", "cm").strip()
        notes = request.POST.get("notes", "").strip()
        try:
            val = float(raw)
            val_cm = val if unit == "cm" else val * 2.54
            entry = Height(child=child, height=round(val_cm, 2), date=timezone.localdate(), notes=notes or None)
            entry.full_clean()
            entry.save()
            messages.success(request, _("Height recorded."))
        except (ValueError, ValidationError) as e:
            msgs = e.messages if hasattr(e, "messages") else [str(e)]
            for m in msgs:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:health-hub", kwargs={"slug": self.kwargs["slug"]}))


class HealthWeightQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_weight",)
    template_name = "dashboard/health_weight_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        raw = request.POST.get("weight", "").strip()
        unit = request.POST.get("unit", "kg").strip()
        notes = request.POST.get("notes", "").strip()
        try:
            val = float(raw)
            val_kg = val if unit == "kg" else val / 2.20462
            entry = Weight(child=child, weight=round(val_kg, 3), date=timezone.localdate(), notes=notes or None)
            entry.full_clean()
            entry.save()
            messages.success(request, _("Weight recorded."))
        except (ValueError, ValidationError) as e:
            msgs = e.messages if hasattr(e, "messages") else [str(e)]
            for m in msgs:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:health-hub", kwargs={"slug": self.kwargs["slug"]}))


class HealthVaccineQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_vaccine",)
    template_name = "dashboard/health_vaccine_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        name = request.POST.get("name", "").strip()
        notes = request.POST.get("notes", "").strip()
        if not name:
            messages.error(request, _("Vaccine name is required."))
            return render(request, self.template_name, {"child": child})
        try:
            entry = Vaccine(child=child, name=name, date=timezone.now(), notes=notes or None)
            entry.full_clean()
            entry.save()
            messages.success(request, _("Vaccine recorded."))
        except ValidationError as e:
            for m in e.messages:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]}))


class HealthMedQuick(PermissionRequiredMixin, View):
    permission_required = ("core.add_medication",)
    template_name = "dashboard/health_med_quick.html"

    def get_child(self):
        return get_object_or_404(Child, slug=self.kwargs["slug"])

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"child": self.get_child()})

    def post(self, request, *args, **kwargs):
        child = self.get_child()
        name = request.POST.get("name", "").strip()
        notes = request.POST.get("notes", "").strip()
        dosage_unit = request.POST.get("dosage_unit", "").strip()
        raw_dosage = request.POST.get("dosage", "").strip()
        if not name:
            messages.error(request, _("Medication name is required."))
            return render(request, self.template_name, {"child": child})
        try:
            dosage = float(raw_dosage) if raw_dosage else None
            entry = Medication(
                child=child, name=name, dosage=dosage, dosage_unit=dosage_unit,
                time=timezone.now(), notes=notes or None
            )
            entry.full_clean()
            entry.save()
            messages.success(request, _("Medication recorded."))
        except (ValueError, ValidationError) as e:
            msgs = e.messages if hasattr(e, "messages") else [str(e)]
            for m in msgs:
                messages.error(request, m)
        return HttpResponseRedirect(reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]}))
