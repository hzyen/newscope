"""
Newscope — main orchestrator.

Pipeline: Scrape -> Store -> Analyze -> Review -> Publish -> Store

Usage:
    python -m src.main                     # run all configured topics
    python -m src.main --topic ai          # run a specific topic
    python -m src.main --dry-run           # skip publishing to Threads
    python -m src.main --migrate           # run DB migrations only
"""

import argparse
import logging
import sys

import yaml
from dotenv import load_dotenv

from src.db import (
    run_migrations, get_today_articles, insert_post,
    update_post_review, update_post_published, update_post_failed,
)
from src.scraper import scrape_topic
from src.analyzer import analyze_articles
from src.reviewer import review_post
from src.threads_client import ThreadsClient

logger = logging.getLogger("newscope")


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_pipeline(topic: str, config: dict, dry_run: bool = False):
    logger.info("=== Pipeline start: topic='%s' ===", topic)

    # Step 1: Scrape
    logger.info("[1/5] Scraping news...")
    scraper_cfg = config.get("scraper", {})
    max_per_source = scraper_cfg.get("max_articles_per_source", 10)
    scrape_topic(topic, scraper_cfg, max_per_source)

    # Step 2: Load today's articles from DB
    articles = get_today_articles(topic)
    if not articles:
        logger.warning("No articles found for topic '%s', skipping.", topic)
        return

    logger.info("[2/5] Loaded %d articles for analysis.", len(articles))

    # Step 3: Analyze with critic model
    logger.info("[3/5] Analyzing with LLM critic...")
    analyzer_cfg = config.get("analyzer", {})
    draft_post, analyzer_model = analyze_articles(articles, analyzer_cfg)

    article_ids = [a["id"] for a in articles]
    post_id = insert_post(topic, draft_post, article_ids, analyzer_model)
    logger.info("Saved draft post #%d", post_id)

    # Step 4: Review with a different model
    logger.info("[4/5] Reviewing post...")
    reviewer_cfg = config.get("reviewer", {})
    review = review_post(draft_post, articles, reviewer_cfg)

    final_content = review["revised_post"]
    review_status = "approved" if review["approved"] else "revised"
    update_post_review(
        post_id, final_content, review["model"],
        review["notes"], review_status,
    )

    if review_status == "revised":
        logger.info("Post was revised by reviewer.")

    # Step 5: Publish to Threads
    if dry_run:
        logger.info("[5/5] DRY RUN — skipping Threads publish.")
        logger.info("Final post:\n%s", final_content)
        return

    logger.info("[5/5] Publishing to Threads...")
    try:
        client = ThreadsClient()
        threads_post_id = client.create_and_publish(final_content)
        update_post_published(post_id, threads_post_id)
        logger.info("Published to Threads: %s", threads_post_id)
    except Exception as e:
        update_post_failed(post_id)
        logger.error("Failed to publish to Threads: %s", e)
        raise

    logger.info("=== Pipeline complete: topic='%s' ===", topic)


def main():
    parser = argparse.ArgumentParser(description="Newscope — news analysis pipeline")
    parser.add_argument("--topic", help="Run pipeline for a specific topic")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run pipeline without publishing to Threads")
    parser.add_argument("--migrate", action="store_true",
                        help="Run database migrations and exit")
    parser.add_argument("--config", default="config/config.yaml",
                        help="Path to config file")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = load_config(args.config)

    if args.migrate:
        logger.info("Running migrations...")
        run_migrations()
        logger.info("Migrations complete.")
        sys.exit(0)

    # Determine which topics to run
    if args.topic:
        topics = [args.topic]
    else:
        from src.scraper import load_sources
        sources_cfg = load_sources()
        topics = sources_cfg.get("topics", [])

    if not topics:
        logger.error("No topics configured. Check config/sources.yaml")
        sys.exit(1)

    for topic in topics:
        try:
            run_pipeline(topic, config, dry_run=args.dry_run)
        except Exception as e:
            logger.error("Pipeline failed for topic '%s': %s", topic, e)
            continue


if __name__ == "__main__":
    main()
