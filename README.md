# Newscope

Automated news pipeline that scrapes multi-source news, analyzes it with an opinionated AI critic, reviews the output with a second model, and publishes to Threads.

## Pipeline

```
Cron -> Scrape -> Store -> Analyze (Critic) -> Review (QA) -> Publish -> Store
```

## Setup

```bash
# Clone & install
git clone https://github.com/hzyen/newscope.git
cd newscope
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys and DB credentials

# Run DB migrations
python -m src.main --migrate

# Edit config/sources.yaml to add your news sources and topics
```

## Usage

### Full Pipeline

```bash
# Run full pipeline for all topics
python -m src.main

# Run a specific topic
python -m src.main --topic ai

# Dry run (no Threads publishing)
python -m src.main --dry-run
```

### Threads Client CLI

The Threads client can be used standalone to manage posts:

```bash
# Post text directly to Threads
python -m src.threads_client post --text "Hello from Newscope!"

# Publish a generated post from the database by its ID
python -m src.threads_client publish --post-id 42

# Preview a generated post without publishing
python -m src.threads_client publish --post-id 42 --dry-run

# Re-publish an already-published post
python -m src.threads_client publish --post-id 42 --force

# Show your Threads profile (auto-resolves user ID via /me)
python -m src.threads_client me

# Show profile for the configured THREADS_USER_ID
python -m src.threads_client profile

# List recent posts
python -m src.threads_client recent --limit 20
```

`THREADS_USER_ID` is optional — if not set in `.env`, the client automatically resolves it via the `/me` API endpoint using your access token.

### ThreadsClient API

When imported as a module, `ThreadsClient` provides:

| Method | Description |
|---|---|
| `get_me()` | Fetch authenticated user profile via `/me` (no user_id needed) |
| `get_profile()` | Fetch profile by configured user_id |
| `create_and_publish(text)` | Create a media container and publish in one call |
| `create_media_container(text, reply_to=...)` | Create a container (supports replies) |
| `publish(container_id)` | Publish a container, polling until ready |
| `get_recent_posts(limit)` | List recent Threads posts |
| `get_post(post_id)` | Get a single post's details |
| `get_replies(post_id)` | Get replies to a post |
| `get_post_insights(post_id)` | Get engagement metrics (likes, replies, reposts, quotes, views) |
| `get_user_insights()` | Get account-level insights |

## Switching Topics

Edit `config/sources.yaml` to add new sources and topics. The pipeline is topic-agnostic — just define your sources with CSS selectors and a topic tag.

## Cron Setup

```bash
# Run daily at 9am
0 9 * * * cd /path/to/newscope && /path/to/python -m src.main >> /var/log/newscope.log 2>&1
```

## Project Structure

```
newscope/
├── config/
│   ├── config.yaml       # Main configuration
│   └── sources.yaml      # News sources & topics
├── migrations/
│   └── 001_init.sql      # Database schema
├── src/
│   ├── main.py           # Pipeline orchestrator
│   ├── scraper.py        # Web scraper
│   ├── analyzer.py       # LLM critic analyzer
│   ├── reviewer.py       # LLM post reviewer
│   ├── threads_client.py # Threads API client & CLI
│   ├── llm.py            # Provider-agnostic LLM client factory
│   └── db.py             # Database layer
├── .env.example
├── requirements.txt
└── README.md
```
