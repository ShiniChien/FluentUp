"""core/chat/tools.py — Gemini Live function declarations for vocab + memory toolkits."""
from __future__ import annotations

from google.genai import types

ADD_VOCABULARY_DECLARATION = types.FunctionDeclaration(
    name="add_vocabulary",
    description=(
        "Save a new English word or phrase the user encountered during our conversation "
        "to their personal vocabulary list for later review."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "word": types.Schema(type=types.Type.STRING, description="The word or phrase."),
            "definition": types.Schema(type=types.Type.STRING, description="Clear English definition."),
            "example_sentence": types.Schema(
                type=types.Type.STRING,
                description="A natural example sentence using the word.",
            ),
        },
        required=["word", "definition"],
    ),
)

SAVE_MEMORY_DECLARATION = types.FunctionDeclaration(
    name="save_memory",
    description=(
        "Save a personal fact about the user that you learned during conversation "
        "so you can remember it in future sessions."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "fact": types.Schema(
                type=types.Type.STRING,
                description="One concise sentence describing a fact about the user.",
            ),
        },
        required=["fact"],
    ),
)

LIVE_TOOLS = types.Tool(
    function_declarations=[ADD_VOCABULARY_DECLARATION, SAVE_MEMORY_DECLARATION]
)
