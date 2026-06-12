# Architecture — Agentic Scraping & Retrieval

This document explains how the PartSelect agent finds information, with a focus
on the **scraping layer**: how it evolved from a fixed-recipe crawler into an
**agentic, self-improving discovery system**, and the best-practices /
scalability seams built into it.

---

## 1. Repository layout

```text
case-study/
├── src/                      # React frontend (Create React App lives at root)
│   ├── components/ pages/ hooks/ utils/ styles/
├── public/                   # static assets (logos, index.html)
├── package.json              # frontend deps + scripts
└── backend/
    ├── main.py               # FastAPI: /chat, /feedback, /metrics
    ├── agent/                # LangGraph agent (router → executor → synthesizer)
    │   └── nodes/executor.py # dispatches intents to tools; agentic on-miss recovery
    ├── tools/                # tool registry (lookup_part, search_rag, discover_and_index, …)
    ├── rag/
    │   ├── pinecone_client.py  # vector upsert/query (batched embeddings)
    │   ├── embeddings.py        # Gemini embeddings (single + batch)
    │   ├── llm.py               # plan / rank / reflect prompts + synthesis
    │   └── self_heal.py         # 3-tier part/model lookup
    └── scraper/
        ├── scraper_backend.py     # ScraperBackend Protocol (swappable) + parallel fetch
        ├── agentic_discovery.py   # PLAN → FETCH → RANK → INDEX → REFLECT/RE-PLAN
        ├── firecrawl_scraper.py   # Firecrawl wrapper + URL grammar + link parsers
        ├── indexer.py             # scrape → extract → chunk → embed → upsert
        ├── scrape_runner.py       # one-time bulk pre-index pipeline
        └── demo_agentic.py        # standalone CLI demo of the agentic engine
```

> **Note on "no frontend folder":** the React app is at the repo root (CRA
> convention) — `src/`, `public/`, and `package.json`. The backend is the only
> nested service (`backend/`).

---

## 2. Retrieval at a glance (what runs for a query)

```text
User message
   │
Router (Gemini Flash + deterministic guards + slot memory)
   │
Executor → tools
   │
Tier 1: Pinecone semantic search ───────────────► good hit? → answer
   │ miss
Tier 2/3: self-heal (direct part URL → site search) ─► found? → answer  [exact PS lookups]
   │ miss (part search + MODEL known)
Agentic discovery (plan → fetch → rank → index → reflect) ─► re-query → answer
   │ still nothing
Clarify (ask for model / refine)
```

Price and stock are **always** re-fetched live (`get_live_price_stock`) — never
trusted from cache.

---

## 3. The scraping evolution (the headline)

### 3.1 Before — *dynamic*, but not *agentic*

The bulk crawler (`scrape_runner.py`) discovers links at runtime, but the
**decisions are hardcoded heuristics**:

```text
seed URL → regex finds links → take the first N (fixed caps) → index
```

It never reasons about *what a particular user needs*. It just grabs whatever N
links a regex matched first.

### 3.2 After — agentic discovery (`scraper/agentic_discovery.py`)

A bounded loop where an **LLM makes the decisions**:

```text
1. PLAN    — LLM picks which page TYPES satisfy the goal, in priority order
             (model? repair? brand? category?) — never raw URLs.
2. FETCH   — resolve targets to concrete URLs via PartSelect's URL grammar,
             then scrape them CONCURRENTLY (one parallel wave).
3. RANK    — regex lists candidate links; the LLM SCORES them by relevance to
             the goal and keeps only the useful ones (not "first N").
4. INDEX   — reuse the existing index_part / index_repair_guide / index_model_cache
             so discovered content is embedded + upserted to Pinecone.
5. REFLECT — if NO part page was indexed and budget remains, the LLM reasons
   /RE-PLAN  about the gap and tries ONE more targeted door.
```

**Nothing is hardcoded to a specific answer URL.** The only fixed knowledge is
PartSelect's URL *grammar* (`/Models/{model}/`, `/PS{n}-Part.htm`,
`/{Brand}-{Appliance}-Parts.htm`) and the two appliance landing pages — the same
structural knowledge a human shopper uses.

### 3.3 What is and isn't hardcoded

| | Hardcoded? | Why |
|---|---|---|
| 2 appliance landing pages + URL grammar | Yes (structural) | Unavoidable entry points; same as a human navigating the site |
| **Which doors to open** | No — LLM plans | Goal-directed |
| **Which discovered links to follow** | No — LLM ranks | Relevance-scored |
| **Whether to try again** | No — LLM reflects | Iterative |

---

## 4. Where the agentic layer connects to live chat

In `executor.py`, on a **part-search miss with a known model number**:

```text
Pinecone miss → _agentic_recover(goal, signals) → discover() → re-query Pinecone
```

Design choices that keep this safe:

- **Model-aware gate** — only runs when a model number is known (model page →
  exact compatible parts). Without a model it would only hit generic pages, so
  it's skipped in favor of asking the user for the model.
- **Flag-gated** — `ENABLE_AGENTIC_DISCOVERY`. Off = byte-for-byte the old path.
- **Strictly additive** — old self-heal + clarify remain as the fallback; the
  agentic layer only ever *adds* vectors to Pinecone.
- **Self-improving** — once indexed, the next identical query is a fast Tier-1
  Pinecone hit (no re-scrape).

---

## 5. Best practices & scalability seams

| Concern | Implementation |
|---|---|
| **Swappable backend** | `ScraperBackend` Protocol (`scraper_backend.py`). Firecrawl is the default impl; Playwright / a test fixture / an internal crawler could replace it with zero engine changes. |
| **Parallel scraping** | `backend.fetch_pages()` fans out independent doors concurrently on a dedicated pool — N scrapes cost ~one scrape of wall-clock. |
| **Batch embeddings** | `generate_embeddings()` embeds a whole page's chunks in one API call instead of 7–14 sequential ones (per-chunk fallback on failure). |
| **Bounded latency** | Per-run budgets: `AGENTIC_MAX_PAGES`, `AGENTIC_MAX_PARTS_INDEXED`, `AGENTIC_TIME_BUDGET_S`, plus a *headroom guard* that never starts a scrape it can't finish in budget. |
| **Graceful degradation** | Every step is wrapped; one bad page/target logs and is skipped, never aborting the run or the request. |
| **Observability** | Each decision emits `AGENT DECISION [...]` (visible in a demo) and a structured `log_event` (pipeline/metrics). |
| **Extensibility** | Adding a new "door type" is localized to URL resolution + one processing branch. |

---

## 6. Latency model

Network scrapes dominate (each PartSelect page ≈ 10–20s via Firecrawl); the LLM
plan/rank/reflect calls are ~1–4s. Mitigations:

- Doors fetched **in parallel** (one wave, not sequential).
- The slow, scraper-hostile `Search.aspx` is **not used** — `search`/`category`
  targets resolve to the reliable parts landing page.
- Budget + headroom guards keep a full discovery run **under ~45–50s**.
- Common queries hit Pinecone at Tier 1 and never trigger discovery (~1–3s).

---

## 7. Configuration (key knobs)

| Setting | Default | Purpose |
|---|---|---|
| `ENABLE_AGENTIC_DISCOVERY` | `True` | Master switch for the live on-miss recovery layer |
| `AGENTIC_MAX_PAGES` | `5` | Max page scrapes per run (cheap — parallel) |
| `AGENTIC_MAX_PARTS_INDEXED` | `5` | Max part pages indexed per run |
| `AGENTIC_TIME_BUDGET_S` | `45.0` | Wall-clock ceiling per run |
| `AGENTIC_REPLAN_MAX_LOOPS` | `1` | Reflect/re-plan attempts |
| `FIRECRAWL_TIMEOUT_S` | `20.0` | Hard per-scrape timeout |
| `SEARCH_RELEVANCE_FLOOR` | `0.66` | Min score for a part hit to surface |

---

## 8. Try it

```bash
# Standalone agentic-discovery demo (prints every AGENT DECISION live)
cd backend
python -m scraper.demo_agentic "ice maker not making ice" \
    --model WRF560SEHZ00 --category refrigerator

# Bulk pre-index (one-time)
python -m scraper.scrape_runner
```
