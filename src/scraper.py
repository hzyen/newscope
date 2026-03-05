import time
import logging
from dataclasses import dataclass
from urllib.parse import urljoin
from datetime import datetime

import requests
import yaml
import feedparser
from bs4 import BeautifulSoup

from src.db import insert_article, article_exists

logger = logging.getLogger(__name__)


@dataclass
class Article:
    source_name: str
    source_url: str
    title: str
    content: str
    topic: str


def load_sources(path: str = "config/sources.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _topic_matches(source_topic: str, query_topic: str) -> bool:
    """Check if a source topic falls under the query topic (prefix match)."""
    return source_topic == query_topic or source_topic.startswith(query_topic + ".")


# --------------- RSS Scraping ---------------

def _scrape_rss(source: dict, max_articles: int) -> list[Article]:
    """Parse an RSS/Atom feed and return articles."""
    feed = feedparser.parse(source["url"])
    if feed.bozo and not feed.entries:
        logger.error("Failed to parse RSS feed %s: %s", source["url"], feed.bozo_exception)
        return []

    articles = []
    for entry in feed.entries[:max_articles]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        if hasattr(summary, "strip"):
            summary = BeautifulSoup(summary, "lxml").get_text(strip=True)

        if not title or not link:
            continue

        articles.append(Article(
            source_name=source["name"],
            source_url=link,
            title=title,
            content=summary[:5000],
            topic=source["topic"],
        ))

    return articles


# --------------- HTML Scraping ---------------

def _fetch_page(url: str, config: dict) -> BeautifulSoup | None:
    headers = {"User-Agent": config.get("user_agent", "Newscope/1.0")}
    timeout = config.get("request_timeout", 15)
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.error("Failed to fetch %s: %s", url, e)
        return None


def _scrape_html(source: dict, config: dict, max_articles: int) -> list[Article]:
    """Scrape articles from an HTML page using CSS selectors."""
    soup = _fetch_page(source["url"], config)
    if not soup:
        return []

    selectors = source["selectors"]
    articles = []
    containers = soup.select(selectors["article"])

    for container in containers[:max_articles]:
        title_el = container.select_one(selectors["title"])
        link_el = container.select_one(selectors["link"])
        summary_el = container.select_one(selectors.get("summary", ""))

        if not title_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        href = link_el.get("href", "")
        url = urljoin(source["url"], href) if href else source["url"]
        content = summary_el.get_text(strip=True) if summary_el else ""

        if not title:
            continue

        articles.append(Article(
            source_name=source["name"],
            source_url=url,
            title=title,
            content=content,
            topic=source["topic"],
        ))

    return articles


# --------------- Full article fetch ---------------

def _scrape_full_article(url: str, config: dict) -> str | None:
    """Attempt to scrape the full article body from its page."""
    soup = _fetch_page(url, config)
    if not soup:
        return None
    article_tag = soup.find("article")
    if article_tag:
        paragraphs = article_tag.find_all("p")
    else:
        paragraphs = soup.select("div.article-body p, div.entry-content p, "
                                 "div.post-content p, div.article__body p")
    if not paragraphs:
        paragraphs = soup.find_all("p")

    text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    return text[:5000] if text else None


# --------------- Main entry point ---------------

def scrape_topic(topic: str, scraper_config: dict,
                 max_per_source: int = 10) -> list[Article]:
    """Scrape all sources matching a topic prefix and store new articles in the DB."""
    sources_cfg = load_sources()
    sources = [s for s in sources_cfg["sources"] if _topic_matches(s["topic"], topic)]
    delay = scraper_config.get("delay_between_requests", 2)
    collected = []

    for source in sources:
        source_type = source.get("type", "rss")
        logger.info("Scraping %s (%s) ...", source["name"], source_type)

        if source_type == "rss":
            articles = _scrape_rss(source, max_per_source)
        else:
            articles = _scrape_html(source, scraper_config, max_per_source)

        for art in articles:
            if article_exists(art.source_url, art.title):
                logger.debug("Skipping duplicate: %s", art.title)
                continue

            if source.get("fetch_full_article", False):
                full_text = _scrape_full_article(art.source_url, scraper_config)
                if full_text:
                    art.content = full_text

            art_id = insert_article(
                source_name=art.source_name,
                source_url=art.source_url,
                title=art.title,
                content=art.content,
                topic=art.topic,
            )
            logger.info("Stored article #%d: %s", art_id, art.title)
            collected.append(art)

        time.sleep(delay)

    logger.info("Scraped %d new articles for topic '%s'", len(collected), topic)
    return collected
