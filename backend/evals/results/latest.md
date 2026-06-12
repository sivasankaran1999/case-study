# RAGAS Evaluation — PartSelect RAG Pipeline

- **Run:** `20260612T010900Z`  
- **Subset:** `all`  ·  **Retrieval top_k:** `5`  
- **Judge model:** `models/gemini-2.5-flash`  ·  **Embeddings:** `models/gemini-embedding-001`  

## Aggregate scores (0.0–1.0, higher is better)

| Metric | Score |
| --- | --- |
| faithfulness | 0.8981 |
| answer_relevancy | 0.6763 |
| llm_context_precision_with_reference | 0.8247 |
| context_recall | 0.6429 |

## Per-query results

| # | Query | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall |
| --- | --- | --- | --- | --- | --- |
| 1 | My refrigerator is not cooling | 0.938 | 0.777 | 0.500 | 0.000 |
| 2 | My ice maker stopped making ice | 1.000 | 0.748 | 1.000 | 1.000 |
| 3 | There is frost building up in my freezer | 1.000 | 0.769 | 0.700 | 0.500 |
| 4 | Water dispenser not working on my fridge | 1.000 | 0.775 | 1.000 | 0.000 |
| 5 | My dishwasher won't drain | 1.000 | 0.792 | 1.000 | 0.000 |
| 6 | Dishwasher not cleaning dishes properly | 0.957 | 0.785 | 1.000 | 1.000 |
| 7 | My dishwasher is leaking from the door | 1.000 | 0.803 | 1.000 | 0.000 |
| 8 | Dishwasher won't start | 1.000 | 0.785 | 0.750 | 1.000 |
| 9 | water inlet valve for my refrigerator | 1.000 | 0.789 | 1.000 | 1.000 |
| 10 | refrigerator water filter | 0.000 | 0.000 | 0.500 | 0.500 |
| 11 | dishwasher drain pump | 1.000 | 0.821 | 1.000 | 1.000 |
| 12 | defrost thermostat | 1.000 | 0.801 | 1.000 | 1.000 |
| 13 | dishwasher door latch | 0.833 | 0.000 | 0.417 | 1.000 |
| 14 | evaporator fan motor | 0.846 | 0.824 | 0.679 | 1.000 |

## What these metrics mean

- **faithfulness** — is the answer grounded in retrieved context (no hallucination)?
- **answer_relevancy** — does the answer actually address the question?
- **context_precision** — are the retrieved chunks relevant (low noise)?
- **context_recall** — did retrieval surface the info in the reference answer?
