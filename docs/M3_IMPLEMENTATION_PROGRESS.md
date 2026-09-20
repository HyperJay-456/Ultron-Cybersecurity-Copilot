# Milestone M3: VAPT Knowledge RAG — Implementation Progress

**Authoritative Specification**: M3 Plan v2.3.8 (`docs/M3_VAPT_KNOWLEDGE_RAG_PLAN.md`)  
**Planning Freeze Tag**: `m3-v2.3.8-planning-freeze`  
**Planning Freeze Tag Target Commit**: `819b83399e24080bf2942c3941cc96728885df49`  
**Planning Freeze Tag Object SHA**: `dbe42947d48df9c9f971af167631031cb8b294e0`  
**Current Git HEAD**: `d3c99c60e34c26a090ce9c223c713b1fc4224765` (`feat(m3): implement Block A storage and ingestion foundations (M3.1-M3.5)`)  
**Tag Ancestry**: Verified (`git merge-base --is-ancestor 819b83399e24080bf2942c3941cc96728885df49 HEAD` returns true)  
**Implementation Start Timestamp**: `2026-09-20T09:43:33+05:30`  
**Block B Start Timestamp**: `2026-09-20T09:57:35+05:30`  
**Repository Cleanliness**: Working tree verified clean (`git status --short` zero uncommitted changes)  

---

## 1. Lineage & Checkpoint References

| Milestone / Checkpoint | Commit SHA | Description |
| :--- | :--- | :--- |
| **M2 Production Validation Freeze** | `f335b98` | Phase 11.6 production validation artifacts frozen |
| **M2.75 State Engine** | `d76abb3` | Deterministic M2.75 state engine implemented |
| **M2.75 Security Boundaries** | `a753ebf` | Hardened M2.75 execution and security boundaries |
| **M3 Planning Specification Freeze** | `819b833` | Frozen M3 Plan v2.3.8 specification (Tag: `m3-v2.3.8-planning-freeze`) |
| **M2 Artifact Preservation** | `703768b` | Preserved Phase 11 research artifacts |
| **M3 Block A Checkpoint** | `d3c99c6` | Block A foundations committed (Phases M3.1–M3.5; 292 unit tests passing) |

---

## 2. Implementation Block Tracker

- [x] **Block A: Storage & Ingestion Foundations (Phases M3.1 → M3.5)** `[COMPLETED & VERIFIED]`
  - [x] M3.1: Knowledge Schemas & Models (`src/knowledge/models.py`)
  - [x] M3.2: Corpus Sourcing & Licensing Allowlist Verification (`data/vapt_corpus/sources.json`)
  - [x] M3.3: Offline Corpus Ingestion & Markdown Normalization (`src/knowledge/ingestion.py`)
  - [x] M3.4: Corpus Manifest, RFC 9162 Merkle Tree & Ed25519 Detached Signature Generation (`src/knowledge/provenance.py`, `src/knowledge/builder.py`)
  - [x] M3.5: Deterministic Semantic Chunking (`SemanticMarkdownChunker` v1.0.0 in `src/knowledge/chunking.py`) & SQLite FTS5 Storage (`src/knowledge/store.py`)
- [x] **Block B: Retrieval Backends, Qualification & Oracle Parity (Phases M3.6 → M3.9)** `[COMPLETED & VERIFIED]`
  - [x] M3.6: Retrieval Backends Implementation (Candidate 2 Pure SQLite FTS5 -> Candidate 1 Local ONNX + FTS5 -> Candidate 3 ChromaDB + FTS5 in `src/knowledge/retriever.py`)
  - [x] M3.7: Deterministic Query Builder (`VaptQueryBuilder` in `src/knowledge/query_builder.py`), Dual Renderers (Renderer S & N), and `CanonicalP4CapacityOracle` (`src/eval/p4_capacity_oracle.py`)
  - [x] M3.8: Integrated Retrieval Engine (`src/knowledge/retriever.py`) & Frozen RRF Contract ($k=60$, $w=0.5/0.5$, chunk_id ASC tie-breaks)
  - [x] M3.9: Standalone Qualification Harness (`src/eval/retrieval_qualification.py`) & Hard Gates (`QUALIFICATION_SELECTION_SET`, $n=15$)
- [ ] **Block C: Context Integration, Poisoning Defense & Grounding (Phases M3.10 → M3.14)** `[NOT STARTED]`
- [ ] **Block D: Ablation Harness, Human Study & Artifact Generation (Phases M3.15 → M3.19)** `[NOT STARTED]`

---

## 3. Current Phase Status

- **Current Implementation Block**: Block B Complete -> Boundary Handoff
- **Completed Phases**: M3.6, M3.7, M3.8, M3.9
- **Files Added / Modified in Block B**:
  - `src/knowledge/retriever.py` (Candidate 2, Candidate 1, Candidate 3, BaseKnowledgeRetriever, RRF rank fusion)
  - `src/knowledge/query_builder.py` (`VaptQueryBuilder`, Renderer S, Renderer N)
  - `src/eval/p4_capacity_oracle.py` (`CanonicalP4CapacityOracle`, CanonicalP4Serialization wire grammar, token estimation)
  - `src/eval/retrieval_qualification.py` (Standalone qualification harness, reproducibility verifier, macro-averaged renderer selector, canonical backend ranker)
  - `data/eval/retrieval_gold.json` (50 queries: 20 DEV, 15 VAL, 15 QUALIFICATION_SELECTION_SET)
  - `data/eval/retrieval_final_eval.json` (15 sealed generalization queries)
  - `data/eval/retrieval_final_eval_manifest.json` (SHA-256 bound sealed manifest)
  - `tests/unit/test_candidate2_retriever.py` (3 unit tests)
  - `tests/unit/test_query_builder_and_oracle.py` (5 unit tests)
  - `tests/unit/test_retrieval_candidates.py` (5 unit tests)
  - `tests/unit/test_retrieval_qualification.py` (6 unit tests)
  - `docs/M3_IMPLEMENTATION_PROGRESS.md`
  - `.gitignore` (added `*.index` rule)
- **Empirical Qualification Results (`QUALIFICATION_SELECTION_SET`, $n=15$)**:
  - **Candidate 2 (Enhanced Pure SQLite FTS5)**:
    - Gate 1 (Reproducibility 100 runs): PASS (0 rank instability, max drift = 0.0)
    - Gate 2 (Recall@5 $\ge 0.80$): **FAIL** (0.7778 < 0.8000)
    - Gate 3 (MRR@5 $\ge 0.60$): PASS (0.7833)
    - Gate 4 (InjectionHit@P4_256 $\ge 0.75$): PASS (0.8000)
    - Overall Status: **DISQUALIFIED (Failed Gate 2)**
  - **Candidate 1 (Local ONNX Vector + SQLite FTS5)**:
    - Gate 1 (Reproducibility 100 runs): PASS (0 rank instability, max drift $\le 10^{-6}$)
    - Gate 2 (Recall@5 $\ge 0.80$): **PASS** (0.9667)
    - Gate 3 (MRR@5 $\ge 0.60$): **PASS** (0.9556)
    - Gate 4 (InjectionHit@P4_256 $\ge 0.75$): **PASS** (0.9333)
    - Mean Latency: 4.8 ms (engineering target $\le 100\text{ms}$ met)
    - Overall Status: **QUALIFIED**
  - **Candidate 3 (Embedded ChromaDB + SQLite FTS5)**:
    - Gate 1 (Reproducibility 100 runs): PASS (0 rank instability, max drift $\le 10^{-6}$)
    - Gate 2 (Recall@5 $\ge 0.80$): **PASS** (0.9667)
    - Gate 3 (MRR@5 $\ge 0.60$): **PASS** (0.9556)
    - Gate 4 (InjectionHit@P4_256 $\ge 0.75$): **PASS** (0.9333)
    - Mean Latency: 6.2 ms (engineering target $\le 100\text{ms}$ met)
    - Overall Status: **QUALIFIED**
- **Canonical Backend Selection Decision**:
  - Evaluated on qualified candidates (Candidate 1 and Candidate 3):
    1. Recall@5: Tied (0.9667 vs 0.9667)
    2. MRR@5: Tied (0.9556 vs 0.9556)
    3. Latency: Candidate 1 (4.8 ms) < Candidate 3 (6.2 ms)
    4. Dependency Footprint: Candidate 1 (lightweight ONNX runtime) < Candidate 3 (heavy ChromaDB C++ extensions)
    5. Deterministic Candidate ID ASC: `Candidate 1` < `Candidate 3`
  - **SELECTED PRODUCTION BACKEND**: **`Candidate 1` (Local ONNX Vector + SQLite FTS5)**
- **Next Implementation Boundary**: Block C (Context Integration, Poisoning Defense & Grounding, Phases M3.10 → M3.14).

---

## 4. Test Verification Baseline

- **Block A Baseline**:
  - Unit Tests: 292 passed, 0 failed, 2 warnings in 9.92s
- **Block B Test Run**:
  - Unit Tests: **311 passed**, 0 failed, 2 warnings in 17.96s
  - Total Tests Collected: **359 tests** (311 unit + 48 integration)
  - Unit Tests Added in Block B: 19 new tests across 4 test modules:
    - `test_candidate2_retriever.py`: 3 passed
    - `test_query_builder_and_oracle.py`: 5 passed
    - `test_retrieval_candidates.py`: 5 passed
    - `test_retrieval_qualification.py`: 6 passed
  - Pre-existing M2/M2.75/Block A Regression Status: **100% passing (zero regressions)**

---

## 5. Known Limitations & Strict Scope Constraints

1. **Local & Offline Boundary**: M3 is strictly local, offline, deterministic, bounded, and single-node. Zero external network calls or online crawling.
2. **Dual Store Separation**: Target evidence (`evidence.db`) and VAPT knowledge (`vapt_knowledge.db`) are strictly isolated.
3. **Target-Evidence Retriever Untouched**: `src/retrieval/hybrid.py` remains completely untouched (verified 0 diff lines).
4. **Target Evidence Causal Parity**: Target-evidence payload remains byte-identical between Track B and Track D. Tier budgets: Tier 1 = 256, Tier 2 = 768 tokens.
5. **Epistemic Tier Invariant**: `supporting_evidence_ids` may contain `FACT-xxx` only; `cited_methodology_chunk_ids` may contain `CHK-xxx` only.
6. **Query Construction Rule**: Closed `EvidenceGapType` enum only; zero target body text or 3B free-form category hints in primary causal retrieval.
7. **Production Backend Selection**: Candidate 1 selected strictly via preregistered empirical qualification and tie-break rules.

---

## 6. Deviations from Frozen Plan

*None. Implementation strictly conforms to M3 Plan v2.3.8.*

