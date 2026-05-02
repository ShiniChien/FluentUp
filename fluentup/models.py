from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class UserProfile:
    name: str
    age: int
    occupation: str          # "student" | "worker" | "other"
    occupation_detail: str   # e.g. "studying Computer Science at HUST"
    profile_id: str = ""
    gender: str = "male"     # "male" | "female" | "other"

    def prompt_context(self) -> str:
        return (
            f"Candidate: {self.name}, {self.age} years old ({self.gender}), {self.occupation_detail}. "
            f"Tailor topics to be relevant to their background.\n\n"
        )


@dataclass
class CriterionFeedback:
    criterion: str   # "FC", "LR", "GR", "Pronunciation"
    feedback: str    # spoken evaluation text from Gemini Live
    audio: bytes = field(default_factory=bytes)  # WAV bytes of spoken feedback


@dataclass
class EvaluationResult:
    transcript: str                            # input_audio_transcription (user's speech)
    feedbacks: list[CriterionFeedback]

    def get_feedback(self, criterion: str) -> CriterionFeedback | None:
        for f in self.feedbacks:
            if f.criterion.upper() == criterion.upper():
                return f
        return None


@dataclass
class Turn:
    part: int
    question: str
    audio_bytes: bytes
    result: EvaluationResult | None = None


@dataclass
class CueCard:
    topic: str
    points: list[str]
    explain: str = ""


@dataclass
class ExamSummary:
    turns: list[Turn] = field(default_factory=list)

    def part_turns(self, part: int) -> list[Turn]:
        return [t for t in self.turns if t.part == part]
