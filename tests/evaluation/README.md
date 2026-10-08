# VAPT Retrieval Benchmark Directory

This directory contains the gold-standard VAPT retrieval evaluation dataset for Phase 0.

- `vapt_retrieval_queries.json`: 100 gold-standard queries with 4-tier relevance ratings, must-retrieve targets, and metadata.
- For full documentation, schema definitions, and labeling methodology, see [`docs/VAPT_RETRIEVAL_BENCHMARK_DATASET.md`](docs/VAPT_RETRIEVAL_BENCHMARK_DATASET.md).
- To run tests:
  ```bash
  .venv\Scripts\python.exe -m pytest tests/unit/test_vapt_benchmark_dataset.py
  ```
