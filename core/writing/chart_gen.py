from __future__ import annotations
import plotly.graph_objects as go


def build_figure(spec: dict) -> go.Figure:
    """Convert a chart_spec dict to a Plotly Figure."""
    chart_type = spec["type"]
    title      = spec.get("title", "")
    labels     = spec["labels"]
    datasets   = spec["datasets"]
    x_label    = spec.get("x_label", "")
    y_label    = spec.get("y_label", "")

    if chart_type == "bar":
        traces = [
            go.Bar(name=ds["label"], x=labels, y=ds["values"])
            for ds in datasets
        ]
        fig = go.Figure(data=traces)
        fig.update_layout(
            title=title,
            xaxis_title=x_label,
            yaxis_title=y_label,
            barmode="group",
        )

    elif chart_type == "line":
        traces = [
            go.Scatter(name=ds["label"], x=labels, y=ds["values"], mode="lines+markers")
            for ds in datasets
        ]
        fig = go.Figure(data=traces)
        fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

    elif chart_type == "pie":
        values = datasets[0]["values"]
        fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
        fig.update_layout(title=title)

    elif chart_type == "scatter":
        traces = [
            go.Scatter(name=ds["label"], x=labels, y=ds["values"], mode="markers")
            for ds in datasets
        ]
        fig = go.Figure(data=traces)
        fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

    else:
        raise ValueError(f"Unsupported chart type: {chart_type!r}")

    return fig
