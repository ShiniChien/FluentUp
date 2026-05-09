import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.writing.topic_pool import _compute_p_generate, _round_band


def test_p_generate_zero_topics():
    assert _compute_p_generate(0) == 1.0


def test_p_generate_500_topics():
    assert _compute_p_generate(500) == pytest.approx(0.5)


def test_p_generate_1000_topics():
    assert _compute_p_generate(1000) == 0.0


def test_p_generate_over_target():
    assert _compute_p_generate(1200) == 0.0


def test_round_band_rounds_to_half():
    assert _round_band(6.3) == 6.5
    assert _round_band(6.74) == 6.5
    assert _round_band(6.75) == 7.0
    assert _round_band(7.0) == 7.0
    assert _round_band(5.1) == 5.0
