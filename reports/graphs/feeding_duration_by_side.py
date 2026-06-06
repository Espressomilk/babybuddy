# -*- coding: utf-8 -*-
from collections import OrderedDict

from django.utils import timezone
from django.utils.translation import gettext as _

import plotly.offline as plotly
import plotly.graph_objs as go

from reports import utils

LEFT = "left breast"
RIGHT = "right breast"
BOTH = "both breasts"
BREAST_METHODS = (LEFT, RIGHT, BOTH)


def feeding_duration_by_side(instances):
    """
    Create a graph showing breastfeeding duration split by side (left/right)
    per day.

    Only breastfeeding entries (method left/right/both breasts) are considered.
    Because the data model stores a single duration per feeding (not per side),
    "both breasts" sessions are split evenly between the two sides -- matching
    the dashboard's breastfeeding card.

    :param instances: a QuerySet of Feeding instances.
    :returns: a tuple of the graph's html and javascript.
    """
    left_totals = OrderedDict()
    right_totals = OrderedDict()

    for instance in instances.order_by("start"):
        if instance.method not in BREAST_METHODS:
            continue
        date = str(timezone.localtime(instance.start).date())
        left_totals.setdefault(date, 0.0)
        right_totals.setdefault(date, 0.0)

        if instance.duration_left is not None or instance.duration_right is not None:
            # Stored per-side durations (exact for entries logged after per-side
            # tracking was added; even-split backfill for older entries).
            if instance.duration_left:
                left_totals[date] += instance.duration_left.total_seconds() / 60
            if instance.duration_right:
                right_totals[date] += instance.duration_right.total_seconds() / 60
        else:
            # Defensive fallback for any entry missing per-side data.
            duration = instance.duration
            minutes = duration.total_seconds() / 60 if duration else 0
            if instance.method == BOTH:
                half = minutes / 2
                left_totals[date] += half
                right_totals[date] += half
            elif instance.method == LEFT:
                left_totals[date] += minutes
            elif instance.method == RIGHT:
                right_totals[date] += minutes

    dates = list(left_totals.keys())
    left_values = [round(v, 1) for v in left_totals.values()]
    right_values = [round(v, 1) for v in right_totals.values()]
    total_values = [round(l + r, 1) for l, r in zip(left_values, right_values)]

    traces = [
        go.Bar(
            name=_("Left"),
            x=dates,
            y=left_values,
            text=left_values,
            hovertemplate="%{x}<br>" + _("Left") + ": %{y} min<extra></extra>",
        ),
        go.Bar(
            name=_("Right"),
            x=dates,
            y=right_values,
            text=right_values,
            hovertemplate="%{x}<br>" + _("Right") + ": %{y} min<extra></extra>",
        ),
    ]

    layout_args = utils.default_graph_layout_options()
    layout_args["title"] = "<b>" + _("Breastfeeding Duration by Side") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Duration (minutes)")

    total_labels = [
        {"x": x, "y": total * 1.1, "text": str(total), "showarrow": False}
        for x, total in zip(dates, total_values)
    ]

    fig = go.Figure({"data": traces, "layout": go.Layout(**layout_args)})
    fig.update_layout(barmode="stack", annotations=total_labels)
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)
