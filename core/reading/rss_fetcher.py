from __future__ import annotations

import re
from dataclasses import dataclass

import feedparser
import httpx

RSS_FEEDS: dict[str, str] = {
    "World News":  "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Science":     "https://rss.sciam.com/ScientificAmerican-Global",
    "Technology":  "https://www.wired.com/feed/rss",
    "Environment": "https://www.theguardian.com/environment/rss",
    "Business":    "https://feeds.reuters.com/reuters/businessNews",
    "Health":      "https://feeds.bbci.co.uk/news/health/rss.xml",
}

_MIN_WORDS = 400
_MAX_WORDS = 900
_MAX_TRIES = 5
_TIMEOUT   = 15


@dataclass
class ArticleData:
    title:        str
    body:         str
    url:          str
    category:     str
    published_at: str


def _word_count(text: str) -> int:
    return len(text.split())


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).strip()


def _fetch_body(url: str) -> str:
    """Fetch page and extract readable text from <p> tags."""
    try:
        resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", resp.text, re.DOTALL)
        body = " ".join(_strip_html(p) for p in paragraphs)
        return re.sub(r"\s+", " ", body).strip()
    except Exception:
        return ""


def fetch_article(category: str) -> ArticleData:
    """Fetch one suitable article from the RSS feed for `category`.

    Raises ValueError if no suitable article found after _MAX_TRIES attempts.
    """
    feed_url = RSS_FEEDS.get(category)
    if not feed_url:
        raise ValueError(f"Unknown category: {category!r}")

    feed = feedparser.parse(feed_url)
    entries = feed.entries[:_MAX_TRIES * 2]

    tried = 0
    for entry in entries:
        if tried >= _MAX_TRIES:
            break
        tried += 1

        url = entry.get("link", "")
        if not url:
            continue

        title = _strip_html(entry.get("title", "")).strip()
        body  = _fetch_body(url)

        wc = _word_count(body)
        if wc < _MIN_WORDS or wc > _MAX_WORDS:
            continue

        published = entry.get("published", "")
        return ArticleData(title=title, body=body, url=url,
                           category=category, published_at=published)

    raise ValueError(f"Không tìm được bài phù hợp trong category '{category}' sau {_MAX_TRIES} lần thử.")
