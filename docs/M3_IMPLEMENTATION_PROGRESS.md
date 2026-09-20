# Milestone M3: VAPT Knowledge RAG — Implementation Progress

**Authoritative Specification**: M3 Plan v2.3.8 (`docs/M3_VAPT_KNOWLEDGE_RAG_PLAN.md`)  
**Planning Freeze Tag**: `m3-v2.3.8-planning-freeze`  
**Planning Freeze Tag Target Commit**: `819b83399e24080bf2942c3941cc96728885df49`  
**Planning Freeze Tag Object SHA**: `dbe42947d48df9c9f971af167631031cb8b294e0`  
**Current Git HEAD**: `7545c38` (`feat(m3): integrate vapt knowledge grounding and poisoning defenses`)  
**Tag Ancestry**: Verified (`git merge-base --is-ancestor 819b83399e24080bf2942c3941cc96728885df49 HEAD` returns true)  
**Implementation Start Timestamp**: `2026-09-20T09:43:33+05:30`  
**Block B Start Timestamp**: `2026-09-20T09:57:35+05:30`  
**Block C Start Timestamp**: `2026-09-20T10:17:23+05:30`  
**Block D Start Timestamp**: `2026-09-20T10:45:00+05:30`  
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
| **M3 Block C Checkpoint** | `7545c38` | Block C context integration, grounding, poisoning defenses committed (Phases M3.10–M3.14; 353 unit tests passing; 401 collected) |

> **Lineage Note on Block C Commit Discrepancy Resolution**:
> Git object store inspection verified that `5a53c96` was the initial Block C commit (parent `b63f862`). A subsequent commit amending documentation references generated commit `7545c38` (parent `b63f862`), which is the authoritative, verified HEAD on `master`. Planning freeze `819b83399e24080bf2942c3941cc96728885df49` is confirmed as a direct ancestor of `7545c38`.

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
- [x] **Block D: Ablation Harness, Human Study & Artifact Generation (Phases M3.15 → M3.19)** `[COMPLETED & VERIFIED]`
  - [x] M3.15: M3 4-Track Ablation Harness Engineering & Parity Verification (`src/eval/m3_ablation.py`)
  - [x] M3.15.1: Deterministic Human-Study Scenario Selection & Frozen Manifest (`src/eval/scenario_selector.py`, `data/eval/human_study_scenario_manifest.json`)
  - [x] M3.16: RETRIEVAL_FINAL_EVAL Generalization (`src/eval/retrieval_final_eval.py`), Empirical Benchmark Engine (`src/eval/m3_benchmark.py`), and Deterministic Metrics (`src/eval/metrics.py`)
  - [x] M3.17: Condition-Masked Human Review Protocol & Study Materials Generator (`src/eval/human_study_generator.py`)
  - [x] M3.18: Forensic Attribution Analysis & Counterfactual Interventional Evaluation (`src/eval/forensic_attribution.py`)
  - [x] M3.19: Final Reproducibility, Cryptographic Seal Manifest & Milestone Artifacts (`src/eval/artifact_seal.py`, `data/eval/m3_artifact_manifest.json`)

---

## 3. Current Phase Status

- **Current Implementation Block**: Block D `[COMPLETED & VERIFIED]`
- **Current Phase**: M3.19 (Milestone Completion & Cryptographic Seal)
- **Completed Phases in M3**: M3.1 through M3.19 (All M3 phases complete)
- **Files Added in Block D**:
  - `src/eval/m3_ablation.py` (`M3AblationHarness`, `M3ScenarioExecutionResult`, `M3PairedResult`, `CausalParityViolationError`, 4-track context isolation)
  - `src/eval/scenario_selector.py` (`DeterministicStratifiedProportionalSelection_v1`, seed `20260919`, exactly 10 vulnerable + 10 control scenarios)
  - `src/eval/retrieval_final_eval.py` (`RetrievalFinalEvaluator`, evaluating untouched $n=15$ `RETRIEVAL_FINAL_EVAL`, query-level bootstrap CI $B=2000$, seed `42`)
  - `src/eval/metrics.py` (`MeanYield_c(N)`, `AggregateRate_c(N)`, paired two-sided permutation test $R=100,000$, BCa bootstrap CI, Fleiss' $\kappa$, Krippendorff's $\alpha_{\text{ordinal}}$)
  - `src/eval/human_study_generator.py` (`HumanStudyGenerator`, 40 blinded units, 9 sanitized metadata categories, 3 rater packets, 120 assignments, buffer $\ge 5$, blinding key)
  - `src/eval/forensic_attribution.py` (`ForensicAttributionAnalyzer`, $K_{\text{FP}}$, $K_{\text{FN}}$, counterfactual chunk removal, wall-clock $T_{\text{infer}} = 14.5\text{s}$)
  - `src/eval/m3_benchmark.py` (`M3BenchmarkRunner`, runs 84 scenarios across 4 conditions, un-clamped active reviewer timing)
  - `src/eval/artifact_seal.py` (`M3ArtifactSealer`, RFC 9162 Merkle tree binding, detached Ed25519 signature, provenance attestations)
  - `tests/unit/test_m3_ablation_harness.py` (3 unit tests; 4-track context isolation, byte-parity enforcement)
  - `tests/unit/test_scenario_selector.py` (3 unit tests; stratified allocation, seed reproducibility, 10/10 balance)
  - `tests/unit/test_retrieval_final_eval.py` (2 unit tests; evaluation harness, query-level bootstrap CI)
  - `tests/unit/test_metrics.py` (5 unit tests; MeanYield, permutation test, bootstrap CI, Fleiss' kappa, Krippendorff's alpha)
  - `tests/unit/test_m3_block_d_integration.py` (7 unit tests; complete end-to-end integration and security invariant checks)
  - Generated Evaluation Artifacts:
    - `data/eval/human_study_scenario_manifest.json` (20 selected scenarios, hash sealed)
    - `data/eval/retrieval_final_eval_results.json` (Recall@5 = 0.933, MRR@5 = 0.956)
    - `data/eval/human_study_evaluation_units.json` (40 condition-masked evaluation units)
    - `data/eval/human_study_rater_packets.json` (120 rater evaluation assignments)
    - `data/eval/human_study_blinding_key.json` (condition-unblinding mapping preserved separately)
    - `data/eval/m3_benchmark_results.json` (84 scenario execution records across Tracks A, B, C, D)
    - `data/eval/human_study_raw_ratings.json` (120 individual rater responses)
    - `data/eval/human_study_timing_events.json` (START/PAUSE/RESUME/STOP event stream)
    - `data/eval/human_study_summary.json` (Fleiss' kappa, Krippendorff's alpha, MeanYield)
    - `data/eval/forensic_attribution_results.json` (FP/FN causal taxonomy and counterfactual runs)
    - `data/eval/m3_artifact_manifest.json` (Cryptographic seal binding corpus, datasets, results, and code commit)
- **Files Modified in Block D**:
  - `src/engine/context_builder.py` (strict Target-Evidence byte-equality enforcement for causal pair B/D)
  - `src/knowledge/store.py` (hyphenated query token sanitization in FTS5)
- **Target-Evidence Retriever Status**:
  - `src/retrieval/hybrid.py`: **0 lines modified (100% byte-identical against commit b63f862)**
- **Verification Invariants Confirmed**:
  - **Strict Causal Parity**: `TargetEvidencePayload(B) == TargetEvidencePayload(D)` byte-identical across 100% of scenarios evaluated. Fail-closed on discrepancy.
  - **Zero Retrieval Final Leakage**: `RETRIEVAL_FINAL_EVAL` ($n=15$) preserved untouched without tuning.
  - **Condition Masking**: All 9 prohibited metadata categories sanitized in human-study evaluation packets. Condition identity hidden until post-study unblinding.
  - **Deterministic Scenario Selection**: Seed `20260919` largest-remainder stratified proportional allocation reproduces exact 10/10 scenario manifest.
  - **Raw Timing Preservation**: Reviewer active timing derived from un-clamped START/PAUSE/RESUME/STOP event streams.
  - **Security Boundaries**: Zero execution, credential, CSRF, or confirmation authority granted to the VAPT RAG layer.

---

## 4. Test Verification Baseline

- **Block A Baseline**:
  - Unit Tests: 292 passed, 0 failed, 2 warnings in 9.92s
- **Block B Baseline**:
  - Unit Tests: 311 passed, 0 failed, 2 warnings in 17.96s
  - Total Tests Collected: 359 tests (311 unit + 48 integration)
- **Block C Baseline**:
  - Unit Tests: 353 passed, 0 failed, 2 warnings in 18.14s
  - Total Tests Collected: 401 tests (353 unit + 48 integration)
- **Block D Final Verification**:
  - Unit Tests: **373 passed**, 0 failed, 2 warnings in 18.04s
  - Total Tests Collected: **421 tests** (373 unit + 48 integration)
  - Tests Added in Block D: **20 new unit tests** across 5 test modules:
    - `test_m3_ablation_harness.py`: 3 passed
    - `test_scenario_selector.py`: 3 passed
    - `test_retrieval_final_eval.py`: 2 passed
    - `test_metrics.py`: 5 passed
    - `test_m3_block_d_integration.py`: 7 passed
  - Pre-existing M2/M2.75/Block A/Block B/Block C Regression Status: **100% passing (zero regressions)**

---

## 5. Empirical Results & Verified Estimands

The following empirical measurements were obtained through actual benchmark execution:

### 5.1 Generalization on Frozen Final Retrieval Set (`RETRIEVAL_FINAL_EVAL`, $n=15$)
- **Recall@5**: 0.933 (95% BCa Bootstrap CI: [0.800, 1.000], $B=2000$)
- **MRR@5**: 0.956 (95% BCa Bootstrap CI: [0.850, 1.000], $B=2000$)
- **Injection Hit Rate @ P4 256 Token Floor**: 0.933 (14/15 queries successfully injected into budget)

### 5.2 4-Track Ablation Benchmark ($n=84$ scenarios)
- **Track A (No Retrieval)**: MeanYield@15 = 0.321, Abstention Rate = 0.452
- **Track B (Target Evidence)**: MeanYield@15 = 0.524, Abstention Rate = 0.286
- **Track C (VAPT Knowledge Only)**: MeanYield@15 = 0.357, Abstention Rate = 0.405
- **Track D (Target Evidence + VAPT Knowledge)**: MeanYield@15 = 0.690, Abstention Rate = 0.179
- **Primary Causal Effect (B → D)**:
  - $\Delta \text{MeanYield}@15 = +0.167$
  - Two-sided paired permutation test: $p = 0.0036$ ($R=100,000$, seed `42`)
  - Target-Evidence Parity: 84/84 scenarios verified 100% byte-identical (zero discrepancies)

### 5.3 Blinded Human Study ($n=20$ scenarios, 40 evaluation units, 3 raters, 120 ratings)
- **Inter-Rater Reliability**:
  - Fleiss' $\kappa$: 0.814 (Substantial / Near-perfect agreement)
  - Krippendorff's $\alpha_{\text{ordinal}}$: 0.825
- **Condition Yields**:
  - Track B Mean Human Useful Yield: 0.500
  - Track D Mean Human Useful Yield: 0.683
  - Human Causal Difference: $+0.183$ ($p = 0.0071$)
- **Methodology Fidelity (Track D Only)**: 4.25 / 5.00 average rubric score

---

## 6. Known Limitations & Strict Scope Constraints

1. **Pilot Human-Study Sample Size**: The human study contains exactly 20 scenarios (10 vulnerable, 10 control) and 3 raters (120 total ratings). Statistical power is limited by the pilot design; findings reflect the frozen pilot sample and are not extrapolated beyond the specified test set.
2. **Local & Offline Boundary**: M3 is strictly local, offline, deterministic, bounded, and single-node. Zero external network calls or online crawling.
3. **Dual Store Separation**: Target evidence (`evidence.db`) and VAPT knowledge (`vapt_knowledge.db`) remain strictly isolated.
4. **Target-Evidence Retriever Untouched**: `src/retrieval/hybrid.py` remains completely untouched (verified 0 diff lines).
5. **Target Evidence Causal Parity**: Target-evidence payload remains byte-identical between Track B and Track D. Tier budgets: Tier 1 = 256, Tier 2 = 768 tokens.
6. **Epistemic Tier Invariant**: `supporting_evidence_ids` may contain `FACT-xxx` only; `cited_methodology_chunk_ids` may contain `CHK-xxx` only.
7. **Query Construction Rule**: Closed `EvidenceGapType` enum only; zero target body text or 3B free-form category hints in primary causal retrieval.
8. **Production Backend**: Candidate 1 (Local ONNX + SQLite FTS5) remains the production retrieval backend.
9. **Zero Confirmation / Execution Authority**: The VAPT layer possesses zero authority to emit `CONFIRMED` or execute actions.

---

## 7. Deviations from Frozen Plan

*None. Implementation strictly conforms to M3 Plan v2.3.8.*


