"""AppTest for the sidebar vocab dialog stay-open behavior."""
from __future__ import annotations

import asyncio
import os
import tempfile

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import core.vocab.sidebar as sidebar_mod
import core.vocab.shared as shared_mod


# A self-contained script that calls render_vocab_sidebar with a mock store.
# AppTest.from_file re-reads the file on EVERY .run(), so the temp file must
# stay on disk for the lifetime of the AppTest (we clean up in test teardown
# via tmp_path, not in a finally block that runs before reruns).
#
# The MockStore is persisted as an attribute on `sidebar_mod` (the imported
# Python module, which is shared across AppTest runs). The script's own
# MockStore class is freshly re-executed each run, so a `MockStore()` inside
# the script would be re-instantiated every run and lose state. Attaching to
# `sidebar_mod._test_store` keeps the same instance across all reruns within
# a test, mirroring how a real MongoDB store survives reruns.
_SCRIPT = r'''
import streamlit as st
from unittest.mock import patch
import asyncio
import core.vocab.sidebar as sidebar_mod
import core.vocab.shared as shared_mod


class MockStore:
    def __init__(self):
        self._docs = {}
        self._counter = 0
    async def get_vocab(self, user_id="default", limit=20, offset=0, sort_by="created_at"):
        docs = [d for d in self._docs.values() if d["user_id"] == user_id]
        docs.sort(key=lambda d: d["created_at"], reverse=True)
        return [dict(d, _id=str(d["_id"])) for d in docs]
    async def search_vocab(self, user_id, query, limit=20):
        import re
        try:
            rx = re.compile(query, re.I)
        except re.error:
            return []
        return [dict(d, _id=str(d["_id"])) for d in self._docs.values()
                if d["user_id"] == user_id
                and (rx.search(d["word"]) or any(rx.search(s.get("meaning", ""))
                                                 for s in d.get("senses", [])))][:limit]
    async def save_vocab(self, word, meaning="", user_id="default"):
        self._counter += 1
        self._docs[str(self._counter)] = {
            "_id": str(self._counter), "word": word, "user_id": user_id,
            "senses": [{"meaning": meaning, "status": "ACTIVE"}],
            "created_at": self._counter,
        }
        return str(self._counter)
    async def add_sense(self, word_id, meaning): pass
    async def delete_vocab(self, entry_id):
        return self._docs.pop(str(entry_id), None) is not None


def fake_run_async(coro, timeout=120):
    return asyncio.run(coro)


async def _no_translate(word):
    return ""


# Persist the store on the sidebar_mod module so it survives reruns.
# (sidebar_mod is the real imported module shared across all AppTest runs;
# the script's own globals are re-executed fresh each .run().)
if not hasattr(sidebar_mod, "_test_store"):
    sidebar_mod._test_store = MockStore()

with patch.object(sidebar_mod, "run_async", fake_run_async), \
     patch.object(shared_mod, "run_async", fake_run_async), \
     patch.object(shared_mod, "_translate_to_vi", _no_translate), \
     patch.object(sidebar_mod, "is_logged_in", lambda: True), \
     patch.object(sidebar_mod, "current_user", lambda: {"_id": "u1"}):
    sidebar_mod.render_vocab_sidebar(sidebar_mod._test_store)
'''


@contextmanager
def _script_file():
    """Write the script to a temp file that lives for the duration of the test.
    AppTest.from_file re-reads the file on each .run(), so we must NOT delete
    it until the test is done with all its reruns."""
    fd, path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(_SCRIPT)
        yield path
    finally:
        os.unlink(path)


@pytest.fixture(autouse=True)
def _reset_test_store():
    """Ensure each test starts with a fresh MockStore (no cross-test leakage)."""
    if hasattr(sidebar_mod, "_test_store"):
        del sidebar_mod._test_store
    yield
    if hasattr(sidebar_mod, "_test_store"):
        del sidebar_mod._test_store


def _dialog_is_open(at) -> bool:
    """Dialog is open iff a dialog-only button ('↗ Xem tất cả') is present."""
    return any("Xem tất cả" in b.label for b in at.button)


def test_dialog_opens_on_sidebar_click():
    with _script_file() as path:
        at = AppTest.from_file(path, default_timeout=30)
        at.run()
        assert not _dialog_is_open(at)
        open_btn = next(b for b in at.button if "Từ điển cá nhân" in b.label)
        at = open_btn.click().run()
        assert _dialog_is_open(at)
        assert not at.exception


def test_dialog_stays_open_after_add_new_word():
    with _script_file() as path:
        at = AppTest.from_file(path, default_timeout=30)
        at.run()
        # Set the query BEFORE opening the dialog: the dialog body reads
        # vd_query on open, so the add-new form (no existing match) renders
        # immediately. (Setting it after open causes a fragment rerun that
        # AppTest does not surface the new buttons for.)
        at.session_state["vd_query"] = "apple"
        at = next(b for b in at.button if "Từ điển cá nhân" in b.label).click().run()
        assert _dialog_is_open(at)
        save_btn = next(b for b in at.button if "Lưu từ" in b.label)
        at = save_btn.click().run()
        # dialog stayed open after the save action's full-app rerun
        assert not at.exception, at.exception
        assert _dialog_is_open(at), "dialog closed after saving a new word"


def test_dialog_stays_open_through_delete_confirm():
    with _script_file() as path:
        at = AppTest.from_file(path, default_timeout=30)
        at.run()
        # Seed a word directly into the persisted mock store BEFORE opening
        # the dialog. This avoids routing through render_add_new_word's save
        # flow (which pops vd_notes and triggers an AppTest harness KeyError
        # on the next rerun). The save flow's stay-open behavior is already
        # covered by test_dialog_stays_open_after_add_new_word; this test
        # focuses on the delete-confirm flow.
        asyncio.run(sidebar_mod._test_store.save_vocab("bank", "bờ sông", user_id="u1"))
        # open the dialog; the seeded word renders in the list with a × button
        at = next(b for b in at.button if "Từ điển cá nhân" in b.label).click().run()
        assert _dialog_is_open(at)
        del_btn = next(b for b in at.button if b.label == "×")
        at = del_btn.click().run()  # enters confirm state
        assert _dialog_is_open(at), "dialog closed after clicking ×"
        confirm_btn = next(b for b in at.button if b.label == "✓")
        at = confirm_btn.click().run()  # confirm delete
        assert not at.exception, at.exception
        assert _dialog_is_open(at), "dialog closed after confirming delete"


def test_dialog_registered_with_on_dismiss():
    """The @st.dialog decorator must be called with on_dismiss so X/ESC clears the flag."""
    import inspect
    src = inspect.getsource(sidebar_mod)
    assert "on_dismiss=" in src, "sidebar dialog must wire on_dismiss callback"
    assert "_on_dismiss" in src
