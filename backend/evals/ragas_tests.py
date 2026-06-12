"""RAGAS evaluation of the PartSelect RAG pipeline.

Measures the quality of retrieval + answer generation over a curated set of
Refrigerator/Dishwasher queries (see ``evals/dataset.py``) using four metrics:

- **faithfulness**        — is the answer grounded in the retrieved context
                            (no hallucinations)?
- **answer_relevancy**    — does the answer actually address the question?
- **context_precision**   — are the retrieved chunks relevant (low noise)?
- **context_recall**      — did retrieval surface the info in the reference?

The judge LLM + embeddings are **Gemini** (reusing this project's key), not
OpenAI, so no extra credentials are needed.

This is an OFFLINE eval: it makes real Pinecone + Gemini calls and is meant to
be run manually or in CI — never on live request traffic.

Setup (use a separate venv to avoid disturbing the app's pinned deps):

    python -m venv .venv-evals && source .venv-evals/bin/activate
    pip install -r evals/requirements-evals.txt

Run (from the ``backend`` directory):

    python -m evals.ragas_tests --subset smoke     # 3 cases, quick/cheap
    python -m evals.ragas_tests --subset all        # full curated set
    python -m evals.ragas_tests --subset repair     # only repair-guide cases
    python -m evals.ragas_tests --subset parts      # only part-lookup cases

Results print as a table and are written to ``evals/results/<timestamp>.json``.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.settings import settings
from rag.pinecone_client import query_index
from rag.llm import synthesize_answer
from evals.dataset import cases, EvalCase


# --------------------------------------------------------------------------- #
# Pipeline harness: mirror the agent's retrieve -> synthesize path per case.
# --------------------------------------------------------------------------- #
def _retrieve_contexts(case: EvalCase, top_k: int) -> list[str]:
    """Retrieve the same context chunks the agent would for this query."""
    hits = query_index(case.question, namespace=case.namespace, top_k=top_k)
    texts = [(h.get("text") or "").strip() for h in hits]
    return [t for t in texts if t]


def _build_sample(case: EvalCase, top_k: int) -> dict:
    """Run retrieval + synthesis and return a RAGAS-shaped sample dict."""
    contexts = _retrieve_contexts(case, top_k)
    context_blob = "\n\n".join(contexts)
    answer = synthesize_answer(case.question, case.intent, context_blob) or (
        "I don't have a specific guide for that yet — please check PartSelect "
        "for your model."
    )
    return {
        "user_input": case.question,
        "retrieved_contexts": contexts,
        "response": answer,
        "reference": case.reference,
    }


# --------------------------------------------------------------------------- #
# Gemini judge wiring (RAGAS defaults to OpenAI; we override with Gemini).
# --------------------------------------------------------------------------- #
def _build_evaluator():
    """Return (llm, embeddings) RAGAS wrappers backed by Gemini."""
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    api_key = (settings.GEMINI_API_KEY or "").strip()
    # ChatGoogleGenerativeAI expects a bare model id (no "models/" prefix).
    chat_model = settings.LLM_FAST_MODEL.replace("models/", "")

    llm = ChatGoogleGenerativeAI(model=chat_model, google_api_key=api_key, temperature=0.0)
    embeddings = GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL, google_api_key=api_key
    )
    return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(embeddings)


def _build_metrics(evaluator_llm, evaluator_embeddings):
    from ragas.metrics import (
        Faithfulness,
        ResponseRelevancy,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )

    return [
        Faithfulness(llm=evaluator_llm),
        ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        LLMContextPrecisionWithReference(llm=evaluator_llm),
        LLMContextRecall(llm=evaluator_llm),
    ]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def run(subset: str = "all", top_k: int | None = None) -> dict:
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import SingleTurnSample

    top_k = top_k or settings.RAG_TOP_K
    selected = cases(subset)
    print(f"Building {len(selected)} samples (retrieve top_k={top_k} + synthesize)…")

    samples = []
    for i, case in enumerate(selected, 1):
        s = _build_sample(case, top_k)
        n_ctx = len(s["retrieved_contexts"])
        print(f"  [{i}/{len(selected)}] {case.question[:48]:<48} ctx={n_ctx}")
        samples.append(SingleTurnSample(**s))

    dataset = EvaluationDataset(samples=samples)
    evaluator_llm, evaluator_embeddings = _build_evaluator()
    metrics = _build_metrics(evaluator_llm, evaluator_embeddings)

    print("Scoring with RAGAS (Gemini judge)… this makes LLM calls per metric.")
    result = evaluate(dataset=dataset, metrics=metrics)

    scores = {k: round(float(v), 4) for k, v in result._repr_dict.items()} \
        if hasattr(result, "_repr_dict") else dict(result)

    try:
        per_sample = result.to_pandas().to_dict(orient="records")
    except Exception:
        per_sample = [
            {
                "user_input": s.user_input,
                "n_contexts": len(s.retrieved_contexts),
                "response": s.response,
            }
            for s in samples
        ]

    _print_scores(scores)
    _save_results(subset, top_k, scores, per_sample)
    return scores


def _print_scores(scores: dict) -> None:
    print("\n=== RAGAS scores (0.0–1.0, higher is better) ===")
    width = max((len(k) for k in scores), default=12)
    for name, value in scores.items():
        print(f"  {name:<{width}} : {value}")
    print()


def _save_results(subset, top_k, scores, per_sample) -> None:
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "timestamp": ts,
        "subset": subset,
        "top_k": top_k,
        "judge_model": settings.LLM_FAST_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "aggregate_scores": scores,
        "samples": per_sample,
    }
    json_text = json.dumps(payload, indent=2, default=str)
    md_text = _render_markdown(payload)

    # Timestamped run + a stable "latest" copy for easy demo access.
    for json_path, md_path in (
        (out_dir / f"ragas_{subset}_{ts}.json", out_dir / f"ragas_{subset}_{ts}.md"),
        (out_dir / "latest.json", out_dir / "latest.md"),
    ):
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")

    print(f"Saved results -> {out_dir / f'ragas_{subset}_{ts}.json'}")
    print(f"Demo report   -> {out_dir / 'latest.md'}")


_METRIC_KEYS = (
    "faithfulness",
    "answer_relevancy",
    "llm_context_precision_with_reference",
    "context_recall",
)


def _render_markdown(payload: dict) -> str:
    """Render a demo-friendly Markdown report from the results payload."""
    scores = payload["aggregate_scores"]
    lines = [
        "# RAGAS Evaluation — PartSelect RAG Pipeline",
        "",
        f"- **Run:** `{payload['timestamp']}`  ",
        f"- **Subset:** `{payload['subset']}`  ·  **Retrieval top_k:** `{payload['top_k']}`  ",
        f"- **Judge model:** `{payload['judge_model']}`  ·  "
        f"**Embeddings:** `{payload['embedding_model']}`  ",
        "",
        "## Aggregate scores (0.0–1.0, higher is better)",
        "",
        "| Metric | Score |",
        "| --- | --- |",
    ]
    for name, value in scores.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", "## Per-query results", ""]
    headers = ["#", "Query"] + [k for k in _METRIC_KEYS]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for i, row in enumerate(payload.get("samples", []), 1):
        q = str(row.get("user_input", ""))[:60].replace("|", "/")
        cells = [str(i), q]
        for key in _METRIC_KEYS:
            val = row.get(key)
            cells.append(f"{float(val):.3f}" if isinstance(val, (int, float)) else "–")
        lines.append("| " + " | ".join(cells) + " |")

    lines += [
        "",
        "## What these metrics mean",
        "",
        "- **faithfulness** — is the answer grounded in retrieved context (no hallucination)?",
        "- **answer_relevancy** — does the answer actually address the question?",
        "- **context_precision** — are the retrieved chunks relevant (low noise)?",
        "- **context_recall** — did retrieval surface the info in the reference answer?",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RAGAS eval for the PartSelect RAG pipeline.")
    parser.add_argument(
        "--subset",
        default="smoke",
        choices=["all", "repair", "parts", "smoke"],
        help="Which curated cases to evaluate (default: smoke = 3 cases).",
    )
    parser.add_argument("--top-k", type=int, default=None, help="Retrieval depth per query.")
    args = parser.parse_args()

    try:
        run(subset=args.subset, top_k=args.top_k)
    except ImportError as exc:
        print(
            "Missing eval dependencies. Install them in a separate venv:\n"
            "  pip install -r evals/requirements-evals.txt\n"
            f"(import error: {exc})",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
