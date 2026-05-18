from __future__ import annotations

import html
import re
from dataclasses import dataclass

import feedparser
import httpx
from googlenewsdecoder import gnewsdecoder

RSS_TOPICS: dict[str, str] = {
    "World":         "WORLD",
    "Nation":        "NATION",
    "Business":      "BUSINESS",
    "Technology":    "TECHNOLOGY",
    "Entertainment": "ENTERTAINMENT",
    "Sports":        "SPORTS",
    "Science":       "SCIENCE",
    "Health":        "HEALTH",
}

_RSS_BASE  = "https://news.google.com/rss/headlines/section/topic/{topic}"
_MAX_ITEMS = 20
_TIMEOUT   = 15


@dataclass
class ArticleEntry:
    title:            str
    link:             str   # decoded real article URL (for Jina fetch + dedup)
    link_google_news: str   # original Google News redirect URL
    pub_date:         str


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw).strip()
    return html.unescape(text)


def _decode_google_news_url(google_url: str) -> str:
    """Decode a Google News RSS link to the real article URL.

    Uses googlenewsdecoder which handles the current Google News encryption format.
    Falls back to the original URL on any failure.
    """
    try:
        result = gnewsdecoder(google_url)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception:
        pass
    return google_url


async def fetch_article_list(topic_key: str) -> list[ArticleEntry]:
    """Fetch Google News RSS for a topic and return up to _MAX_ITEMS entries.

    Real article URLs are decoded from each Google News link via googlenewsdecoder.
    Raises ValueError on feed fetch failure.
    """
    topic = RSS_TOPICS.get(topic_key)
    if not topic:
        raise ValueError(f"Unknown topic: {topic_key!r}")

    feed_url = _RSS_BASE.format(topic=topic)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(feed_url, timeout=_TIMEOUT, follow_redirects=True,
                                    headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"Failed to fetch RSS for topic '{topic_key}': {exc}") from exc

    feed = feedparser.parse(resp.text)
    results: list[ArticleEntry] = []
    for entry in feed.entries[:_MAX_ITEMS]:
        google_link = entry.get("link", "")
        if not google_link:
            continue
        real_link = _decode_google_news_url(google_link)
        results.append(ArticleEntry(
            title=_strip_html(entry.get("title", "Untitled")),
            link=real_link,
            link_google_news=google_link,
            pub_date=entry.get("published", ""),
        ))

    if not results:
        raise ValueError(f"No entries found in RSS feed for topic '{topic_key}'.")
    return results


