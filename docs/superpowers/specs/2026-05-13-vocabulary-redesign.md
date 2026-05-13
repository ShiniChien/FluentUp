# Vocabulary Redesign — Spec

**Date:** 2026-05-13  
**Status:** Approved

## Overview

Redesign the vocabulary system so each word can hold multiple meanings (senses), each with its own status. Migrate existing data, update Store API, improve duplicate-word UX, and show a review-count banner on the Home page.

---

## 1. Data Schema

**Collection:** `vocabulary`  
**One document per (word, user_id) pair.**

```json
{
  "_id": ObjectId,
  "word": "bank",
  "user_id": "abc123",
  "created_at": ISODate,
  "senses": [
    { "meaning": "bờ sông",   "status": "ACTIVE",    "created_at": ISODate },
    { "meaning": "ngân hàng", "status": "IN_REVIEW", "created_at": ISODate }
  ]
}
```

- Status enum per sense: `"ACTIVE"` | `"IN_REVIEW"`
- `IN_REVIEW` is reserved for a future feature; the UI currently only creates `ACTIVE` senses
- Unique compound index: `(word, user_id)`
- Old `notes` field is removed after migration

---

## 2. DB Migration

Run once inside `store.ensure_indexes()`, guarded by checking whether any document still has a `notes` field:

1. For each doc with non-empty `notes`: set `senses = [{"meaning": notes, "status": "ACTIVE", "created_at": doc.created_at}]`
2. For each doc with empty/null `notes`: set `senses = []`
3. `$unset` the `notes` field on all docs
4. Create unique compound index `(word, user_id)` (background)

Migration is idempotent: if `notes` field is absent, the guard skips it.

---

## 3. Store API

### Removed
- `update_vocab(entry_id, notes)` — replaced by sense-level operations

### Kept (signature unchanged)
- `get_vocab(user_id, limit)` — returns docs with `senses` instead of `notes`
- `search_vocab(user_id, query, limit)` — same
- `delete_vocab(entry_id)` — deletes entire word document

### Changed
- `save_vocab(word, meaning, user_id)` — if word already exists for user: appends a new sense `{meaning, status: ACTIVE, created_at: now}`. If new word: inserts document with one sense.

### New
| Method | Description |
|---|---|
| `add_sense(word_id, meaning)` | Append a new ACTIVE sense to an existing word |
| `update_sense(word_id, sense_idx, meaning)` | Update the `meaning` of sense at index |
| `delete_sense(word_id, sense_idx)` | Remove sense at index; if senses array becomes empty, delete the whole document |
| `count_review_vocab(user_id)` | Count words that have at least one sense with `status == "IN_REVIEW"` |

---

## 4. Vocab Dialog UI (`core/vocab_sidebar.py`)

### New word (no duplicate)
Same as current: input meaning → "💾 Lưu từ" → creates word with one ACTIVE sense.

### Duplicate word (word already exists)
Replace the current "Chỉnh sửa" form with a **sense manager panel**:

```
bank                                          [× Xóa từ]
─────────────────────────────────────────────────────────
Các nghĩa hiện có:
  • bờ sông    [ACTIVE]      [✏️ edit inline]  [🗑️]
  • ngân hàng  [IN_REVIEW]   [✏️ edit inline]  [🗑️]

─────────────────────────────────────────────────────────
Thêm nghĩa mới:
  [ input: nghĩa mới… ]   [💾 Thêm nghĩa]
```

Rules:
- Each sense row: shows meaning + status badge + edit button + delete button
- Edit: inline text_input replacing the label, confirmed with Enter or a small ✅ button
- Delete last sense → confirm dialog → deletes entire word on confirm
- Status badge displayed but no toggle (IN_REVIEW toggling is a future feature)
- "Xóa từ" button at top deletes the whole word document (with confirmation)

---

## 5. Home Page — Review Banner (`pages/0_Home.py`)

Shown only for regular logged-in users (not root/admin), immediately below the header divider, only when count > 0:

```
📚  Bạn có 3 từ vựng đang chờ review  —  [Xem ngay →]
```

- `count_review_vocab` result cached in `st.session_state["_vocab_review_count"]` for the session
- "Xem ngay" button sets `st.session_state["_vocab_dialog_open"] = True` and triggers `st.rerun()` to open the vocab dialog via the sidebar mechanism
- Banner is an `st.info(...)` or styled `st.markdown` block — subtle, not alarming

---

## Out of Scope

- Toggling `IN_REVIEW` status from the UI (future feature)
- Spaced-repetition scheduling or review queue ordering
- Per-sense examples or part-of-speech tagging
