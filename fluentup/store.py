"""
fluentup/store.py
-----------------
MongoDB persistence layer via motor (async).

Collections:
  sessions   — completed exam sessions (scores, transcripts, no audio bytes)
  vocabulary — words saved during sessions for spaced-repetition review
"""
from __future__ import annotations

import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from fluentup.models import ExamSummary


class FluentUpStore:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self._client = AsyncIOMotorClient(
            uri,
            username=username,
            password=password,
            serverSelectionTimeoutMS=5000,
        )
        db = self._client["fluentup"]
        self._sessions   = db["sessions"]
        self._vocabulary = db["vocabulary"]

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def save_session(
        self, summary: ExamSummary, user_id: str = "default"
    ) -> str:
        """Persist a completed session. Audio bytes are NOT stored."""
        doc: dict[str, Any] = {
            "user_id":    user_id,
            "created_at": datetime.datetime.utcnow(),
            "overall":    summary.overall,
            "avg_fc":     summary.avg_fc,
            "avg_lr":     summary.avg_lr,
            "avg_gr":     summary.avg_gr,
            "avg_pronun": summary.avg_pronun,
            "turns": [
                {
                    "part":         t.part,
                    "question":     t.question,
                    "transcript":   t.result.transcript if t.result else "",
                    "overall_band": t.result.overall_band if t.result else 0.0,
                    "scores": [
                        {
                            "criterion": s.criterion,
                            "band":      s.band,
                            "feedback":  s.feedback,
                            "examples":  s.examples,
                            "tips":      s.tips,
                        }
                        for s in t.result.scores
                    ] if t.result else [],
                }
                for t in summary.turns
            ],
        }
        result = await self._sessions.insert_one(doc)
        return str(result.inserted_id)

    async def get_recent_sessions(
        self, user_id: str = "default", limit: int = 10
    ) -> list[dict]:
        """Return recent sessions (without turn details) for history panel."""
        cursor = self._sessions.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
            projection={"turns": 0},
        )
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    async def get_session(self, session_id: str) -> dict | None:
        doc = await self._sessions.find_one({"_id": ObjectId(session_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    # ── Vocabulary ────────────────────────────────────────────────────────────

    async def add_word(
        self,
        word: str,
        definition: str,
        example: str = "",
        user_id: str = "default",
    ) -> None:
        await self._vocabulary.update_one(
            {"user_id": user_id, "word": word.lower()},
            {
                "$set": {
                    "definition": definition,
                    "example":    example,
                    "updated_at": datetime.datetime.utcnow(),
                },
                "$setOnInsert": {
                    "created_at": datetime.datetime.utcnow(),
                    "review_count": 0,
                },
            },
            upsert=True,
        )

    async def get_vocabulary(
        self, user_id: str = "default", limit: int = 100
    ) -> list[dict]:
        cursor = self._vocabulary.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
        )
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    # ── Health check ──────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False
