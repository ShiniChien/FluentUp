# Vocab Quiz Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Actions workflow chạy mỗi 6 tiếng, tạo Google Form quiz từ vựng (mix 3 loại câu) cho mỗi user trong MongoDB, gửi tất cả link lên Discord qua webhook.

**Architecture:** Script Python độc lập (`scripts/vocab_quiz.py`) kết nối thẳng MongoDB bằng `pymongo` (sync, không cần Motor), dùng Google Forms API + Drive API để tạo quiz form với answer key, gửi Discord message qua HTTP POST. GitHub Actions cron trigger, credentials qua Secrets.

**Tech Stack:** Python 3.11, `pymongo`, `google-auth`, `google-api-python-client`, `requests`, GitHub Actions

---

## File Structure

```
.github/
  workflows/
    vocab-quiz.yml              # Cron trigger + job definition
scripts/
  vocab_quiz.py                 # Main script: fetch → build questions → create forms → notify Discord
  requirements-quiz.txt         # Dependencies tách riêng khỏi app
tests/
  test_vocab_quiz.py            # Unit tests cho question builder
```

---

### Task 1: Setup dependencies và test skeleton

**Files:**
- Create: `scripts/requirements-quiz.txt`
- Create: `tests/test_vocab_quiz.py`

- [ ] **Step 1: Tạo requirements-quiz.txt**

```
pymongo==4.7.3
google-auth==2.29.0
google-api-python-client==2.128.0
requests==2.32.3
```

- [ ] **Step 2: Tạo test file skeleton**

```python
# tests/test_vocab_quiz.py
import random
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WORDS = [
    {"word": "happy", "notes": "vui vẻ"},
    {"word": "sad", "notes": "buồn"},
    {"word": "angry", "notes": "tức giận"},
    {"word": "excited", "notes": "hào hứng"},
    {"word": "tired", "notes": "mệt mỏi"},
]

GLOBAL_POOL = SAMPLE_WORDS + [
    {"word": "beautiful", "notes": "đẹp"},
    {"word": "ugly", "notes": "xấu"},
    {"word": "fast", "notes": "nhanh"},
    {"word": "slow", "notes": "chậm"},
]
```

- [ ] **Step 3: Commit skeleton**

```bash
git add scripts/requirements-quiz.txt tests/test_vocab_quiz.py
git commit -m "feat: add quiz script dependencies and test skeleton"
```

---

### Task 2: Implement `build_question` — core question builder

**Files:**
- Create: `scripts/vocab_quiz.py` (function `build_question`)
- Modify: `tests/test_vocab_quiz.py`

`build_question` nhận 1 vocab entry + global pool, trả về dict mô tả 1 câu hỏi cho Forms API.

Return type (dict):
```python
{
    "type": "SHORT_ANSWER" | "MULTIPLE_CHOICE",
    "question_text": str,          # text hiển thị cho user
    "correct_answer": str,         # đáp án đúng
    "choices": list[str] | None,   # None nếu SHORT_ANSWER, list[str] 4 lựa chọn nếu MC
}
```

- [ ] **Step 1: Viết test cho SHORT_ANSWER Anh→Việt**

Thêm vào `tests/test_vocab_quiz.py`:

```python
from scripts.vocab_quiz import build_question


def test_short_answer_en_to_vi():
    random.seed(0)
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="en_vi")
    assert q["type"] == "SHORT_ANSWER"
    assert q["question_text"] == "happy"
    assert q["correct_answer"] == "vui vẻ"
    assert q["choices"] is None
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
cd /home/misa/Desktop/RD/Eng
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py::test_short_answer_en_to_vi -v
```

Expected: `ImportError` hoặc `ModuleNotFoundError`

- [ ] **Step 3: Tạo `scripts/vocab_quiz.py` với `build_question`**

```python
# scripts/vocab_quiz.py
from __future__ import annotations

import random
from typing import Any


_QUESTION_TYPES = ["en_vi", "vi_en", "multiple_choice"]
_WEIGHTS = [6, 1, 3]


def build_question(
    entry: dict[str, Any],
    global_pool: list[dict[str, Any]],
    force_type: str | None = None,
) -> dict[str, Any]:
    """Build one quiz question dict from a vocabulary entry.

    Args:
        entry: {"word": str, "notes": str}
        global_pool: all vocabulary docs across all users (for MC distractors)
        force_type: override random selection; one of "en_vi", "vi_en", "multiple_choice"
    """
    q_type = force_type or random.choices(_QUESTION_TYPES, weights=_WEIGHTS, k=1)[0]

    if q_type == "en_vi":
        return {
            "type": "SHORT_ANSWER",
            "question_text": entry["word"],
            "correct_answer": entry["notes"],
            "choices": None,
        }

    if q_type == "vi_en":
        return {
            "type": "SHORT_ANSWER",
            "question_text": entry["notes"],
            "correct_answer": entry["word"],
            "choices": None,
        }

    # multiple_choice — random direction 50-50
    if random.random() < 0.5:
        question_text = entry["word"]
        correct_answer = entry["notes"]
        distractor_pool = [e["notes"] for e in global_pool if e["notes"] != correct_answer]
    else:
        question_text = entry["notes"]
        correct_answer = entry["word"]
        distractor_pool = [e["word"] for e in global_pool if e["word"] != correct_answer]

    distractors = random.sample(distractor_pool, min(3, len(distractor_pool)))
    choices = [correct_answer] + distractors
    random.shuffle(choices)

    return {
        "type": "MULTIPLE_CHOICE",
        "question_text": question_text,
        "correct_answer": correct_answer,
        "choices": choices,
    }
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py::test_short_answer_en_to_vi -v
```

Expected: `PASSED`

- [ ] **Step 5: Viết test Việt→Anh và multiple choice**

Thêm vào `tests/test_vocab_quiz.py`:

```python
def test_short_answer_vi_to_en():
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="vi_en")
    assert q["type"] == "SHORT_ANSWER"
    assert q["question_text"] == "vui vẻ"
    assert q["correct_answer"] == "happy"
    assert q["choices"] is None


def test_multiple_choice_has_4_choices():
    random.seed(42)
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="multiple_choice")
    assert q["type"] == "MULTIPLE_CHOICE"
    assert len(q["choices"]) == 4
    assert q["correct_answer"] in q["choices"]


def test_multiple_choice_correct_not_in_distractors():
    random.seed(42)
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, GLOBAL_POOL, force_type="multiple_choice")
    correct = q["correct_answer"]
    others = [c for c in q["choices"] if c != correct]
    assert correct not in others


def test_multiple_choice_small_pool():
    """Pool nhỏ hơn 3 distractors vẫn hoạt động."""
    small_pool = [
        {"word": "happy", "notes": "vui vẻ"},
        {"word": "sad", "notes": "buồn"},
    ]
    entry = {"word": "happy", "notes": "vui vẻ"}
    q = build_question(entry, small_pool, force_type="multiple_choice")
    assert q["type"] == "MULTIPLE_CHOICE"
    assert len(q["choices"]) >= 1
    assert q["correct_answer"] in q["choices"]
```

- [ ] **Step 6: Chạy tất cả tests, xác nhận PASS**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả `PASSED`

- [ ] **Step 7: Commit**

```bash
git add scripts/vocab_quiz.py tests/test_vocab_quiz.py
git commit -m "feat: implement build_question with weighted random types and MC distractors"
```

---

### Task 3: Implement `build_form_body` — chuyển questions → Forms API payload

**Files:**
- Modify: `scripts/vocab_quiz.py` (thêm `build_form_body`)
- Modify: `tests/test_vocab_quiz.py`

Google Forms API `batchUpdate` nhận list `requests`. Mỗi request là 1 dict. Task này build payload đó.

- [ ] **Step 1: Viết test**

Thêm vào `tests/test_vocab_quiz.py`:

```python
from scripts.vocab_quiz import build_question, build_form_body


def test_build_form_body_structure():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
        {"type": "MULTIPLE_CHOICE", "question_text": "sad", "correct_answer": "buồn",
         "choices": ["buồn", "vui vẻ", "tức giận", "hào hứng"]},
    ]
    requests = build_form_body(questions)
    assert len(requests) == 2


def test_build_form_body_short_answer_has_grading():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    requests = build_form_body(questions)
    req = requests[0]
    # Must have createItem with textQuestion
    assert "createItem" in req
    item = req["createItem"]["item"]
    assert "questionItem" in item
    assert item["questionItem"]["question"]["textQuestion"]["paragraph"] is False
    # Must have grading with correct answer
    grading = item["questionItem"]["question"]["grading"]
    assert grading["pointValue"] == 1
    assert grading["correctAnswers"]["answers"][0]["value"] == "vui vẻ"


def test_build_form_body_multiple_choice_has_options():
    questions = [
        {"type": "MULTIPLE_CHOICE", "question_text": "sad", "correct_answer": "buồn",
         "choices": ["buồn", "vui vẻ", "tức giận", "hào hứng"]},
    ]
    requests = build_form_body(questions)
    req = requests[0]
    item = req["createItem"]["item"]
    choice_q = item["questionItem"]["question"]["choiceQuestion"]
    assert choice_q["type"] == "RADIO"
    option_values = [o["value"] for o in choice_q["options"]]
    assert "buồn" in option_values
    assert len(option_values) == 4
    grading = item["questionItem"]["question"]["grading"]
    assert grading["correctAnswers"]["answers"][0]["value"] == "buồn"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py::test_build_form_body_structure tests/test_vocab_quiz.py::test_build_form_body_short_answer_has_grading tests/test_vocab_quiz.py::test_build_form_body_multiple_choice_has_options -v
```

Expected: `ImportError` (function chưa tồn tại)

- [ ] **Step 3: Implement `build_form_body`**

Thêm vào `scripts/vocab_quiz.py` (sau `build_question`):

```python
def build_form_body(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert question dicts to Google Forms API batchUpdate request list."""
    requests = []
    for idx, q in enumerate(questions):
        if q["type"] == "SHORT_ANSWER":
            item = {
                "title": q["question_text"],
                "questionItem": {
                    "question": {
                        "required": True,
                        "grading": {
                            "pointValue": 1,
                            "correctAnswers": {
                                "answers": [{"value": q["correct_answer"]}]
                            },
                            "whenRight": {"text": "Correct!"},
                            "whenWrong": {"text": f"Correct answer: {q['correct_answer']}"},
                        },
                        "textQuestion": {"paragraph": False},
                    }
                },
            }
        else:  # MULTIPLE_CHOICE
            item = {
                "title": q["question_text"],
                "questionItem": {
                    "question": {
                        "required": True,
                        "grading": {
                            "pointValue": 1,
                            "correctAnswers": {
                                "answers": [{"value": q["correct_answer"]}]
                            },
                            "whenRight": {"text": "Correct!"},
                            "whenWrong": {"text": f"Correct answer: {q['correct_answer']}"},
                        },
                        "choiceQuestion": {
                            "type": "RADIO",
                            "options": [{"value": c} for c in q["choices"]],
                            "shuffle": False,
                        },
                    }
                },
            }

        requests.append({
            "createItem": {
                "item": item,
                "location": {"index": idx},
            }
        })

    return requests
```

- [ ] **Step 4: Chạy tests, xác nhận PASS**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py tests/test_vocab_quiz.py
git commit -m "feat: implement build_form_body for Google Forms API payload"
```

---

### Task 4: Implement `create_quiz_form` — gọi Google Forms API

**Files:**
- Modify: `scripts/vocab_quiz.py` (thêm `create_quiz_form`)

Function này nhận credentials + list questions, tạo form trên Google Drive, trả về form URL. **Không có unit test** vì gọi external API — sẽ test thủ công ở Task 7.

- [ ] **Step 1: Thêm `create_quiz_form` vào `scripts/vocab_quiz.py`**

```python
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build


_SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_google_credentials() -> service_account.Credentials:
    sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sa_info = json.loads(sa_json)
    return service_account.Credentials.from_service_account_info(sa_info, scopes=_SCOPES)


def create_quiz_form(
    username: str,
    questions: list[dict[str, Any]],
    credentials: service_account.Credentials,
) -> str:
    """Create a Google Form quiz. Returns the form's viewform URL."""
    forms_service = google_build("forms", "v1", credentials=credentials)
    drive_service = google_build("drive", "v3", credentials=credentials)

    import datetime
    date_str = datetime.date.today().isoformat()

    # Step 1: create empty form
    form = forms_service.forms().create(body={
        "info": {"title": f"Vocabulary Quiz - {username} - {date_str}"}
    }).execute()
    form_id = form["formId"]

    # Step 2: set quiz mode + add questions
    requests_payload = [
        {
            "updateSettings": {
                "settings": {
                    "quizSettings": {
                        "isQuiz": True,
                    }
                },
                "updateMask": "quizSettings.isQuiz",
            }
        }
    ] + build_form_body(questions)

    forms_service.forms().batchUpdate(
        formId=form_id,
        body={"requests": requests_payload},
    ).execute()

    # Step 3: make form publicly accessible
    drive_service.permissions().create(
        fileId=form_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return f"https://docs.google.com/forms/d/{form_id}/viewform"
```

- [ ] **Step 2: Đặt imports lên đầu file**

Đảm bảo phần đầu `scripts/vocab_quiz.py` là:

```python
from __future__ import annotations

import datetime
import json
import os
import random
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
```

- [ ] **Step 3: Kiểm tra syntax**

```bash
conda run -n tmchien python -m py_compile scripts/vocab_quiz.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Chạy unit tests để đảm bảo không break gì**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py
git commit -m "feat: implement create_quiz_form via Google Forms API"
```

---

### Task 5: Implement `fetch_all_vocab` và `send_discord` — MongoDB + Discord

**Files:**
- Modify: `scripts/vocab_quiz.py` (thêm `fetch_all_vocab`, `send_discord`)
- Modify: `tests/test_vocab_quiz.py`

- [ ] **Step 1: Viết test cho `send_discord`**

Thêm vào `tests/test_vocab_quiz.py`:

```python
from unittest.mock import patch, MagicMock
from scripts.vocab_quiz import send_discord


def test_send_discord_posts_correct_payload():
    with patch("scripts.vocab_quiz.requests") as mock_requests:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_resp

        send_discord("https://discord.webhook/test", "Hello world")

        mock_requests.post.assert_called_once_with(
            "https://discord.webhook/test",
            json={"content": "Hello world"},
            timeout=10,
        )
        mock_resp.raise_for_status.assert_called_once()
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py::test_send_discord_posts_correct_payload -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `fetch_all_vocab` và `send_discord`**

Thêm vào `scripts/vocab_quiz.py`:

```python
import requests as requests_lib


def fetch_all_vocab(mongo_uri: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """Fetch all vocabulary from MongoDB.

    Returns:
        global_pool: all vocab docs (for MC distractors)
        per_user: {user_id: [vocab docs]} mapping
    """
    from pymongo import MongoClient

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
    db = client["fluentup"]

    all_docs = list(db["vocabulary"].find({}, {"_id": 0, "word": 1, "notes": 1, "user_id": 1}))

    per_user: dict[str, list[dict]] = {}
    for doc in all_docs:
        uid = doc["user_id"]
        per_user.setdefault(uid, []).append(doc)

    client.close()
    return all_docs, per_user


def fetch_users(mongo_uri: str) -> list[str]:
    """Return list of usernames from MongoDB users collection."""
    from pymongo import MongoClient

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
    db = client["fluentup"]
    users = list(db["users"].find({}, {"_id": 0, "username": 1}))
    client.close()
    return [u["username"] for u in users]


def send_discord(webhook_url: str, message: str) -> None:
    """POST message to Discord webhook."""
    resp = requests_lib.post(webhook_url, json={"content": message}, timeout=10)
    resp.raise_for_status()
```

- [ ] **Step 4: Chạy tất cả tests**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py tests/test_vocab_quiz.py
git commit -m "feat: implement fetch_all_vocab, fetch_users, send_discord"
```

---

### Task 6: Implement `main()` — orchestrator

**Files:**
- Modify: `scripts/vocab_quiz.py` (thêm `main`)

- [ ] **Step 1: Thêm `main()` vào `scripts/vocab_quiz.py`**

```python
def main() -> None:
    mongo_uri = os.environ["MONGODB_URI"]
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    credentials = _get_google_credentials()

    print("Fetching vocabulary from MongoDB...")
    global_pool, per_user = fetch_all_vocab(mongo_uri)
    usernames = fetch_users(mongo_uri)

    now_ict = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    header = f"📚 Vocabulary Quiz - {now_ict.strftime('%Y-%m-%d %H:%M')} ICT"
    lines = [header]

    for username in usernames:
        user_vocab = per_user.get(username, [])
        if not user_vocab:
            print(f"  Skipping {username}: no vocabulary")
            continue

        sample = random.sample(user_vocab, min(20, len(user_vocab)))
        questions = [build_question(entry, global_pool) for entry in sample]

        try:
            form_url = create_quiz_form(username, questions, credentials)
            lines.append(f"• {username}: {form_url}")
            print(f"  Created form for {username}: {form_url}")
        except Exception as exc:
            print(f"  ERROR creating form for {username}: {exc}")

    if len(lines) == 1:
        print("No forms created, skipping Discord notification.")
        return

    send_discord(webhook_url, "\n".join(lines))
    print("Discord notification sent.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Kiểm tra syntax**

```bash
conda run -n tmchien python -m py_compile scripts/vocab_quiz.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Chạy tất cả unit tests**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả `PASSED`

- [ ] **Step 4: Commit**

```bash
git add scripts/vocab_quiz.py
git commit -m "feat: implement main orchestrator for vocab quiz workflow"
```

---

### Task 7: Tạo GitHub Actions workflow

**Files:**
- Create: `.github/workflows/vocab-quiz.yml`

- [ ] **Step 1: Tạo `.github/workflows/vocab-quiz.yml`**

```yaml
name: Vocab Quiz

on:
  schedule:
    # 7:00, 13:00, 19:00, 01:00 ICT (UTC+7) = 00:00, 06:00, 12:00, 18:00 UTC
    - cron: "0 0,6,12,18 * * *"
  workflow_dispatch:  # manual trigger for testing

jobs:
  send-quiz:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r scripts/requirements-quiz.txt

      - name: Run vocab quiz script
        env:
          MONGODB_URI: ${{ secrets.MONGODB_URI }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python scripts/vocab_quiz.py
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/vocab-quiz.yml
git commit -m "feat: add GitHub Actions cron workflow for vocab quiz"
```

---

### Task 8: Thêm GitHub Secrets và test end-to-end

**Files:** Không có file thay đổi — config trên GitHub UI.

- [ ] **Step 1: Enable Google Forms API và Drive API trong Google Cloud Console**

Truy cập: https://console.cloud.google.com/apis/library?project=shinichien

Tìm và enable:
- **Google Forms API**
- **Google Drive API**

- [ ] **Step 2: Thêm secrets vào GitHub repository**

Truy cập: `Settings → Secrets and variables → Actions → New repository secret`

Thêm 3 secrets:
- `MONGODB_URI` — MongoDB connection string (từ `.streamlit/secrets.toml`, key `MONGODB_URI`)
- `GOOGLE_SERVICE_ACCOUNT_JSON` — nội dung toàn bộ file `credentials/shinichien-0bc21ed9f8c7.json` (copy paste JSON)
- `DISCORD_WEBHOOK_URL` — Discord channel webhook URL

**Lưu ý bảo mật:** Không commit file `credentials/shinichien-0bc21ed9f8c7.json` lên git. Kiểm tra `.gitignore` có entry `credentials/`.

- [ ] **Step 3: Trigger workflow thủ công**

Truy cập: `Actions → Vocab Quiz → Run workflow`

Kiểm tra logs để xác nhận:
- MongoDB kết nối thành công
- Form được tạo cho từng user
- Discord message được gửi

- [ ] **Step 4: Kiểm tra Discord channel**

Xác nhận message xuất hiện với format:
```
📚 Vocabulary Quiz - 2026-05-08 HH:MM ICT
• username1: https://docs.google.com/forms/d/.../viewform
• username2: https://docs.google.com/forms/d/.../viewform
```

- [ ] **Step 5: Mở 1 form link, điền quiz, submit, xác nhận hiện điểm**

Sau khi submit phải thấy: `N/20 điểm`, từng câu đúng/sai với đáp án.
