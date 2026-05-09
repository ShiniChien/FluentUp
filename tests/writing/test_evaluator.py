import pytest
from core.writing.evaluator import _parse_response, _overall_band, _first_criterion_name

SAMPLE_RAW = '''{
  "task_achievement": {"band": 6.5, "comment": "Covers main features."},
  "coherence_cohesion": {"band": 7.0, "comment": "Well organised."},
  "lexical_resource": {"band": 6.0, "comment": "Adequate range."},
  "grammatical_range": {"band": 7.0, "comment": "Few errors."},
  "overall_band": 6.5,
  "summary": "A solid attempt."
}'''


def test_parse_response_returns_dict():
    result = _parse_response(SAMPLE_RAW)
    assert result["task_achievement"]["band"] == 6.5
    assert result["overall_band"] == 6.5
    assert result["summary"] == "A solid attempt."


def test_overall_band_rounds_correctly():
    bands = [6.5, 7.0, 6.0, 7.0]
    assert _overall_band(bands) == 6.5  # mean=6.625 → rounds to 6.5


def test_overall_band_rounds_up():
    bands = [7.0, 7.0, 7.0, 7.0]
    assert _overall_band(bands) == 7.0


def test_first_criterion_name_task1():
    assert _first_criterion_name("task1") == "Task Achievement"


def test_first_criterion_name_task2():
    assert _first_criterion_name("task2") == "Task Response"
