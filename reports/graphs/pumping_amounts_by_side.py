# -*- coding: utf-8 -*-
from collections import OrderedDict

from django.utils import timezone
from django.utils.translation import gettext as _

import plotly.offline as plotly
import plotly.graph_objs as go

from reports import utils


def pumping_amounts_by_side(objects):
    """
    Create a graph showing pumping amounts split by side (left/right) per day.

    Pumping entries that predate per-side tracking (or that were logged from a
    generic timer) have no per-side breakdown; their amount is aggregated into
    an "Unspecified" series so daily totals still match the overall pumping
    amounts report.

    :param objects: a QuerySet of Pumping instances.
    :returns: a tuple of the graph's html and javascript.
    """
    objects = objects.order_by("start")

    left_totals = OrderedDict()
    right_totals = OrderedDict()
    unspecified_totals = OrderedDict()

    for obj in objects:
        date = str(timezone.localtime(obj.start).date())
        for totals in (left_totals, right_totals, unspecified_totals):
            totals.setdefault(date, 0.0)

        if obj.amount_left is not None or obj.amount_right is not None:
            left_totals[date] += obj.amount_left or 0
            right_totals[date] += obj.amount_right or 0
        else:
            unspecified_totals[date] += obj.amount or 0

    dates = list(left_totals.keys())
    left_values = [round(v, 2) for v in left_totals.values()]
    right_values = [round(v, 2) for v in right_totals.values()]
    unspecified_values = [round(v, 2) for v in unspecified_totals.values()]
    total_values = [
        round(l + r + u, 2)
        for l, r, u in zip(left_values, right_values, unspecified_values)
    ]

    traces = [
        go.Bar(
            name=_("Left"),
            x=dates,
            y=left_values,
            text=left_values,
            hovertemplate="%{x}<br>" + _("Left") + ": %{y}<extra></extra>",
        ),
        go.Bar(
            name=_("Right"),
            x=dates,
            y=right_values,
            text=right_values,
            hovertemplate="%{x}<br>" + _("Right") + ": %{y}<extra></extra>",
        ),
    ]
    if any(unspecified_values):
        traces.append(
            go.Bar(
                name=_("Unspecified"),
                x=dates,
                y=unspecified_values,
                text=unspecified_values,
                hovertemplate="%{x}<br>"
                + _("Unspecified")
                + ": %{y}<extra></extra>",
            )
        )

    layout_args = utils.default_graph_layout_options()
    layout_args["title"] = "<b>" + _("Pumping Amount by Side") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Pumping Amount")

    total_labels = [
        {"x": x, "y": total * 1.1, "text": str(total), "showarrow": False}
        for x, total in zip(dates, total_values)
    ]

    fig = go.Figure({"data": traces, "layout": go.Layout(**layout_args)})
    fig.update_layout(barmode="stack", annotations=total_labels)
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)
