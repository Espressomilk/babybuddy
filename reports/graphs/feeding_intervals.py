# -*- coding: utf-8 -*-
from django.utils.translation import gettext as _

import plotly.offline as plotly
import plotly.graph_objs as go

from core.utils import duration_parts, group_feeding_sessions

from reports import utils


def feeding_intervals(instances):
    """
    Create a graph showing intervals between feeding sessions over time.

    Consecutive feedings (e.g. a breast feed plus top-up bottles) are grouped
    into a single session, so the interval reflects time between feedings rather
    than between the individual sources of one feeding.

    :param instances: a QuerySet of Feeding instances.
    :returns: a tuple of the graph's html and javascript.
    """
    sessions = group_feeding_sessions(instances.order_by("start"))

    starts = []
    intervals = []
    last_session = sessions[0] if sessions else None
    for session in sessions[1:]:
        interval = session["start"] - last_session["start"]
        if interval.total_seconds() > 0:
            starts.append(session["start"])
            intervals.append(interval)
        last_session = session

    trace_avg = go.Scatter(
        name=_("Interval"),
        line=dict(shape="spline"),
        x=starts,
        y=[i.total_seconds() / 3600 for i in intervals],
        hoverinfo="text",
        text=[_duration_string_hms(i) for i in intervals],
    )

    layout_args = utils.default_graph_layout_options()
    layout_args["title"] = "<b>" + _("Feeding intervals") + "</b>"
    layout_args["xaxis"]["title"] = _("Date")
    layout_args["xaxis"]["type"] = "date"
    layout_args["xaxis"]["autorange"] = True
    if starts:
        layout_args["xaxis"]["autorangeoptions"] = utils.autorangeoptions(starts)
    layout_args["xaxis"]["rangeselector"] = utils.rangeselector_date()
    layout_args["yaxis"]["title"] = _("Feeding interval (hours)")

    fig = go.Figure({"data": [trace_avg], "layout": go.Layout(**layout_args)})
    output = plotly.plot(fig, output_type="div", include_plotlyjs=False)
    return utils.split_graph_output(output)


def _duration_string_hms(duration):
    """
    Format a duration string with hours, minutes and seconds. This is
    intended to fit better in smaller spaces on a graph.
    :returns: a string of the form Xm.
    """
    h, m, s = duration_parts(duration)
    return "{}h{}m{}s".format(h, m, s)
