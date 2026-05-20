# -*- coding: utf-8 -*-
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic.base import TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, FormView

from babybuddy.mixins import LoginRequiredMixin, PermissionRequiredMixin
from core.models import Child, Pumping, Sleep, Timer, TummyTime

from .forms import BottleFeedForm, BreastfeedForm, DiaperChangeQuickForm, PumpCommitForm, SleepNoteForm, TummyTimeMilestoneForm
from .models import PumpPending


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
        return super(Dashboard, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        context["objects"] = Child.objects.all().order_by("last_name", "first_name", "id")
        return context


class ChildDashboard(PermissionRequiredMixin, DetailView):
    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/child.html"


class ChildTrack(PermissionRequiredMixin, DetailView):
    model = Child
    permission_required = ("core.view_child",)
    template_name = "dashboard/track.html"

    SLEEP_TIMER_NAMES = ["Sleep", "Nap"]
    PUMP_TIMER_NAMES = ["Pump Left", "Pump Right"]
    TUMMY_TIMER_NAME = "Tummy Time"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        excluded = self.SLEEP_TIMER_NAMES + self.PUMP_TIMER_NAMES + [self.TUMMY_TIMER_NAME]
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

        start = min(p.start for p in pending)
        end = max(p.end for p in pending)
        amount = (amount_left if left.exists() else 0) + (amount_right if right.exists() else 0)

        try:
            entry = Pumping(
                child=child,
                start=start,
                end=end,
                amount=amount,
                notes=notes,
            )
            entry.full_clean()
            entry.save()
            pending.delete()
            messages.success(self.request, _("Pumping entry saved."))
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
        kwargs["child"] = self.get_child()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["child"] = self.get_child()
        return ctx

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Bottle feeding entry added!"))
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("dashboard:track-child", kwargs={"slug": self.kwargs["slug"]})
