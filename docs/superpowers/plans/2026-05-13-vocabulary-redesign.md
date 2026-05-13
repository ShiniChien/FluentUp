# Vocabulary Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the vocabulary system so each word holds multiple senses (meanings) each with its own status, migrate existing data, and add a review-count banner on the Home page.

**Architecture:** Modify `FluentUpStore` in `core/store.py` to replace the single `notes` field with a `senses` array; run a one-time migration inside `ensure_indexes`; update `core/vocab_sidebar.py` to show a sense-manager panel for duplicate words; add a review banner to `pages/0_Home.py`.

**Tech Stack:** Python, Motor (async MongoDB), Streamlit, pytest

---

## File Map

| File | Change |
|---|---|
| `core/store.py` | Add `add_sense`, `update_sense`, `delete_sense`, `count_review_vocab`; change `save_vocab`; remove `update_vocab`; add migration in `ensure_indexes` |
| `core/vocab_sidebar.py` | Replace duplicate-word "edit" form with sense-manager panel; add `count_review_vocab` call for badge |
| `pages/0_Home.py` | Add review-count banner in `_render_app()` |
| `tests/test_store_vocab.py` | New — unit tests for all store vocab methods using `mongomock` |

---

### Task 1: Add pytest + mongomock and write failing Store tests

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_store_vocab.py`

- [ ] **Step 1: Install test dependencies**

```bash
conda run -n tmchien pip install pytest mongomock motor
```

Expected: packages install without error.

- [ ] **Step 2: Create `tests/__init__.py`**

```python
```
(empty file)

- [ ] **Step 3: Write failing tests**

Create `tests/test_store_vocab.py`:

```python
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
    # manually inject an IN_REVIEW sense via add_sense then patch status
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
```

- [ ] **Step 4: Run tests to confirm they all fail**

```bash
conda run -n tmchien python -m pytest tests/test_store_vocab.py -v 2>&1 | head -40
```

Expected: multiple FAILED / ImportError — the new methods don't exist yet.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/
git commit -m "test: add failing vocab store tests"
```

---

### Task 2: Implement new Store vocab methods

**Files:**
- Modify: `core/store.py`

- [ ] **Step 1: Update `ensure_indexes` to call migration**

In `core/store.py`, replace the `ensure_indexes` method body:

```python
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
```

- [ ] **Step 2: Add `_migrate_vocab` method**

Add after `ensure_indexes`:

```python
async def _migrate_vocab(self) -> None:
    """One-time migration: convert `notes` field → senses array."""
    sample = await self._vocabulary.find_one({"notes": {"$exists": True}})
    if sample is None:
        return
    cursor = self._vocabulary.find({"notes": {"$exists": True}})
    async for doc in cursor:
        notes = doc.get("notes", "").strip()
        senses = (
            [{"meaning": notes, "status": "ACTIVE", "created_at": doc.get("created_at", datetime.datetime.utcnow())}]
            if notes else []
        )
        await self._vocabulary.update_one(
            {"_id": doc["_id"]},
            {"$set": {"senses": senses}, "$unset": {"notes": ""}},
        )
    _logger.info("vocab migration complete")
```

- [ ] **Step 3: Replace `save_vocab`**

Replace the existing `save_vocab` method:

```python
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
    result = await self._vocabulary.find_one_and_update(
        {"word": word, "user_id": user_id},
        {"$push": {"senses": sense}, "$setOnInsert": {"created_at": now}},
        upsert=True,
        return_document=True,
    )
    return str(result["_id"])
```

- [ ] **Step 4: Remove `update_vocab`, add `add_sense` / `update_sense` / `delete_sense` / `count_review_vocab`**

Remove the entire `update_vocab` method. Add after `delete_vocab`:

```python
async def add_sense(self, word_id: str, meaning: str) -> None:
    sense: dict[str, Any] = {
        "meaning": meaning.strip(),
        "status": "ACTIVE",
        "created_at": datetime.datetime.utcnow(),
    }
    await self._vocabulary.update_one(
        {"_id": ObjectId(word_id)},
        {"$push": {"senses": sense}},
    )

async def update_sense(self, word_id: str, sense_idx: int, meaning: str) -> bool:
    result = await self._vocabulary.update_one(
        {"_id": ObjectId(word_id)},
        {"$set": {f"senses.{sense_idx}.meaning": meaning.strip()}},
    )
    return result.modified_count > 0

async def delete_sense(self, word_id: str, sense_idx: int) -> bool:
    """Remove sense at index. Returns True if the whole word was deleted."""
    doc = await self._vocabulary.find_one({"_id": ObjectId(word_id)})
    if doc is None:
        return False
    senses: list = doc.get("senses", [])
    if len(senses) <= 1:
        await self._vocabulary.delete_one({"_id": ObjectId(word_id)})
        return True
    senses.pop(sense_idx)
    await self._vocabulary.update_one(
        {"_id": ObjectId(word_id)},
        {"$set": {"senses": senses}},
    )
    return False

async def count_review_vocab(self, user_id: str) -> int:
    return await self._vocabulary.count_documents(
        {"user_id": user_id, "senses.status": "IN_REVIEW"}
    )
```

- [ ] **Step 5: Run tests**

```bash
conda run -n tmchien python -m pytest tests/test_store_vocab.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Import / syntax check**

```bash
conda run -n tmchien python -m py_compile core/store.py && echo OK
```

- [ ] **Step 7: Commit**

```bash
git add core/store.py
git commit -m "feat(store): redesign vocab — multi-sense per word with status"
```

---

### Task 3: Update `core/vocab_sidebar.py`

**Files:**
- Modify: `core/vocab_sidebar.py`

The sidebar renders each word as `word — notes`. Now notes is gone; it must render the senses list. The duplicate-word section must be replaced with a sense-manager panel.

- [ ] **Step 1: Update `_render_entry_list` to show senses**

Replace `_render_entry_list`:

```python
def _render_entry_list(entries: list[dict], store) -> None:
    for entry in entries:
        col_word, col_del = st.columns([8, 1])
        with col_word:
            w = entry.get("word", "")
            senses = entry.get("senses", [])
            if senses:
                meanings = "; ".join(
                    f"_{s['meaning']}_" + (" `REVIEW`" if s.get("status") == "IN_REVIEW" else "")
                    for s in senses if s.get("meaning")
                )
                st.markdown(f"**{w}** — {meanings}")
            else:
                st.markdown(f"**{w}**")
        with col_del:
            if st.button("×", key=f"del_vocab_{entry['_id']}", help="Xoá"):
                try:
                    run_async(store.delete_vocab(entry["_id"]))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Xoá thất bại: {exc}")
```

- [ ] **Step 2: Replace the add/edit section with the sense-manager panel**

Replace everything from `# ── Add / edit section` to end of `_vocab_dialog`:

```python
    # ── Add / edit section ────────────────────────────────────────────────────
    if q:
        st.divider()

        dup_entry = next((e for e in entries if e.get("word", "").lower() == q.lower()), None)

        if dup_entry:
            word_id = dup_entry["_id"]
            senses: list[dict] = dup_entry.get("senses", [])

            col_title, col_del_word = st.columns([7, 2])
            with col_title:
                st.markdown(f"##### {dup_entry['word']}")
            with col_del_word:
                if st.button("🗑️ Xóa từ", use_container_width=True, key="del_whole_word"):
                    st.session_state["_confirm_delete_word"] = word_id

            if st.session_state.get("_confirm_delete_word") == word_id:
                st.warning("Xóa toàn bộ từ này?")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("Xác nhận xóa", type="primary", use_container_width=True, key="confirm_del_word"):
                        try:
                            run_async(store.delete_vocab(word_id))
                            st.session_state.pop("_confirm_delete_word", None)
                            st.session_state.pop("vd_query", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Xoá thất bại: {exc}")
                with cc2:
                    if st.button("Hủy", use_container_width=True, key="cancel_del_word"):
                        st.session_state.pop("_confirm_delete_word", None)
                        st.rerun()

            if senses:
                st.markdown("**Các nghĩa hiện có:**")
                for idx, sense in enumerate(senses):
                    edit_key = f"_edit_sense_{word_id}_{idx}"
                    is_editing = st.session_state.get(edit_key, False)
                    status_badge = " `REVIEW`" if sense.get("status") == "IN_REVIEW" else ""
                    s_col, e_col, d_col = st.columns([7, 1, 1])
                    with s_col:
                        if is_editing:
                            new_meaning = st.text_input(
                                "Sửa nghĩa", value=sense.get("meaning", ""),
                                key=f"sense_input_{word_id}_{idx}",
                                label_visibility="collapsed",
                            )
                        else:
                            st.markdown(f"• _{sense.get('meaning', '')}_" + status_badge)
                    with e_col:
                        if is_editing:
                            if st.button("✅", key=f"save_sense_{word_id}_{idx}", help="Lưu"):
                                val = st.session_state.get(f"sense_input_{word_id}_{idx}", "").strip()
                                if val:
                                    try:
                                        run_async(store.update_sense(word_id, idx, val))
                                        st.session_state.pop(edit_key, None)
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Cập nhật thất bại: {exc}")
                        else:
                            if st.button("✏️", key=f"edit_sense_{word_id}_{idx}", help="Sửa"):
                                st.session_state[edit_key] = True
                                st.rerun()
                    with d_col:
                        if st.button("🗑️", key=f"del_sense_{word_id}_{idx}", help="Xoá nghĩa"):
                            try:
                                run_async(store.delete_sense(word_id, idx))
                                st.session_state.pop("vd_query", None)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Xoá thất bại: {exc}")
            else:
                st.caption("Từ này chưa có nghĩa nào.")

            st.markdown("**Thêm nghĩa mới:**")
            new_meaning_val = st.text_input(
                "Nghĩa mới", placeholder="nghĩa, ví dụ…",
                key="vd_new_sense", label_visibility="collapsed",
            )
            if st.button("💾 Thêm nghĩa", type="primary", use_container_width=True):
                val = new_meaning_val.strip()
                if val:
                    try:
                        run_async(store.add_sense(word_id, val))
                        st.session_state.pop("vd_new_sense", None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Thêm nghĩa thất bại: {exc}")
                else:
                    st.warning("Vui lòng nhập nghĩa.")

        else:
            st.markdown("##### Thêm mới")
            notes = st.text_input("Ghi chú / nghĩa", placeholder="nghĩa, ví dụ…", key="vd_notes")
            if st.button("💾 Lưu từ", type="primary", use_container_width=True):
                try:
                    run_async(store.save_vocab(q, notes.strip(), user_id=user_id))
                    st.session_state.pop("vd_notes", None)
                    st.session_state.pop("vd_query", None)
                    st.session_state["_vocab_dialog_open"] = True
                    st.rerun()
                except Exception as exc:
                    st.error(f"Lưu thất bại: {exc}")
```

- [ ] **Step 3: Update `_on_query_change` — remove `_is_duplicate` reference to `notes`**

The `_on_query_change` function calls `_is_duplicate` which compares `entry.get("word")`. That comparison is still valid (word-level). No change needed there. But the auto-translate should only fire when no word doc exists yet. Verify the logic is:

```python
def _on_query_change() -> None:
    q = st.session_state.get("vd_query", "").strip()
    if not q or not _is_valid_regex(q):
        return
    try:
        existing = run_async(store.search_vocab(user_id=user_id, query=q))
    except Exception:
        _logger.exception("vocab_sidebar: failed to search vocab from DB")
        existing = []
    if _is_duplicate(q, existing):
        return
    try:
        st.session_state["vd_notes"] = run_async(_translate_to_vi(q))
    except Exception:
        _logger.exception("vocab_sidebar: translation to Vietnamese failed")
```

This is already the correct logic — no change needed.

- [ ] **Step 4: Syntax check**

```bash
conda run -n tmchien python -m py_compile core/vocab_sidebar.py && echo OK
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add core/vocab_sidebar.py
git commit -m "feat(vocab): sense-manager panel for duplicate words"
```

---

### Task 4: Add review-count banner on Home page

**Files:**
- Modify: `pages/0_Home.py`

- [ ] **Step 1: Add `count_review_vocab` call and banner in `_render_app`**

In `pages/0_Home.py`, find `_render_app()`. After the `st.divider()` that follows the header bar (line ~319), add the review banner block:

```python
def _render_app() -> None:
    user = current_user()
    name = user.get("name") or user.get("username", "")
    avatar_letter = name[0].upper() if name else "U"

    # Header bar
    col_logo, col_avatar = st.columns([6, 1])
    with col_logo:
        st.markdown(
            "<span style='font-size:1.4em;font-weight:700'>🎯 FluentUp</span>",
            unsafe_allow_html=True,
        )
    with col_avatar:
        with st.popover(
            f"**{avatar_letter}**",
            use_container_width=True,
        ):
            st.markdown(f"**{name}**")
            occ_label = {"student": "Đang học", "worker": "Đang đi làm", "other": "Khác"}.get(
                user.get("occupation", ""), ""
            )
            if user.get("occupation_detail"):
                st.caption(f"{occ_label} — {user['occupation_detail']}")
            elif occ_label:
                st.caption(occ_label)
            if user.get("age"):
                st.caption(f"Tuổi: {user['age']}")
            gender_label = {"male": "Nam", "female": "Nữ", "other": "Khác"}.get(
                user.get("gender", ""), ""
            )
            if gender_label:
                st.caption(f"Giới tính: {gender_label}")
            st.divider()
            if st.button("Đăng xuất", use_container_width=True, key="user_logout"):
                logout()
                st.rerun()

    st.divider()

    # ── Vocab review banner ───────────────────────────────────────────────────
    if store is not None and "_vocab_review_count" not in st.session_state:
        user_id = user.get("_id", "default")
        try:
            st.session_state["_vocab_review_count"] = run_async(
                store.count_review_vocab(user_id)
            )
        except Exception:
            st.session_state["_vocab_review_count"] = 0

    review_count: int = st.session_state.get("_vocab_review_count", 0)
    if review_count > 0:
        col_msg, col_btn = st.columns([5, 1])
        with col_msg:
            st.info(f"📚 Bạn có **{review_count}** từ vựng đang chờ review.")
        with col_btn:
            if st.button("Xem ngay →", use_container_width=True):
                st.session_state["_vocab_dialog_open"] = True
                st.rerun()

    # ── App cards ─────────────────────────────────────────────────────────────
    _, col_speaking, _, col_listening, _, col_chat, _ = st.columns([1, 3, 0.5, 3, 0.5, 3, 1])
    # ... rest of cards unchanged
```

Keep everything after the cards section (`col_speaking`, `col_listening`, `col_chat`) exactly as-is.

- [ ] **Step 2: Syntax check**

```bash
conda run -n tmchien python -m py_compile pages/0_Home.py && echo OK
```

Expected: `OK`

- [ ] **Step 3: Import check**

```bash
conda run -n tmchien python -c "import app" && echo OK
```

Expected: `OK`

- [ ] **Step 4: Smoke test**

```bash
conda run -n tmchien streamlit run app.py --server.headless true &
sleep 6 && curl -s http://localhost:8501/_stcore/health
kill %1
```

Expected: `"ok"`

- [ ] **Step 5: Commit**

```bash
git add pages/0_Home.py
git commit -m "feat(home): show vocab review-count banner after login"
```

---

### Task 5: Clear `_vocab_review_count` cache on vocab changes

When the user adds/reviews vocab from the sidebar, the cached count becomes stale. Clear it on every vocab write so the next Home page load re-fetches.

**Files:**
- Modify: `core/vocab_sidebar.py`

- [ ] **Step 1: Add cache-bust helper and call it after every store write**

Add this one-liner helper at module level (after imports):

```python
def _bust_review_cache() -> None:
    st.session_state.pop("_vocab_review_count", None)
```

Then call `_bust_review_cache()` immediately before each `st.rerun()` that follows a successful store write inside `_vocab_dialog`. The relevant locations are:

1. After `store.save_vocab(...)` succeeds → add `_bust_review_cache()` before `st.rerun()`
2. After `store.delete_vocab(word_id)` succeeds (delete whole word) → add `_bust_review_cache()`
3. After `store.add_sense(...)` succeeds → add `_bust_review_cache()`
4. After `store.update_sense(...)` succeeds → add `_bust_review_cache()`
5. After `store.delete_sense(...)` succeeds → add `_bust_review_cache()`
6. After `store.delete_vocab(entry["_id"])` in `_render_entry_list` → add `_bust_review_cache()`

- [ ] **Step 2: Syntax check**

```bash
conda run -n tmchien python -m py_compile core/vocab_sidebar.py && echo OK
```

- [ ] **Step 3: Run all store tests**

```bash
conda run -n tmchien python -m pytest tests/test_store_vocab.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add core/vocab_sidebar.py
git commit -m "feat(vocab): bust review-count cache on every vocab write"
```
