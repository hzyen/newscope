"""
Standalone Threads API client using Meta's Graph API.

Can be imported as a module or used as a CLI tool:
    python -m src.threads_client post --text "Hello Threads!"
    python -m src.threads_client publish --post-id 42
    python -m src.threads_client me
    python -m src.threads_client profile
    python -m src.threads_client recent
    python -m src.threads_client auth              # one-time OAuth setup
    python -m src.threads_client refresh-token     # refresh long-lived token (cron this)

    # Legacy (still works):
    python -m src.threads_client --text "Hello from Newscope!"

Threads Publishing Flow:
    1. Create a media container (POST /{user_id}/threads)
    2. Publish the container (POST /{user_id}/threads_publish)

Token Lifecycle (automated after first auth):
    1. [manual]  Browser auth → authorization code
    2. [auto]    Code → short-lived token (~1h)
    3. [auto]    Short-lived → long-lived token (~60 days)
    4. [auto]    Refresh long-lived token before expiry (cron every ~50 days)
"""

import os
import sys
import time
import json
import logging
import argparse
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv, set_key

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://graph.threads.net/v1.0"
OAUTH_BASE_URL = "https://threads.net"
GRAPH_BASE_URL = "https://graph.threads.net"

DEFAULT_SCOPES = (
    "threads_basic,"
    "threads_content_publish,"
    "threads_manage_insights,"
    "threads_manage_replies,"
    "threads_read_replies"
)


def _find_env_file() -> Path:
    """Walk up from cwd to find .env file."""
    candidate = Path.cwd()
    for _ in range(5):
        env_path = candidate / ".env"
        if env_path.exists():
            return env_path
        candidate = candidate.parent
    return Path.cwd() / ".env"


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

    # ------------------------------------------------------------- OAuth/token
    @staticmethod
    def get_auth_url(app_id: str | None = None,
                     redirect_uri: str = "https://localhost/callback",
                     scopes: str = DEFAULT_SCOPES) -> str:
        """Build the browser URL for the one-time OAuth authorization."""
        app_id = app_id or os.getenv("THREADS_APP_ID")
        if not app_id:
            raise ValueError("THREADS_APP_ID is required")
        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "response_type": "code",
        }
        return f"{OAUTH_BASE_URL}/oauth/authorize?{urlencode(params)}"

    @staticmethod
    def exchange_code(code: str,
                      redirect_uri: str = "https://localhost/callback",
                      app_id: str | None = None,
                      app_secret: str | None = None) -> dict:
        """Exchange an authorization code for a short-lived access token (~1h)."""
        app_id = app_id or os.getenv("THREADS_APP_ID")
        app_secret = app_secret or os.getenv("THREADS_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("THREADS_APP_ID and THREADS_APP_SECRET are required")

        resp = requests.post(
            f"{GRAPH_BASE_URL}/oauth/access_token",
            data={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def exchange_for_long_lived(short_lived_token: str,
                                app_secret: str | None = None) -> dict:
        """Exchange a short-lived token for a long-lived token (~60 days).

        Returns dict with 'access_token', 'token_type', 'expires_in'.
        """
        app_secret = app_secret or os.getenv("THREADS_APP_SECRET")
        if not app_secret:
            raise ValueError("THREADS_APP_SECRET is required")

        resp = requests.get(
            f"{GRAPH_BASE_URL}/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": app_secret,
                "access_token": short_lived_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def refresh_long_lived_token(token: str | None = None) -> dict:
        """Refresh a long-lived token — returns a new one valid for ~60 days.

        Must be called before the current token expires.
        Returns dict with 'access_token', 'token_type', 'expires_in'.
        """
        token = token or os.getenv("THREADS_ACCESS_TOKEN")
        if not token:
            raise ValueError("No token to refresh")

        resp = requests.get(
            f"{GRAPH_BASE_URL}/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def save_token_to_env(token: str, env_path: str | Path | None = None):
        """Persist a new token to the .env file."""
        env_path = str(env_path or _find_env_file())
        set_key(env_path, "THREADS_ACCESS_TOKEN", token)
        logger.info("Token saved to %s", env_path)

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


def cmd_auth(args):
    """Interactive one-time OAuth setup: browser auth \u2192 long-lived token \u2192 .env."""
    redirect_uri = args.redirect_uri

    print("=== Threads OAuth Setup ===\n")
    auth_url = ThreadsClient.get_auth_url(redirect_uri=redirect_uri)
    print(f"1. Open this URL in your browser:\n\n   {auth_url}\n")
    print(f"2. Authorize the app, then copy the 'code' parameter from the redirect URL.")
    print(f"   (The redirect will go to {redirect_uri}?code=XXXXXX#_)\n")

    code = input("Paste the authorization code here: ").strip().rstrip("#_")
    if not code:
        print("No code provided, aborting.")
        sys.exit(1)

    print("\nExchanging code for short-lived token...")
    short_lived = ThreadsClient.exchange_code(code, redirect_uri=redirect_uri)
    sl_token = short_lived["access_token"]
    print(f"  Short-lived token obtained (expires in {short_lived.get('expires_in', '?')}s)")

    print("Exchanging for long-lived token...")
    long_lived = ThreadsClient.exchange_for_long_lived(sl_token)
    ll_token = long_lived["access_token"]
    expires_days = long_lived.get("expires_in", 0) // 86400
    print(f"  Long-lived token obtained (expires in ~{expires_days} days)")

    client = ThreadsClient(access_token=ll_token)
    me = client.get_me()
    user_id = me["id"]
    username = me.get("username", "unknown")
    print(f"  Authenticated as: @{username} (ID: {user_id})")

    if not args.no_save:
        env_path = _find_env_file()
        ThreadsClient.save_token_to_env(ll_token, env_path)
        set_key(str(env_path), "THREADS_USER_ID", user_id)
        print(f"\n  Saved THREADS_ACCESS_TOKEN and THREADS_USER_ID to {env_path}")

    print("\nDone! Set up a cron to keep the token alive:")
    print("  0 0 1,15 * * cd /path/to/newscope && python -m src.threads_client refresh-token")


def cmd_refresh_token(args):
    """Refresh the long-lived token and save to .env. Designed for cron."""
    current_token = os.getenv("THREADS_ACCESS_TOKEN")
    if not current_token:
        print("Error: THREADS_ACCESS_TOKEN not set")
        sys.exit(1)

    print("Refreshing long-lived token...")
    result = ThreadsClient.refresh_long_lived_token(current_token)
    new_token = result["access_token"]
    expires_days = result.get("expires_in", 0) // 86400
    print(f"  New token obtained (expires in ~{expires_days} days)")

    client = ThreadsClient(access_token=new_token)
    me = client.get_me()
    print(f"  Token valid for: @{me.get('username', '?')} (ID: {me['id']})")

    if not args.no_save:
        env_path = _find_env_file()
        ThreadsClient.save_token_to_env(new_token, env_path)
        print(f"  Saved to {env_path}")

    print("Done.")


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

    p_auth = sub.add_parser("auth",
                            help="One-time OAuth setup (browser \u2192 long-lived token)")
    p_auth.add_argument("--redirect-uri", default="https://localhost/callback",
                        help="OAuth redirect URI (must match app settings)")
    p_auth.add_argument("--no-save", action="store_true",
                        help="Don't save token to .env (print only)")

    p_refresh = sub.add_parser("refresh-token",
                               help="Refresh long-lived token (cron this)")
    p_refresh.add_argument("--no-save", action="store_true",
                           help="Don't save token to .env (print only)")

    args = parser.parse_args()

    commands = {
        "post": cmd_post,
        "publish": cmd_publish,
        "me": cmd_me,
        "profile": cmd_profile,
        "recent": cmd_recent,
        "auth": cmd_auth,
        "refresh-token": cmd_refresh_token,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
