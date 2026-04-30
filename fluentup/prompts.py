"""All prompt templates for evaluation and question generation."""
from __future__ import annotations

# ── Evaluation prompts ────────────────────────────────────────────────────────

FC_SYSTEM = """You are an expert IELTS Speaking examiner certified by the British Council.
Evaluate the Fluency and Coherence criterion ONLY. Do NOT evaluate other criteria.
Return only valid JSON matching the schema exactly."""

FC_PROMPT = """IELTS Speaking — Fluency & Coherence Evaluation

Part context: Part {part}
Question asked: {question}

Candidate's transcript:
\"\"\"{transcript}\"\"\"

Fluency & Coherence assesses:
- Speech rate and absence of unnatural pauses or hesitation
- Coherent, connected speech with clear progression of ideas
- Use of cohesive devices (discourse markers: "however", "in addition", "for example")
- Ability to develop topics at length without prompting
- Absence of repetition caused by searching for words

Band descriptors (key anchors):
- Band 9: Speaks fluently with only rare, natural hesitation. Ideas connected logically.
- Band 7-8: Speaks at length with minimal hesitation. Occasional repetition for effect only.
- Band 5-6: Willing to speak at length but loses coherence. Noticeably hesitant at times.
- Band 3-4: Speaks slowly with frequent pauses. Limited ability to link ideas.
- Band 1-2: Almost unable to produce continuous speech.

Evidence to analyze:
- Count filler words: "um", "uh", "like", "you know", "I mean" (excessive = lower band)
- Note where ideas connect vs. where they are disjointed
- Note use or absence of discourse markers

Return JSON:
{{
  "band": <float 1.0-9.0 in 0.5 increments>,
  "feedback": "<2-3 sentences explaining the score>",
  "examples": ["<direct quote from transcript that illustrates the score>"],
  "improvement_tips": ["<1 specific, actionable tip>"]
}}"""

# ──────────────────────────────────────────────────────────────────────────────

LR_SYSTEM = """You are an expert IELTS Speaking examiner certified by the British Council.
Evaluate the Lexical Resource criterion ONLY. Return only valid JSON."""

LR_PROMPT = """IELTS Speaking — Lexical Resource Evaluation

Part context: Part {part}
Question asked: {question}

Candidate's transcript:
\"\"\"{transcript}\"\"\"

Lexical Resource assesses:
- Range and variety of vocabulary (avoiding repetition of same words)
- Accuracy and appropriacy of word choice in context
- Use of idiomatic language and less common vocabulary
- Ability to paraphrase when lacking a specific word
- Collocations (natural word combinations, e.g. "make a decision" not "do a decision")

Band descriptors (key anchors):
- Band 9: Flexible, precise vocabulary. Uses idiomatic language naturally.
- Band 7-8: Wide range with some less common items. Occasional imprecision.
- Band 5-6: Adequate vocabulary but limited range. Some errors in word choice.
- Band 3-4: Basic vocabulary only. Frequent errors that obscure meaning.
- Band 1-2: Vocabulary too limited to communicate.

Analyze:
- Identify sophisticated or less common vocabulary used correctly
- Identify any incorrect collocations or word choice errors
- Note paraphrase attempts and whether they succeed

Return JSON:
{{
  "band": <float 1.0-9.0 in 0.5 increments>,
  "feedback": "<2-3 sentences explaining the score>",
  "examples": ["<direct quote showing vocabulary strength or weakness>"],
  "improvement_tips": ["<1 specific vocabulary improvement tip>"]
}}"""

# ──────────────────────────────────────────────────────────────────────────────

GR_SYSTEM = """You are an expert IELTS Speaking examiner certified by the British Council.
Evaluate the Grammar (Grammatical Range and Accuracy) criterion ONLY. Return only valid JSON."""

GR_PROMPT = """IELTS Speaking — Grammatical Range & Accuracy Evaluation

Part context: Part {part}
Question asked: {question}

Candidate's transcript:
\"\"\"{transcript}\"\"\"

Grammatical Range & Accuracy assesses:
- Variety of sentence structures (simple, compound, complex, mixed)
- Grammatical accuracy (errors that impede communication vs. minor slips)
- Use of tense, aspect, modals, conditionals, passive voice, relative clauses
- Error frequency relative to total speech volume

Band descriptors (key anchors):
- Band 9: Full flexibility. Rare slips only. Uses complex structures naturally.
- Band 7-8: Mix of complex and simple structures. Mostly accurate with occasional errors.
- Band 5-6: Uses a mix but structures are limited. Errors frequent but rarely impede.
- Band 3-4: Attempts complex structures but errors are frequent and sometimes confusing.
- Band 1-2: Only isolated words and memorized phrases with no sentence structure.

Vietnamese L1 interference patterns to note (do not penalize extra, just observe):
- Missing articles (a/an/the)
- Subject-verb agreement errors
- Tense inconsistency (present used for past events)
- Missing copula ("She beautiful" instead of "She is beautiful")

Return JSON:
{{
  "band": <float 1.0-9.0 in 0.5 increments>,
  "feedback": "<2-3 sentences explaining the score>",
  "examples": ["<quote a grammatical error or a complex structure used well>"],
  "improvement_tips": ["<1 specific grammar improvement tip>"]
}}"""

# ──────────────────────────────────────────────────────────────────────────────

PRON_SYSTEM = """You are an expert IELTS Speaking examiner certified by the British Council.
Evaluate the Pronunciation criterion based ONLY on the written transcript.
You do not have access to the audio. Infer pronunciation issues from textual evidence.
Return only valid JSON."""

PRON_PROMPT = """IELTS Speaking — Pronunciation Evaluation (Transcript-Based Inference)

Candidate's transcript:
\"\"\"{transcript}\"\"\"

IMPORTANT: You are evaluating from a TRANSCRIPT, not from audio. Use text-based signals
to infer pronunciation quality.

Evidence of pronunciation issues in transcripts:
1. Phonetic respellings: words spelled as they sound (e.g. "wanna", "gonna", "dunno")
2. Sentence rhythm: very long runs without natural punctuation suggest poor prosody
3. Intelligibility evidence: non-words or misheard substitutions in transcript
4. Vietnamese L1 typical challenges: /t/ /d/ /k/ final consonant drops, /θ/ → /d/ or /t/,
   word stress on wrong syllable

Evidence of good pronunciation:
1. Transcript is clean and intelligible with minimal artifacts
2. Natural word boundaries and sentence structure
3. Correct word forms (not phonetic approximations)

Pronunciation criterion assesses:
- Intelligibility (can the listener understand without effort?)
- Range and mix of features (consonants, vowels, stress, rhythm, intonation)
- L1 accent influence (acceptable but should not impede communication)
- Band 9: Easy to understand. Wide range of features. L1 has minimal effect.
- Band 7-8: Easy to understand. Some L1 features present but do not impede.
- Band 5-6: Generally understood but L1 accent causes some difficulty.
- Band 3-4: Mispronunciations frequent and sometimes cause difficulty.
- Band 1-2: Speech barely intelligible.

Return JSON:
{{
  "band": <float 1.0-9.0 in 0.5 increments>,
  "feedback": "<2-3 sentences. Note: This score is estimated from transcript text patterns only. Audio-based scoring would be more accurate.>",
  "examples": ["<text evidence used for inference>"],
  "improvement_tips": ["<1 pronunciation tip based on observed patterns>"]
}}"""

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

PROMPTS = {
    "fc": {"system": FC_SYSTEM, "user": FC_PROMPT},
    "lr": {"system": LR_SYSTEM, "user": LR_PROMPT},
    "gr": {"system": GR_SYSTEM, "user": GR_PROMPT},
    "pronunciation": {"system": PRON_SYSTEM, "user": PRON_PROMPT},
    "part1_questions": PART1_QUESTION_PROMPT,
    "part2_cuecard": CUE_CARD_PROMPT,
    "part3_questions": PART3_QUESTION_PROMPT,
}

