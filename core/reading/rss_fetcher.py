from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass

import feedparser
import httpx

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

_RSS_BASE   = "https://news.google.com/news/rss/headlines/section/topic/{topic}"
_MAX_ITEMS  = 20
_TIMEOUT    = 15


@dataclass
class ArticleEntry:
    title:    str
    link:     str   # resolved (real) URL after following Google redirect
    pub_date: str


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw).strip()
    return html.unescape(text)


async def _resolve_redirect(url: str, client: httpx.AsyncClient) -> str:
    """Follow Google redirect to get the real article URL."""
    try:
        resp = await client.head(url, timeout=_TIMEOUT, follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"})
        return str(resp.url)
    except (httpx.HTTPError, httpx.TimeoutException):
        return url


async def fetch_article_list(topic_key: str) -> list[ArticleEntry]:
    """Fetch Google News RSS for a topic and return up to _MAX_ITEMS entries.

    Each entry's link is resolved through Google's redirect to the real URL.
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
            feed = feedparser.parse(resp.text)
            entries = feed.entries[:_MAX_ITEMS]
            valid_entries = [e for e in entries if e.get("link", "")]
            real_links = await asyncio.gather(
                *(_resolve_redirect(e["link"], client) for e in valid_entries)
            )
            results: list[ArticleEntry] = []
            for entry, real_link in zip(valid_entries, real_links):
                title    = _strip_html(entry.get("title", "Untitled"))
                pub_date = entry.get("published", "")
                results.append(ArticleEntry(title=title, link=real_link, pub_date=pub_date))
    except httpx.HTTPError as exc:
        raise ValueError(f"Failed to fetch RSS for topic '{topic_key}': {exc}") from exc

    if not results:
        raise ValueError(f"No entries found in RSS feed for topic '{topic_key}'.")
    return results
