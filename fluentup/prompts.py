"""All prompt templates for evaluation and question generation."""
from __future__ import annotations

# ── Question generation prompts ───────────────────────────────────────────────

PART1_QUESTION_PROMPT = """You are an IELTS Speaking examiner.
Generate {n} natural Part 1 questions on the topic: "{topic}".
Topics must be from everyday life (home, work, hobbies, travel, food, technology).
Questions should be conversational, clear, and vary in difficulty (easy to moderate).
Return a JSON array of strings only.
Example: ["Do you enjoy cooking?", "How often do you cook at home?"]"""

CUE_CARD_PROMPT = """You are an IELTS Speaking examiner.
Generate an IELTS Speaking Part 2 cue card on a random interesting topic.
Return JSON with this exact schema:
{{
  "topic": "Describe a ...",
  "points": ["What/who it was", "When/where it happened", "How it happened", "Why it was memorable"],
  "explain": "And explain why this was important/interesting/memorable to you."
}}
Make the topic specific and engaging. Use past experiences or hypothetical scenarios."""

PART3_QUESTION_PROMPT = """You are an IELTS Speaking examiner.
The candidate just completed Part 2 on the topic: "{part2_topic}".
Generate {n} Part 3 discussion questions that expand on this theme with abstract ideas.
Questions should require analysis, comparison, opinion, or speculation.
They should be significantly more abstract and challenging than Part 1 questions.
Return a JSON array of strings only."""

PART3_RANDOM_QUESTION_PROMPT = """You are an IELTS Speaking examiner.
Generate {n} IELTS Speaking Part 3 discussion questions on the topic: "{topic}".
Questions should require analysis, comparison, opinion, or speculation.
They should be abstract and thought-provoking, appropriate for Part 3.
Return a JSON array of strings only."""


# ── Gemini Live evaluation prompts (audio-aware) ──────────────────────────────
# Each prompt is used in a separate Gemini Live session that receives the audio.
# Respond with ONLY a JSON object — no markdown fences, no explanation.

_JSON_SCHEMA = """
Respond with ONLY valid JSON (no markdown, no extra text):
{{"band": <float 1.0-9.0 step 0.5>, "feedback": "<2-3 sentence assessment>", "examples": ["<short quoted phrase from speech>"], "tips": ["<specific actionable improvement>"]}}"""

FC_LIVE_SYSTEM = (
    "You are an IELTS Speaking examiner evaluating ONLY Fluency & Coherence (FC).\n"
    "The candidate was asked (Part {part}): \"{question}\"\n"
    "Listen to the audio directly. Assess:\n"
    "- Fluency: speaking rate, unnatural pauses, repetitions, self-corrections\n"
    "- Filler words heard: um, uh, er, like, you know\n"
    "- Coherence: logical sequencing, topic relevance, clear main idea\n"
    "- Discourse markers: firstly, moreover, however, in addition, as a result\n"
    "- Cohesive devices: correlative conjunctions, subordinating conjunctions\n"
    + _JSON_SCHEMA
)

LR_LIVE_SYSTEM = (
    "You are an IELTS Speaking examiner evaluating ONLY Lexical Resource (LR).\n"
    "The candidate was asked (Part {part}): \"{question}\"\n"
    "Listen to the audio directly. Assess:\n"
    "- Topic-specific vocabulary: appropriate and varied word choices\n"
    "- Phrasal verbs used naturally (e.g. 'grow up', 'deal with')\n"
    "- Collocations: natural word partnerships (e.g. 'make a decision')\n"
    "- Idioms: used accurately and contextually\n"
    "- Avoidance of repetition and over-reliance on basic words\n"
    + _JSON_SCHEMA
)

GR_LIVE_SYSTEM = (
    "You are an IELTS Speaking examiner evaluating ONLY Grammatical Range & Accuracy (GR).\n"
    "The candidate was asked (Part {part}): \"{question}\"\n"
    "Listen to the audio directly. Assess:\n"
    "- Tense accuracy and variety (past, present, conditional, perfect)\n"
    "- Complex sentences: subordinate clauses, relative clauses\n"
    "- Compound sentences: coordinating conjunctions\n"
    "- Advanced structures: passive voice, inversion, reported speech\n"
    "- Frequency and impact of grammatical errors\n"
    + _JSON_SCHEMA
)

PRONUN_LIVE_SYSTEM = (
    "You are an IELTS Speaking examiner evaluating ONLY Pronunciation.\n"
    "The candidate was asked (Part {part}): \"{question}\"\n"
    "Listen carefully to the audio directly. Assess the SPOKEN audio:\n"
    "- Individual sounds: final consonants, vowel quality, minimal pairs\n"
    "- Word stress: correct syllable emphasis (e.g. pho-TO-graph vs PHO-to-graph)\n"
    "- Sentence stress and rhythm: content vs function words\n"
    "- Intonation: rising/falling patterns, question intonation\n"
    "- Connected speech: linking, elision, weak forms, schwa reduction\n"
    "- Overall intelligibility for a native English speaker\n"
    + _JSON_SCHEMA
)
