# Gemma Text Provider — Design Spec
Date: 2026-05-09

## Goal

Add Gemma (via Gemini API) as an alternative text-generation provider alongside OpenRouter. Root admin can switch provider via UI toggle; all four text-gen tasks (Speaking question gen, Writing evaluator, Writing topic pool, Listening topic gen) use whichever provider is active.

## Architecture

### New module: `core/text_provider.py`

Abstract base + two concrete implementations:

```
TextProvider (ABC)
  .chat(prompt, temperature) → str   # async

OpenRouterProvider(base_url, api_key, model)
  → wraps core/openrouter.async_chat

GemmaProvider(gemini_api_key, model)
  → uses google-genai client.aio.models.generate_content
```

Factory function:

```
get_text_provider(secrets) → TextProvider
```

Resolution order:
1. `st.session_state["text_provider"]` (cached)
2. MongoDB `settings` collection, doc `{"_id": "config", "text_provider": ...}`
3. `secrets.toml` key `TEXT_PROVIDER` (default: `"openrouter"`)

### Callers updated

| File | Change |
|------|--------|
| `core/speaking/question_gen.py` | `__init__` accepts `provider: TextProvider`; `_chat` delegates to `provider.chat` |
| `core/writing/evaluator.py` | same pattern |
| `core/writing/topic_pool.py` | same pattern |
| `core/viet_words.py` | `generate_topic` accepts `provider: TextProvider` |

`core/openrouter.py` — unchanged.

### Secrets

| Key | Purpose | Default |
|-----|---------|---------|
| `TEXT_PROVIDER` | `"openrouter"` or `"gemma"` | `"openrouter"` |
| `GEMMA_MODEL` | Gemma model ID | `"gemma-4-31b-it"` |

Existing OpenRouter keys unchanged.

## UI Toggle

Location: `pages/0_Home.py`, inside existing root-only admin block.

Renders `st.radio("Text provider", ["openrouter", "gemma"])` + Save button. On save:
1. Write `{"_id": "config", "text_provider": value}` to MongoDB (upsert)
2. `st.session_state["text_provider"] = value`
3. Rebuild `QuestionGenerator` and `SpeakingEvaluator` with new provider on next Speaking page load (existing session reset pattern)

If MongoDB unavailable, show warning and skip persistence (setting lives in session only).

## Gemma API Call

```python
from google import genai
from google.genai.types import GenerateContentConfig

client = genai.Client(api_key=gemini_api_key)
response = await client.aio.models.generate_content(
    model=model,           # "gemma-4-31b-it"
    contents=prompt,
    config=GenerateContentConfig(temperature=temperature),
)
return response.text.strip()
```

Uses `client.aio` (async) — no blocking calls on main thread.

## Error Handling

- Gemma quota/rate limit errors propagate as exceptions — no auto-fallback to OpenRouter.
- Root must manually switch provider via UI toggle.
- OpenRouter errors: unchanged behavior.

## Out of Scope

- Gemini Live sessions — unaffected.
- Per-user provider preference — global setting only.
- Automatic provider benchmarking or quality comparison.
