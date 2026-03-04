import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """{persona}

Your task:
1. Read the articles below from different news sources about the same topic.
2. Identify the key narrative each source is pushing — who's spinning what and why.
3. Point out contradictions, omissions, and biases across sources.
4. Deliver YOUR OWN bold, critical take on what's actually going on.
5. Write a punchy social media post (under 500 characters) that a smart reader
   would want to share. Be opinionated. Be sharp. Don't hedge.

Rules:
- Under 500 characters total (this is for Threads).
- No generic filler like "In today's news..." or "It's interesting that...".
- Max 3 hashtags at the end if relevant.
- Write as a single paragraph — no bullet points.
"""


def _build_articles_prompt(articles: list[dict]) -> str:
    parts = []
    for i, art in enumerate(articles, 1):
        parts.append(
            f"--- Article {i} ---\n"
            f"Source: {art['source_name']}\n"
            f"Title: {art['title']}\n"
            f"Content: {art['content'][:2000]}\n"
        )
    return "\n".join(parts)


def analyze_articles(articles: list[dict], config: dict) -> tuple[str, str]:
    """
    Analyze articles with an opinionated critic persona.

    Returns:
        (generated_post, model_used)
    """
    if not articles:
        raise ValueError("No articles to analyze")

    model = config.get("model", "gpt-4o")
    persona = config.get("persona", "You are a sharp, opinionated news critic.")

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(persona=persona)
    user_prompt = (
        f"Topic: {articles[0]['topic']}\n\n"
        f"Here are {len(articles)} articles from different sources:\n\n"
        f"{_build_articles_prompt(articles)}\n"
        "Now write your critical take as a Threads post."
    )

    client = OpenAI()
    logger.info("Analyzing %d articles with %s ...", len(articles), model)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=config.get("max_tokens", 1024),
        temperature=config.get("temperature", 0.8),
    )

    post = response.choices[0].message.content.strip()
    logger.info("Generated post (%d chars): %s", len(post), post[:100])
    return post, model
