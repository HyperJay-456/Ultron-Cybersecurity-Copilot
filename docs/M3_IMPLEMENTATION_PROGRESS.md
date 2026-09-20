# Milestone M3: VAPT Knowledge RAG — Implementation Progress

**Authoritative Specification**: M3 Plan v2.3.8 (`docs/M3_VAPT_KNOWLEDGE_RAG_PLAN.md`)  
**Planning Freeze Tag**: `m3-v2.3.8-planning-freeze`  
**Planning Freeze Tag Target Commit**: `819b83399e24080bf2942c3941cc96728885df49`  
**Planning Freeze Tag Object SHA**: `dbe42947d48df9c9f971af167631031cb8b294e0`  
**Current Git HEAD**: `5a53c96` (`feat(m3): integrate vapt knowledge grounding and poisoning defenses`)  
**Tag Ancestry**: Verified (`git merge-base --is-ancestor 819b83399e24080bf2942c3941cc96728885df49 HEAD` returns true)  
**Implementation Start Timestamp**: `2026-09-20T09:43:33+05:30`  
**Block B Start Timestamp**: `2026-09-20T09:57:35+05:30`  
**Block C Start Timestamp**: `2026-09-20T10:17:23+05:30`  
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
| **M3 Block B Checkpoint** | `b63f862` | Block B retrieval & qualification foundations committed (Phases M3.6–M3.9; 311 unit tests passing) |
| **M3 Block C Checkpoint** | `5a53c96` | Block C context integration, grounding, poisoning defenses committed (Phases M3.10–M3.14; 353 unit tests passing) |

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
- [x] **Block C: Context Integration, Poisoning Defense & Grounding (Phases M3.10 → M3.14)** `[COMPLETED & VERIFIED]`
  - [x] M3.10: VAPT RAG Context Integration, Production Serializer & Causal Context-Budget Invariant (`src/knowledge/serializer.py`, `src/engine/context_builder.py`)
  - [x] M3.11: Dual Grounding Validation & Strict Epistemic Namespace Separation (`src/knowledge/grounding_validator.py`, `src/engine/models.py`)
  - [x] M3.12: Runtime Knowledge Poisoning Defense, Delimiter Sandboxing & Non-Destructive Sanitization (`src/knowledge/poisoning_defense.py`)
  - [x] M3.13: Integrated Retrieval/Reasoning Pipeline & Fail-Safe Degradation (`src/knowledge/pipeline.py`)
  - [x] M3.14: Negative Controls & Strict Execution Boundary Enforcement (`tests/unit/test_m3_negative_controls.py`, `tests/fixtures/negative_controls/`)
- [ ] **Block D: Ablation Harness, Human Study & Artifact Generation (Phases M3.15 → M3.19)** `[NOT STARTED]`

---

## 3. Current Phase Status

- **Current Implementation Block**: Block C `[COMPLETED]`
- **Completed Phases**: M3.10, M3.11, M3.12, M3.13, M3.14
- **Files Added in Block C**:
  - `src/knowledge/serializer.py` (`ProductionP4Serializer`, CanonicalP4Serialization wire grammar, Section 13.7 priority ordering)
  - `src/knowledge/grounding_validator.py` (`KnowledgeGroundingValidator`, epistemic namespace enforcement, RFC 9162 Merkle audit path verification, license allowlist checking)
  - `src/knowledge/poisoning_defense.py` (`KnowledgePoisoningDefense`, non-destructive XML escaping, injection directive marker telemetry, execution boundary enforcement)
  - `src/knowledge/pipeline.py` (`VaptReasoningPipeline`, end-to-end integration, fail-soft degradation modes)
  - `tests/fixtures/negative_controls/fixture_a.json` (Synthetic Fixture A: Irrelevant Methodology Probe)
  - `tests/fixtures/negative_controls/fixture_b.json` (Synthetic Fixture B: Misleading Inverted Methodology Probe)
  - `tests/fixtures/negative_controls/fixture_c.json` (Synthetic Fixture C: Generic Boilerplate Probe)
  - `tests/unit/test_p4_serializer_oracle_parity.py` (3 unit tests; 100% byte parity with CanonicalP4CapacityOracle)
  - `tests/unit/test_m3_context_builder.py` (4 unit tests; Track B vs D Target-Evidence byte parity, floor preservation)
  - `tests/unit/test_knowledge_grounding_validator.py` (8 unit tests; epistemic confusion, Merkle paths, zero confirmation authority)
  - `tests/unit/test_poisoning_defense.py` (4 unit tests; XML escaping, non-destructive telemetry, execution boundary)
  - `tests/unit/test_vapt_pipeline.py` (4 unit tests; end-to-end pipeline, offline retriever degradation, byte identity)
  - `tests/unit/test_m3_negative_controls.py` (9 unit tests; 8 negative control probes, secret/session protection)
  - `tests/unit/test_m3_block_c_integration.py` (10 unit tests; items A through K formal verification)
- **Files Modified in Block C**:
  - `src/engine/context_builder.py` (integrated M3 tracks, strict Target-Evidence cap = 256/768, fail-soft P4 advisory injection, floor preservation)
  - `src/engine/models.py` (added `cited_methodology_chunk_ids`, aliased `ReasoningHypothesis = HypothesisModelOutput`)
  - `src/knowledge/models.py` (extended `VaptKnowledgePack` with `serialized_p4_wire` and `epistemic_tier`)
  - `src/knowledge/provenance.py` (added RFC 9162 `compute_rfc9162_audit_path` and `verify_rfc9162_audit_path`)
  - `src/knowledge/__init__.py` (re-exported Block C components)
- **Target-Evidence Retriever Status**:
  - `src/retrieval/hybrid.py`: **0 lines modified (100% byte-identical against commit b63f862)**
- **Verification Invariants Confirmed**:
  - **Causal Parity**: `TargetEvidencePayload(B) == TargetEvidencePayload(D)` byte-identical.
  - **Epistemic Discipline**: `supporting_evidence_ids` strictly restricted to `FACT-xxx`; `cited_methodology_chunk_ids` strictly restricted to `CHK-xxx`.
  - **Zero Confirmation Authority**: Reasoning engine cannot emit `CONFIRMED`.
  - **Poisoning Defense**: Advisory text is escaped non-destructively; directives cannot alter system instructions or execution policies.
  - **Degradation Semantics**: Vector backend failure, empty retrieval, or corpus tamper gracefully omits VAPT advisory context and falls back to unaugmented Track B reasoning.
  - **Execution Boundary**: LLM/VAPT layer possesses zero authority over credentials, cookies, CSRF tokens, nonces, signing keys, scope, or approvals.
- **Next Implementation Boundary**: Block D (Phases M3.15 → M3.19: Ablation Harness, Human Study & Empirical Benchmark Evaluation).

---

## 4. Test Verification Baseline

- **Block A Baseline**:
  - Unit Tests: 292 passed, 0 failed, 2 warnings in 9.92s
- **Block B Baseline**:
  - Unit Tests: 311 passed, 0 failed, 2 warnings in 17.96s
  - Total Tests Collected: 359 tests (311 unit + 48 integration)
- **Block C Test Run**:
  - Unit Tests: **353 passed**, 0 failed, 2 warnings in 18.14s
  - Total Tests Collected: **401 tests** (353 unit + 48 integration)
  - Tests Added in Block C: **42 new tests** across 7 test modules:
    - `test_p4_serializer_oracle_parity.py`: 3 passed
    - `test_m3_context_builder.py`: 4 passed
    - `test_knowledge_grounding_validator.py`: 8 passed
    - `test_poisoning_defense.py`: 4 passed
    - `test_vapt_pipeline.py`: 4 passed
    - `test_m3_negative_controls.py`: 9 passed
    - `test_m3_block_c_integration.py`: 10 passed
  - Pre-existing M2/M2.75/Block A/Block B Regression Status: **100% passing (zero regressions)**

---

## 5. Known Limitations & Strict Scope Constraints

1. **Local & Offline Boundary**: M3 is strictly local, offline, deterministic, bounded, and single-node. Zero external network calls or online crawling.
2. **Dual Store Separation**: Target evidence (`evidence.db`) and VAPT knowledge (`vapt_knowledge.db`) are strictly isolated.
3. **Target-Evidence Retriever Untouched**: `src/retrieval/hybrid.py` remains completely untouched (verified 0 diff lines).
4. **Target Evidence Causal Parity**: Target-evidence payload remains byte-identical between Track B and Track D. Tier budgets: Tier 1 = 256, Tier 2 = 768 tokens.
5. **Epistemic Tier Invariant**: `supporting_evidence_ids` may contain `FACT-xxx` only; `cited_methodology_chunk_ids` may contain `CHK-xxx` only.
6. **Query Construction Rule**: Closed `EvidenceGapType` enum only; zero target body text or 3B free-form category hints in primary causal retrieval.
7. **Production Backend Selection**: Candidate 1 selected strictly via preregistered empirical qualification and tie-break rules.
8. **No Empirical Overclaiming in Block C**: No claims of improved yield, precision, or recall; Block C establishes integration, grounding invariants, and safety boundaries. Research outcomes are evaluated in Block D.

---

## 6. Deviations from Frozen Plan

*None. Implementation strictly conforms to M3 Plan v2.3.8.*

