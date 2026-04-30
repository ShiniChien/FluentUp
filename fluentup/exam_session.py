from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from fluentup.models import Turn, CueCard, ExamSummary
from fluentup.config import PREP_SECONDS, SPEAK_SECONDS  # noqa: F401 – re-exported for app.py

Phase = Literal[
    "home",
    "part1_loading", "part1_idle", "part1_feedback", "part1_evaluating", "part1_summary",
    "part2_idle", "part2_thinking", "part2_recording", "part2_evaluating", "part2_result",
    "part3_loading", "part3_idle", "part3_result", "part3_summary",
    "session_summary",
]



@dataclass
class ExamSession:
    phase: Phase = "home"
    turns: list[Turn] = field(default_factory=list)

    # Part 1
    part1_questions: list[str] = field(default_factory=list)
    part1_index: int = 0

    # Part 2
    part2_cue_card: CueCard | None = None
    part2_topic: str = ""
    prep_start_time: float = 0.0
    speaking_start_time: float = 0.0

    # Part 3
    part3_questions: list[str] = field(default_factory=list)
    part3_index: int = 0

    def current_part1_question(self) -> str | None:
        if self.part1_index < len(self.part1_questions):
            return self.part1_questions[self.part1_index]
        return None

    def current_part3_question(self) -> str | None:
        if self.part3_index < len(self.part3_questions):
            return self.part3_questions[self.part3_index]
        return None

    def prep_remaining(self) -> int:
        elapsed = time.time() - self.prep_start_time
        return max(0, PREP_SECONDS - int(elapsed))

    def speak_remaining(self) -> int:
        elapsed = time.time() - self.speaking_start_time
        return max(0, SPEAK_SECONDS - int(elapsed))

    def part_turns(self, part: int) -> list[Turn]:
        return [t for t in self.turns if t.part == part]

    def build_summary(self) -> ExamSummary:
        return ExamSummary(turns=list(self.turns))
