from __future__ import annotations
import plotly.graph_objects as go
from plotly.subplots import make_subplots


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

    elif chart_type == "table":
        # labels = column headers; datasets = rows (label=row name, values=cells)
        header_vals = [""] + labels
        row_labels  = [ds["label"] for ds in datasets]
        cell_rows   = [ds["values"] for ds in datasets]
        # transpose: each element of cols is a column
        n_cols = len(labels)
        cols = [[row[i] for row in cell_rows] for i in range(n_cols)]
        fig = go.Figure(data=[go.Table(
            header=dict(values=header_vals, fill_color="steelblue", font=dict(color="white")),
            cells=dict(values=[row_labels] + cols),
        )])
        fig.update_layout(title=title)

    elif chart_type == "map":
        # Represent spatial layout as annotated scatter on a simple grid
        import math
        n = len(labels)
        xs = [math.cos(2 * math.pi * i / n) for i in range(n)]
        ys = [math.sin(2 * math.pi * i / n) for i in range(n)]
        traces = []
        for ds in datasets:
            text = [f"{labels[i]}<br>{ds['values'][i]}" for i in range(n)]
            traces.append(go.Scatter(
                x=xs, y=ys, mode="markers+text",
                name=ds["label"],
                text=text, textposition="top center",
                marker=dict(size=18),
            ))
        fig = go.Figure(data=traces)
        fig.update_layout(
            title=title,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )

    elif chart_type == "process":
        # Horizontal flow: steps as boxes with arrows
        n = len(labels)
        x_positions = list(range(n))
        fig = go.Figure()
        # Arrows between steps
        for i in range(n - 1):
            fig.add_annotation(
                x=i + 0.85, y=0, ax=i + 0.15, ay=0,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.5, arrowwidth=2,
                arrowcolor="#555",
            )
        # Step boxes as scatter markers with text
        fig.add_trace(go.Scatter(
            x=x_positions, y=[0] * n,
            mode="markers+text",
            marker=dict(size=40, color="steelblue", symbol="square"),
            text=[f"<b>{i+1}</b>" for i in range(n)],
            textfont=dict(color="white"),
            textposition="middle center",
            showlegend=False,
        ))
        # Step labels below
        for i, label in enumerate(labels):
            fig.add_annotation(x=i, y=-0.15, text=label, showarrow=False,
                               font=dict(size=11), xref="x", yref="y")
        fig.update_layout(
            title=title,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                       range=[-0.5, n - 0.5]),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                       range=[-0.4, 0.3]),
            height=300,
        )

    elif chart_type == "mixed":
        # bar + line on same figure; each dataset has chart_subtype field
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for ds in datasets:
            subtype = ds.get("chart_subtype", "bar")
            if subtype == "bar":
                fig.add_trace(
                    go.Bar(name=ds["label"], x=labels, y=ds["values"]),
                    secondary_y=False,
                )
            else:
                fig.add_trace(
                    go.Scatter(name=ds["label"], x=labels, y=ds["values"],
                               mode="lines+markers"),
                    secondary_y=True,
                )
        fig.update_layout(title=title, xaxis_title=x_label, barmode="group")
        fig.update_yaxes(title_text=y_label, secondary_y=False)

    else:
        raise ValueError(f"Unsupported chart type: {chart_type!r}")

    return fig
