"""
Standalone Threads API client using Meta's Graph API.

Can be imported as a module or used as a CLI tool:
    python -m src.threads_client --text "Hello Threads!"

Threads Publishing Flow:
    1. Create a media container (POST /{user_id}/threads)
    2. Publish the container (POST /{user_id}/threads_publish)
"""

import os
import time
import logging
import argparse

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://graph.threads.net/v1.0"


class ThreadsClient:
    def __init__(self, access_token: str | None = None,
                 user_id: str | None = None,
                 base_url: str = DEFAULT_BASE_URL):
        self.access_token = access_token or os.getenv("THREADS_ACCESS_TOKEN")
        self.user_id = user_id or os.getenv("THREADS_USER_ID")
        self.base_url = base_url

        if not self.access_token:
            raise ValueError("THREADS_ACCESS_TOKEN is required")
        if not self.user_id:
            raise ValueError("THREADS_USER_ID is required")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        kwargs.setdefault("params", {})
        kwargs["params"]["access_token"] = self.access_token

        resp = requests.request(method, self._url(path), timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def create_media_container(self, text: str,
                               media_type: str = "TEXT") -> str:
        """Step 1: Create a media container and return its ID."""
        data = {
            "media_type": media_type,
            "text": text,
        }
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

    def create_and_publish(self, text: str) -> str:
        """Convenience: create container + publish in one call."""
        container_id = self.create_media_container(text)
        return self.publish(container_id)

    def get_profile(self) -> dict:
        return self._request(
            "GET", f"{self.user_id}",
            params={"fields": "id,username,threads_profile_picture_url"},
        )

    def get_recent_posts(self, limit: int = 10) -> list[dict]:
        result = self._request(
            "GET", f"{self.user_id}/threads",
            params={"fields": "id,text,timestamp", "limit": limit},
        )
        return result.get("data", [])


# --- CLI entry point ---

def main():
    parser = argparse.ArgumentParser(description="Publish a text post to Threads")
    parser.add_argument("--text", required=True, help="Text content to post")
    parser.add_argument("--dry-run", action="store_true",
                        help="Create container but don't publish")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    client = ThreadsClient()

    if args.dry_run:
        cid = client.create_media_container(args.text)
        print(f"Container created (not published): {cid}")
    else:
        post_id = client.create_and_publish(args.text)
        print(f"Published: {post_id}")


if __name__ == "__main__":
    main()
