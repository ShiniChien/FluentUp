from __future__ import annotations

import json
import random

from google import genai

from fluentup.prompts import (
    PART1_QUESTION_PROMPT,
    CUE_CARD_PROMPT,
    PART3_QUESTION_PROMPT,
    PART3_RANDOM_QUESTION_PROMPT,
)
from fluentup.models import CueCard
from fluentup.live_session import gemini_live_speak, LIVE_MODEL

TEXT_MODEL = "gemini-2.0-flash"

PART1_TOPICS = [
    "hometown", "work or studies", "hobbies", "travel", "food",
    "technology", "music", "sports", "family", "environment",
]

PART3_TOPICS = [
    "education", "technology and society", "environmental challenges",
    "cultural traditions", "urban development", "health and wellbeing",
]


class QuestionGenerator:
    def __init__(self, api_key: str, live_model: str = LIVE_MODEL):
        self._client     = genai.Client(api_key=api_key)
        self._api_key    = api_key
        self._model      = TEXT_MODEL
        self._live_model = live_model

    async def generate_part1_questions(self, n: int = 10) -> list[str]:
        topic = random.choice(PART1_TOPICS)
        prompt = PART1_QUESTION_PROMPT.format(n=n, topic=topic)
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[prompt],
        )
        text = (response.text or "[]").strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            questions = json.loads(text)
            if isinstance(questions, list):
                return questions[:n]
        except json.JSONDecodeError:
            pass
        return [f"Tell me about your {topic}."] * n

    async def generate_cue_card(self) -> CueCard:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[CUE_CARD_PROMPT],
        )
        text = (response.text or "{}").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
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

    async def generate_part3_questions(self, part2_topic: str, n: int = 5) -> list[str]:
        if part2_topic:
            prompt = PART3_QUESTION_PROMPT.format(part2_topic=part2_topic, n=n)
        else:
            topic = random.choice(PART3_TOPICS)
            prompt = PART3_RANDOM_QUESTION_PROMPT.format(topic=topic, n=n)

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[prompt],
        )
        text = (response.text or "[]").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            questions = json.loads(text)
            if isinstance(questions, list):
                return questions[:n]
        except json.JSONDecodeError:
            pass
        return [f"What do you think about {part2_topic or 'this topic'}?"] * n

    async def speak_question(self, text: str, voice: str = "Kore") -> bytes:
        """Return WAV bytes of the question spoken by the Gemini Live examiner voice."""
        return await gemini_live_speak(
            api_key=self._api_key,
            text=text,
            voice=voice,
            model=self._live_model,
        )
