# -*- coding: utf-8 -*-
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("dashboard/", views.Dashboard.as_view(), name="dashboard"),
    path("track/", views.Track.as_view(), name="track"),
    path(
        "children/<str:slug>/dashboard/",
        views.ChildDashboard.as_view(),
        name="dashboard-child",
    ),
    path(
        "children/<str:slug>/track/",
        views.ChildTrack.as_view(),
        name="track-child",
    ),
    path(
        "children/<str:slug>/breastfeed/",
        views.BreastfeedAdd.as_view(),
        name="breastfeed-add",
    ),
    path(
        "children/<str:slug>/bottlefeed/",
        views.BottleFeedAdd.as_view(),
        name="bottlefeed-add",
    ),
    path(
        "children/<str:slug>/diaper/",
        views.DiaperChangeAdd.as_view(),
        name="diaper-add",
    ),
    path(
        "children/<str:slug>/sleep-timer/start/",
        views.SleepTimerStart.as_view(),
        name="sleep-timer-start",
    ),
    path(
        "children/<str:slug>/sleep-timer/<int:pk>/save/",
        views.SleepTimerSave.as_view(),
        name="sleep-timer-save",
    ),
    path(
        "children/<str:slug>/sleep-timer/<int:pk>/note/",
        views.SleepTimerNote.as_view(),
        name="sleep-timer-note",
    ),
    path(
        "children/<str:slug>/tummytime-timer/start/",
        views.TummyTimerStart.as_view(),
        name="tummytime-timer-start",
    ),
    path(
        "children/<str:slug>/tummytime-timer/<int:pk>/save/",
        views.TummyTimerSave.as_view(),
        name="tummytime-timer-save",
    ),
    path(
        "children/<str:slug>/tummytime-timer/<int:pk>/note/",
        views.TummyTimerNote.as_view(),
        name="tummytime-timer-note",
    ),
    path(
        "children/<str:slug>/timer/<int:pk>/use/",
        views.TimerUse.as_view(),
        name="timer-use",
    ),
    path(
        "children/<str:slug>/timer/<int:pk>/use/save/",
        views.TimerUseSave.as_view(),
        name="timer-use-save",
    ),
    path(
        "children/<str:slug>/timer/<int:pk>/stop/",
        views.TimerStop.as_view(),
        name="timer-stop",
    ),
    path(
        "children/<str:slug>/pump-timer/<str:side>/toggle/",
        views.PumpTimerToggle.as_view(),
        name="pump-timer-toggle",
    ),
    path(
        "children/<str:slug>/pump-timer/<str:side>/discard/",
        views.PumpSideDiscard.as_view(),
        name="pump-side-discard",
    ),
    path(
        "children/<str:slug>/pump/commit/",
        views.PumpCommit.as_view(),
        name="pump-commit",
    ),
    path(
        "children/<str:slug>/pump/discard/",
        views.PumpPendingDiscard.as_view(),
        name="pump-discard",
    ),
]
