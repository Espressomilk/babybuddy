# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404
from django.utils import timezone, translation
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

from rest_framework import viewsets, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.schemas.openapi import AutoSchema

from core import models
from core.utils import duration_string, group_feeding_sessions
from babybuddy import models as babybuddy_models

from . import serializers, filters


def _format_amount(value):
    """Format a feeding amount, dropping a trailing ``.0``."""
    value = round(value or 0, 1)
    if value == int(value):
        return str(int(value))
    return "{:.1f}".format(value)


def _pump_side_label(sides):
    """Spoken side label for pump messages: both / left / right."""
    s = set(sides)
    if {"left", "right"} <= s:
        return _("both")
    if "right" in s:
        return _("right")
    return _("left")


class BMIViewSet(viewsets.ModelViewSet):
    queryset = models.BMI.objects.all()
    serializer_class = serializers.BMISerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("child", "date")
    ordering = "-date"

    def get_view_name(self):
        """
        Gets the view name without changing the case of the model verbose name.
        """
        name = models.BMI._meta.verbose_name
        if self.suffix:
            name += " " + self.suffix
        return name


class ChildViewSet(viewsets.ModelViewSet):
    queryset = models.Child.objects.all()
    serializer_class = serializers.ChildSerializer
    lookup_field = "slug"
    filterset_fields = (
        "id",
        "first_name",
        "last_name",
        "slug",
        "birth_date",
        "birth_time",
    )
    ordering_fields = ("birth_date", "birth_time", "first_name", "last_name", "slug")
    ordering = ["-birth_date", "-birth_time"]


class DiaperChangeViewSet(viewsets.ModelViewSet):
    queryset = models.DiaperChange.objects.all()
    serializer_class = serializers.DiaperChangeSerializer
    filterset_class = filters.DiaperChangeFilter
    ordering_fields = ("amount", "time")
    ordering = "-time"


class FeedingViewSet(viewsets.ModelViewSet):
    queryset = models.Feeding.objects.all()
    serializer_class = serializers.FeedingSerializer
    filterset_class = filters.FeedingFilter
    ordering_fields = ("amount", "duration", "end", "start")
    ordering = "-end"


class HeadCircumferenceViewSet(viewsets.ModelViewSet):
    queryset = models.HeadCircumference.objects.all()
    serializer_class = serializers.HeadCircumferenceSerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("date", "head_circumference")
    ordering = "-date"


class HeightViewSet(viewsets.ModelViewSet):
    queryset = models.Height.objects.all()
    serializer_class = serializers.HeightSerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("date", "height")
    ordering = "-date"


class MedicationViewSet(viewsets.ModelViewSet):
    queryset = models.Medication.objects.all()
    serializer_class = serializers.MedicationSerializer
    filterset_class = filters.MedicationFilter
    ordering_fields = ("time", "name", "dosage")
    ordering = "-time"

    def get_view_name(self):
        # Use model's verbose_name for consistency with user-facing strings
        name = self.queryset.model._meta.verbose_name
        suffix = getattr(self, "suffix", None)
        if suffix:
            name = f"{name} {suffix}"
        return name


class NoteViewSet(viewsets.ModelViewSet):
    queryset = models.Note.objects.all()
    serializer_class = serializers.NoteSerializer
    filterset_class = filters.NoteFilter
    ordering_fields = "time"
    ordering = "-time"


class PumpingViewSet(viewsets.ModelViewSet):
    queryset = models.Pumping.objects.all()
    serializer_class = serializers.PumpingSerializer
    filterset_class = filters.PumpingFilter
    ordering_fields = ("amount", "duration", "end", "start")
    ordering = "-end"


class SleepViewSet(viewsets.ModelViewSet):
    queryset = models.Sleep.objects.all()
    serializer_class = serializers.SleepSerializer
    filterset_class = filters.SleepFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-end"


class TagViewSet(viewsets.ModelViewSet):
    queryset = models.Tag.objects.all()
    serializer_class = serializers.TagSerializer
    lookup_field = "slug"
    filterset_fields = ("last_used", "name")
    ordering_fields = ("last_used", "name", "slug")
    ordering = "name"


class TemperatureViewSet(viewsets.ModelViewSet):
    queryset = models.Temperature.objects.all()
    serializer_class = serializers.TemperatureSerializer
    filterset_class = filters.TemperatureFilter
    ordering_fields = ("temperature", "time")
    ordering = "-time"


class TimerViewSet(viewsets.ModelViewSet):
    queryset = models.Timer.objects.all()
    serializer_class = serializers.TimerSerializer
    filterset_class = filters.TimerFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-start"

    @action(detail=True, methods=["patch"])
    def restart(self, request, pk=None):
        timer = self.get_object()
        timer.restart()
        return Response(self.serializer_class(timer).data)


class TummyTimeViewSet(viewsets.ModelViewSet):
    queryset = models.TummyTime.objects.all()
    serializer_class = serializers.TummyTimeSerializer
    filterset_class = filters.TummyTimeFilter
    ordering_fields = ("duration", "end", "start")
    ordering = "-start"


class WeightViewSet(viewsets.ModelViewSet):
    queryset = models.Weight.objects.all()
    serializer_class = serializers.WeightSerializer
    filterset_fields = ("child", "date")
    ordering_fields = ("date", "weight")
    ordering = "-date"


class ProfileView(views.APIView):
    schema = AutoSchema(operation_id_base="CurrentProfile")

    action = "get"
    basename = "profile"

    queryset = babybuddy_models.Settings.objects.all()
    serializer_class = serializers.ProfileSerializer

    def get(self, request):
        settings = get_object_or_404(
            babybuddy_models.Settings.objects, user=request.user
        )
        serializer = self.serializer_class(settings)
        return Response(serializer.data)


class QuickStatusView(views.APIView):
    """
    A compact, Siri-friendly status summary for a child.

    Returns a ready-to-speak ``speech`` string (localized to the requesting
    user's language) plus structured fields. Intended to back an Apple Shortcut
    that asks Siri something like "How is the baby doing?".
    """

    schema = None
    action = "get"
    basename = "quick-status"

    queryset = models.Child.objects.all()

    BREAST_METHODS = ("left breast", "right breast", "both breasts")

    def get(self, request):
        child_slug = request.query_params.get("child")
        if child_slug:
            child = get_object_or_404(models.Child, slug=child_slug)
        else:
            children = models.Child.objects.all()
            if children.count() != 1:
                return Response(
                    {
                        "detail": "Multiple children exist; pass ?child=<slug>.",
                        "children": list(
                            children.values_list("slug", flat=True)
                        ),
                    },
                    status=400,
                )
            child = children.first()

        language = getattr(
            getattr(request.user, "settings", None), "language", None
        )
        with translation.override(language or translation.get_language()):
            data = self._build(child)
        return Response(data)

    def _method_label(self, feeding):
        if feeding.method in self.BREAST_METHODS:
            return _("breast")
        if feeding.method == "bottle":
            if feeding.type == "formula":
                return _("formula bottle")
            return _("breast-milk bottle")
        return feeding.get_method_display()

    def _build(self, child):
        now = timezone.localtime()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        feedings_today = models.Feeding.objects.filter(
            child=child, start__gte=day_start
        ).order_by("start")
        diapers_today = models.DiaperChange.objects.filter(
            child=child, time__gte=day_start
        )

        breast_total = timezone.timedelta()
        bottle_total = 0.0
        for feeding in feedings_today:
            if feeding.method in self.BREAST_METHODS:
                breast_total += feeding.duration_left or timezone.timedelta()
                breast_total += feeding.duration_right or timezone.timedelta()
            elif feeding.method == "bottle":
                bottle_total += feeding.amount or 0

        sessions_today = len(group_feeding_sessions(feedings_today))
        wet = diapers_today.filter(wet=True).count()
        solid = diapers_today.filter(solid=True).count()

        last = models.Feeding.objects.filter(child=child).order_by("-start").first()

        parts = []
        if last is None:
            parts.append(
                _("No feedings recorded yet for %(child)s.")
                % {"child": child.first_name}
            )
        else:
            parts.append(
                _("%(child)s was last fed %(since)s ago (%(method)s).")
                % {
                    "child": child.first_name,
                    "since": timesince(timezone.localtime(last.start), now),
                    "method": self._method_label(last),
                }
            )
            if last.method == "bottle" and last.amount:
                parts.append(
                    _("Last amount %(amount)s ml.")
                    % {"amount": _format_amount(last.amount)}
                )

        parts.append(
            _(
                "Today: %(sessions)s feeding sessions, %(breast)s of "
                "breastfeeding, %(bottle)s ml from bottles, %(wet)s wet and "
                "%(solid)s solid diapers."
            )
            % {
                "sessions": sessions_today,
                "breast": duration_string(breast_total, "m"),
                "bottle": _format_amount(bottle_total),
                "wet": wet,
                "solid": solid,
            }
        )

        return {
            "child": child.first_name,
            "speech": " ".join(parts),
            "last_feeding": (
                None if last is None else timezone.localtime(last.start).isoformat()
            ),
            "today": {
                "feeding_sessions": sessions_today,
                "breastfeeding_minutes": int(breast_total.total_seconds() // 60),
                "bottle_ml": round(bottle_total, 1),
                "wet_diapers": wet,
                "solid_diapers": solid,
            },
        }


FEED_TIMER_NAMES = {"left": "Feed Left", "right": "Feed Right"}
PUMP_TIMER_NAMES = {"left": "Pump Left", "right": "Pump Right"}


class _QuickActionBase(views.APIView):
    """Shared helpers for Siri-friendly quick-action write endpoints."""

    schema = None

    def get_child(self, request):
        """Resolve the target child. Returns (child, error_response)."""
        slug = request.query_params.get("child") or request.data.get("child")
        if slug:
            return get_object_or_404(models.Child, slug=slug), None
        children = models.Child.objects.all()
        if children.count() != 1:
            return None, Response(
                {
                    "detail": "Multiple children exist; pass child=<slug>.",
                    "children": list(children.values_list("slug", flat=True)),
                },
                status=400,
            )
        return children.first(), None

    def language(self, request):
        return (
            getattr(getattr(request.user, "settings", None), "language", None)
            or translation.get_language()
        )

    def _param(self, request, key, default=None):
        return request.query_params.get(key) or request.data.get(key) or default

    def _broadcast(self, slug):
        try:
            from dashboard.views import _broadcast_track

            _broadcast_track(slug)
        except Exception:
            pass


class QuickDiaperView(_QuickActionBase):
    """POST /api/quick/diaper?type=wet|solid|mixed"""

    queryset = models.DiaperChange.objects.all()

    def _type_label(self, wet, solid):
        if wet and solid:
            return _("wet and solid")
        if solid:
            return _("solid")
        return _("wet")

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        # Accept either explicit type/color params, or a free-text phrase
        # (e.g. dictated "solid yellow" / "大便 黄色") that we parse here so a
        # single Siri shortcut can cover every type/color combination.
        text = (self._param(request, "text", "") or "").lower()
        dtype = self._param(request, "type")
        color = self._param(request, "color")

        if not dtype and text:
            has_mixed = any(k in text for k in ("mixed", "both", "混合"))
            has_wet = any(
                k in text for k in ("wet", "pee", "urine", "小便", "尿")
            )
            has_solid = any(
                k in text
                for k in ("solid", "poop", "poo", "stool", "大便", "便便", "粑粑")
            )
            if has_mixed or (has_wet and has_solid):
                dtype = "mixed"
            elif has_solid:
                dtype = "solid"
            elif has_wet:
                dtype = "wet"

        if not color and text:
            color_keywords = (
                ("yellow", ("yellow", "黄")),
                ("green", ("green", "绿")),
                ("brown", ("brown", "棕", "褐")),
                ("black", ("black", "黑")),
            )
            for candidate, keys in color_keywords:
                if any(k in text for k in keys):
                    color = candidate
                    break

        color = (color or "").lower()
        if color not in ("black", "brown", "green", "yellow"):
            color = ""
        # A colour with no stated type means a solid diaper; otherwise wet.
        if not dtype:
            dtype = "solid" if color else "wet"
        dtype = dtype.lower()
        wet = dtype in ("wet", "mixed", "both")
        solid = dtype in ("solid", "mixed", "both")
        # Solid / mixed diapers should always record a colour.
        needs_color = solid and not color
        canonical = "mixed" if (wet and solid) else ("solid" if solid else "wet")

        preview = str(
            self._param(request, "preview")
            or self._param(request, "dry_run")
            or ""
        ).lower() in ("1", "true", "yes")

        if preview:
            with translation.override(self.language(request)):
                label = self._type_label(wet, solid)
                if color:
                    color_label = models.DiaperChange(color=color).get_color_display()
                    speech = _(
                        "Log a %(color)s %(type)s diaper for %(child)s?"
                    ) % {
                        "color": color_label,
                        "type": label,
                        "child": child.first_name,
                    }
                else:
                    speech = _("Log a %(type)s diaper for %(child)s?") % {
                        "type": label,
                        "child": child.first_name,
                    }
            return Response(
                {
                    "type": canonical,
                    "color": color,
                    "needs_color": 1 if needs_color else 0,
                    "speech": speech,
                }
            )

        change = models.DiaperChange(
            child=child, time=timezone.now(), wet=wet, solid=solid, color=color
        )
        try:
            change.full_clean()
            change.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
        self._broadcast(child.slug)
        with translation.override(self.language(request)):
            label = self._type_label(wet, solid)
            if color:
                speech = _(
                    "Logged a %(color)s %(type)s diaper for %(child)s."
                ) % {
                    "color": change.get_color_display(),
                    "type": label,
                    "child": child.first_name,
                }
            else:
                speech = _("Logged a %(type)s diaper for %(child)s.") % {
                    "type": label,
                    "child": child.first_name,
                }
        return Response({"speech": speech}, status=201)


class QuickBottleView(_QuickActionBase):
    """POST /api/quick/bottle?amount=90&type=breast_milk|formula"""

    queryset = models.Feeding.objects.all()

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        amount = self._param(request, "amount")
        try:
            amount = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount = None
        ftype = (self._param(request, "type", "breast_milk")).lower()
        feeding_type = "formula" if ftype in ("formula", "f") else "breast milk"
        now = timezone.now()
        feeding = models.Feeding(
            child=child,
            start=now,
            end=now,
            type=feeding_type,
            method="bottle",
            amount=amount,
        )
        try:
            feeding.full_clean()
            feeding.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
        self._broadcast(child.slug)
        with translation.override(self.language(request)):
            type_label = _("formula") if feeding_type == "formula" else _("breast milk")
            if amount:
                speech = _(
                    "Logged a %(amount)s ml %(type)s bottle for %(child)s."
                ) % {
                    "amount": _format_amount(amount),
                    "type": type_label,
                    "child": child.first_name,
                }
            else:
                speech = _("Logged a %(type)s bottle for %(child)s.") % {
                    "type": type_label,
                    "child": child.first_name,
                }
        return Response({"speech": speech}, status=201)


class QuickBreastStartView(_QuickActionBase):
    """POST /api/quick/breast/start?side=left|right|both"""

    queryset = models.Feeding.objects.all()

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        # Breastfeeding is one side at a time: require left or right.
        side = (self._param(request, "side", "")).lower()
        if side not in ("left", "right"):
            with translation.override(self.language(request)):
                speech = _(
                    "Please choose a side for %(child)s: say left or right."
                ) % {"child": child.first_name}
            return Response({"speech": speech}, status=200)
        name = FEED_TIMER_NAMES[side]
        if models.Timer.objects.filter(child=child, name=name).exists():
            with translation.override(self.language(request)):
                speech = _("Breastfeeding is already running for %(child)s.") % {
                    "child": child.first_name
                }
            return Response({"speech": speech}, status=200)
        # One side at a time: stop the other side (into pending) if running.
        other = "right" if side == "left" else "left"
        other_timer = models.Timer.objects.filter(
            child=child, name=FEED_TIMER_NAMES[other]
        ).first()
        stopped_other = False
        if other_timer:
            from dashboard.models import FeedPending

            FeedPending.objects.create(
                child=child, side=other, start=other_timer.start, end=timezone.now()
            )
            other_timer.stop()
            stopped_other = True
        models.Timer.objects.create(child=child, user=request.user, name=name)
        self._broadcast(child.slug)
        with translation.override(self.language(request)):
            speech = _("Started breastfeeding (%(side)s) for %(child)s.") % {
                "side": self._side_label([side]),
                "child": child.first_name,
            }
            if stopped_other:
                speech += " " + _("Stopped the %(side)s side.") % {
                    "side": self._side_label([other])
                }
        return Response({"speech": speech}, status=201)

    def _side_label(self, sides):
        if "left" in sides and "right" in sides:
            return _("both sides")
        if "right" in sides:
            return _("right")
        return _("left")


class QuickBreastStopView(_QuickActionBase):
    """POST /api/quick/breast/stop — stop the breast timer(s) into pending (no log)."""

    queryset = models.Feeding.objects.all()

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        now = timezone.now()
        left = models.Timer.objects.filter(
            child=child, name=FEED_TIMER_NAMES["left"]
        ).first()
        right = models.Timer.objects.filter(
            child=child, name=FEED_TIMER_NAMES["right"]
        ).first()
        if not left and not right:
            with translation.override(self.language(request)):
                msg = _("No breastfeeding timer was running for %(child)s.") % {
                    "child": child.first_name
                }
            return Response({"speech": msg}, status=200)

        # Stop only: persist as pending for Review & Save in the app; no log.
        from dashboard.models import FeedPending

        if left:
            FeedPending.objects.create(
                child=child, side="left", start=left.start, end=now
            )
            left.stop()
        if right:
            FeedPending.objects.create(
                child=child, side="right", start=right.start, end=now
            )
            right.stop()
        self._broadcast(child.slug)
        with translation.override(self.language(request)):
            speech = _("Stopped breastfeeding for %(child)s.") % {
                "child": child.first_name
            } + " " + _("Remember to review and save in the app.")
        return Response({"speech": speech}, status=201)


class QuickBreastView(_QuickActionBase):
    """
    POST /api/quick/breast?text=...

    A single free-text breastfeeding endpoint that toggles: if a breast timer is
    running it stops it (into pending for Review & Save in the app, no log),
    otherwise it starts. Side and start/stop can be set via the spoken phrase.
    """

    queryset = models.Feeding.objects.all()

    STOP_WORDS = ("stop", "end", "done", "停", "结束", "完成")
    START_WORDS = ("start", "begin", "开始")

    def _side_label(self, sides):
        if "left" in sides and "right" in sides:
            return _("both sides")
        if "right" in sides:
            return _("right")
        return _("left")

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        text = (self._param(request, "text", "") or "").lower()
        left = models.Timer.objects.filter(
            child=child, name=FEED_TIMER_NAMES["left"]
        ).first()
        right = models.Timer.objects.filter(
            child=child, name=FEED_TIMER_NAMES["right"]
        ).first()
        any_running = bool(left or right)

        # Breastfeeding does not toggle: a side word starts that side, and only
        # a stop word stops. (Stopping can stop both running sides.)
        if any(k in text for k in self.STOP_WORDS):
            action = "stop"
        else:
            action = "start"

        language = self.language(request)

        if action == "start":
            # Breastfeeding is one side at a time: require left or right.
            if "左" in text or "left" in text:
                side = "left"
            elif "右" in text or "right" in text:
                side = "right"
            else:
                side = None
            if side is None:
                with translation.override(language):
                    speech = _(
                        "Please choose a side for %(child)s: say left or right."
                    ) % {"child": child.first_name}
                return Response({"speech": speech}, status=200)
            name = FEED_TIMER_NAMES[side]
            if models.Timer.objects.filter(child=child, name=name).exists():
                with translation.override(language):
                    speech = _("Breastfeeding is already running for %(child)s.") % {
                        "child": child.first_name
                    }
                return Response({"speech": speech}, status=200)
            # One side at a time: stop the other side (into pending) if running.
            other = "right" if side == "left" else "left"
            other_timer = models.Timer.objects.filter(
                child=child, name=FEED_TIMER_NAMES[other]
            ).first()
            stopped_other = False
            if other_timer:
                from dashboard.models import FeedPending

                FeedPending.objects.create(
                    child=child,
                    side=other,
                    start=other_timer.start,
                    end=timezone.now(),
                )
                other_timer.stop()
                stopped_other = True
            models.Timer.objects.create(child=child, user=request.user, name=name)
            self._broadcast(child.slug)
            with translation.override(language):
                speech = _("Started breastfeeding (%(side)s) for %(child)s.") % {
                    "side": self._side_label([side]),
                    "child": child.first_name,
                }
                if stopped_other:
                    speech += " " + _("Stopped the %(side)s side.") % {
                        "side": self._side_label([other])
                    }
            return Response({"speech": speech}, status=201)

        # action == "stop"
        if not any_running:
            with translation.override(language):
                speech = _("No breastfeeding timer was running for %(child)s.") % {
                    "child": child.first_name
                }
            return Response({"speech": speech}, status=200)

        from dashboard.models import FeedPending

        now = timezone.now()
        if left:
            FeedPending.objects.create(
                child=child, side="left", start=left.start, end=now
            )
            left.stop()
        if right:
            FeedPending.objects.create(
                child=child, side="right", start=right.start, end=now
            )
            right.stop()
        self._broadcast(child.slug)
        with translation.override(language):
            speech = _("Stopped breastfeeding for %(child)s.") % {
                "child": child.first_name
            } + " " + _("Remember to review and save in the app.")
        return Response({"speech": speech}, status=201)


class QuickPumpStartView(_QuickActionBase):
    """POST /api/quick/pump/start?side=left|right|both"""

    queryset = models.Pumping.objects.all()

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        side = (self._param(request, "side", "both")).lower()
        sides = ["left", "right"] if side in ("both", "both breasts") else [side]
        valid = [s for s in sides if PUMP_TIMER_NAMES.get(s)]
        if not valid:
            return Response({"detail": "Invalid side."}, status=400)
        started = []
        already = []
        for s in valid:
            name = PUMP_TIMER_NAMES[s]
            if models.Timer.objects.filter(child=child, name=name).exists():
                already.append(s)
                continue
            models.Timer.objects.create(child=child, user=request.user, name=name)
            started.append(s)
        self._broadcast(child.slug)
        with translation.override(self.language(request)):
            parts = []
            if started:
                parts.append(
                    _("Started pumping %(side)s.")
                    % {"side": _pump_side_label(started)}
                )
            if already:
                parts.append(
                    _("Pumping %(side)s is already started.")
                    % {"side": _pump_side_label(already)}
                )
            speech = " ".join(parts)
        return Response({"speech": speech}, status=201)


class QuickPumpStopView(_QuickActionBase):
    """POST /api/quick/pump/stop — stop the pump timer(s) into pending (no log)."""

    queryset = models.Pumping.objects.all()

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        now = timezone.now()
        left = models.Timer.objects.filter(
            child=child, name=PUMP_TIMER_NAMES["left"]
        ).first()
        right = models.Timer.objects.filter(
            child=child, name=PUMP_TIMER_NAMES["right"]
        ).first()
        if not left and not right:
            with translation.override(self.language(request)):
                msg = _("No pumping timer was running.")
            return Response({"speech": msg}, status=200)

        side = (self._param(request, "side", "") or "").lower()
        if side == "left":
            targets = {"left"}
        elif side == "right":
            targets = {"right"}
        else:
            targets = {"left", "right"}

        # Stop only: persist as pending for Review & Save in the app; no log.
        from dashboard.models import PumpPending

        stopped = []
        if left and "left" in targets:
            PumpPending.objects.create(
                child=child, side="left", start=left.start, end=now
            )
            left.stop()
            stopped.append("left")
        if right and "right" in targets:
            PumpPending.objects.create(
                child=child, side="right", start=right.start, end=now
            )
            right.stop()
            stopped.append("right")
        if not stopped:
            with translation.override(self.language(request)):
                msg = _("No pumping timer was running.")
            return Response({"speech": msg}, status=200)
        self._broadcast(child.slug)
        with translation.override(self.language(request)):
            speech = _("Stopped pumping %(side)s.") % {
                "side": _pump_side_label(stopped)
            } + " " + _("Remember to review and save in the app.")
        return Response({"speech": speech}, status=201)


class QuickPumpView(_QuickActionBase):
    """
    POST /api/quick/pump?text=...

    A single free-text pump endpoint that toggles: if a pump timer is running it
    stops and logs (parsing per-side amounts from the phrase), otherwise it
    starts. The action can be forced with start/stop keywords; the side and
    amounts are parsed from the spoken phrase.
    """

    queryset = models.Pumping.objects.all()

    STOP_WORDS = ("stop", "end", "done", "停", "结束", "完成")
    START_WORDS = ("start", "begin", "开始")

    def post(self, request):
        child, error = self.get_child(request)
        if error:
            return error
        text = (self._param(request, "text", "") or "").lower()
        left = models.Timer.objects.filter(
            child=child, name=PUMP_TIMER_NAMES["left"]
        ).first()
        right = models.Timer.objects.filter(
            child=child, name=PUMP_TIMER_NAMES["right"]
        ).first()
        any_running = bool(left or right)

        if any(k in text for k in self.STOP_WORDS):
            action = "stop"
        elif any(k in text for k in self.START_WORDS):
            action = "start"
        else:
            action = "stop" if any_running else "start"

        language = self.language(request)

        if action == "start":
            if any(k in text for k in ("两", "both", "双")):
                sides = ["left", "right"]
            elif "左" in text or "left" in text:
                sides = ["left"]
            elif "右" in text or "right" in text:
                sides = ["right"]
            else:
                sides = ["left", "right"]
            started = []
            already = []
            for side in sides:
                name = PUMP_TIMER_NAMES[side]
                if models.Timer.objects.filter(child=child, name=name).exists():
                    already.append(side)
                    continue
                models.Timer.objects.create(
                    child=child, user=request.user, name=name
                )
                started.append(side)
            self._broadcast(child.slug)
            with translation.override(language):
                parts = []
                if started:
                    parts.append(
                        _("Started pumping %(side)s.")
                        % {"side": _pump_side_label(started)}
                    )
                if already:
                    parts.append(
                        _("Pumping %(side)s is already started.")
                        % {"side": _pump_side_label(already)}
                    )
                speech = " ".join(parts)
            return Response({"speech": speech}, status=201)

        # action == "stop" — honor a side if given, else stop both.
        if not any_running:
            with translation.override(language):
                speech = _("No pumping timer was running.")
            return Response({"speech": speech}, status=200)

        if "左" in text or "left" in text:
            targets = {"left"}
        elif "右" in text or "right" in text:
            targets = {"right"}
        else:
            targets = {"left", "right"}

        # Stop only: persist the timer(s) as pending (matching the dashboard's
        # stop) so they can be reviewed and saved with amounts in the app. Do
        # not create the Pumping log here.
        from dashboard.models import PumpPending

        now = timezone.now()
        stopped = []
        if left and "left" in targets:
            PumpPending.objects.create(
                child=child, side="left", start=left.start, end=now
            )
            left.stop()
            stopped.append("left")
        if right and "right" in targets:
            PumpPending.objects.create(
                child=child, side="right", start=right.start, end=now
            )
            right.stop()
            stopped.append("right")
        if not stopped:
            with translation.override(language):
                speech = _("No pumping timer was running.")
            return Response({"speech": speech}, status=200)
        self._broadcast(child.slug)
        with translation.override(language):
            speech = _("Stopped pumping %(side)s.") % {
                "side": _pump_side_label(stopped)
            } + " " + _("Remember to review and save in the app.")
        return Response({"speech": speech}, status=201)
