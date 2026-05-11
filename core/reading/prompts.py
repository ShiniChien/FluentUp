QUESTION_GEN_PROMPT = """\
You are an IELTS Academic Reading question writer (band 6–8 difficulty).

Given the article below, produce exactly 20 questions in this JSON format:

{{
  "tfng": [
    {{"statement": "...", "answer": "True", "paragraph_ref": 1}},
    ... (6 items, answer is exactly "True", "False", or "Not Given")
  ],
  "headings": [
    {{"paragraph_idx": 0, "correct_heading": "...", "options": ["...", "...", "...", "...", "..."]}},
    ... (4 items, 5 options each, correct_heading is one of the options)
  ],
  "fill_blank": [
    {{"sentence": "The economy ___ significantly.", "answer": "grew", "word_limit": "ONE WORD ONLY"}},
    ... (5 items)
  ],
  "mcq": [
    {{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "answer": "A"}},
    ... (5 items)
  ]
}}

Rules:
- Every answer must be derivable from the article text only — no outside knowledge.
- paragraph_ref is 1-indexed (first paragraph = 1).
- paragraph_idx in headings is 0-indexed.
- Respond with ONLY the JSON object. No preamble, no explanation.

ARTICLE TITLE: {title}

ARTICLE:
{body}
"""

QUESTION_GEN_RETRY_PROMPT = """\
Your previous response was not valid JSON. Respond with ONLY the JSON object, no other text.

ARTICLE TITLE: {title}

ARTICLE:
{body}
"""
