# scripts/vocab_quiz.py
from __future__ import annotations

import datetime
import os
import random
import re
from typing import Any

import requests as requests_lib

_QUESTION_TYPES = ["en_vi", "vi_en", "multiple_choice"]
_WEIGHTS = [6, 2, 2]


def build_question(
    entry: dict[str, Any],
    global_pool: list[dict[str, Any]],
    force_type: str | None = None,
) -> dict[str, Any]:
    """Build one quiz question dict from a vocabulary entry."""
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

    # multiple_choice  random direction 50-50
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


def fetch_all_vocab(mongo_uri: str, username: str = "", password: str = "") -> tuple[list[dict], dict[str, list[dict]]]:
    """Fetch all vocabulary from MongoDB."""
    from pymongo import MongoClient

    client = MongoClient(
        mongo_uri,
        username=username or None,
        password=password or None,
        serverSelectionTimeoutMS=10000,
    )
    db = client["fluentup"]
    all_docs = list(db["vocabulary"].find({}, {"_id": 0, "word": 1, "notes": 1, "user_id": 1}))
    client.close()

    per_user: dict[str, list[dict]] = {}
    for doc in all_docs:
        uid = doc["user_id"]
        per_user.setdefault(uid, []).append(doc)

    return all_docs, per_user


def fetch_users(mongo_uri: str, username: str = "", password: str = "") -> list[dict]:
    """Return list of users (with _id and username) from MongoDB users collection."""
    from pymongo import MongoClient

    client = MongoClient(
        mongo_uri,
        username=username or None,
        password=password or None,
        serverSelectionTimeoutMS=10000,
    )
    db = client["fluentup"]
    users = list(db["users"].find({}, {"username": 1}))
    client.close()
    return [{"id": str(u["_id"]), "username": u["username"]} for u in users]


def send_discord(webhook_url: str, message: str) -> None:
    """POST message to Discord webhook."""
    resp = requests_lib.post(webhook_url, json={"content": message}, timeout=10)
    resp.raise_for_status()


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

