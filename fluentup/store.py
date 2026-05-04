"""
fluentup/store.py
-----------------
MongoDB persistence layer via motor (async).

Collections:
  sessions — completed exam sessions (transcripts + text feedback, no audio bytes)
  profiles — user profiles (name, age, occupation)
"""
from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from fluentup.models import ExamSummary

if TYPE_CHECKING:
    from fluentup.models import UserProfile

_WRITE_RETRIES = 3
_RETRY_DELAY = 1.0


async def _retry_write(coro_fn, *args, **kwargs):
    """Retry a write coroutine up to _WRITE_RETRIES times on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(_WRITE_RETRIES):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < _WRITE_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAY * (attempt + 1))
    raise last_exc


class FluentUpStore:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self._client = AsyncIOMotorClient(
            uri,
            username=username,
            password=password,
            serverSelectionTimeoutMS=5000,
        )
        db = self._client["fluentup"]
        self._sessions = db["sessions"]
        self._profiles = db["profiles"]

    async def save_session(
        self, summary: ExamSummary, user_id: str = "default"
    ) -> str:
        """Persist a completed session. Audio bytes are NOT stored."""
        doc: dict[str, Any] = {
            "user_id":    user_id,
            "created_at": datetime.datetime.utcnow(),
            "turns": [
                {
                    "part":       t.part,
                    "question":   t.question,
                    "transcript": t.result.transcript if t.result else "",
                    "feedbacks": [
                        {
                            "criterion": f.criterion,
                            "feedback":  f.feedback,
                        }
                        for f in t.result.feedbacks
                    ] if t.result else [],
                }
                for t in summary.turns
            ],
        }
        result = await _retry_write(self._sessions.insert_one, doc)
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

    async def delete_session(self, session_id: str) -> bool:
        result = await self._sessions.delete_one({"_id": ObjectId(session_id)})
        return result.deleted_count > 0

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    # ── Profile CRUD ──────────────────────────────────────────────────────────

    async def save_profile(self, profile: "UserProfile") -> str:
        """Insert or update a profile. Updates in-place if profile_id is set."""
        doc: dict[str, Any] = {
            "name":               profile.name,
            "age":                profile.age,
            "occupation":         profile.occupation,
            "occupation_detail":  profile.occupation_detail,
            "gender":             profile.gender,
            "updated_at":         datetime.datetime.utcnow(),
        }
        if profile.profile_id:
            await _retry_write(
                self._profiles.update_one,
                {"_id": ObjectId(profile.profile_id)},
                {"$set": doc},
                upsert=True,
            )
            return profile.profile_id
        doc["created_at"] = doc["updated_at"]
        result = await _retry_write(self._profiles.insert_one, doc)
        return str(result.inserted_id)

    async def get_profiles(self, limit: int = 20) -> list[dict]:
        cursor = self._profiles.find(
            {}, sort=[("updated_at", -1)], limit=limit
        )
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    async def delete_profile(self, profile_id: str) -> bool:
        result = await self._profiles.delete_one({"_id": ObjectId(profile_id)})
        return result.deleted_count > 0
