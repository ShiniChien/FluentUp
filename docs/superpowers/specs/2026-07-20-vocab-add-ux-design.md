# Vocab Add/Edit UX Optimization — Design

**Date:** 2026-07-20
**Status:** Approved (pending spec review)
**Scope:** `core/vocab/` subpackage — sidebar dictionary dialog + full-page dictionary

## Problem

Two pain points when adding/managing vocabulary:

### 1. Sidebar dictionary dialog closes on every button action
- Adding a word, confirming a delete, saving a sense — any button inside the dialog closes it.
- Delete-confirm flow is especially broken: click × → confirm state set → dialog closes → reopen → × again → confirm state lost (or stale) → must re-confirm.
- Root cause (verified via `AppTest`): `core/vocab/sidebar.py:92-95` clears the `_vocab_dialog_open` flag *in the same render pass that opens the dialog*. Any button inside the dialog calls `st.rerun()` (default `scope="app"`), which triggers a full-app rerun; the flag is now `False`, so `_vocab_dialog` is not called again → the dialog closes. The dialog body is a fragment, but `st.rerun()` with default scope reruns the whole app, not just the fragment.

### 2. Full-page dictionary: crash after add + poor pagination
- **Crash:** Right after saving a new word via the quick-add bar, the page raises `StreamlitAPIException: st.session_state.vocab_quick_word cannot be modified after the widget with key vocab_quick_word is instantiated`. Root cause (verified): `core/vocab/shared.py:93-94` assigns `st.session_state["vocab_quick_word"] = ""` *after* the `st.text_input(key="vocab_quick_word")` widget is already instantiated. Streamlit forbids setting a widget key after instantiation; `pop()` is allowed (verified) and resets the widget to its default on the next rerun.
- **Pagination:** Current implementation (`core/vocab/page.py`) uses offset-based "Load more" with client-side filtering. Filtering is client-side (fetches a page, then filters in Python), so the visible set shrinks unpredictably and page boundaries are inconsistent. No numbered pagination, no ellipsis, no total-page awareness.

## Goals

1. Sidebar dialog stays open across all in-dialog actions (add / add-sense / edit-sense / delete-sense / delete-word / translate) and closes only via explicit dismiss (X / ESC / click-outside).
2. Page quick-add no longer crashes after save; inputs clear correctly.
3. Page list uses server-side filtering + numbered pagination with ellipsis and prev/next, adapted from `refers/streamlit-transwise-manager-master/tool_components/monitors.py:get_show_pages`.

## Non-goals

- No change to the card-based list layout (inline Sửa/Xoá per card stays).
- No `@st.cache_data` pagination cache — vocabulary mutates frequently (add/edit/delete from both dialog and page), and cache invalidation across two entry points is bug-prone. Each page render fetches fresh.
- No change to the mini-quiz, bulk-insert, or sense-manager components beyond what the dialog-stay-open fix requires (none — they already use `st.rerun()`).
- No switch to `st.popover`/`st.expander` or dataframe-based list.

## Verified facts

- Streamlit version: **1.54.0** (`conda run -n tmchien python -c "import streamlit; print(streamlit.__version__)"`).
- `st.rerun(scope="fragment")` inside a dialog does **not** keep the dialog open in 1.54 (verified via `AppTest`: after a fragment-scope rerun, the dialog body disappears). Rejected as a fix path.
- The "flag stays True + `on_dismiss` callback clears it" pattern **does** keep the dialog open across multiple full-app reruns triggered by in-dialog buttons (verified via `AppTest`: counter incremented across 3 button clicks, dialog content persisted each time).
- `st.session_state.pop("<widget_key>", None)` after the widget is instantiated is **allowed** and resets the widget to its default on the next rerun (verified). `st.session_state["<widget_key>"] = ""` after instantiation **raises** (verified — this is the page crash).
- `@st.dialog(on_dismiss=<callable>)` registers the dialog as a widget so that X / ESC / outside-click triggers a rerun and invokes the callback before the rest of the app (per `streamlit/elements/lib/dialog.py` and `dialog_decorator.py`).

## Design

### Section 1 — Dialog stay-open (`core/vocab/sidebar.py`)

Add an `on_dismiss` callback that clears the open flag, and stop clearing the flag in the render pass that opens the dialog.

```python
def _on_dismiss() -> None:
    """Clear the open flag when the user dismisses (X / ESC / click-outside)."""
    st.session_state["_vocab_dialog_open"] = False


@st.dialog("📖 Từ điển cá nhân", width="large", on_dismiss=_on_dismiss)
def _vocab_dialog(store, user_id: str) -> None:
    # ... body unchanged ...
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
        # Do NOT clear the flag here — it must stay True so in-dialog
        # st.rerun() calls reopen the dialog. The flag is cleared only
        # by the on_dismiss callback (X / ESC / click-outside).
        _vocab_dialog(store, user_id)
```

**Behavior:**
- Click sidebar button → flag set `True` → dialog opens (same render pass).
- Any in-dialog button calls `st.rerun()` → full-app rerun → flag still `True` → dialog reopens with refreshed content (entries re-fetched, so the list reflects the add/delete).
- X / ESC / click-outside → `on_dismiss` callback fires → flag set `False` → rerun → dialog not called → closes.

**Constraint satisfied:** `_assert_first_dialog_to_be_opened` allows only one dialog per script run; the flag guard ensures `_vocab_dialog` is called at most once per run.

**No changes to the dialog-*used* `shared.py` components** — `render_entry_list`, `render_sense_manager`, `render_add_new_word`, `render_search_input` all already use `st.rerun()`, which now correctly reopens the dialog. (Section 2 fixes `render_quick_add_bar`, which is page-only and not used inside the dialog.)

### Section 2 — Page quick-add crash fix (`core/vocab/shared.py`)

In `render_quick_add_bar`, replace the two post-save assignments with `pop`:

```python
# was (raises StreamlitAPIException):
#   st.session_state["vocab_quick_word"] = ""
#   st.session_state["vocab_quick_meaning"] = ""
st.session_state.pop("vocab_quick_word", None)
st.session_state.pop("vocab_quick_meaning", None)
bust_review_cache()
st.rerun()
```

`pop` is allowed after widget instantiation and clears the inputs on the next rerun (widgets fall back to their default value when their key is absent from session state).

**Other components already use `pop` correctly** — `render_add_new_word` (`pop("vd_notes")`, `pop("vd_query")`), `render_bulk_insert` (`pop("vocab_bulk_input")`), `render_sense_manager` (`pop("vd_new_sense_{id}")`) — no changes needed.

### Section 3 — Server-side filter + numbered pagination

#### 3a. New store method (`core/store.py`)

Add `import re` to `core/store.py` imports, then add a unified query method that returns `(total, docs)` in one call with server-side filtering:

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

This replaces the page's current combination of `get_vocab` + `count_vocab` + client-side list comprehension filtering. `search_vocab` (used by the sidebar dialog) is left untouched.

#### 3b. Page rewrite (`core/vocab/page.py`)

Replace the offset/"Load more" section of `render_vocab_page` with page-numbered pagination.

**State migration:** `vocab_offset` (int) → `vocab_page` (int, 1-indexed, default `1`). `page_size = 20`.

**Reset-on-change:** When `sort_by`, `filter_text`, or `review_only` changes, set `vocab_page = 1` (replacing the current `vocab_offset = 0` reset).

**Fetch (single call):**
```python
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
# Clamp page if out of range (e.g. after a delete reduced total)
if page > total_pages:
    st.session_state["vocab_page"] = total_pages
    st.rerun()
```

Remove the client-side `ft`/`review_only` list-comprehension filtering block (now server-side).

**Results info:**
```python
st.markdown(
    f"<small style='color:gray'>Hiển thị {offset + 1}–{offset + len(entries)} / {total} từ</small>",
    unsafe_allow_html=True,
)
```
(Header keeps `count_vocab` for the unfiltered total badge; the "Hiển thị" line uses the filtered `total` from `query_vocab`.)

**Pagination helpers (in `page.py`):**

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

**Replace the "Load more" block** at the bottom of `render_vocab_page` with `_render_pagination(page, total_pages)`.

`st.button(disabled=...)` is supported in Streamlit 1.54.

### Section 4 — Testing

#### 4a. Store unit tests (`tests/test_store_vocab.py`)

Add tests for `query_vocab` using the existing `_make_store()` mongomock harness:
- `test_query_vocab_filter_word` — `filter_text` matches `word` (case-insensitive), returns only matches, `total` reflects filter.
- `test_query_vocab_filter_meaning` — `filter_text` matches a sense's `meaning`.
- `test_query_vocab_review_only` — `review_only=True` returns only docs with a `IN_REVIEW` sense.
- `test_query_vocab_sort_word` — `sort_by="word"` returns A→Z.
- `test_query_vocab_offset_limit` — `offset`/`limit` return the correct slice; `total` is the full matching count (independent of offset/limit).
- `test_query_vocab_combined` — filter + review + sort + offset together.

#### 4b. Page AppTest (`tests/test_vocab_page.py`, new)

Mock store + `run_async` (run coroutines synchronously via `asyncio.run`), patch `current_user`. Verify:
- Initial render: no exception, pagination renders when total > page_size.
- Quick-add save: set `vocab_quick_word`/`vocab_quick_meaning`, click 💾 Lưu → **no exception**, toast appears, inputs cleared, new word in list.
- Page navigation: click page 2 → `vocab_page == 2`, entries slice changes.
- Filter change: set `vocab_filter` → `vocab_page` resets to 1.
- Out-of-range clamp: simulate `vocab_page` beyond `total_pages` → clamped + rerun.

#### 4c. Dialog AppTest (`tests/test_vocab_sidebar.py`, new)

Mock store + `run_async`, patch `is_logged_in`/`current_user`. Verify:
- Open dialog → set `vd_query` to a new word → 💾 Lưu từ → dialog **stays open** (in-dialog buttons still present), list reflects the new word.
- Delete flow: click × on an entry → confirm state shows → dialog stays open → click ✓ confirm → entry removed, dialog stays open.
- Dismiss: (best-effort — AppTest cannot click X directly) assert the `on_dismiss` callback is wired by checking the dialog is registered with `on_dismiss` (or document this as a manual smoke-test step).

## Files touched

| File | Change |
|------|--------|
| `core/vocab/sidebar.py` | Add `_on_dismiss`, pass `on_dismiss=` to `@st.dialog`; stop clearing flag in open pass. |
| `core/vocab/shared.py` | `render_quick_add_bar`: `pop` instead of `= ""` for the two widget keys. |
| `core/store.py` | `import re`; add `query_vocab` method. |
| `core/vocab/page.py` | Offset→page migration; single `query_vocab` call; `_page_window` + `_render_pagination`; remove "Load more" + client-side filter. |
| `tests/test_store_vocab.py` | Add `query_vocab` tests. |
| `tests/test_vocab_page.py` | New — page AppTest. |
| `tests/test_vocab_sidebar.py` | New — dialog AppTest. |

## Acceptance criteria

- [ ] Sidebar dialog stays open after: add new word, add sense, edit sense, delete sense, delete word (confirm), translate.
- [ ] Sidebar dialog closes via X / ESC / click-outside (manual smoke test).
- [ ] Page quick-add save no longer raises; inputs clear; new word appears in list.
- [ ] Page list shows numbered pagination with ellipsis + prev/next when total > page_size.
- [ ] Filter / sort / review-only are server-side; changing them resets to page 1.
- [ ] "Hiển thị X–Y / N" reflects the filtered total.
- [ ] `query_vocab` unit tests pass.
- [ ] Page + dialog AppTests pass.
- [ ] `conda run -n tmchien python -m py_compile` on all touched files.
- [ ] `conda run -n tmchien python -c "import app"` succeeds.
- [ ] Headless smoke test: `streamlit run app.py --server.headless true` health check passes.
