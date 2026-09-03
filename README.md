# sumnews

Gather, summarize, tag and store news about a tracked company.

- **Loads** news on a schedule from RSS feeds and Telegram channels.
- **Filters** to relevant items — keyword prefilter, then an optional LLM relevance check.
- **Extracts** a summary, a category (Regulation / Reputation / Competitors / Trends) and a
  priority (high / medium / low) via a LangChain structured-output chain.
- **Stores** the result in Postgres.
- **Serves** a web feed/dashboard (FastAPI + Jinja) for review, editing and notes.

See `.claude/plans/sumnews-mvp.md` for the implementation plan.

## Setup

```bash
uv sync
cp .env.example .env            # fill in DATABASE_URL, LLM_*, TELEGRAM_*
cp watchlist.example.yaml watchlist.yaml
docker compose up -d db         # local Postgres for dev
make db-init
```

## Commands

```bash
make lint            # ruff
make lint-typecheck  # mypy
make test            # pytest
make run-ingest      # one manual ingestion pass
make run-extract     # run the extraction chain on ad-hoc text
make run-bench       # extraction/keyword-filter accuracy report
make run-web         # uvicorn dev server
```
