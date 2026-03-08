"""
Standalone Threads API client using Meta's Graph API.

Can be imported as a module or used as a CLI tool:
    python -m src.threads_client post --text "Hello Threads!"
    python -m src.threads_client publish --post-id 42
    python -m src.threads_client me
    python -m src.threads_client profile
    python -m src.threads_client recent

    # Legacy (still works):
    python -m src.threads_client --text "Hello from Newscope!"

Threads Publishing Flow:
    1. Create a media container (POST /{user_id}/threads)
    2. Publish the container (POST /{user_id}/threads_publish)
"""

import os
import sys
import time
import json
import logging
import argparse

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://graph.threads.net/v1.0"


class ThreadsClient:
    def __init__(self, access_token: str | None = None,
                 user_id: str | None = None,
                 base_url: str = DEFAULT_BASE_URL):
        self.access_token = access_token or os.getenv("THREADS_ACCESS_TOKEN")
        self.base_url = base_url
        self._user_id = user_id or os.getenv("THREADS_USER_ID")

        if not self.access_token:
            raise ValueError("THREADS_ACCESS_TOKEN is required")

    @property
    def user_id(self) -> str:
        """Lazily resolve user_id — fetches from /me if not configured."""
        if not self._user_id:
            logger.info("THREADS_USER_ID not set, resolving via /me endpoint...")
            me = self.get_me()
            self._user_id = me["id"]
            logger.info("Resolved user ID: %s", self._user_id)
        return self._user_id

    # ------------------------------------------------------------------ core
    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        kwargs.setdefault("params", {})
        kwargs["params"]["access_token"] = self.access_token

        resp = requests.request(method, self._url(path), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------- identity
    def get_me(self) -> dict:
        """Fetch the authenticated user's profile via GET /me.

        Works without a user_id — useful for initial setup / token validation.
        """
        return self._request(
            "GET", "me",
            params={"fields": "id,username,name,threads_profile_picture_url,threads_biography"},
        )

    def get_profile(self) -> dict:
        return self._request(
            "GET", f"{self.user_id}",
            params={"fields": "id,username,name,threads_profile_picture_url,threads_biography"},
        )

    # ------------------------------------------------------------ publishing
    def create_media_container(self, text: str,
                               media_type: str = "TEXT",
                               reply_to: str | None = None) -> str:
        """Step 1: Create a media container and return its ID."""
        data = {
            "media_type": media_type,
            "text": text,
        }
        if reply_to:
            data["reply_to_id"] = reply_to
        result = self._request("POST", f"{self.user_id}/threads", data=data)
        container_id = result["id"]
        logger.info("Created media container: %s", container_id)
        return container_id

    def publish(self, container_id: str,
                poll_interval: float = 2.0,
                max_wait: float = 30.0) -> str:
        """Step 2: Publish a media container. Polls until ready."""
        elapsed = 0.0
        while elapsed < max_wait:
            status = self.get_container_status(container_id)
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(f"Container {container_id} in ERROR state")
            logger.debug("Container status: %s, waiting...", status)
            time.sleep(poll_interval)
            elapsed += poll_interval

        result = self._request(
            "POST", f"{self.user_id}/threads_publish",
            data={"creation_id": container_id},
        )
        post_id = result["id"]
        logger.info("Published post: %s", post_id)
        return post_id

    def get_container_status(self, container_id: str) -> str:
        result = self._request(
            "GET", container_id,
            params={"fields": "status"},
        )
        return result.get("status", "UNKNOWN")

    def create_and_publish(self, text: str,
                           reply_to: str | None = None) -> str:
        """Convenience: create container + publish in one call."""
        container_id = self.create_media_container(text, reply_to=reply_to)
        return self.publish(container_id)

    # --------------------------------------------------------------- reading
    def get_recent_posts(self, limit: int = 10) -> list[dict]:
        result = self._request(
            "GET", f"{self.user_id}/threads",
            params={
                "fields": "id,text,timestamp,media_type,shortcode,is_quote_post",
                "limit": limit,
            },
        )
        return result.get("data", [])

    def get_post(self, post_id: str) -> dict:
        """Get details of a single Threads post."""
        return self._request(
            "GET", post_id,
            params={
                "fields": "id,text,timestamp,media_type,shortcode,is_quote_post,username",
            },
        )

    def get_replies(self, post_id: str) -> list[dict]:
        """Get replies to a specific post."""
        result = self._request(
            "GET", f"{post_id}/replies",
            params={"fields": "id,text,timestamp,username"},
        )
        return result.get("data", [])

    # ------------------------------------------------------------- insights
    def get_post_insights(self, post_id: str) -> list[dict]:
        """Get engagement metrics for a post."""
        result = self._request(
            "GET", f"{post_id}/insights",
            params={"metric": "likes,replies,reposts,quotes,views"},
        )
        return result.get("data", [])

    def get_user_insights(self, metric: str = "views,likes",
                          period: str = "day") -> list[dict]:
        """Get account-level insights."""
        result = self._request(
            "GET", f"{self.user_id}/threads_insights",
            params={"metric": metric, "period": period},
        )
        return result.get("data", [])


# ================================================================= CLI =====

def cmd_post(args):
    """Publish a new text post."""
    client = ThreadsClient()
    if args.dry_run:
        cid = client.create_media_container(args.text)
        print(f"Container created (not published): {cid}")
    else:
        post_id = client.create_and_publish(args.text)
        print(f"Published: {post_id}")


def cmd_publish(args):
    """Publish a generated post from the DB by its ID."""
    from src.db import get_post, update_post_published, update_post_failed

    post = get_post(args.post_id)
    if not post:
        print(f"Error: No generated post found with id={args.post_id}")
        sys.exit(1)

    content = post.get("final_content") or post.get("draft_content")
    if not content:
        print(f"Error: Post #{args.post_id} has no content")
        sys.exit(1)

    status = post.get("status")
    if status == "published" and not args.force:
        print(f"Post #{args.post_id} is already published "
              f"(threads_post_id={post.get('threads_post_id')})")
        print("Use --force to publish again.")
        return

    content_type = "final" if post.get("final_content") else "draft"
    print(f"Post #{args.post_id} [{status}, {content_type}] \u2014 {len(content)} chars:")
    print(f"---\n{content}\n---")

    if args.dry_run:
        print("DRY RUN \u2014 not publishing.")
        return

    client = ThreadsClient()
    try:
        threads_post_id = client.create_and_publish(content)
        update_post_published(args.post_id, threads_post_id)
        print(f"Published to Threads: {threads_post_id}")
    except Exception as e:
        update_post_failed(args.post_id)
        print(f"Failed to publish: {e}")
        raise


def cmd_me(args):
    """Show the authenticated user profile via /me (no user_id needed)."""
    client = ThreadsClient()
    me = client.get_me()
    print(json.dumps(me, indent=2))


def cmd_profile(args):
    """Show profile for the configured user_id."""
    client = ThreadsClient()
    profile = client.get_profile()
    print(json.dumps(profile, indent=2))


def cmd_recent(args):
    """List recent posts."""
    client = ThreadsClient()
    posts = client.get_recent_posts(limit=args.limit)
    for p in posts:
        ts = p.get("timestamp", "")
        text = (p.get("text") or "")[:80]
        print(f"  [{p['id']}] {ts}  {text}")
    print(f"\n{len(posts)} post(s)")


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Legacy support: `--text "..."` without a subcommand \u2192 treat as `post`
    if "--text" in sys.argv and sys.argv[1:] and sys.argv[1].startswith("-"):
        sys.argv.insert(1, "post")

    parser = argparse.ArgumentParser(
        description="Threads API client \u2014 publish, read, and manage Threads posts",
    )
    sub = parser.add_subparsers(dest="command")

    p_post = sub.add_parser("post", help="Publish a text post to Threads")
    p_post.add_argument("--text", required=True, help="Text content to post")
    p_post.add_argument("--dry-run", action="store_true",
                        help="Create container but don't publish")

    p_pub = sub.add_parser("publish",
                           help="Publish a generated post from DB by ID")
    p_pub.add_argument("--post-id", type=int, required=True,
                       help="ID from home.generated_posts table")
    p_pub.add_argument("--dry-run", action="store_true",
                       help="Show post content but don't publish")
    p_pub.add_argument("--force", action="store_true",
                       help="Publish even if already published")

    sub.add_parser("me", help="Show authenticated user profile via /me")
    sub.add_parser("profile", help="Show profile for configured user_id")

    p_recent = sub.add_parser("recent", help="List recent posts")
    p_recent.add_argument("--limit", type=int, default=10,
                          help="Number of posts to fetch (default: 10)")

    args = parser.parse_args()

    commands = {
        "post": cmd_post,
        "publish": cmd_publish,
        "me": cmd_me,
        "profile": cmd_profile,
        "recent": cmd_recent,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
