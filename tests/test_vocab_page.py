"""AppTest for the full-page vocabulary management UI."""
from __future__ import annotations

import asyncio
import re
from contextlib import contextmanager
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import core.vocab.page as page_mod
import core.vocab.shared as shared_mod
import core.vocab.quiz as quiz_mod


class _MockStore:
    """In-memory store mirroring the FluentUpStore vocab surface used by the page."""
    def __init__(self):
        self._docs = {}
        self._counter = 0

    async def count_vocab(self, user_id):
        return sum(1 for d in self._docs.values() if d["user_id"] == user_id)

    async def get_vocab(self, user_id="default", limit=20, offset=0, sort_by="created_at"):
        # Used by page.py BEFORE the Task 4 rewrite; kept so the mock works at both stages.
        docs = [d for d in self._docs.values() if d["user_id"] == user_id]
        docs.sort(key=lambda d: d["word"] if sort_by == "word" else d["created_at"],
                  reverse=(sort_by != "word"))
        page = docs[offset:offset + limit]
        return [dict(d, _id=str(d["_id"])) for d in page]

    async def query_vocab(self, user_id, limit=20, offset=0, sort_by="created_at",
                          filter_text="", review_only=False):
        docs = [d for d in self._docs.values() if d["user_id"] == user_id]
        if filter_text:
            ft = filter_text.lower()
            docs = [d for d in docs
                    if ft in d["word"].lower()
                    or any(ft in s.get("meaning", "").lower() for s in d.get("senses", []))]
        if review_only:
            docs = [d for d in docs
                    if any(s.get("status") == "IN_REVIEW" for s in d.get("senses", []))]
        docs.sort(key=lambda d: d["word"] if sort_by == "word" else d["created_at"],
                  reverse=(sort_by != "word"))
        total = len(docs)
        page = docs[offset:offset + limit]
        return total, [dict(d, _id=str(d["_id"])) for d in page]

    async def save_vocab(self, word, meaning="", user_id="default"):
        self._counter += 1
        self._docs[str(self._counter)] = {
            "_id": str(self._counter), "word": word, "user_id": user_id,
            "senses": [{"meaning": meaning, "status": "ACTIVE"}],
            "created_at": self._counter,
        }
        return str(self._counter)

    async def search_vocab(self, user_id, query, limit=20):
        try:
            rx = re.compile(query, re.I)
        except re.error:
            return []
        return [dict(d, _id=str(d["_id"])) for d in self._docs.values()
                if d["user_id"] == user_id
                and (rx.search(d["word"]) or any(rx.search(s.get("meaning", ""))
                                                 for s in d.get("senses", [])))][:limit]

    async def add_sense(self, word_id, meaning): pass
    async def update_sense(self, word_id, idx, meaning): return True
    async def delete_sense(self, word_id, idx): return True
    async def delete_vocab(self, entry_id):
        return self._docs.pop(str(entry_id), None) is not None
    async def sample_vocab(self, user_id, n=5): return []
    async def mark_sense_review(self, word_id, sense_idx=0): return True


def _fake_run_async(coro, timeout=120):
    return asyncio.run(coro)


async def _no_translate(word):
    return ""


@contextmanager
def _patches():
    # Patches must be active WHILE the script runs. AppTest runs the script
    # inside .run(), so we wrap each .run() call in this context manager.
    with patch.object(page_mod, "run_async", _fake_run_async), \
         patch.object(shared_mod, "run_async", _fake_run_async), \
         patch.object(quiz_mod, "run_async", _fake_run_async), \
         patch.object(shared_mod, "_translate_to_vi", _no_translate), \
         patch.object(page_mod, "current_user", lambda: {"_id": "u1"}):
        yield


def _render(store_arg):
    # from_function compiles this function's body as a standalone script.
    # Imports inside the body run in the script's namespace; the store arrives
    # via args=(store,) below.
    import core.vocab.page as pm
    pm.render_vocab_page(store_arg)


def _run_page(store):
    at = AppTest.from_function(_render, default_timeout=30, args=(store,))
    with _patches():
        at.run()
    return at


def _run(at):
    """Re-run an existing AppTest (or widget) with patches active.

    `save_btn.click()` returns the Button widget, whose `.run()` proxies to
    the AppTest and returns it — so we must return the result of `.run()`,
    not the input. Works for both AppTest and widget inputs.
    """
    with _patches():
        return at.run()


def _ss(at, key, default=""):
    """Safe session_state read on AppTest (SafeSessionState has no .get)."""
    return at.session_state[key] if key in at.session_state else default


def test_quick_add_save_does_not_crash():
    store = _MockStore()
    asyncio.run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    at = _run_page(store)
    assert not at.exception
    # fill the quick-add bar
    at.session_state["vocab_quick_word"] = "apple"
    at.session_state["vocab_quick_meaning"] = "quả táo"
    save_btn = next(b for b in at.button if b.label == "💾 Lưu")
    at = _run(save_btn.click())
    # PRIMARY criterion: no StreamlitAPIException about "cannot be modified"
    exc_msg = str(at.exception[0]) if at.exception else ""
    assert "cannot be modified" not in exc_msg, exc_msg
    # new word persisted in the mock store (real success signal)
    assert any(d["word"] == "apple" for d in store._docs.values())
    # inputs cleared (robust to harness artifact: key may be absent after pop)
    assert _ss(at, "vocab_quick_word", "") == ""
    assert _ss(at, "vocab_quick_meaning", "") == ""
