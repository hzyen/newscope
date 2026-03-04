import json
import logging

from src.llm import create_client

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """You are a meticulous post reviewer for a social media account.
You will receive a draft post and the original source articles it was based on.
Your job is to review the post against these criteria:

{criteria}

Respond in JSON with exactly these fields:
{{
    "approved": true/false,
    "revised_post": "the revised post if changes needed, or the original if approved as-is",
    "notes": "brief explanation of your decision and any changes made"
}}

If the post is good, set approved=true and return the original as revised_post.
If it needs changes, set approved=false, fix it in revised_post, and explain in notes.
Always ensure revised_post is under 500 characters.
Respond ONLY with valid JSON, no markdown fences.
"""


def review_post(draft: str, articles: list[dict],
                config: dict) -> dict:
    """
    Review a generated post with a different model.

    Returns:
        {
            "approved": bool,
            "revised_post": str,
            "notes": str,
            "model": str,
        }
    """
    model = config.get("model", "gpt-4o-mini")
    criteria_list = config.get("criteria", [])
    criteria_text = "\n".join(f"- {c}" for c in criteria_list)

    system_prompt = REVIEW_SYSTEM_PROMPT.format(criteria=criteria_text)

    article_summaries = "\n".join(
        f"- [{a['source_name']}] {a['title']}" for a in articles
    )

    user_prompt = (
        f"Draft post to review:\n\"{draft}\"\n\n"
        f"Source articles:\n{article_summaries}"
    )

    client = create_client(config)
    logger.info("Reviewing post with %s ...", model)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=config.get("max_tokens", 512),
        temperature=config.get("temperature", 0.3),
    )

    raw = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Reviewer returned non-JSON, treating as approved: %s", raw)
        result = {"approved": True, "revised_post": draft, "notes": raw}

    result["model"] = model
    review_status = "approved" if result.get("approved") else "revised"
    logger.info("Review result: %s — %s", review_status, result.get("notes", ""))
    return result
