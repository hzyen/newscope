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

```bash
# Run full pipeline for all topics
python -m src.main

# Run a specific topic
python -m src.main --topic ai

# Dry run (no Threads publishing)
python -m src.main --dry-run

# Post to Threads directly
python -m src.threads_client --text "Hello from Newscope!"
```

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
│   ├── threads_client.py # Threads API client
│   └── db.py             # Database layer
├── .env.example
├── requirements.txt
└── README.md
```
