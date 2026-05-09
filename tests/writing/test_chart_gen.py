import pytest
from core.writing.chart_gen import build_figure

BAR_SPEC = {
    "type": "bar",
    "title": "Internet Access by Country",
    "labels": ["UK", "US", "DE"],
    "datasets": [{"label": "2020", "values": [90, 85, 88]}],
    "x_label": "Country",
    "y_label": "% Households",
}

LINE_SPEC = {
    "type": "line",
    "title": "Trend",
    "labels": ["2000", "2010", "2020"],
    "datasets": [{"label": "UK", "values": [50, 70, 90]}],
    "x_label": "Year",
    "y_label": "%",
}

PIE_SPEC = {
    "type": "pie",
    "title": "Energy Mix",
    "labels": ["Solar", "Wind", "Coal"],
    "datasets": [{"label": "Share", "values": [30, 45, 25]}],
    "x_label": "",
    "y_label": "",
}

SCATTER_SPEC = {
    "type": "scatter",
    "title": "GDP vs Life Expectancy",
    "labels": ["A", "B", "C"],
    "datasets": [{"label": "Countries", "values": [72, 78, 65]}],
    "x_label": "GDP",
    "y_label": "Life Exp",
}


def test_bar_returns_figure():
    fig = build_figure(BAR_SPEC)
    assert fig is not None
    assert fig.layout.title.text == "Internet Access by Country"


def test_line_returns_figure():
    fig = build_figure(LINE_SPEC)
    assert fig is not None


def test_pie_returns_figure():
    fig = build_figure(PIE_SPEC)
    assert fig is not None


def test_scatter_returns_figure():
    fig = build_figure(SCATTER_SPEC)
    assert fig is not None


def test_unknown_type_raises():
    bad = {**BAR_SPEC, "type": "heatmap"}
    with pytest.raises(ValueError, match="Unsupported chart type"):
        build_figure(bad)


TABLE_SPEC = {
    "type": "table",
    "title": "Monthly Sales",
    "labels": ["Jan", "Feb", "Mar"],
    "datasets": [
        {"label": "Product A", "values": [100, 120, 110]},
        {"label": "Product B", "values": [80, 95, 105]},
    ],
    "x_label": "",
    "y_label": "",
}

MAP_SPEC = {
    "type": "map",
    "title": "Town Changes 1990-2020",
    "labels": ["North", "South", "Center"],
    "datasets": [
        {"label": "1990", "values": ["Forest", "Farmland", "Market"]},
        {"label": "2020", "values": ["Park", "Housing", "Shopping Mall"]},
    ],
    "x_label": "",
    "y_label": "",
}

PROCESS_SPEC = {
    "type": "process",
    "title": "How Paper is Made",
    "labels": ["Cut trees", "Make pulp", "Form sheets", "Dry"],
    "datasets": [{"label": "Process", "values": []}],
    "x_label": "",
    "y_label": "",
}

MIXED_SPEC = {
    "type": "mixed",
    "title": "Sales and Growth Rate",
    "labels": ["2018", "2019", "2020", "2021"],
    "datasets": [
        {"label": "Sales", "values": [100, 120, 115, 140], "chart_subtype": "bar"},
        {"label": "Growth %", "values": [0, 20, -4, 22], "chart_subtype": "line"},
    ],
    "x_label": "Year",
    "y_label": "Value",
}


def test_table_returns_figure():
    fig = build_figure(TABLE_SPEC)
    assert fig is not None


def test_map_returns_figure():
    fig = build_figure(MAP_SPEC)
    assert fig is not None


def test_process_returns_figure():
    fig = build_figure(PROCESS_SPEC)
    assert fig is not None


def test_mixed_returns_figure():
    fig = build_figure(MIXED_SPEC)
    assert fig is not None
