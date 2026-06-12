# PartSelect AI Chat Agent

An agentic chat assistant for **Refrigerator** and **Dishwasher** parts, built on
PartSelect data. It helps users find parts, diagnose problems, follow repair
guides, check compatibility with their model, and get to the right place to order
or return.

For a deep dive on the scraping/retrieval design, see **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

## Architecture

- **Frontend:** React + Tailwind + React Router (landing page + chat). The app
  lives at the repo root (Create React App): `src/`, `public/`, `package.json`.
- **Backend:** FastAPI + LangGraph agent, Pinecone RAG, Firecrawl scraping,
  Gemini for embeddings + structured extraction + synthesis.
- **Agent:** a 3-layer router (deterministic guards → Gemini Flash NLU →
  conversation slot memory) → executor (dispatches tools) → synthesizer.

```text
case-study/
├── src/        public/   package.json     # React frontend (CRA at root)
└── backend/
    ├── main.py                            # FastAPI: /chat, /feedback, /metrics
    ├── agent/                             # LangGraph: router → executor → synthesizer
    ├── tools/                             # tool registry
    ├── rag/                               # Pinecone, embeddings, LLM, self-heal
    ├── scraper/                           # Firecrawl + agentic discovery + indexer
    ├── observability/                     # structured logs + metrics
    └── evals/                             # RAGAS evaluation harness
```

## Retrieval (multi-tier, self-healing)

1. **Pinecone** — pre-indexed parts + repair guides (semantic search).
2. **Self-heal** — on a miss for an exact `PS` number: construct the canonical
   part URL → scrape → upsert; falls back to PartSelect search.
3. **Agentic discovery** — on a part-search miss *with a known model number*: an
   LLM **plans** which pages to open, scrapes them **in parallel**, **ranks**
   discovered links by relevance, **indexes** the best ones, and **reflects /
   re-plans** once if no part was found. Strictly additive and flag-gated
   (`ENABLE_AGENTIC_DISCOVERY`). See [ARCHITECTURE.md](./ARCHITECTURE.md).

**Live data:** price and stock are always fetched live — never trusted from cache.

## Agentic scraping (highlights)

- LLM-driven **plan → fetch → rank → index → reflect/re-plan** loop, not a fixed
  regex + "first N" crawl.
- **Swappable backend** via a `ScraperBackend` Protocol (Firecrawl is the default
  impl; can be replaced without touching the engine).
- **Scales in code:** parallel page fetches + batch embeddings.
- **Bounded latency:** page/part/time budgets + a headroom guard keep a full
  discovery run under ~45–50s; common queries hit Pinecone at ~1–3s.
- **Observable:** every decision logs an `AGENT DECISION [...]` line.

```bash
# Watch the agent plan/rank/reflect live:
cd backend
python -m scraper.demo_agentic "ice maker not making ice" \
    --model WRF560SEHZ00 --category refrigerator
```

## Order placement, status & returns — redirect by design

The agent **does not place orders, scrape order status, or process returns**.
Instead it returns a direct PartSelect link:

- **Ordering a part** → product URL with an "Order on PartSelect →" button.
- **Order status** → `https://www.partselect.com/user/orders/`.
- **Returns** → the 365-day returns page.

This is **intentional**: transactions and order tracking happen on the real
PartSelect platform for **security and accuracy**. The agent never collects
payment info, credentials, or personal data. See `backend/guardrails/nemo_gateway.py`.

## Observability & feedback

- **Structured logging + metrics** (`backend/observability/`): per-request id,
  timing, LLM-call usage, in-process counters exposed at `GET /metrics`.
- **LangSmith tracing** (when `LANGSMITH_API_KEY` is set): full per-node traces;
  the `/chat` response returns a `trace_id`.
- **User feedback loop:** 👍/👎 buttons on each answer (`POST /feedback`) log to
  metrics and attach feedback to the LangSmith trace.

## Evaluation (RAGAS)

A RAGAS harness (`backend/evals/`) scores the RAG pipeline (faithfulness, answer
relevancy, context precision/recall) using Gemini as the judge.

```bash
cd backend
pip install -r evals/requirements-evals.txt
python -m evals.ragas_tests          # results saved under evals/results/
```

## Backend setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env .env   # GEMINI / PINECONE / FIRECRAWL / (optional) LANGSMITH keys

# One-time crawl + index (parts + repair guides; brand/model links → data/catalog.json)
python -m scraper.scrape_runner

# Run the API (LangGraph agent on POST /chat)
uvicorn main:app --reload --port 8000
```

## Frontend setup

```bash
npm install
npm start   # http://localhost:3000
```

## Key configuration

| Setting | Default | Purpose |
|---|---|---|
| `ENABLE_AGENTIC_DISCOVERY` | `True` | Live on-miss agentic recovery layer |
| `AGENTIC_TIME_BUDGET_S` | `45.0` | Wall-clock ceiling per discovery run |
| `AGENTIC_REPLAN_MAX_LOOPS` | `1` | Reflect/re-plan attempts |
| `FIRECRAWL_TIMEOUT_S` | `20.0` | Hard per-scrape timeout |
| `SEARCH_RELEVANCE_FLOOR` | `0.66` | Min score for a part hit to surface |
| `LLM_FAST_MODEL` / `LLM_REASONING_MODEL` | Gemini Flash / Pro | Two-tier LLM setup |
