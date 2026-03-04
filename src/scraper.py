import time
import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
import yaml
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


def _extract_articles(soup: BeautifulSoup, source: dict) -> list[Article]:
    selectors = source["selectors"]
    articles = []
    containers = soup.select(selectors["article"])

    for container in containers:
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


def scrape_topic(topic: str, scraper_config: dict,
                 max_per_source: int = 10) -> list[Article]:
    """Scrape all sources for a given topic and store new articles in the DB."""
    sources_cfg = load_sources()
    sources = [s for s in sources_cfg["sources"] if s["topic"] == topic]
    delay = scraper_config.get("delay_between_requests", 2)
    collected = []

    for source in sources:
        logger.info("Scraping %s ...", source["name"])
        soup = _fetch_page(source["url"], scraper_config)
        if not soup:
            continue

        articles = _extract_articles(soup, source)[:max_per_source]

        for art in articles:
            if article_exists(art.source_url, art.title):
                logger.debug("Skipping duplicate: %s", art.title)
                continue

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
