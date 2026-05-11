from __future__ import annotations

import html
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
_MAX_CANDIDATES = _MAX_TRIES * 2


@dataclass
class ArticleData:
    title:        str
    body:         str
    url:          str
    category:     str
    published_at: str


def _word_count(text: str) -> int:
    return len(text.split())


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw).strip()
    text = html.unescape(text)
    return text


def _fetch_body(url: str) -> str:
    """Fetch page and extract readable text from <p> tags."""
    try:
        resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", resp.text, re.DOTALL)
        body = " ".join(_strip_html(p) for p in paragraphs)
        return re.sub(r"\s+", " ", body).strip()
    except (httpx.HTTPError, httpx.TimeoutException):
        return ""


def fetch_article(category: str) -> ArticleData:
    """Fetch one suitable article from the RSS feed for `category`.

    Raises ValueError if no suitable article found after _MAX_TRIES attempts.
    """
    feed_url = RSS_FEEDS.get(category)
    if not feed_url:
        raise ValueError(f"Unknown category: {category!r}")

    try:
        response = httpx.get(feed_url, timeout=_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        feed = feedparser.parse(response.text)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        raise ValueError(f"Failed to fetch RSS feed for category '{category}': {exc}") from exc

    entries = feed.entries[:_MAX_CANDIDATES]

    tried = 0
    for entry in entries:
        if tried >= _MAX_TRIES:
            break

        url = entry.get("link", "")
        if not url:
            continue

        tried += 1

        title = _strip_html(entry.get("title", ""))
        body  = _fetch_body(url)

        wc = _word_count(body)
        if wc < _MIN_WORDS or wc > _MAX_WORDS:
            continue

        published = entry.get("published", "")
        return ArticleData(title=title, body=body, url=url,
                           category=category, published_at=published)

    raise ValueError(f"No suitable article found in category '{category}' after {_MAX_TRIES} attempts.")
