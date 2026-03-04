import json
import os
import logging
from datetime import datetime
from contextlib import contextmanager

import mysql.connector

logger = logging.getLogger(__name__)


def _get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "home"),
    )


@contextmanager
def get_cursor(commit=False):
    conn = _get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def run_migrations(migrations_dir: str = "migrations"):
    """Execute all .sql files in the migrations directory in sorted order."""
    with get_cursor(commit=True) as cur:
        for filename in sorted(os.listdir(migrations_dir)):
            if not filename.endswith(".sql"):
                continue
            path = os.path.join(migrations_dir, filename)
            logger.info("Running migration: %s", filename)
            with open(path) as f:
                statements = f.read().split(";")
            for stmt in statements:
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)


# --------------- news_articles ---------------

def insert_article(source_name: str, source_url: str, title: str,
                   content: str, topic: str, summary: str | None = None,
                   published_at: datetime | None = None) -> int:
    sql = """
        INSERT INTO news_articles
            (source_name, source_url, title, content, summary, topic, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with get_cursor(commit=True) as cur:
        cur.execute(sql, (source_name, source_url, title, content,
                          summary, topic, published_at))
        return cur.lastrowid


def get_today_articles(topic: str) -> list[dict]:
    sql = """
        SELECT * FROM news_articles
        WHERE topic = %s AND DATE(scraped_at) = CURDATE()
        ORDER BY scraped_at DESC
    """
    with get_cursor() as cur:
        cur.execute(sql, (topic,))
        return cur.fetchall()


def article_exists(source_url: str, title: str) -> bool:
    sql = """
        SELECT 1 FROM news_articles
        WHERE source_url = %s AND title = %s
        LIMIT 1
    """
    with get_cursor() as cur:
        cur.execute(sql, (source_url, title))
        return cur.fetchone() is not None


# --------------- generated_posts ---------------

def insert_post(topic: str, draft_content: str, article_ids: list[int],
                analyzer_model: str) -> int:
    sql = """
        INSERT INTO generated_posts
            (topic, draft_content, article_ids, analyzer_model, status)
        VALUES (%s, %s, %s, %s, 'draft')
    """
    with get_cursor(commit=True) as cur:
        cur.execute(sql, (topic, draft_content, json.dumps(article_ids),
                          analyzer_model))
        return cur.lastrowid


def update_post_review(post_id: int, final_content: str, reviewer_model: str,
                       review_notes: str, review_status: str):
    sql = """
        UPDATE generated_posts
        SET final_content = %s, reviewer_model = %s, review_notes = %s,
            review_status = %s, status = 'reviewed'
        WHERE id = %s
    """
    with get_cursor(commit=True) as cur:
        cur.execute(sql, (final_content, reviewer_model, review_notes,
                          review_status, post_id))


def update_post_published(post_id: int, threads_post_id: str):
    sql = """
        UPDATE generated_posts
        SET threads_post_id = %s, status = 'published', published_at = NOW()
        WHERE id = %s
    """
    with get_cursor(commit=True) as cur:
        cur.execute(sql, (threads_post_id, post_id))


def update_post_failed(post_id: int):
    sql = """
        UPDATE generated_posts SET status = 'failed' WHERE id = %s
    """
    with get_cursor(commit=True) as cur:
        cur.execute(sql, (post_id,))


def get_post(post_id: int) -> dict | None:
    sql = "SELECT * FROM generated_posts WHERE id = %s"
    with get_cursor() as cur:
        cur.execute(sql, (post_id,))
        return cur.fetchone()
