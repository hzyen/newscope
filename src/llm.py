"""
Provider-agnostic LLM client factory.

Supports any OpenAI-compatible API (OpenRouter, Groq, Gemini, etc.)
by configuring base_url and api_key_env per component.
"""

import os
import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"


def create_client(config: dict) -> OpenAI:
    """
    Create an OpenAI-compatible client from config.

    Config keys:
        base_url: API endpoint (default: OpenRouter)
        api_key_env: env var name holding the API key (default: OPENROUTER_API_KEY)
    """
    base_url = config.get("base_url", DEFAULT_BASE_URL)
    api_key_env = config.get("api_key_env", DEFAULT_API_KEY_ENV)
    api_key = os.getenv(api_key_env)

    if not api_key:
        raise ValueError(
            f"API key not found. Set the {api_key_env} environment variable."
        )

    logger.debug("Creating LLM client: base_url=%s, key_env=%s", base_url, api_key_env)
    return OpenAI(base_url=base_url, api_key=api_key)
