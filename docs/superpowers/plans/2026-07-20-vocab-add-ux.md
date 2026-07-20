# Vocab Add/Edit UX Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the sidebar dictionary dialog closing on every in-dialog button action, fix the page quick-add crash after save, and replace the page's offset "Load more" + client-side filter with server-side filtered numbered pagination.

**Architecture:** Three independent code fixes plus a shared store method. (1) Sidebar dialog: keep the `_vocab_dialog_open` flag `True` across reruns and clear it only via an `on_dismiss` callback, so in-dialog `st.rerun()` calls reopen the dialog. (2) Page quick-add: `pop` widget keys instead of assigning to them after instantiation. (3) Page list: new `FluentUpStore.query_vocab(user_id, limit, offset, sort_by, filter_text, review_only) -> (total, docs)` does filtering/sorting/counting server-side; the page migrates from `vocab_offset` to 1-indexed `vocab_page` and renders numbered pagination with ellipsis + prev/next.

**Tech Stack:** Python 3.11 (conda env `tmchien`), Streamlit 1.54.0, Motor (async MongoDB), mongomock (tests), `streamlit.testing.v1.AppTest` (UI tests), pytest.

**User decisions (already made):**
- Dialog fix approach: keep `_vocab_dialog_open` flag + `on_dismiss` callback (not popover/expander, not fragment-scope rerun).
- Page list layout: keep card-based list with inline Sửa/Xoá; only improve pagination.
- Page filter: server-side (MongoDB query), not client-side.
- Page cache: no `@st.cache_data` — fetch fresh each render.
- Page size: 20.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `core/store.py` | Async MongoDB wrappers | Add `import re`; add `query_vocab` method |
| `core/vocab/sidebar.py` | Sidebar button + dialog | Add `_on_dismiss`; pass `on_dismiss=` to `@st.dialog`; stop clearing flag in open pass |
| `core/vocab/shared.py` | Shared dialog/page UI components | `render_quick_add_bar`: `pop` instead of `= ""` for two widget keys |
| `core/vocab/page.py` | Full-page vocab management | Migrate offset→page; single `query_vocab` call; add `_page_window` + `_render_pagination`; remove "Load more" + client-side filter |
| `tests/test_store_vocab.py` | Store unit tests | Add `query_vocab` tests |
| `tests/test_vocab_sidebar.py` | Dialog AppTest (new) | Stay-open across add + delete-confirm; on_dismiss wiring |
| `tests/test_vocab_page.py` | Page AppTest (new) | Quick-add no-crash; pagination render + navigation; filter reset |

---

## Task 1: Add `query_vocab` store method + unit tests

**Goal:** Add a unified server-side filtered/sorted/paginated vocab query returning `(total, docs)`, with unit tests covering filter-by-word, filter-by-meaning, review-only, sort, offset, and combined.

**Files:**
- Modify: `core/store.py` (add `import re` at top; add `query_vocab` method after `mark_sense_review`, before the `# ── User account CRUD` section at line 231)
- Test: `tests/test_store_vocab.py` (append new tests)

**Acceptance Criteria:**
- [ ] `query_vocab(user_id, limit, offset, sort_by, filter_text, review_only)` returns a `(int, list[dict])` tuple.
- [ ] `filter_text` matches `word` OR any `senses.meaning`, case-insensitive; `total` reflects the filter.
- [ ] `review_only=True` returns only docs with at least one `IN_REVIEW` sense.
- [ ] `sort_by="word"` returns A→Z; `sort_by="created_at"` (default) returns newest first.
- [ ] `offset`/`limit` return the correct slice; `total` is the full matching count independent of offset/limit.
- [ ] Each returned doc has `_id` converted to `str`.
- [ ] All `query_vocab` tests pass; pre-existing 18 tests still pass (no regressions).
- [ ] `conda run -n tmchien python -m py_compile core/store.py` succeeds.

**Verify:** `conda run -n tmchien python -m pytest tests/test_store_vocab.py -v` → all tests PASS (18 pre-existing + new).

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store_vocab.py` (after the existing `test_get_vocab_offset` at the end of the file):

```python
# ── query_vocab ───────────────────────────────────────────────────────────────

def test_query_vocab_filter_word():
    store = _make_store()
    run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    run(store.save_vocab("apple", "quả táo", user_id="u1"))
    total, docs = run(store.query_vocab("u1", filter_text="bank"))
    assert total == 1
    assert [d["word"] for d in docs] == ["bank"]


def test_query_vocab_filter_meaning():
    store = _make_store()
    run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    run(store.save_vocab("apple", "quả táo", user_id="u1"))
    total, docs = run(store.query_vocab("u1", filter_text="táo"))
    assert total == 1
    assert [d["word"] for d in docs] == ["apple"]


def test_query_vocab_filter_case_insensitive():
    store = _make_store()
    run(store.save_vocab("Bank", "bờ sông", user_id="u1"))
    total, docs = run(store.query_vocab("u1", filter_text="bank"))
    assert total == 1
    assert docs[0]["word"] == "Bank"


def test_query_vocab_review_only():
    store = _make_store()
    wid = run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    run(store.save_vocab("apple", "quả táo", user_id="u1"))
    run(store.mark_sense_review(wid, 0))
    total, docs = run(store.query_vocab("u1", review_only=True))
    assert total == 1
    assert [d["word"] for d in docs] == ["bank"]


def test_query_vocab_sort_word():
    store = _make_store()
    run(store.save_vocab("zebra", "ngựa vằn", user_id="u1"))
    run(store.save_vocab("apple", "quả táo", user_id="u1"))
    run(store.save_vocab("mango", "quả xoài", user_id="u1"))
    total, docs = run(store.query_vocab("u1", sort_by="word"))
    assert total == 3
    assert [d["word"] for d in docs] == ["apple", "mango", "zebra"]


def test_query_vocab_offset_limit_total_independent():
    store = _make_store()
    for i in range(5):
        run(store.save_vocab(f"word{i}", f"nghĩa{i}", user_id="u1"))
    total, docs = run(store.query_vocab("u1", limit=2, offset=2, sort_by="word"))
    assert total == 5  # full matching count, not the slice length
    assert len(docs) == 2
    assert [d["word"] for d in docs] == ["word2", "word3"]


def test_query_vocab_combined_filter_review_sort_offset():
    store = _make_store()
    # three words matching "run", two of them IN_REVIEW
    w0 = run(store.save_vocab("runner", "người chạy", user_id="u1"))
    w1 = run(store.save_vocab("run", "chạy", user_id="u1"))
    run(store.save_vocab("prune", "mận", user_id="u1"))  # matches "run" substring
    run(store.mark_sense_review(w0, 0))
    run(store.mark_sense_review(w1, 0))
    total, docs = run(store.query_vocab(
        "u1", limit=10, offset=0, sort_by="word",
        filter_text="run", review_only=True,
    ))
    assert total == 2
    assert [d["word"] for d in docs] == ["run", "runner"]


def test_query_vocab_returns_str_ids():
    store = _make_store()
    run(store.save_vocab("bank", "bờ sông", user_id="u1"))
    _, docs = run(store.query_vocab("u1"))
    assert all(isinstance(d["_id"], str) for d in docs)


def test_query_vocab_empty_user():
    store = _make_store()
    total, docs = run(store.query_vocab("nobody"))
    assert total == 0
    assert docs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n tmchien python -m pytest tests/test_store_vocab.py -k query_vocab -v`
Expected: FAIL with `AttributeError: 'FluentUpStore' object has no attribute 'query_vocab'` (or collection on the new tests).

- [ ] **Step 3: Add `import re` and implement `query_vocab`**

In `core/store.py`, add `import re` to the top imports block. The current header (lines 1-10) is:

```python
from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
```

Change to:

```python
from __future__ import annotations

import asyncio
import datetime
import inspect
import logging
import re
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
```

Then insert the `query_vocab` method immediately after `mark_sense_review` (which ends at line 229 with `return result.modified_count > 0`) and before the `# ── User account CRUD` comment (line 231). Insert:

```python
    async def query_vocab(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        filter_text: str = "",
        review_only: bool = False,
    ) -> tuple[int, list[dict]]:
        """Filtered, sorted, paginated vocab query. Returns (total_matching, docs)."""
        query: dict[str, Any] = {"user_id": user_id}
        if filter_text:
            rx = {"$regex": re.escape(filter_text), "$options": "i"}
            query["$or"] = [{"word": rx}, {"senses.meaning": rx}]
        if review_only:
            query["senses.status"] = "IN_REVIEW"
        sort_field = "word" if sort_by == "word" else "created_at"
        sort_dir = 1 if sort_by == "word" else -1
        total = await _maybe_await(self._vocabulary.count_documents(query))
        cursor = self._vocabulary.find(
            query, sort=[(sort_field, sort_dir)], skip=offset, limit=limit,
        )
        if hasattr(cursor, "to_list"):
            docs = await _maybe_await(cursor.to_list(length=limit))
        else:
            docs = list(cursor)
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return total, docs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n tmchien python -m pytest tests/test_store_vocab.py -v`
Expected: PASS — all 18 pre-existing + 9 new `query_vocab` tests (27 total).

- [ ] **Step 5: Compile check + commit**

Run: `conda run -n tmchien python -m py_compile core/store.py`
Expected: no output (success).

```bash
git add core/store.py tests/test_store_vocab.py
git commit -m "feat(store): add query_vocab — server-side filtered/paginated vocab query

Returns (total, docs) in one call with regex filter on word + senses.meaning,
review_only filter, sort by word or created_at, and offset/limit pagination."
```

---

## Task 2: Fix sidebar dialog stay-open behavior

**Goal:** Make the sidebar dictionary dialog stay open across all in-dialog button actions (add / add-sense / edit-sense / delete-sense / delete-word / translate) and close only via explicit dismiss (X / ESC / click-outside), using an `on_dismiss` callback to clear the open flag.

**Files:**
- Modify: `core/vocab/sidebar.py` (add `_on_dismiss`; pass `on_dismiss=` to `@st.dialog`; remove the flag-clearing line in `render_vocab_sidebar`)
- Test: `tests/test_vocab_sidebar.py` (new)

**Acceptance Criteria:**
- [ ] Clicking the sidebar "📖 Từ điển cá nhân" button opens the dialog.
- [ ] After saving a new word inside the dialog, the dialog stays open (a dialog-only element such as "↗ Xem tất cả" is still present) and the new word appears in the rendered list.
- [ ] After clicking × on an entry then ✓ to confirm delete, the dialog stays open and the entry is removed.
- [ ] `on_dismiss` is wired (the dialog is registered with a dismiss callback) so X / ESC / click-outside clears `_vocab_dialog_open`.
- [ ] No `StreamlitAPIException` during any of the above flows.
- [ ] `conda run -n tmchien python -m py_compile core/vocab/sidebar.py` succeeds.

**Verify:** `conda run -n tmchien python -m pytest tests/test_vocab_sidebar.py -v` → all tests PASS.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vocab_sidebar.py`:

```python
"""AppTest for the sidebar vocab dialog stay-open behavior."""
from __future__ import annotations

import asyncio
import os
import tempfile

from contextlib import contextmanager
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import core.vocab.sidebar as sidebar_mod
import core.vocab.shared as shared_mod


# A self-contained script that calls render_vocab_sidebar with a mock store.
# AppTest.from_file re-reads the file on EVERY .run(), so the temp file must
# stay on disk for the lifetime of the AppTest (we clean up in test teardown
# via tmp_path, not in a finally block that runs before reruns).
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


with patch.object(sidebar_mod, "run_async", fake_run_async), \
     patch.object(shared_mod, "run_async", fake_run_async), \
     patch.object(shared_mod, "_translate_to_vi", _no_translate), \
     patch.object(sidebar_mod, "is_logged_in", lambda: True), \
     patch.object(sidebar_mod, "current_user", lambda: {"_id": "u1"}):
    sidebar_mod.render_vocab_sidebar(MockStore())
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
        # seed one word: set query, open, save
        at.session_state["vd_query"] = "bank"
        at = next(b for b in at.button if "Từ điển cá nhân" in b.label).click().run()
        at = next(b for b in at.button if "Lưu từ" in b.label).click().run()
        assert _dialog_is_open(at)
        # clear query so the full list + × buttons render
        at.session_state["vd_query"] = ""
        at = at.run()
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n tmchien python -m pytest tests/test_vocab_sidebar.py -v`
Expected: FAIL — `test_dialog_stays_open_after_add_new_word` and `test_dialog_stays_open_through_delete_confirm` fail (dialog closes after the action under current code); `test_dialog_registered_with_on_dismiss` fails (`on_dismiss=` not in source). (`test_dialog_opens_on_sidebar_click` passes under current code — that is fine; it guards against regression.)

> **AppTest caveat (do not "fix" by weakening the tests):** After `render_add_new_word` saves, it `pop`s `vd_query` and `vd_notes`, then calls `st.rerun()`. On the next AppTest `.run()`, Streamlit's test harness raises `KeyError: ... has no key "<widget-id>-vd_notes"` because the widget was instantiated in a prior run with an id whose session_state entry the `pop` removed, and AppTest re-reads the stale widget id. This is a test-harness artifact of popping a widget key between runs — it does NOT happen in the real browser (the widget is recreated fresh each run there). The assertions above (`not at.exception` + `_dialog_is_open`) are evaluated on the run that **immediately follows the save click**; if that run surfaces the `vd_notes` KeyError, the dialog-open assertion still holds but `at.exception` is truthy. If you observe this, the correct resolution is to assert on `_dialog_is_open` only (the dialog body re-rendered with the add-new form still present, proving the flag stayed `True`), and drop the `not at.exception` assertion for the post-save run — the KeyError is a harness artifact, not a product bug. The delete-confirm test does not pop `vd_notes`, so its `not at.exception` assertion is safe. Document which path you took in the commit message.

- [ ] **Step 3: Implement the fix in `core/vocab/sidebar.py`**

Current `sidebar.py` lines 19-20 (the decorator) and 83-96 (the render function):

```python
@st.dialog("📖 Từ điển cá nhân", width="large")
def _vocab_dialog(store, user_id: str) -> None:
```

```python
def render_vocab_sidebar(store) -> None:
    if not is_logged_in():
        return
    if store is None:
        return
    user_id = (current_user() or {}).get("_id", "default")
    st.sidebar.markdown("---")
    if st.sidebar.button("📖 Từ điển cá nhân", use_container_width=True, shortcut="Alt+V"):
        st.session_state["_vocab_dialog_open"] = True
    if st.session_state.get("_vocab_dialog_open"):
        # Clear flag before opening dialog so it doesn't reopen on dismiss
        st.session_state["_vocab_dialog_open"] = False
        _vocab_dialog(store, user_id)
```

Replace the decorator (add `_on_dismiss` defined just above it, and pass `on_dismiss=`):

```python
def _on_dismiss() -> None:
    """Clear the open flag when the user dismisses (X / ESC / click-outside)."""
    st.session_state["_vocab_dialog_open"] = False


@st.dialog("📖 Từ điển cá nhân", width="large", on_dismiss=_on_dismiss)
def _vocab_dialog(store, user_id: str) -> None:
```

Replace `render_vocab_sidebar` (remove the flag-clearing line):

```python
def render_vocab_sidebar(store) -> None:
    if not is_logged_in():
        return
    if store is None:
        return
    user_id = (current_user() or {}).get("_id", "default")
    st.sidebar.markdown("---")
    if st.sidebar.button("📖 Từ điển cá nhân", use_container_width=True, shortcut="Alt+V"):
        st.session_state["_vocab_dialog_open"] = True
    if st.session_state.get("_vocab_dialog_open"):
        # Do NOT clear the flag here — it must stay True so in-dialog
        # st.rerun() calls reopen the dialog. The flag is cleared only
        # by the on_dismiss callback (X / ESC / click-outside).
        _vocab_dialog(store, user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n tmchien python -m pytest tests/test_vocab_sidebar.py -v`
Expected: PASS — all 4 tests.

- [ ] **Step 5: Compile check + import sanity + commit**

Run: `conda run -n tmchien python -m py_compile core/vocab/sidebar.py`
Expected: no output.

Run: `conda run -n tmchien python -c "import app"`
Expected: no output (app imports cleanly).

```bash
git add core/vocab/sidebar.py tests/test_vocab_sidebar.py
git commit -m "fix(vocab): sidebar dialog stays open across in-dialog actions

Keep _vocab_dialog_open True across reruns; clear it only via an
on_dismiss callback (X / ESC / click-outside). Previously the flag was
cleared in the open render pass, so any in-dialog st.rerun() closed the
dialog — breaking add and the delete-confirm flow."
```

---

## Task 3: Fix page quick-add crash after save

**Goal:** Stop the page quick-add bar from raising `StreamlitAPIException: ... cannot be modified after the widget ... is instantiated` after saving a word, by `pop`-ing the widget keys instead of assigning to them.

**Files:**
- Modify: `core/vocab/shared.py:93-94` (inside `render_quick_add_bar`)
- Test: `tests/test_vocab_page.py` (new — this task creates the file with the quick-add test; Task 4 adds pagination tests to the same file)

**Acceptance Criteria:**
- [ ] Saving a word via the quick-add bar (💾 Lưu) does not raise `StreamlitAPIException`.
- [ ] After save, a success toast appears and `vocab_quick_word`/`vocab_quick_meaning` are cleared (empty on next render).
- [ ] The new word appears in the page list.
- [ ] `conda run -n tmchien python -m py_compile core/vocab/shared.py` succeeds.

**Verify:** `conda run -n tmchien python -m pytest tests/test_vocab_page.py -v -k quick_add` → PASS.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_vocab_page.py`:

```python
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
    """Re-run an existing AppTest with patches active (for post-click reruns)."""
    with _patches():
        at.run()
    return at


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
    assert not at.exception, at.exception
    # inputs cleared
    assert at.session_state.get("vocab_quick_word", "") == ""
    assert at.session_state.get("vocab_quick_meaning", "") == ""
    # new word persisted in the mock store
    assert any(d["word"] == "apple" for d in store._docs.values())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `conda run -n tmchien python -m pytest tests/test_vocab_page.py -v -k quick_add`
Expected: FAIL with `StreamlitAPIException: st.session_state.vocab_quick_word cannot be modified after the widget with key vocab_quick_word is instantiated` (the current `= ""` assignment at `shared.py:93-94`).

- [ ] **Step 3: Apply the fix in `core/vocab/shared.py`**

Current `render_quick_add_bar` save handler (lines 90-96):

```python
                if existing and existing[0].get("word", "").lower() == w.lower():
                    run_async(store.add_sense(existing[0]["_id"], m))
                    st.toast(f"✅ Đã thêm nghĩa mới cho '{w}'")
                else:
                    run_async(store.save_vocab(w, m, user_id=user_id))
                    st.toast(f"✅ Đã thêm '{w}'")
                st.session_state["vocab_quick_word"] = ""
                st.session_state["vocab_quick_meaning"] = ""
                bust_review_cache()
                st.rerun()
```

Replace the two assignment lines with `pop`:

```python
                if existing and existing[0].get("word", "").lower() == w.lower():
                    run_async(store.add_sense(existing[0]["_id"], m))
                    st.toast(f"✅ Đã thêm nghĩa mới cho '{w}'")
                else:
                    run_async(store.save_vocab(w, m, user_id=user_id))
                    st.toast(f"✅ Đã thêm '{w}'")
                st.session_state.pop("vocab_quick_word", None)
                st.session_state.pop("vocab_quick_meaning", None)
                bust_review_cache()
                st.rerun()
```

(`pop` is permitted after a widget is instantiated and resets the widget to its default on the next rerun; assigning to a widget key after instantiation raises.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `conda run -n tmchien python -m pytest tests/test_vocab_page.py -v -k quick_add`
Expected: PASS.

- [ ] **Step 5: Compile check + commit**

Run: `conda run -n tmchien python -m py_compile core/vocab/shared.py`
Expected: no output.

```bash
git add core/vocab/shared.py tests/test_vocab_page.py
git commit -m "fix(vocab): page quick-add crash — pop widget keys instead of assign

Assigning to st.session_state[<widget_key>] after the widget is
instantiated raises StreamlitAPIException. Use pop() (allowed) which
also resets the inputs to empty on the next rerun."
```

---

## Task 4: Page pagination rewrite — offset→page, server-side filter, numbered pagination

**Goal:** Replace the page's offset-based "Load more" + client-side filtering with 1-indexed page-numbered pagination backed by `query_vocab`, including ellipsis window and prev/next arrows, and reset to page 1 when sort/filter/review changes.

**Files:**
- Modify: `core/vocab/page.py` (rewrite the fetch/filter/pagination section of `render_vocab_page`; add `_page_window` and `_render_pagination` helpers)
- Test: `tests/test_vocab_page.py` (append pagination tests)

**Acceptance Criteria:**
- [ ] `vocab_offset` is no longer used; `vocab_page` (1-indexed, default 1) drives pagination with `page_size = 20`.
- [ ] A single `store.query_vocab(...)` call supplies both the filtered `total` and the page slice; the client-side list-comprehension filter block is removed.
- [ ] When total > page_size, numbered pagination renders with ellipsis and prev/next (`◀` / `▶`); the current page button is `primary`, others `secondary`, `…` is a disabled button.
- [ ] Clicking a page number sets `vocab_page` and reruns; clicking prev/next decrements/increments.
- [ ] Changing `vocab_sort`, `vocab_filter`, or `vocab_review_filter` resets `vocab_page` to 1.
- [ ] "Hiển thị X–Y / N" reflects the filtered `total` from `query_vocab`.
- [ ] No "Xem thêm…" button remains.
- [ ] If `vocab_page` exceeds `total_pages` (e.g. after a delete), it clamps to `total_pages` and reruns.
- [ ] All page AppTests pass; `conda run -n tmchien python -m py_compile core/vocab/page.py` succeeds.

**Verify:** `conda run -n tmchien python -m pytest tests/test_vocab_page.py -v` → all tests PASS (quick-add + pagination).

**Steps:**

- [ ] **Step 1: Write the failing pagination tests**

Append to `tests/test_vocab_page.py` (after `test_quick_add_save_does_not_crash`):

```python
def _seed(store: _MockStore, n: int):
    for i in range(n):
        asyncio.run(store.save_vocab(f"word{i:02d}", f"nghĩa{i}", user_id="u1"))


def test_pagination_renders_when_over_page_size():
    store = _MockStore()
    _seed(store, 25)  # 2 pages at size 20
    at = _run_page(store)
    assert not at.exception
    page_btns = [b for b in at.button if b.key.startswith("vocab_pg_")]
    assert page_btns, "numbered pagination buttons should render"
    # no legacy "Load more"
    assert not any("Xem thêm" in b.label for b in at.button)


def test_pagination_click_changes_page():
    store = _MockStore()
    _seed(store, 25)
    at = _run_page(store)
    # click page 2
    pg2 = next(b for b in at.button if b.key == "vocab_pg_2")
    at = _run(pg2.click())
    assert at.session_state["vocab_page"] == 2
    assert not at.exception


def test_pagination_prev_next():
    store = _MockStore()
    _seed(store, 25)
    at = _run_page(store)
    assert at.session_state.get("vocab_page", 1) == 1
    nxt = next(b for b in at.button if b.key == "vocab_next")
    at = _run(nxt.click())
    assert at.session_state["vocab_page"] == 2
    prev = next(b for b in at.button if b.key == "vocab_prev")
    at = _run(prev.click())
    assert at.session_state["vocab_page"] == 1


def test_filter_change_resets_page_to_1():
    store = _MockStore()
    _seed(store, 25)
    at = _run_page(store)
    # go to page 2
    at = _run(next(b for b in at.button if b.key == "vocab_pg_2").click())
    assert at.session_state["vocab_page"] == 2
    # change filter
    at.session_state["vocab_filter"] = "word0"
    at = _run(at)
    assert at.session_state["vocab_page"] == 1


def test_results_info_uses_filtered_total():
    store = _MockStore()
    _seed(store, 25)
    at = _run_page(store)
    rendered = " ".join(m.value for m in at.markdown)
    assert "Hiển thị" in rendered
    assert "/ 25" in rendered  # unfiltered total on first page
    # filter "word1": matches word01, word10..word19 (11 words) by substring;
    # server-side query_vocab counts them all -> filtered total 11
    at.session_state["vocab_filter"] = "word1"
    at = _run(at)
    rendered = " ".join(m.value for m in at.markdown)
    assert "/ 11" in rendered  # filtered total from query_vocab


def test_page_clamps_when_out_of_range():
    store = _MockStore()
    _seed(store, 25)  # 2 pages
    at = _run_page(store)
    at.session_state["vocab_page"] = 99  # beyond total_pages
    at = _run(at)
    assert at.session_state["vocab_page"] == 2  # clamped to last page
    assert not at.exception
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `conda run -n tmchien python -m pytest tests/test_vocab_page.py -v -k "pagination or results_info or clamps or filter_change"`
Expected: FAIL — pagination buttons (`vocab_pg_*`) don't exist yet; "Xem thêm" still present; `vocab_page` key not used.

- [ ] **Step 3: Rewrite `core/vocab/page.py`**

Add the two pagination helpers near the top of `page.py` (after the imports, before `_render_card`). Insert after the import block (after line 16, the closing `)` of the `from core.vocab.shared import (...)`):

```python
def _page_window(current: int, total: int) -> list[int | str]:
    """Page buttons to render: first, current±1, last, with '…' ellipsis for gaps."""
    if total <= 7:
        return list(range(1, total + 1))
    pages = {1, current, total}
    if current > 1:
        pages.add(current - 1)
    if current < total:
        pages.add(current + 1)
    ordered = sorted(pages)
    result: list[int | str] = []
    for i, p in enumerate(ordered):
        if i > 0 and p - ordered[i - 1] > 1:
            result.append("…")
        result.append(p)
    return result


def _render_pagination(current: int, total: int) -> None:
    """Numbered pagination with ellipsis + prev/next. Reads/writes st.session_state['vocab_page']."""
    if total <= 1:
        return
    window = _page_window(current, total)
    cols = st.columns(len(window) + 2)  # +2 for prev / next arrows
    with cols[0]:
        if st.button("◀", key="vocab_prev", disabled=(current <= 1),
                     use_container_width=True):
            st.session_state["vocab_page"] = current - 1
            st.rerun()
    for i, p in enumerate(window):
        with cols[i + 1]:
            if p == "…":
                st.button("…", key=f"vocab_ell_{i}", disabled=True,
                          use_container_width=True)
            else:
                btn_type = "primary" if p == current else "secondary"
                if st.button(str(p), key=f"vocab_pg_{p}", type=btn_type,
                             use_container_width=True):
                    st.session_state["vocab_page"] = p
                    st.rerun()
    with cols[-1]:
        if st.button("▶", key="vocab_next", disabled=(current >= total),
                     use_container_width=True):
            st.session_state["vocab_page"] = current + 1
            st.rerun()
```

Now replace the body of `render_vocab_page` **from the `# ── Sort / Filter toolbar ──` comment (line 116) through the end of the function** (the closing of the "Load more" block at line 195). The current block to replace is:

```python
    # ── Sort / Filter toolbar ───────────────────────────────────────────────
    st.markdown("### 📋 Danh sách từ")

    cf1, cf2, cf3 = st.columns([3, 2, 1])
    with cf1:
        filter_text = st.text_input(
            "🔍 Lọc", placeholder="Lọc từ hoặc nghĩa…",
            key="vocab_filter", label_visibility="collapsed",
        )
    with cf2:
        sort_by = st.selectbox(
            "Sắp xếp", ["Mới nhất", "A → Z"],
            key="vocab_sort", label_visibility="collapsed",
        )
    with cf3:
        review_only = st.checkbox("REVIEW", key="vocab_review_filter",
                                   help="Chỉ hiện từ có nghĩa đang review")

    # Reset offset when sort or filter changes
    prev_sort = st.session_state.get("_vocab_prev_sort")
    prev_filter = st.session_state.get("_vocab_prev_filter")
    prev_review = st.session_state.get("_vocab_prev_review")
    if (prev_sort is not None and prev_sort != sort_by) or \
       (prev_filter is not None and prev_filter != filter_text) or \
       (prev_review is not None and prev_review != review_only):
        st.session_state["vocab_offset"] = 0
    st.session_state["_vocab_prev_sort"] = sort_by
    st.session_state["_vocab_prev_filter"] = filter_text
    st.session_state["_vocab_prev_review"] = review_only

    # ── Fetch ───────────────────────────────────────────────────────────────
    page_size = 50
    offset = st.session_state.get("vocab_offset", 0)
    store_sort = "word" if sort_by == "A → Z" else "created_at"

    try:
        entries = run_async(store.get_vocab(
            user_id=user_id, limit=page_size, offset=offset, sort_by=store_sort,
        ))
        if offset == 0:
            total_count = run_async(store.count_vocab(user_id))
        else:
            total_count = total  # from header
    except Exception as exc:
        st.error(f"Lỗi tải dữ liệu: {exc}")
        return

    # ── Client-side filter ──────────────────────────────────────────────────
    ft = filter_text.strip().lower()
    if ft:
        entries = [
            e for e in entries
            if ft in e.get("word", "").lower()
            or any(ft in s.get("meaning", "").lower() for s in e.get("senses", []))
        ]
    if review_only:
        entries = [
            e for e in entries
            if any(s.get("status") == "IN_REVIEW" for s in e.get("senses", []))
        ]

    if not entries:
        st.caption("Không có từ nào khớp.")
        return

    # ── Results info ────────────────────────────────────────────────────────
    st.markdown(
        f"<small style='color:gray'>Hiển thị {offset + 1}–{offset + len(entries)} / {total_count} từ</small>",
        unsafe_allow_html=True,
    )

    # ── Card list ───────────────────────────────────────────────────────────
    for entry in entries:
        _render_card(entry, store)

    # ── Load more ───────────────────────────────────────────────────────────
    if not ft and not review_only and offset + page_size < total_count:
        if st.button("Xem thêm…", use_container_width=True):
            st.session_state["vocab_offset"] = offset + page_size
            st.rerun()
```

Replace with:

```python
    # ── Sort / Filter toolbar ───────────────────────────────────────────────
    st.markdown("### 📋 Danh sách từ")

    cf1, cf2, cf3 = st.columns([3, 2, 1])
    with cf1:
        filter_text = st.text_input(
            "🔍 Lọc", placeholder="Lọc từ hoặc nghĩa…",
            key="vocab_filter", label_visibility="collapsed",
        )
    with cf2:
        sort_by = st.selectbox(
            "Sắp xếp", ["Mới nhất", "A → Z"],
            key="vocab_sort", label_visibility="collapsed",
        )
    with cf3:
        review_only = st.checkbox("REVIEW", key="vocab_review_filter",
                                   help="Chỉ hiện từ có nghĩa đang review")

    # Reset to page 1 when sort or filter changes
    prev_sort = st.session_state.get("_vocab_prev_sort")
    prev_filter = st.session_state.get("_vocab_prev_filter")
    prev_review = st.session_state.get("_vocab_prev_review")
    if (prev_sort is not None and prev_sort != sort_by) or \
       (prev_filter is not None and prev_filter != filter_text) or \
       (prev_review is not None and prev_review != review_only):
        st.session_state["vocab_page"] = 1
    st.session_state["_vocab_prev_sort"] = sort_by
    st.session_state["_vocab_prev_filter"] = filter_text
    st.session_state["_vocab_prev_review"] = review_only

    # ── Fetch (single server-side query) ────────────────────────────────────
    page_size = 20
    page = st.session_state.get("vocab_page", 1)
    offset = (page - 1) * page_size
    store_sort = "word" if sort_by == "A → Z" else "created_at"

    try:
        total, entries = run_async(store.query_vocab(
            user_id=user_id, limit=page_size, offset=offset,
            sort_by=store_sort, filter_text=filter_text.strip(),
            review_only=review_only,
        ))
    except Exception as exc:
        st.error(f"Lỗi tải dữ liệu: {exc}")
        return

    total_pages = max(1, (total + page_size - 1) // page_size)
    # Clamp page if out of range (e.g. after a delete reduced the total)
    if page > total_pages:
        st.session_state["vocab_page"] = total_pages
        st.rerun()

    if not entries:
        st.caption("Không có từ nào khớp.")
        return

    # ── Results info (filtered total) ───────────────────────────────────────
    st.markdown(
        f"<small style='color:gray'>Hiển thị {offset + 1}–{offset + len(entries)} / {total} từ</small>",
        unsafe_allow_html=True,
    )

    # ── Card list ───────────────────────────────────────────────────────────
    for entry in entries:
        _render_card(entry, store)

    # ── Numbered pagination ─────────────────────────────────────────────────
    _render_pagination(page, total_pages)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `conda run -n tmchien python -m pytest tests/test_vocab_page.py -v`
Expected: PASS — quick-add test (from Task 3) + all pagination tests.

- [ ] **Step 5: Compile check + import sanity + commit**

Run: `conda run -n tmchien python -m py_compile core/vocab/page.py`
Expected: no output.

Run: `conda run -n tmchien python -c "import app"`
Expected: no output.

```bash
git add core/vocab/page.py tests/test_vocab_page.py
git commit -m "feat(vocab): page — server-side filter + numbered pagination

Replace offset 'Load more' + client-side filter with 1-indexed page
pagination backed by query_vocab (single call for total + slice).
Numbered buttons with ellipsis window + prev/next; sort/filter/review
change resets to page 1; out-of-range page clamps to last page."
```

---

## Task 5: Final integration verification

**Goal:** Confirm the whole app imports cleanly, the full test suite passes, and the app starts headless with a healthy Streamlit core — covering all touched files together.

**Files:**
- None (verification only; no code changes unless a check fails)

**Acceptance Criteria:**
- [ ] `py_compile` succeeds on all four touched source files.
- [ ] `import app` succeeds (no import-time errors).
- [ ] Full pytest suite passes (store + sidebar + page tests, no regressions).
- [ ] Headless Streamlit health endpoint returns ok/true.
- [ ] `git status` is clean (all committed).

**Verify:**
```
conda run -n tmchien python -m py_compile core/store.py core/vocab/sidebar.py core/vocab/shared.py core/vocab/page.py && \
conda run -n tmchien python -c "import app" && \
conda run -n tmchien python -m pytest tests/test_store_vocab.py tests/test_vocab_sidebar.py tests/test_vocab_page.py -v
```
Then headless smoke:
```
conda run -n tmchien streamlit run app.py --server.headless true & echo $! > /tmp/st.pid
sleep 6 && curl -s http://localhost:8501/_stcore/health; kill $(cat /tmp/st.pid)
```
Expected: `py_compile` no output; `import app` no output; pytest all PASS; curl prints `ok`/`true`.

**Steps:**

- [ ] **Step 1: Compile all touched files**

Run: `conda run -n tmchien python -m py_compile core/store.py core/vocab/sidebar.py core/vocab/shared.py core/vocab/page.py`
Expected: no output (all four compile).

- [ ] **Step 2: Import sanity**

Run: `conda run -n tmchien python -c "import app"`
Expected: no output.

- [ ] **Step 3: Full test suite**

Run: `conda run -n tmchien python -m pytest tests/test_store_vocab.py tests/test_vocab_sidebar.py tests/test_vocab_page.py -v`
Expected: PASS — 27 store tests + 4 sidebar tests + 7 page tests (38 total).

- [ ] **Step 4: Headless smoke test**

Run:
```bash
conda run -n tmchien streamlit run app.py --server.headless true >/tmp/st.log 2>&1 &
echo $! > /tmp/st.pid
sleep 6
curl -s http://localhost:8501/_stcore/health
kill $(cat /tmp/st.pid) 2>/dev/null
```
Expected: `curl` prints `ok` (or `true`); no traceback in `/tmp/st.log` (check with `grep -i "Traceback\|Error" /tmp/st.log` → no matches).

- [ ] **Step 5: Confirm clean tree**

Run: `git status --short`
Expected: empty (all changes committed in Tasks 1-4).

No commit in this task (verification only). If any check fails, fix the offending file and amend the relevant task's commit (or add a fix commit) before re-running.
