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
