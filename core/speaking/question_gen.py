from __future__ import annotations

import json
import random
import re
from typing import TYPE_CHECKING

from core.openrouter import async_chat
from core.speaking.prompts import (
    CUE_CARD_PROMPT,
    NEXT_QUESTION_SYSTEM,
    NEXT_PART3_QUESTION_SYSTEM,
    PART3_QUESTION_PROMPT,
    PART3_RANDOM_QUESTION_PROMPT,
)
from core.models import CueCard
from core.live_session import gemini_live_speak, gemini_live_next_question
from core.speaking.question_bank import pick_opening_question
from core.viet_words import seed_words as _seed_words_shared
from core.config import (
    EXAMINER_ACCENTS,
    DEFAULT_ACCENT,
    DEFAULT_VOICE,
    PART3_QUESTIONS_PER_SESSION,
    PART3_TOPICS,
    SEED_WORDS_MIN,
    SEED_WORDS_MAX,
)

if TYPE_CHECKING:
    from core.models import UserProfile


def _seed_words(n: int = 2) -> list[str]:
    return _seed_words_shared(n)


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
        self._or_base    = openrouter_base_url
        self._or_key     = openrouter_api_key
        self._or_model   = openrouter_model

    async def _chat(self, prompt: str) -> str:
        return await async_chat(
            base_url=self._or_base,
            api_key=self._or_key,
            model=self._or_model,
            prompt=prompt,
        )

    async def generate_part1_questions(self, n: int = 1, profile: "UserProfile | None" = None) -> list[str]:
        """Pick the opening Part 1 question from the local bank (no LLM call needed)."""
        occupation = profile.occupation if profile else ""
        _, question = pick_opening_question(profile_occupation=occupation)
        return [question]

    async def generate_next_part1_question(
        self,
        prev_question: str,
        answer_wav: bytes,
        accent: str = DEFAULT_ACCENT,
        profile: "UserProfile | None" = None,
    ) -> tuple[str, bytes]:
        """Generate Q(n+1) dynamically from Q(n) text + audio of A(n).
        Returns (question_text, question_wav)."""
        accent_instruction = EXAMINER_ACCENTS.get(accent, EXAMINER_ACCENTS[DEFAULT_ACCENT])
        profile_ctx = profile.prompt_context() if profile else ""
        context = ""
        if accent_instruction.strip():
            context += accent_instruction + "\n\n"
        if profile_ctx.strip():
            context += profile_ctx
        system_prompt = NEXT_QUESTION_SYSTEM.format(
            context=context,
            prev_question=prev_question,
        )
        return await gemini_live_next_question(
            api_key=self._api_key,
            system_prompt=system_prompt,
            answer_wav=answer_wav,
            model=self._live_model,
        )

    async def generate_next_part3_question(
        self,
        prev_question: str,
        answer_wav: bytes,
        part2_topic: str = "",
        accent: str = DEFAULT_ACCENT,
        profile: "UserProfile | None" = None,
    ) -> tuple[str, bytes]:
        """Generate the next Part 3 question from previous question text + audio of answer."""
        accent_instruction = EXAMINER_ACCENTS.get(accent, EXAMINER_ACCENTS[DEFAULT_ACCENT])
        profile_ctx = profile.prompt_context() if profile else ""
        context = ""
        if accent_instruction.strip():
            context += accent_instruction + "\n\n"
        if profile_ctx.strip():
            context += profile_ctx + "\n\n"
        system_prompt = NEXT_PART3_QUESTION_SYSTEM.format(
            context=context,
            part2_topic=part2_topic or "a general topic",
            prev_question=prev_question,
        )
        return await gemini_live_next_question(
            api_key=self._api_key,
            system_prompt=system_prompt,
            answer_wav=answer_wav,
            model=self._live_model,
        )

    async def generate_cue_card(self, profile: "UserProfile | None" = None) -> CueCard:
        # Sample 1-3 Vietnamese seed words to diversify the topic
        seeds = _seed_words(random.randint(SEED_WORDS_MIN, SEED_WORDS_MAX))
        seed_hint = ""
        if seeds:
            seed_hint = (
                f"\nFor inspiration, use 1-3 of these Vietnamese concept words as a thematic seed "
                f"(translate / interpret them freely into an English IELTS topic): {', '.join(seeds)}"
            )
        ctx = profile.prompt_context() if profile else ""
        text = _strip_fences(await self._chat(ctx + CUE_CARD_PROMPT + seed_hint))
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

    async def generate_part3_questions(self, part2_topic: str, n: int = PART3_QUESTIONS_PER_SESSION, part2_cue_card=None, profile: "UserProfile | None" = None) -> list[str]:
        ctx = profile.prompt_context() if profile else ""
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

        text = _strip_fences(await self._chat(ctx + prompt))
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

        accent: one of 'us', 'uk', 'in', 'au' (see core/accents.py)
        """
        system_instruction = EXAMINER_ACCENTS.get(accent, EXAMINER_ACCENTS[DEFAULT_ACCENT])
        return await gemini_live_speak(
            api_key=self._api_key,
            text=text,
            voice=voice,
            model=self._live_model,
            system_instruction=system_instruction,
        )
