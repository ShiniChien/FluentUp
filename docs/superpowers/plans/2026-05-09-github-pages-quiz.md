# GitHub Pages Quiz Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay thế Google Forms bằng HTML quiz tĩnh deploy lên branch `gh-pages` của repo `ShiniChien/FluentUp`, gửi link `https://shinichien.github.io/FluentUp/quiz/{username}_{date}_{time}.html` qua Discord.

**Architecture:** Script xóa code Google Forms, thêm `generate_quiz_html()` tạo HTML self-contained với JS chấm điểm client-side, thêm `cleanup_old_quiz_files()` xóa file > 3 ngày. Workflow checkout gh-pages, copy file cũ vào `quiz/`, chạy script, deploy lại lên gh-pages bằng `peaceiris/actions-gh-pages@v3`.

**Tech Stack:** Python 3.11, pymongo, requests, HTML/CSS/JS (vanilla), GitHub Actions, GitHub Pages

---

## File Structure

```
scripts/
  vocab_quiz.py        # Xóa Google code, thêm generate_quiz_html + cleanup_old_quiz_files
  requirements-quiz.txt  # Xóa google-auth và google-api-python-client
.github/
  workflows/
    vocab-quiz.yml     # Thêm checkout gh-pages + deploy step, xóa Google env vars
tests/
  test_vocab_quiz.py   # Xóa test build_form_body, thêm test generate_quiz_html + cleanup
```

---

### Task 1: Xóa Google Forms code khỏi vocab_quiz.py và requirements

**Files:**
- Modify: `scripts/vocab_quiz.py`
- Modify: `scripts/requirements-quiz.txt`
- Modify: `tests/test_vocab_quiz.py`

- [ ] **Step 1: Cập nhật `scripts/requirements-quiz.txt`**

Nội dung mới (xóa 2 dòng google):
```
pymongo==4.7.3
requests==2.32.3
```

- [ ] **Step 2: Xóa Google imports và functions khỏi `scripts/vocab_quiz.py`**

Xóa các dòng import sau ở đầu file:
```python
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
```

Xóa các constant và functions sau (toàn bộ body):
- `_SCOPES = [...]`
- `def _get_google_credentials() -> ...`
- `def build_form_body(...) -> ...`
- `def create_quiz_form(...) -> ...`

Phần đầu file sau khi xóa phải là:
```python
# scripts/vocab_quiz.py
from __future__ import annotations

import datetime
import os
import random
from typing import Any

import requests as requests_lib

_QUESTION_TYPES = ["en_vi", "vi_en", "multiple_choice"]
_WEIGHTS = [6, 1, 3]
```

- [ ] **Step 3: Xóa tests liên quan đến build_form_body trong `tests/test_vocab_quiz.py`**

Xóa toàn bộ 3 test functions và import của chúng:
- `from scripts.vocab_quiz import build_question, build_form_body` → đổi thành `from scripts.vocab_quiz import build_question`
- `def test_build_form_body_structure()`
- `def test_build_form_body_short_answer_has_grading()`
- `def test_build_form_body_multiple_choice_has_options()`

- [ ] **Step 4: Kiểm tra syntax và chạy tests còn lại**

```bash
cd /home/misa/Desktop/RD/Eng
conda run -n tmchien python -m py_compile scripts/vocab_quiz.py && echo "OK"
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: syntax OK, 6 tests PASS (test_short_answer_en_to_vi, test_short_answer_vi_to_en, test_multiple_choice_*, test_send_discord_*)

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py scripts/requirements-quiz.txt tests/test_vocab_quiz.py
git commit -m "refactor: remove Google Forms code, keep core quiz logic"
```

---

### Task 2: Implement `generate_quiz_html`

**Files:**
- Modify: `scripts/vocab_quiz.py` (thêm function)
- Modify: `tests/test_vocab_quiz.py` (thêm tests)

Signature: `generate_quiz_html(username: str, questions: list[dict[str, Any]], timestamp: str) -> str`

`timestamp` format: `"2026-05-09_07-00"` — dùng trong title và để embed vào HTML.

- [ ] **Step 1: Viết tests cho `generate_quiz_html`**

Thêm vào cuối `tests/test_vocab_quiz.py`:

```python
from scripts.vocab_quiz import generate_quiz_html


def test_generate_quiz_html_contains_username():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("shinichien", questions, "2026-05-09_07-00")
    assert "shinichien" in html


def test_generate_quiz_html_short_answer_has_input():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert 'type="text"' in html
    assert "happy" in html


def test_generate_quiz_html_multiple_choice_has_radio():
    questions = [
        {"type": "MULTIPLE_CHOICE", "question_text": "sad", "correct_answer": "buồn",
         "choices": ["buồn", "vui vẻ", "tức giận", "hào hứng"]},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert 'type="radio"' in html
    assert "buồn" in html
    assert "vui vẻ" in html


def test_generate_quiz_html_correct_answer_embedded():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert "vui vẻ" in html


def test_generate_quiz_html_has_submit_button():
    questions = [
        {"type": "SHORT_ANSWER", "question_text": "happy", "correct_answer": "vui vẻ", "choices": None},
    ]
    html = generate_quiz_html("u", questions, "2026-05-09_07-00")
    assert "submit" in html.lower() or "nộp" in html.lower()
```

- [ ] **Step 2: Chạy tests, xác nhận FAIL**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py::test_generate_quiz_html_contains_username -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `generate_quiz_html` trong `scripts/vocab_quiz.py`**

Thêm sau `build_question` (trước `fetch_all_vocab`):

```python
def generate_quiz_html(
    username: str,
    questions: list[dict[str, Any]],
    timestamp: str,
) -> str:
    """Generate a self-contained HTML quiz page."""

    def _escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    items_html = ""
    for idx, q in enumerate(questions):
        correct_escaped = _escape(q["correct_answer"])
        question_escaped = _escape(q["question_text"])

        if q["type"] == "SHORT_ANSWER":
            answer_html = f'<input type="text" class="ans" autocomplete="off" style="width:300px;padding:4px;font-size:1em">'
        else:
            opts = "".join(
                f'<label style="display:block;margin:4px 0"><input type="radio" name="q{idx}" class="ans" value="{_escape(c)}"> {_escape(c)}</label>'
                for c in q["choices"]
            )
            answer_html = f'<div>{opts}</div>'

        items_html += f"""
<div class="q" data-correct="{correct_escaped}" style="margin:16px 0;padding:12px;border:1px solid #ddd;border-radius:6px">
  <p style="margin:0 0 8px;font-weight:bold">{idx + 1}. {question_escaped}</p>
  {answer_html}
  <p class="feedback" style="margin:6px 0 0;display:none"></p>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vocab Quiz - {_escape(username)} - {timestamp}</title>
<style>
  body{{font-family:sans-serif;max-width:720px;margin:32px auto;padding:0 16px}}
  .correct{{background:#d4edda!important}}
  .wrong{{background:#f8d7da!important}}
  #score{{font-size:1.4em;font-weight:bold;padding:12px;border-radius:6px;margin-bottom:16px;display:none}}
  button{{padding:10px 24px;font-size:1em;cursor:pointer;background:#0d6efd;color:#fff;border:none;border-radius:6px}}
</style>
</head>
<body>
<h2>📚 Vocabulary Quiz — {_escape(username)}</h2>
<p style="color:#666">{timestamp.replace("_", " ").replace("-", ":")}</p>
<div id="score"></div>
<div id="questions">{items_html}</div>
<br>
<button onclick="submitQuiz()">Nộp bài</button>
<script>
function submitQuiz(){{
  var qs=document.querySelectorAll('.q');
  var correct=0;
  qs.forEach(function(q){{
    var expected=q.dataset.correct.trim().toLowerCase();
    var input=q.querySelector('input[type="text"]');
    var ans='';
    if(input){{ans=input.value.trim().toLowerCase();}}
    else{{var r=q.querySelector('input[type="radio"]:checked');ans=r?r.value.trim().toLowerCase():'';}}
    var fb=q.querySelector('.feedback');
    fb.style.display='block';
    if(ans===expected){{q.classList.add('correct');correct++;fb.textContent='✓ Correct';fb.style.color='green';}}
    else{{q.classList.add('wrong');fb.textContent='✗ Đáp án: '+q.dataset.correct;fb.style.color='red';}}
  }});
  var sc=document.getElementById('score');
  sc.style.display='block';
  sc.textContent='Score: '+correct+'/'+qs.length;
  sc.style.background=correct===qs.length?'#d4edda':'#fff3cd';
  sc.scrollIntoView();
}}
</script>
</body>
</html>"""
```

- [ ] **Step 4: Chạy tất cả tests, xác nhận PASS**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả PASS (6 cũ + 5 mới = 11 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py tests/test_vocab_quiz.py
git commit -m "feat: implement generate_quiz_html with client-side scoring"
```

---

### Task 3: Implement `cleanup_old_quiz_files`

**Files:**
- Modify: `scripts/vocab_quiz.py`
- Modify: `tests/test_vocab_quiz.py`

GC xóa file trong `quiz_dir` có tên match pattern `*_{YYYY-MM-DD}_{HH-MM}.html` và date > `days` ngày trước.

- [ ] **Step 1: Viết tests**

Thêm vào cuối `tests/test_vocab_quiz.py`:

```python
import os
import tempfile
from scripts.vocab_quiz import cleanup_old_quiz_files


def test_cleanup_removes_old_files():
    with tempfile.TemporaryDirectory() as d:
        # File 4 ngày trước — phải bị xóa
        old_date = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
        old_file = os.path.join(d, f"user_{old_date}_07-00.html")
        with open(old_file, "w") as f:
            f.write("old")

        cleanup_old_quiz_files(d, days=3)

        assert not os.path.exists(old_file)


def test_cleanup_keeps_recent_files():
    with tempfile.TemporaryDirectory() as d:
        # File hôm nay — phải giữ lại
        today = datetime.date.today().isoformat()
        new_file = os.path.join(d, f"user_{today}_07-00.html")
        with open(new_file, "w") as f:
            f.write("new")

        cleanup_old_quiz_files(d, days=3)

        assert os.path.exists(new_file)


def test_cleanup_ignores_non_matching_files():
    with tempfile.TemporaryDirectory() as d:
        # File không match pattern — không bị xóa
        other = os.path.join(d, "index.html")
        with open(other, "w") as f:
            f.write("index")

        cleanup_old_quiz_files(d, days=3)

        assert os.path.exists(other)
```

Thêm import `datetime` ở đầu test file nếu chưa có (đã có `import random`, thêm `import datetime`).

- [ ] **Step 2: Chạy tests, xác nhận FAIL**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py::test_cleanup_removes_old_files -v
```

Expected: `ImportError`

- [ ] **Step 3: Implement `cleanup_old_quiz_files` trong `scripts/vocab_quiz.py`**

Thêm vào sau `generate_quiz_html`, trước `fetch_all_vocab`. Cần thêm `import re` ở đầu file.

Thêm `import re` vào imports:
```python
import re
```

Thêm function:
```python
_QUIZ_FILE_RE = re.compile(r"^.+_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}\.html$")


def cleanup_old_quiz_files(quiz_dir: str, days: int = 3) -> None:
    """Delete quiz files older than `days` days from quiz_dir."""
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    if not os.path.isdir(quiz_dir):
        return
    for fname in os.listdir(quiz_dir):
        m = _QUIZ_FILE_RE.match(fname)
        if not m:
            continue
        file_date = datetime.date.fromisoformat(m.group(1))
        if file_date < cutoff:
            os.remove(os.path.join(quiz_dir, fname))
            print(f"  GC: removed {fname}")
```

- [ ] **Step 4: Chạy tất cả tests**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả PASS (11 cũ + 3 mới = 14 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py tests/test_vocab_quiz.py
git commit -m "feat: implement cleanup_old_quiz_files with date-based GC"
```

---

### Task 4: Cập nhật `main()` để dùng HTML thay vì Google Forms

**Files:**
- Modify: `scripts/vocab_quiz.py`

`main()` mới:
1. Đọc `QUIZ_DIR` env var (default `quiz`)
2. `cleanup_old_quiz_files(quiz_dir)`
3. Với mỗi user: `generate_quiz_html()` → ghi file, tạo GitHub Pages URL
4. `send_discord()`

- [ ] **Step 1: Thay thế toàn bộ `main()` trong `scripts/vocab_quiz.py`**

```python
_GH_PAGES_BASE = "https://shinichien.github.io/FluentUp"


def main() -> None:
    mongo_uri = os.environ["MONGODB_URI"]
    mongo_user = os.environ.get("MONGODB_USERNAME", "")
    mongo_pass = os.environ.get("MONGODB_PASSWORD", "")
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    quiz_dir = os.environ.get("QUIZ_DIR", "quiz")

    os.makedirs(quiz_dir, exist_ok=True)

    print(f"Running GC on {quiz_dir}...")
    cleanup_old_quiz_files(quiz_dir, days=3)

    print("Fetching vocabulary from MongoDB...")
    global_pool, per_user = fetch_all_vocab(mongo_uri, mongo_user, mongo_pass)
    users = fetch_users(mongo_uri, mongo_user, mongo_pass)

    now_ict = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    timestamp = now_ict.strftime("%Y-%m-%d_%H-%M")
    header = f"📚 Vocabulary Quiz - {now_ict.strftime('%Y-%m-%d %H:%M')} ICT"
    lines = [header]

    for user in users:
        username = user["username"]
        user_vocab = per_user.get(user["id"], [])
        if not user_vocab:
            print(f"  Skipping {username}: no vocabulary")
            continue

        sample = random.sample(user_vocab, min(20, len(user_vocab)))
        questions = [build_question(entry, global_pool) for entry in sample]

        html = generate_quiz_html(username, questions, timestamp)
        filename = f"{username}_{timestamp}.html"
        filepath = os.path.join(quiz_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Generated {filepath}")

        url = f"{_GH_PAGES_BASE}/quiz/{filename}"
        lines.append(f"• {username}: {url}")

    if len(lines) == 1:
        print("No quizzes generated, skipping Discord notification.")
        return

    message = "\n".join(lines)
    print(message)
    send_discord(webhook_url, message)
    print("Discord notification sent.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Kiểm tra syntax**

```bash
conda run -n tmchien python -m py_compile scripts/vocab_quiz.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Chạy tất cả tests**

```bash
conda run -n tmchien python -m pytest tests/test_vocab_quiz.py -v
```

Expected: tất cả 14 PASS

- [ ] **Step 4: Test local với MongoDB thật**

```bash
cd /home/misa/Desktop/RD/Eng
MONGODB_URI="mongodb://10.8.28.45:27017/" MONGODB_USERNAME="" MONGODB_PASSWORD="" \
DISCORD_WEBHOOK_URL="DISCORD_WEBHOOK_PLACEHOLDER" \
QUIZ_DIR="/tmp/quiz_test" \
conda run -n tmchien python scripts/vocab_quiz.py
```

Expected: file `/tmp/quiz_test/shinichien_{date}_{time}.html` được tạo, Discord message được gửi với GitHub Pages URL.

Mở file HTML trong browser để xác nhận quiz hiển thị đúng: câu hỏi, input/radio, nộp bài chấm điểm.

- [ ] **Step 5: Commit**

```bash
git add scripts/vocab_quiz.py
git commit -m "feat: update main() to generate HTML quiz files for GitHub Pages"
```

---

### Task 5: Cập nhật GitHub Actions workflow

**Files:**
- Modify: `.github/workflows/vocab-quiz.yml`

- [ ] **Step 1: Thay thế toàn bộ nội dung `.github/workflows/vocab-quiz.yml`**

```yaml
name: Vocab Quiz

on:
  schedule:
    # 7:00, 13:00, 19:00, 01:00 ICT (UTC+7) = 00:00, 06:00, 12:00, 18:00 UTC
    - cron: "0 0,6,12,18 * * *"
  workflow_dispatch:

jobs:
  send-quiz:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout main branch
        uses: actions/checkout@v4

      - name: Checkout gh-pages (for existing quiz files)
        uses: actions/checkout@v4
        with:
          ref: gh-pages
          path: .gh-pages
        continue-on-error: true

      - name: Restore existing quiz files
        run: |
          mkdir -p quiz
          if [ -d .gh-pages/quiz ]; then
            cp -r .gh-pages/quiz/. quiz/
          fi

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r scripts/requirements-quiz.txt

      - name: Run vocab quiz script
        env:
          MONGODB_URI: "mongodb://10.8.28.45:27017/"
          MONGODB_USERNAME: ""
          MONGODB_PASSWORD: ""
          DISCORD_WEBHOOK_URL: "DISCORD_WEBHOOK_PLACEHOLDER"
          QUIZ_DIR: quiz
        run: python scripts/vocab_quiz.py

      - name: Deploy quiz to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./quiz
          destination_dir: quiz
          keep_files: true
```

- [ ] **Step 2: Kiểm tra YAML syntax**

```bash
conda run -n tmchien python -c "import yaml; yaml.safe_load(open('.github/workflows/vocab-quiz.yml'))" && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit và push**

```bash
git add .github/workflows/vocab-quiz.yml
git commit -m "feat: update workflow to deploy HTML quiz to GitHub Pages"
git push origin main
```

- [ ] **Step 4: Enable GitHub Pages trên repo**

Truy cập: `https://github.com/ShiniChien/FluentUp/settings/pages`

Chọn:
- Source: **Deploy from a branch**
- Branch: **gh-pages** / **/ (root)**
- Save

- [ ] **Step 5: Trigger workflow thủ công và verify**

Truy cập: `https://github.com/ShiniChien/FluentUp/actions` → **Vocab Quiz** → **Run workflow**

Sau khi chạy xong:
1. Kiểm tra branch `gh-pages` có file `quiz/shinichien_{date}_{time}.html`
2. Mở link trong Discord, xác nhận quiz load được
3. Làm quiz, ấn Nộp bài, xác nhận điểm hiển thị + đúng/sai từng câu
