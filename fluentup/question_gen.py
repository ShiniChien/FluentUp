from __future__ import annotations

import json
import random
import re
from pathlib import Path

import openai

from fluentup.prompts import (
    CUE_CARD_PROMPT,
    PART3_QUESTION_PROMPT,
    PART3_RANDOM_QUESTION_PROMPT,
)
from fluentup.models import CueCard
from fluentup.live_session import gemini_live_speak, gemini_live_next_question
from fluentup.config import (
    EXAMINER_ACCENTS,
    DEFAULT_ACCENT,
    DEFAULT_VOICE,
    PART1_QUESTIONS_PER_SESSION,
    PART3_QUESTIONS_PER_SESSION,
    PART3_TOPICS,
    SEED_WORDS_MIN,
    SEED_WORDS_MAX,
)
from fluentup.question_bank import QUESTION_BANK

_VIET11K_PATH = Path(__file__).parent / "Viet11K.txt"
_viet_words: list[str] | None = None


def _load_viet_words() -> list[str]:
    global _viet_words
    if _viet_words is None:
        try:
            lines = _VIET11K_PATH.read_text(encoding="utf-8").splitlines()
            _viet_words = [ln.strip() for ln in lines if ln.strip()]
        except Exception:
            _viet_words = []
    return _viet_words


def _seed_words(n: int = 2) -> list[str]:
    """Pick n random Vietnamese words to seed topic generation."""
    words = _load_viet_words()
    if not words:
        return []
    return random.sample(words, min(n, len(words)))


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


class QuestionGenerator:
    def __init__(
        self,
        api_key: str,
        live_model: str,
        openrouter_base_url: str,
        openrouter_api_key: str,
        openrouter_model: str,
    ):
        if not live_model:
            raise ValueError("live_model is required")
        if not openrouter_base_url:
            raise ValueError("openrouter_base_url is required")
        if not openrouter_api_key:
            raise ValueError("openrouter_api_key is required")
        if not openrouter_model:
            raise ValueError("openrouter_model is required")

        self._api_key    = api_key
        self._live_model = live_model

        self._or_client = openai.AsyncOpenAI(
            base_url=openrouter_base_url,
            api_key=openrouter_api_key,
        )
        self._or_model = openrouter_model

    async def _chat(self, prompt: str) -> str:
        resp = await self._or_client.chat.completions.create(
            model=self._or_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()

    async def generate_part1_questions(self, n: int = 1) -> list[str]:
        """Pick n questions from the pre-built bank for a random topic.
        Defaults to 1 (only the first question; subsequent ones are generated dynamically)."""
        topic = random.choice(list(QUESTION_BANK.keys()))
        pool = QUESTION_BANK[topic]
        return random.sample(pool, min(n, len(pool)))

    async def generate_next_part1_question(
        self,
        prev_question: str,
        answer_wav: bytes,
        accent: str = DEFAULT_ACCENT,
    ) -> tuple[str, bytes]:
        """Generate Q(n+1) dynamically from Q(n) text + audio of A(n).
        Returns (question_text, question_wav)."""
        accent_instruction = EXAMINER_ACCENTS.get(accent, EXAMINER_ACCENTS[DEFAULT_ACCENT])
        return await gemini_live_next_question(
            api_key=self._api_key,
            prev_question=prev_question,
            answer_wav=answer_wav,
            model=self._live_model,
            accent_instruction=accent_instruction,
        )

    async def generate_cue_card(self) -> CueCard:
        # Sample 1-3 Vietnamese seed words to diversify the topic
        seeds = _seed_words(random.randint(SEED_WORDS_MIN, SEED_WORDS_MAX))
        seed_hint = ""
        if seeds:
            seed_hint = (
                f"\nFor inspiration, use 1-3 of these Vietnamese concept words as a thematic seed "
                f"(translate / interpret them freely into an English IELTS topic): {', '.join(seeds)}"
            )
        text = _strip_fences(await self._chat(CUE_CARD_PROMPT + seed_hint))
        try:
            data = json.loads(text)
            return CueCard(
                topic=data.get("topic", "Describe a memorable experience."),
                points=data.get("points", ["What happened", "When it happened", "Who was involved", "How you felt"]),
                explain=data.get("explain", "And explain why it was memorable."),
            )
        except json.JSONDecodeError:
            return CueCard(
                topic="Describe a memorable place you have visited.",
                points=["Where it is", "When you visited", "What you did there", "Who you went with"],
                explain="And explain why you found it particularly interesting.",
            )

    async def generate_part3_questions(self, part2_topic: str, n: int = PART3_QUESTIONS_PER_SESSION, part2_cue_card=None) -> list[str]:
        if part2_topic:
            points_str = ", ".join(part2_cue_card.points) if part2_cue_card else ""
            explain_str = part2_cue_card.explain if part2_cue_card else ""
            prompt = PART3_QUESTION_PROMPT.format(
                part2_topic=part2_topic,
                part2_points=points_str,
                part2_explain=explain_str,
                n=n,
            )
        else:
            topic = random.choice(PART3_TOPICS)
            prompt = PART3_RANDOM_QUESTION_PROMPT.format(topic=topic, n=n)

        text = _strip_fences(await self._chat(prompt))
        try:
            questions = json.loads(text)
            if isinstance(questions, list):
                return questions[:n]
        except json.JSONDecodeError:
            pass
        return [f"What do you think about {part2_topic or 'this topic'}?"] * n

    async def speak_question(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        accent: str = DEFAULT_ACCENT,
    ) -> bytes:
        """Return WAV bytes of the question spoken by the Gemini Live examiner voice.

        accent: one of 'us', 'uk', 'in', 'au' (see fluentup/accents.py)
        """
        system_instruction = EXAMINER_ACCENTS.get(accent, EXAMINER_ACCENTS[DEFAULT_ACCENT])
        return await gemini_live_speak(
            api_key=self._api_key,
            text=text,
            voice=voice,
            model=self._live_model,
            system_instruction=system_instruction,
        )
