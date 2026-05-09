# scripts/vocab_quiz.py
from __future__ import annotations

import datetime
import os
import random
from typing import Any

import requests as requests_lib

_QUESTION_TYPES = ["en_vi", "vi_en", "multiple_choice"]
_WEIGHTS = [6, 1, 3]


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
    # PLACEHOLDER: Google Forms code removed
    print("Fetching vocabulary from MongoDB...")
    global_pool, per_user = fetch_all_vocab(mongo_uri, mongo_user, mongo_pass)
    users = fetch_users(mongo_uri, mongo_user, mongo_pass)

    now_ict = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    header = f"\U0001F4DA Vocabulary Quiz - {now_ict.strftime('%Y-%m-%d %H:%M')} ICT"
    lines = [header]

    for user in users:
        username = user["username"]
        user_vocab = per_user.get(user["id"], [])
        if not user_vocab:
            print(f"  Skipping {username}: no vocabulary")
            continue
        sample = random.sample(user_vocab, min(20, len(user_vocab)))
        questions = [build_question(entry, global_pool) for entry in sample]
        # Google Forms code removed, nothing to do here (will update in Task 4)
        pass

    if len(lines) == 1:
        print("No forms created, skipping Discord notification.")
        return

    message = "\n".join(lines)
    print(message)
    send_discord(webhook_url, message)
    print("Discord notification sent.")


if __name__ == "__main__":
    main()

