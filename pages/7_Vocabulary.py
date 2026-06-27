"""pages/7_Vocabulary.py — Vocabulary management full page."""
from __future__ import annotations

from core.shared import get_store, load_secrets
from core.vocab.page import render_vocab_page

secrets = load_secrets()
store = get_store(secrets)

render_vocab_page(store)
