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

### Threads Token Setup

The Threads API uses OAuth 2.0. You need to authorize once in a browser, then the token can be refreshed automatically forever.

```bash
# One-time: interactive OAuth setup (opens browser, saves long-lived token to .env)
python -m src.threads_client auth

# Refresh the token before it expires (~60 days). Cron this!
python -m src.threads_client refresh-token

# Refresh without saving to .env (print only)
python -m src.threads_client refresh-token --no-save
```

The `auth` command walks you through the full flow:
1. Prints a URL to open in your browser
2. You authorize and paste back the code
3. Exchanges code → short-lived token → long-lived token
4. Saves `THREADS_ACCESS_TOKEN` and `THREADS_USER_ID` to `.env`

After the initial setup, schedule `refresh-token` to run every ~50 days to keep the token alive indefinitely.

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
| `get_auth_url()` | Build the OAuth authorization URL (static) |
| `exchange_code(code)` | Exchange auth code for short-lived token (static) |
| `exchange_for_long_lived(token)` | Convert short-lived → long-lived token (static) |
| `refresh_long_lived_token()` | Refresh a long-lived token for another ~60 days (static) |
| `save_token_to_env(token)` | Persist token to `.env` file (static) |

## Switching Topics

Edit `config/sources.yaml` to add new sources and topics. The pipeline is topic-agnostic — just define your sources with CSS selectors and a topic tag.

## Cron Setup

```bash
# Run pipeline daily at 9am
0 9 * * * cd /path/to/newscope && /path/to/python -m src.main >> /var/log/newscope.log 2>&1

# Refresh Threads token on the 1st and 15th of each month
0 0 1,15 * * cd /path/to/newscope && /path/to/python -m src.threads_client refresh-token >> /var/log/newscope-token.log 2>&1
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
