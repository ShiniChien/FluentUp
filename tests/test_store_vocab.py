"""Tests for FluentUpStore vocabulary methods."""
from __future__ import annotations

import asyncio
import datetime

import mongomock
import pytest
from unittest.mock import patch, MagicMock


def _make_store():
    """Return a FluentUpStore wired to an in-memory mongomock client."""
    from core.store import FluentUpStore

    with patch("core.store.AsyncIOMotorClient") as mock_cls:
        mock_client = mongomock.MongoClient()
        mock_cls.return_value = mock_client
        store = FluentUpStore.__new__(FluentUpStore)
        db = mock_client["fluentup"]
        store._vocabulary = db["vocabulary"]
        store._users = db["users"]
        store._part2_attempts = db["speaking_part2"]
        store._settings = db["settings"]
        store._reading_articles = db["reading_articles"]
        store._client = mock_client
    return store


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── save_vocab ─────────────────────────────────────────────────────────────────

def test_save_vocab_creates_new_word():
    store = _make_store()
    word_id = run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    assert word_id is not None
    docs = run(store.get_vocab(user_id="u1"))
    assert len(docs) == 1
    assert docs[0]["word"] == "bank"
    assert len(docs[0]["senses"]) == 1
    assert docs[0]["senses"][0]["meaning"] == "bờ sông"
    assert docs[0]["senses"][0]["status"] == "ACTIVE"


def test_save_vocab_appends_sense_on_duplicate():
    store = _make_store()
    run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    run(store.save_vocab("bank", "ngân hàng", user_id="u1"))
    docs = run(store.get_vocab(user_id="u1"))
    assert len(docs) == 1
    assert len(docs[0]["senses"]) == 2
    meanings = [s["meaning"] for s in docs[0]["senses"]]
    assert "bờ sông" in meanings
    assert "ngân hàng" in meanings


def test_save_vocab_different_users_separate_docs():
    store = _make_store()
    run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    run(store.save_vocab("bank", "ngân hàng", user_id="u2"))
    docs_u1 = run(store.get_vocab(user_id="u1"))
    docs_u2 = run(store.get_vocab(user_id="u2"))
    assert len(docs_u1) == 1
    assert len(docs_u2) == 1


# ── add_sense ──────────────────────────────────────────────────────────────────

def test_add_sense_appends():
    store = _make_store()
    wid = run(store.save_vocab("run", "chạy", user_id="u1"))
    run(store.add_sense(wid, "điều hành"))
    docs = run(store.get_vocab(user_id="u1"))
    assert len(docs[0]["senses"]) == 2


# ── update_sense ───────────────────────────────────────────────────────────────

def test_update_sense_changes_meaning():
    store = _make_store()
    wid = run(store.save_vocab("run", "chạy", user_id="u1"))
    ok = run(store.update_sense(wid, 0, "chạy bộ"))
    assert ok is True
    docs = run(store.get_vocab(user_id="u1"))
    assert docs[0]["senses"][0]["meaning"] == "chạy bộ"


# ── delete_sense ───────────────────────────────────────────────────────────────

def test_delete_sense_removes_one():
    store = _make_store()
    wid = run(store.save_vocab("run", "chạy", user_id="u1"))
    run(store.add_sense(wid, "điều hành"))
    deleted_word = run(store.delete_sense(wid, 0))
    assert deleted_word is False  # word still exists
    docs = run(store.get_vocab(user_id="u1"))
    assert len(docs[0]["senses"]) == 1
    assert docs[0]["senses"][0]["meaning"] == "điều hành"


def test_delete_sense_removes_word_when_last():
    store = _make_store()
    wid = run(store.save_vocab("run", "chạy", user_id="u1"))
    deleted_word = run(store.delete_sense(wid, 0))
    assert deleted_word is True  # whole doc deleted
    docs = run(store.get_vocab(user_id="u1"))
    assert len(docs) == 0


# ── count_review_vocab ─────────────────────────────────────────────────────────

def test_count_review_vocab_zero():
    store = _make_store()
    run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    assert run(store.count_review_vocab("u1")) == 0


def test_count_review_vocab_counts_words_with_any_review_sense():
    store = _make_store()
    wid = run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    store._vocabulary.update_one(
        {"_id": __import__("bson").ObjectId(wid)},
        {"$push": {"senses": {"meaning": "ngân hàng", "status": "IN_REVIEW",
                               "created_at": datetime.datetime.utcnow()}}},
    )
    assert run(store.count_review_vocab("u1")) == 1


# ── migration ──────────────────────────────────────────────────────────────────

def test_migrate_converts_notes_to_senses():
    store = _make_store()
    import datetime, bson
    now = datetime.datetime.utcnow()
    store._vocabulary.insert_one({
        "word": "legacy", "notes": "di sản", "user_id": "u1", "created_at": now,
    })
    store._vocabulary.insert_one({
        "word": "empty_notes", "notes": "", "user_id": "u1", "created_at": now,
    })
    run(store._migrate_vocab())
    docs = list(store._vocabulary.find({"user_id": "u1"}))
    by_word = {d["word"]: d for d in docs}
    assert "notes" not in by_word["legacy"]
    assert by_word["legacy"]["senses"][0]["meaning"] == "di sản"
    assert by_word["legacy"]["senses"][0]["status"] == "ACTIVE"
    assert "notes" not in by_word["empty_notes"]
    assert by_word["empty_notes"]["senses"] == []
