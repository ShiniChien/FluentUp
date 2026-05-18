CONTENT_REWRITE_PROMPT = """\
You are an IELTS Reading passage editor.
Below is raw markdown scraped from a news article.
Rewrite it into a clean, coherent reading passage suitable for IELTS Academic Reading (band 6–8).
- Remove ads, navigation text, author bios, and irrelevant sidebars.
- Keep factual content, statistics, and quotes.
- Use clear paragraphs. Each paragraph should be 3–6 sentences.
- Target 400–600 words total.
- Output ONLY the rewritten passage (plain text, no markdown headers).

RAW CONTENT:
{markdown}
"""

QUESTION_GEN_PROMPT = """\
You are an IELTS Reading question writer.
Given the passage below, generate exactly 10 fill-in-the-blank questions.

Rules:
- Each blank answer must be taken VERBATIM from the passage (1–3 words).
- Write the sentence with a single blank represented as ___.
- The requirement for every question is: NO MORE THAN THREE WORDS from the passage.
- Vary which part of the passage each question targets.

Return ONLY valid JSON in this exact format:
{{
  "requirement": "NO MORE THAN THREE WORDS from the passage",
  "questions": [
    {{"sentence": "The economy ___ significantly in 2023.", "answer": "grew rapidly"}},
    ...
  ]
}}

PASSAGE:
{content}
"""

QUESTION_GEN_RETRY_PROMPT = """\
Your previous response was not valid JSON. Respond with ONLY valid JSON matching this exact schema:

{{
  "requirement": "NO MORE THAN THREE WORDS from the passage",
  "questions": [
    {{"sentence": "The economy ___ significantly in 2023.", "answer": "grew rapidly"}},
    ...10 items total...
  ]
}}

PASSAGE:
{content}
"""
