# scripts/vocab_quiz.py
from __future__ import annotations

import datetime
import json
import os
import random
from typing import Any

import requests as requests_lib
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build

_QUESTION_TYPES = ["en_vi", "vi_en", "multiple_choice"]
_WEIGHTS = [6, 1, 3]

_SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_google_credentials() -> service_account.Credentials:
    # Support file path (private repo) or JSON string (GitHub Secrets)
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE")
    if key_file:
        return service_account.Credentials.from_service_account_file(key_file, scopes=_SCOPES)
    sa_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    return service_account.Credentials.from_service_account_info(sa_info, scopes=_SCOPES)


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


def create_quiz_form(
    username: str,
    questions: list[dict[str, Any]],
    credentials: service_account.Credentials,
) -> str:
    """Create a Google Form quiz. Returns the form's viewform URL."""
    forms_service = google_build("forms", "v1", credentials=credentials)
    drive_service = google_build("drive", "v3", credentials=credentials)

    date_str = datetime.date.today().isoformat()

    form = forms_service.forms().create(body={
        "info": {"title": f"Vocabulary Quiz - {username} - {date_str}"}
    }).execute()
    form_id = form["formId"]

    requests_payload = [
        {
            "updateSettings": {
                "settings": {"quizSettings": {"isQuiz": True}},
                "updateMask": "quizSettings.isQuiz",
            }
        }
    ] + build_form_body(questions)

    forms_service.forms().batchUpdate(
        formId=form_id,
        body={"requests": requests_payload},
    ).execute()

    drive_service.permissions().create(
        fileId=form_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return f"https://docs.google.com/forms/d/{form_id}/viewform"


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


def main() -> None:
    mongo_uri = os.environ["MONGODB_URI"]
    mongo_user = os.environ.get("MONGODB_USERNAME", "")
    mongo_pass = os.environ.get("MONGODB_PASSWORD", "")
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    credentials = _get_google_credentials()

    print("Fetching vocabulary from MongoDB...")
    global_pool, per_user = fetch_all_vocab(mongo_uri, mongo_user, mongo_pass)
    users = fetch_users(mongo_uri, mongo_user, mongo_pass)

    now_ict = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
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

        try:
            form_url = create_quiz_form(username, questions, credentials)
            lines.append(f"• {username}: {form_url}")
            print(f"  Created form for {username}: {form_url}")
        except Exception as exc:
            print(f"  ERROR creating form for {username}: {exc}")

    if len(lines) == 1:
        print("No forms created, skipping Discord notification.")
        return

    message = "\n".join(lines)
    print(message)
    send_discord(webhook_url, message)
    print("Discord notification sent.")


if __name__ == "__main__":
    main()

