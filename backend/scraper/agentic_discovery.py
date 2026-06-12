"""Agentic discovery — an LLM-planned, relevance-ranked scraper.

WHAT MAKES THIS "AGENTIC" (vs. the existing fixed-recipe crawl)
---------------------------------------------------------------
The existing pipeline (``scrape_runner.py``) is *dynamic* — it discovers links
at runtime — but the DECISIONS are hardcoded heuristics:

    seed URL -> regex finds links -> take the first N (fixed caps) -> index

There is no reasoning about *what* a particular user actually needs. This module
adds that reasoning as a bounded four-step loop:

    1. PLAN   — an LLM looks at the goal + signals and proposes which page
                TYPES to open, in priority order (model? repair? brand? search?).
    2. FETCH  — we turn each planned target into a concrete URL (templates for
                model/search/brand, the category landing for repair) and scrape
                it. Firecrawl stays the backend, behind a swappable interface.
    3. RANK   — regex still lists the candidate links on the page, but an LLM
                SCORES them by relevance to the goal and keeps only the useful
                ones (e.g. ice-maker parts, not "the first 20 links").
    4. INDEX  — we reuse the EXISTING ``index_part`` / ``index_repair_guide`` /
                ``index_model_cache`` functions, so discovered content is
                embedded + upserted into the same Pinecone namespaces. The next
                query is a fast Tier-1 hit (same self-healing behavior we have).

Nothing here is hardcoded to a specific *answer* URL. The only fixed knowledge
is PartSelect's URL *grammar* (model/part/search/brand patterns) and the two
category landing pages — exactly the structural knowledge a human shopper uses.

LATENCY
-------
Network scrapes dominate runtime (the ~1s Flash plan/rank calls are cheap), so
every run is bounded by THREE guardrails from settings: a max page-fetch count,
a max parts-indexed count, and an overall wall-clock budget. The engine checks
the budget BEFORE starting any new scrape and stops early with whatever it has —
so a run can't spiral into a minute-long crawl.

SAFETY / ADDITIVITY
-------------------
This module never mutates existing behavior. It only ADDS vectors to Pinecone
via the same indexers used today. If anything fails, it logs and returns a
partial result; callers fall back to their normal path.
"""

from __future__ import annotations

import re
import time

from config.settings import settings
from observability import log_event
from rag.llm import plan_discovery, rank_links, replan_discovery
from scraper.scraper_backend import ScraperBackend, default_backend
from scraper.firecrawl_scraper import (
    construct_model_url,
    extract_part_urls,
    extract_repair_symptom_urls,
)
from scraper.indexer import index_part, index_repair_guide, index_model_cache


# PartSelect's top-level structure is fixed (Refrigerator vs Dishwasher). This is
# structural knowledge, not a hardcoded answer link.
_APPLIANCE_WORD = {"refrigerator": "Refrigerator", "dishwasher": "Dishwasher"}

# Execution cost order for target types. The LLM decides WHICH doors are
# relevant; this decides the ORDER we actually open them within the latency
# budget. Model/repair/brand pages are deterministic and fast; the PartSelect
# site-search page (used by 'search' and the URL-less 'category' target) is
# heavy and can eat the whole time budget — so it's tried LAST, after the cheap
# doors have had a chance to index something. This preserves the planner's
# relevance choices while spending the budget productively.
_TARGET_COST = {"model": 0, "repair": 1, "brand": 2, "category": 3, "search": 4}


def _slug_label(url: str) -> str:
    """Cheap human-ish label from a part URL slug, for the ranking prompt."""
    m = re.search(r"PS\d+-(.+?)\.htm", url, re.I)
    if not m:
        return url.rsplit("/", 1)[-1]
    return m.group(1).replace("-", " ").strip()


def _part_number_from_url(url: str) -> str:
    m = re.search(r"(PS\d+)", url, re.I)
    return m.group(1).upper() if m else ""


def _brand_parts_url(brand: str, category: str) -> str | None:
    """Construct a brand parts page URL from PartSelect's pattern, e.g.
    /Whirlpool-Refrigerator-Parts.htm. Returns None if we can't (unknown
    category) so the planner's search fallback handles it instead."""
    word = _APPLIANCE_WORD.get(category)
    if not word or not brand:
        return None
    safe = brand.strip().title().replace(" ", "-")
    return f"{settings.PARTSELECT_BASE_URL}/{safe}-{word}-Parts.htm"


class _Budget:
    """Tracks the three latency guardrails for a single discovery run."""

    def __init__(self):
        self.start = time.monotonic()
        self.pages = 0
        self.parts = 0

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def can_fetch_page(self) -> bool:
        if self.pages >= settings.AGENTIC_MAX_PAGES:
            return False
        if self.elapsed >= settings.AGENTIC_TIME_BUDGET_S:
            return False
        # Headroom guard: never START a scrape we can't FINISH inside the budget.
        # A single scrape can run up to FIRECRAWL_TIMEOUT_S, so once the
        # remaining budget is smaller than that, starting another page would
        # blow past the ceiling (the cause of the 44s overshoot). The first page
        # is always allowed so a run never no-ops.
        if self.pages > 0:
            remaining = settings.AGENTIC_TIME_BUDGET_S - self.elapsed
            if remaining < settings.FIRECRAWL_TIMEOUT_S:
                return False
        return True

    def can_index_part(self) -> bool:
        if self.parts >= settings.AGENTIC_MAX_PARTS_INDEXED:
            return False
        # Indexing a part scrapes its page (up to FIRECRAWL_TIMEOUT_S), so apply
        # the same headroom guard as page fetches: never START a part index we
        # can't FINISH inside the budget. This is what kept a run from
        # overshooting the wall-clock ceiling (e.g. starting a 2nd part at ~40s
        # that then ran to ~55s). The first part is always allowed so a run with
        # a known model still returns at least one part.
        if self.parts > 0:
            remaining = settings.AGENTIC_TIME_BUDGET_S - self.elapsed
            if remaining < settings.FIRECRAWL_TIMEOUT_S:
                return False
        return self.elapsed < settings.AGENTIC_TIME_BUDGET_S

    def reason(self) -> str:
        if self.elapsed >= settings.AGENTIC_TIME_BUDGET_S:
            return "time_budget"
        if self.pages >= settings.AGENTIC_MAX_PAGES:
            return "page_budget"
        if self.parts >= settings.AGENTIC_MAX_PARTS_INDEXED:
            return "part_budget"
        return "complete"


def _decide(step: str, detail: str, result: dict):
    """Emit an explicit, greppable 'AGENT DECISION' record.

    Both prints (so it's visible in a live demo terminal) and a structured log
    event (so it shows up in the observability pipeline / LangSmith metadata).
    """
    print(f"  AGENT DECISION [{step}]: {detail}")
    result["steps"].append({"step": step, "detail": detail, "t": round(_now(), 2)})
    log_event("agentic_discovery_step", step=step, detail=detail)


_T0 = time.monotonic()


def _now() -> float:
    return time.monotonic() - _T0


def _index_ranked_parts(
    goal: str,
    markdown: str,
    category: str,
    budget: _Budget,
    result: dict,
    part_type: str = "",
    brand: str = "",
):
    """RANK + INDEX step for any page that lists parts (search, model, brand,
    category). The LLM picks the relevant part links; we index only those."""
    part_urls = extract_part_urls(markdown)
    if not part_urls:
        _decide("rank", "no part links found on page", result)
        return

    remaining = settings.AGENTIC_MAX_PARTS_INDEXED - budget.parts
    candidates = [{"url": u, "label": _slug_label(u)} for u in part_urls]
    ranked = rank_links(goal, candidates, limit=max(1, remaining))
    _decide(
        "rank",
        f"{len(part_urls)} candidate part links -> kept {len(ranked)} most relevant",
        result,
    )

    for url in ranked:
        if not budget.can_index_part():
            _decide("index", f"stopped early ({budget.reason()})", result)
            return
        pn = _part_number_from_url(url)
        try:
            indexed = index_part(url, category or "dishwasher", part_type=part_type, brand=brand)
            budget.parts += 1
            if indexed:
                result["indexed_parts"].append(pn or url)
                _decide("index", f"indexed part {pn or url}", result)
        except Exception as e:  # noqa: BLE001 — never let one bad page abort the run
            _decide("index", f"part index failed for {pn or url}: {e}", result)


def _resolve_target_url(target: dict, signals: dict, category: str) -> str | None:
    """Turn an abstract planner target into ONE concrete door URL (no network).

    Pure URL construction from PartSelect's grammar + the user's signals, so all
    door URLs can be resolved up front and then fetched in parallel. Returns None
    when the target can't be built (e.g. brand door with no brand) — the caller
    skips it.
    """
    ttype = target["type"]
    value = (target.get("value") or "").strip()
    if ttype == "model":
        model = (value or signals.get("model_number") or "").strip()
        return construct_model_url(model) if model else None
    if ttype == "repair":
        return settings.REPAIR_URLS.get(category)
    if ttype == "brand":
        return _brand_parts_url(value or signals.get("brand") or "", category)
    # 'category' and 'search' both resolve to the appliance's parts LANDING page.
    # We deliberately do NOT use PartSelect's Search.aspx: via Firecrawl it
    # reliably hits the scrape timeout (~20s wasted) and leaves abandoned worker
    # threads. The landing page is a real, reliable content page with many part
    # links the ranker can score — a far better broad door. Returns None when the
    # category is unknown so the target is simply skipped.
    if ttype in ("category", "search"):
        return settings.PARTS_URLS.get(category)
    return None


def _process_door(
    target: dict, url: str, markdown: str, goal: str, signals: dict,
    category: str, budget: _Budget, result: dict,
):
    """RANK + INDEX a single already-fetched door page, by target type.

    Door pages are fetched in parallel up front; this is the per-page work that
    follows. Part/guide sub-pages are scraped here (they depend on links found
    on the door), bounded by the part/time budget.
    """
    ttype = target["type"]
    if not markdown:
        _decide("process", f"{ttype}: empty page, skipped", result)
        return

    if ttype == "model":
        model = (target.get("value") or signals.get("model_number") or "").strip()
        try:
            index_model_cache(url, category or "dishwasher", markdown=markdown)
            if model:
                result["models_cached"].append(model.upper())
            _decide("index", f"cached model {model.upper() or '?'}", result)
        except Exception as e:  # noqa: BLE001
            _decide("index", f"model cache failed for {model}: {e}", result)
        _index_ranked_parts(goal, markdown, category, budget, result)

    elif ttype == "repair":
        symptom_urls = extract_repair_symptom_urls(markdown, category)
        if not symptom_urls:
            _decide("rank", "no symptom guides found on landing", result)
            return
        candidates = [
            {"url": u, "label": u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")}
            for u in symptom_urls
        ]
        ranked = rank_links(target.get("value") or goal, candidates, limit=2)
        _decide(
            "rank",
            f"{len(symptom_urls)} symptom guides -> kept {len(ranked)} most relevant",
            result,
        )
        for guide_url in ranked:
            if budget.elapsed >= settings.AGENTIC_TIME_BUDGET_S:
                _decide("index", "stopped early (time_budget)", result)
                return
            try:
                index_repair_guide(guide_url, category)
                result["indexed_repairs"].append(guide_url)
                _decide("index", f"indexed repair guide {guide_url}", result)
            except Exception as e:  # noqa: BLE001
                _decide("index", f"repair index failed for {guide_url}: {e}", result)

    else:  # brand | category | search — all list parts to rank
        brand = (target.get("value") or signals.get("brand") or "") if ttype == "brand" else ""
        _index_ranked_parts(goal, markdown, category, budget, result, brand=brand)


def _run_pass(targets, goal, signals, category, backend, budget, result):
    """Execute one discovery pass over a set of targets.

    SCALABILITY: all door URLs are resolved (pure) then fetched CONCURRENTLY in
    a single wave (``backend.fetch_pages``), so N independent doors cost ~one
    scrape of wall-clock instead of N. Pages are then processed in cost order so
    cheap/precise doors (model, repair) index before the heavy search results.
    """
    # Resolve every target to its deterministic door URL (pure, no network) and
    # dedup — 'category' and 'search' both map to the parts landing page, so the
    # seen-set collapses them to a single fetch.
    resolved: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for t in targets:
        if len(resolved) >= settings.AGENTIC_MAX_PAGES:
            break
        url = _resolve_target_url(t, signals, category)
        if not url or url in seen:
            continue
        seen.add(url)
        resolved.append((t, url))

    if not resolved:
        return
    if not budget.can_fetch_page():
        _decide("stop", f"budget reached before fetch ({budget.reason()})", result)
        return

    # Parallel fetch wave — the core scalability win.
    urls = [u for _, u in resolved]
    _decide("fetch", f"parallel fetch {len(urls)} door(s): " + ", ".join(urls), result)
    pages = backend.fetch_pages(urls)
    budget.pages += len(urls)

    # Process in cost order (model/repair before category/search).
    resolved.sort(key=lambda pair: _TARGET_COST.get(pair[0]["type"], 9))
    for t, url in resolved:
        if budget.elapsed >= settings.AGENTIC_TIME_BUDGET_S:
            _decide("stop", "budget reached during processing (time_budget)", result)
            break
        markdown = (pages.get(url) or {}).get("content", "") or ""
        try:
            _process_door(t, url, markdown, goal, signals, category, budget, result)
        except Exception as e:  # noqa: BLE001
            _decide(t["type"], f"processing failed: {e}", result)


def discover(
    goal: str,
    signals: dict | None = None,
    backend: ScraperBackend | None = None,
) -> dict:
    """Run a bounded, iterative agentic-discovery run for ``goal``.

    ``signals`` is the agent's extracted slot memory (model_number, brand,
    category, part_name, symptom) — used by the planner to choose the best entry
    doors. The run is a PLAN → (parallel) FETCH → RANK → INDEX pass, followed by
    a bounded REFLECT → RE-PLAN loop that tries one more targeted door if the
    first pass found no relevant part and budget remains. Returns a structured
    report of every decision + what was indexed.
    """
    signals = signals or {}
    backend = backend or default_backend
    category = (signals.get("category") or "").strip().lower()

    result = {
        "goal": goal,
        "backend": getattr(backend, "name", "custom"),
        "plan": [],
        "steps": [],
        "indexed_parts": [],
        "indexed_repairs": [],
        "models_cached": [],
        "pages_fetched": 0,
        "replans": 0,
        "elapsed_s": 0.0,
        "stopped_reason": "complete",
    }

    print(f"\n=== AGENTIC DISCOVERY: {goal!r} ===")
    budget = _Budget()

    # STEP 1 — PLAN. The LLM proposes ordered page targets for this goal.
    plan = plan_discovery(goal, signals)
    targets = plan.get("targets", [])
    result["plan"] = targets
    _decide(
        "plan",
        "targets -> " + ", ".join(f"{t['type']}({t.get('value') or ''})" for t in targets),
        result,
    )

    tried_types: list[str] = [t["type"] for t in targets]

    # STEPS 2-4 — first pass: parallel fetch + rank + index.
    _run_pass(targets, goal, signals, category, backend, budget, result)

    # STEP 5 — REFLECT → RE-PLAN. If no relevant PART was indexed and budget
    # remains, reason about the gap and try ONE more targeted door. The headroom
    # guard inside can_fetch_page() ensures a re-plan scrape only starts when it
    # can finish in budget, so total latency stays bounded.
    loops = 0
    while (
        loops < settings.AGENTIC_REPLAN_MAX_LOOPS
        and not result["indexed_parts"]
        and budget.can_fetch_page()
    ):
        found = (
            f"{len(result['indexed_repairs'])} repair guide(s), "
            f"{len(result['models_cached'])} model(s), 0 parts"
        )
        nxt = replan_discovery(goal, signals, tried_types, found)
        if not nxt:
            _decide("replan", "reflection decided to stop (no better door)", result)
            break
        loops += 1
        result["replans"] = loops
        _decide(
            "replan",
            f"attempt {loops}: try {nxt['type']}({nxt.get('value') or ''}) — {nxt.get('reason') or ''}",
            result,
        )
        tried_types.append(nxt["type"])
        _run_pass([nxt], goal, signals, category, backend, budget, result)

    result["pages_fetched"] = budget.pages
    result["elapsed_s"] = round(budget.elapsed, 2)
    result["stopped_reason"] = budget.reason()
    print(
        f"=== DONE in {result['elapsed_s']}s — "
        f"{len(result['indexed_parts'])} parts, "
        f"{len(result['indexed_repairs'])} guides, "
        f"{len(result['models_cached'])} models cached, "
        f"{result['replans']} replan(s) "
        f"({result['stopped_reason']}) ===\n"
    )
    log_event(
        "agentic_discovery_done",
        goal=goal,
        pages=budget.pages,
        parts=len(result["indexed_parts"]),
        repairs=len(result["indexed_repairs"]),
        replans=result["replans"],
        elapsed_s=result["elapsed_s"],
        stopped_reason=result["stopped_reason"],
    )
    return result
