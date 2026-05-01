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
        """One-line context string injected into LLM prompts."""
        return (
            f"Candidate: {self.name}, {self.age} years old ({self.gender}), {self.occupation_detail}. "
            f"Tailor topics to be relevant to their background.\n\n"
        )


@dataclass
class BandScore:
    criterion: str  # "FC", "LR", "GR", "Pronunciation"
    band: float     # 1.0 - 9.0, step 0.5
    feedback: str
    tips: list[str]
    weak_points: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    transcript: str
    scores: list[BandScore]
    criterion_audio: dict[str, bytes] = field(default_factory=dict)  # criterion → WAV bytes

    @property
    def overall_band(self) -> float:
        if not self.scores:
            return 0.0
        avg = sum(s.band for s in self.scores) / len(self.scores)
        return round(avg * 2) / 2  # round to nearest 0.5

    def get_score(self, criterion: str) -> BandScore | None:
        for s in self.scores:
            if s.criterion.upper() == criterion.upper():
                return s
        return None


@dataclass
class Turn:
    part: int            # 1, 2, 3
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

    @property
    def avg_fc(self) -> float:
        return self._avg_criterion("FC")

    @property
    def avg_lr(self) -> float:
        return self._avg_criterion("LR")

    @property
    def avg_gr(self) -> float:
        return self._avg_criterion("GR")

    @property
    def avg_pronun(self) -> float:
        return self._avg_criterion("Pronunciation")

    @property
    def overall(self) -> float:
        scores = [self.avg_fc, self.avg_lr, self.avg_gr, self.avg_pronun]
        valid = [s for s in scores if s > 0]
        if not valid:
            return 0.0
        return round(sum(valid) / len(valid) * 2) / 2

    def _avg_criterion(self, criterion: str) -> float:
        bands = []
        for t in self.turns:
            if t.result:
                score = t.result.get_score(criterion)
                if score and score.band > 0:
                    bands.append(score.band)
        if not bands:
            return 0.0
        return round(sum(bands) / len(bands) * 2) / 2
