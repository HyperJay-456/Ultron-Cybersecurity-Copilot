# Local AI-Assisted Bug Bounty Research Platform (v10.0 Deep Android & Binary Reverse Engineering)

An evidence-grounded, local-first, human-in-the-loop security research assistant designed to operate strictly on consumer hardware (AMD Ryzen 5 5600H, 24GB RAM, RTX 3050 4GB VRAM).

---

## 0. The Research Question
> **Under a fixed evidence budget, does an explicit Application Model → Security Invariant → Evidence Gap → Hypothesis → Experiment architecture improve security-hypothesis precision, abstention quality, and human investigation efficiency compared to conventional LLM + RAG?**

This is **not** an automated hacking scanner. The AI is a hypothesis-generation and evidence-reasoning engine mediated by deterministic software and human verification:
```text
Observe → Understand App → Map Identities & State Transitions → Derive Security Invariants → Identify Violations (Hypothesis) → Design Experiment → Human Test → Update Hypothesis
```

---

## 1. Non-Negotiable Invariants
1. **Scope Invariant**: No network action executes unless authorized by a `ScopeDecisionObject` for the *resolved destination* (with DNS TOCTOU defense and redirect re-evaluation).
2. **Grounding Invariant**: No hypothesis reaches a human unless every canonical ID it references exists, and the structural relationships between those IDs hold.
3. **Epistemic Invariant**: Facts (`DOCUMENTED`, `OBSERVED`, `DETERMINISTIC_DERIVATION`) are strictly segregated from model assumptions (`MODEL_PROPOSED`).
4. **Provenance Invariant**: Ingested data carries `source` and `trust: UNTRUSTED`. RAG contexts delimit this data to prevent prompt injection.

---

## 2. Hardware-Aware Phased Scheduling
To prevent CPU/IO and VRAM contention on Ryzen 5 5600H & RTX 3050:
- **Phase 1 (Recon & Ingestion)**: 100% CPU allocation.
- **Phase 2 (Embedding & Indexing)**: 100% CPU allocation to ChromaDB and SQLite FTS5 (BM25).
- **Phase 3 (Reasoning Sweeps)**: 100% GPU allocation to Ollama (`qwen2.5-coder:3b` for broad sweeps, `qwen2.5-coder:7b` for survivor sets).

---

## 3. Quickstart & Testing
```bash
# Activate virtual environment
.venv\Scripts\activate

# Run test suite
pytest -q
```

---

## 4. Documentation
- [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md): Reproduction setup guide and benchmark execution.
- [ARCHITECTURE.md](ARCHITECTURE.md): Architectural design and subsystem breakdown.
- [DECISIONS.md](DECISIONS.md): Architectural decision records (ADRs).
- [TODO.md](TODO.md): Phase implementation roadmap and active tasks.
- [TEST_STATUS.md](TEST_STATUS.md): Component test matrix.
- [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md): Evaluation and ablation experiment tracking.
- [docs/M10_FINAL_REPORT.md](docs/M10_FINAL_REPORT.md): Milestone 10 Deep Android & Binary Reverse Engineering Report.
