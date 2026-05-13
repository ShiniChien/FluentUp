from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

_logger = logging.getLogger(__name__)

_WRITE_RETRIES = 3
_RETRY_DELAY = 1.0


async def _maybe_await(value):
    """Await value if it is a coroutine/awaitable; otherwise return it directly.

    Needed because tests wire mongomock (sync) collections in place of Motor
    (async) collections, so method calls may return plain values instead of
    coroutines.
    """
    if inspect.isawaitable(value):
        return await value
    return value


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
        self._settings = db["settings"]
        self._reading_articles = db["reading_articles"]

    async def ensure_indexes(self) -> None:
        await self._vocabulary.create_index("user_id", background=True)
        await self._vocabulary.create_index(
            [("word", 1), ("user_id", 1)], unique=True, background=True
        )
        db = self._client["fluentup"]
        await db["writing_topics"].create_index([("task_type", 1)], background=True)
        await db["writing_topics"].create_index([("created_at", -1)], background=True)
        await self._reading_articles.create_index("url", unique=True, background=True)
        await self._reading_articles.create_index("category", background=True)
        await self._reading_articles.create_index([("created_at", -1)], background=True)
        await self._migrate_vocab()

    async def _migrate_vocab(self) -> None:
        """One-time migration: convert `notes` field → senses array."""
        sample = await _maybe_await(self._vocabulary.find_one({"notes": {"$exists": True}}))
        if sample is None:
            return
        cursor = self._vocabulary.find({"notes": {"$exists": True}})
        # Support both sync (mongomock) and async (Motor) cursors
        if inspect.isasyncgen(cursor) or hasattr(cursor, '__aiter__'):
            docs = await _maybe_await(cursor.to_list(length=10000))
        else:
            docs = list(cursor)
        for doc in docs:
            notes = doc.get("notes", "").strip()
            senses = (
                [{"meaning": notes, "status": "ACTIVE", "created_at": doc.get("created_at", datetime.datetime.utcnow())}]
                if notes else []
            )
            await _maybe_await(self._vocabulary.update_one(
                {"_id": doc["_id"]},
                {"$set": {"senses": senses}, "$unset": {"notes": ""}},
            ))
        _logger.info("vocab migration complete")

    async def ping(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            _logger.exception("MongoDB ping failed")
            return False

    # ── Vocabulary CRUD ───────────────────────────────────────────────────────

    async def save_vocab(
        self, word: str, meaning: str = "", user_id: str = "default"
    ) -> str:
        word = word.strip()
        sense: dict[str, Any] = {
            "meaning": meaning.strip(),
            "status": "ACTIVE",
            "created_at": datetime.datetime.utcnow(),
        }
        now = datetime.datetime.utcnow()
        result = await _maybe_await(self._vocabulary.update_one(
            {"word": word, "user_id": user_id},
            {"$push": {"senses": sense}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
        if result.upserted_id is not None:
            return str(result.upserted_id)
        doc = await _maybe_await(self._vocabulary.find_one({"word": word, "user_id": user_id}, {"_id": 1}))
        return str(doc["_id"])

    async def get_vocab(
        self, user_id: str = "default", limit: int = 20
    ) -> list[dict]:
        cursor = self._vocabulary.find(
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
        )
        if hasattr(cursor, 'to_list'):
            docs = await _maybe_await(cursor.to_list(length=limit))
        else:
            docs = list(cursor)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs

    async def search_vocab(
        self, user_id: str, query: str, limit: int = 20
    ) -> list[dict]:
        regex = {"$regex": query, "$options": "i"}
        cursor = self._vocabulary.find(
            {"user_id": user_id, "$or": [{"word": regex}, {"senses.meaning": regex}]},
            sort=[("created_at", -1)],
            limit=limit,
        )
        if hasattr(cursor, 'to_list'):
            docs = await _maybe_await(cursor.to_list(length=limit))
        else:
            docs = list(cursor)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return docs

    async def delete_vocab(self, entry_id: str) -> bool:
        result = await self._vocabulary.delete_one({"_id": ObjectId(entry_id)})
        return result.deleted_count > 0

    async def add_sense(self, word_id: str, meaning: str) -> None:
        sense: dict[str, Any] = {
            "meaning": meaning.strip(),
            "status": "ACTIVE",
            "created_at": datetime.datetime.utcnow(),
        }
        await _maybe_await(self._vocabulary.update_one(
            {"_id": ObjectId(word_id)},
            {"$push": {"senses": sense}},
        ))

    async def update_sense(self, word_id: str, sense_idx: int, meaning: str) -> bool:
        result = await _maybe_await(self._vocabulary.update_one(
            {"_id": ObjectId(word_id)},
            {"$set": {f"senses.{sense_idx}.meaning": meaning.strip()}},
        ))
        return result.modified_count > 0

    async def delete_sense(self, word_id: str, sense_idx: int) -> bool:
        """Remove sense at index. Returns True if the whole word was deleted."""
        doc = await _maybe_await(self._vocabulary.find_one({"_id": ObjectId(word_id)}))
        if doc is None:
            return False
        senses: list = doc.get("senses", [])
        if len(senses) <= 1:
            await _maybe_await(self._vocabulary.delete_one({"_id": ObjectId(word_id)}))
            return True
        senses.pop(sense_idx)
        await _maybe_await(self._vocabulary.update_one(
            {"_id": ObjectId(word_id)},
            {"$set": {"senses": senses}},
        ))
        return False

    async def count_review_vocab(self, user_id: str) -> int:
        return await _maybe_await(self._vocabulary.count_documents(
            {"user_id": user_id, "senses.status": "IN_REVIEW"}
        ))

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

    # ── Provider config ───────────────────────────────────────────────────────

    async def get_provider_config(self) -> dict | None:
        doc = await self._settings.find_one({"_id": "config"})
        if doc is not None:
            doc.pop("_id", None)
        return doc

    async def save_provider_config(self, active: str, providers: dict) -> None:
        if active not in providers:
            raise ValueError(f"active provider {active!r} not found in providers keys")
        await self._settings.update_one(
            {"_id": "config"},
            {"$set": {"active_provider": active, "providers": providers}},
            upsert=True,
        )

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
        self, user_id: str, limit: int = 20,
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

    # ── Reading articles ──────────────────────────────────────────────────────

    async def get_reading_article_by_url(self, url: str) -> dict | None:
        doc = await self._reading_articles.find_one({"url": url})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    async def save_reading_article(
        self,
        url: str,
        title: str,
        body: str,
        category: str,
        published_at: str,
        questions: dict,
    ) -> str:
        from pymongo.errors import DuplicateKeyError
        doc = {
            "url":          url,
            "title":        title,
            "body":         body,
            "category":     category,
            "published_at": published_at,
            "questions":    questions,
            "created_at":   datetime.datetime.utcnow(),
            "attempts":     [],
        }
        try:
            result = await _retry_write(self._reading_articles.insert_one, doc)
            return str(result.inserted_id)
        except DuplicateKeyError:
            existing = await self._reading_articles.find_one({"url": url})
            return str(existing["_id"]) if existing else ""

    async def push_reading_attempt(
        self,
        doc_id: str,
        user_id: str,
        answers: dict,
        score: dict,
    ) -> None:
        attempt = {
            "user_id":      user_id,
            "answers":      answers,
            "score":        score,
            "attempted_at": datetime.datetime.utcnow(),
        }
        await _retry_write(
            self._reading_articles.update_one,
            {"_id": ObjectId(doc_id)},
            {"$push": {"attempts": attempt}},
        )

    async def list_reading_attempts(self, user_id: str, limit: int = 20) -> list[dict]:
        """Return articles that have at least one attempt by user_id."""
        cursor = self._reading_articles.find(
            {"attempts.user_id": user_id},
            {"title": 1, "category": 1, "url": 1, "attempts": 1, "created_at": 1},
            sort=[("created_at", -1)],
            limit=limit,
        )
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["attempts"] = [a for a in doc.get("attempts", []) if a["user_id"] == user_id]
        return docs
