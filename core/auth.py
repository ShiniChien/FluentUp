"""core/auth.py — password hashing and session helpers."""
from __future__ import annotations

import hashlib

import streamlit as st

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


def build_root_user(username: str, password: str) -> dict:
    return {
        "username": username,
        "password_hash": hash_password(password),
        "role": "root",
        "name": "Administrator",
        "age": 0,
        "occupation": "other",
        "occupation_detail": "System administrator",
        "gender": "other",
        "_id": username,
    }


def current_user() -> dict | None:
    return st.session_state.get("current_user")


def is_logged_in() -> bool:
    return current_user() is not None


def is_root() -> bool:
    u = current_user()
    return u is not None and u.get("role") == "root"


def logout() -> None:
    st.session_state.pop("current_user", None)
