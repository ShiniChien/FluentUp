from __future__ import annotations

import asyncio
import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

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
            username=username if username else None,
            password=password if password else None,
            serverSelectionTimeoutMS=5000,
        )
        db = self._client["fluentup"]
        self._vocabulary = db["vocabulary"]
        self._users = db["users"]
        self._part2_attempts = db["speaking_part2"]

    async def ensure_indexes(self) -> None:
        await self._vocabulary.create_index("user_id", background=True)

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    # ── Vocabulary CRUD ───────────────────────────────────────────────────────

    async def save_vocab(
        self, word: str, notes: str = "", user_id: str = "default"
    ) -> str:
        doc: dict[str, Any] = {
            "word":       word.strip(),
            "notes":      notes.strip(),
            "user_id":    user_id,
            "created_at": datetime.datetime.utcnow(),
        }
        result = await _retry_write(self._vocabulary.insert_one, doc)
        return str(result.inserted_id)

    async def get_vocab(
        self, user_id: str = "default", limit: int = 20
    ) -> list[dict]:
        cursor = self._vocabulary.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
        )
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs

    async def search_vocab(
        self, user_id: str, query: str, limit: int = 20
    ) -> list[dict]:
        regex = {"$regex": query, "$options": "i"}
        cursor = self._vocabulary.find(
            {"user_id": user_id, "$or": [{"word": regex}, {"notes": regex}]},
            sort=[("created_at", -1)],
            limit=limit,
        )
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs

    async def delete_vocab(self, entry_id: str) -> bool:
        result = await self._vocabulary.delete_one({"_id": ObjectId(entry_id)})
        return result.deleted_count > 0

    async def update_vocab(self, entry_id: str, notes: str) -> bool:
        result = await self._vocabulary.update_one(
            {"_id": ObjectId(entry_id)},
            {"$set": {"notes": notes.strip()}},
        )
        return result.modified_count > 0

    # ── User account CRUD ─────────────────────────────────────────────────────

    async def get_user_by_username(self, username: str) -> dict | None:
        doc = await self._users.find_one({"username": username})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def list_users(self) -> list[dict]:
        cursor = self._users.find({}, sort=[("created_at", 1)])
        docs = await cursor.to_list(length=500)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs

    async def create_user(
        self,
        username: str,
        password_hash: str,
        name: str = "",
        age: int = 22,
        occupation: str = "student",
        occupation_detail: str = "",
        gender: str = "male",
    ) -> str | None:
        """Insert a new user. Returns inserted _id, or None if username taken."""
        existing = await self._users.find_one({"username": username})
        if existing:
            return None
        now = datetime.datetime.utcnow()
        result = await _retry_write(self._users.insert_one, {
            "username":          username,
            "password_hash":     password_hash,
            "role":              "user",
            "name":              name,
            "age":               age,
            "occupation":        occupation,
            "occupation_detail": occupation_detail,
            "gender":            gender,
            "created_at":        now,
            "updated_at":        now,
        })
        return str(result.inserted_id)

    async def update_user(self, user_id: str, **fields: Any) -> bool:
        fields["updated_at"] = datetime.datetime.utcnow()
        result = await _retry_write(
            self._users.update_one,
            {"_id": ObjectId(user_id)},
            {"$set": fields},
        )
        return result.matched_count > 0

    async def delete_user(self, user_id: str) -> bool:
        result = await self._users.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0

    # ── Part 2 attempts ───────────────────────────────────────────────────────

    async def save_part2_attempt(
        self,
        user_id: str,
        topic: str,
        transcript: str,
        cue_points: list[str],
        cue_explain: str = "",
    ) -> str:
        doc: dict[str, Any] = {
            "user_id":     user_id,
            "topic":       topic,
            "transcript":  transcript,
            "cue_points":  cue_points,
            "cue_explain": cue_explain,
            "created_at":  datetime.datetime.utcnow(),
        }
        result = await _retry_write(self._part2_attempts.insert_one, doc)
        return str(result.inserted_id)

    async def get_part2_attempts(
        self, user_id: str, limit: int = 20
    ) -> list[dict]:
        cursor = self._part2_attempts.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
        )
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs
