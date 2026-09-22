# Milestone M5 Phase 10: Full-Population Confirmatory Benchmark
## Pre-Benchmark Engineering & Preflight Validation Report

**Status**: PRE-BENCHMARK ENGINEERING COMPLETE — AWAITING BENCHMARK APPROVAL  
**Author**: Pair Programming Implementation Agent  
**Date**: September 22, 2026  
**Git Branch**: `master`  
**Git HEAD**: `381cef1d7c1256437685bff0855417febe22163b`  

> [!IMPORTANT]
> **PRE-BENCHMARK GATE NOTICE**:  
> The Phase 10 engineering stack, runtime controls, benchmark runner, preflight gate, and comprehensive test suite are complete and verified.  
> **THE 336-CALL LIVE FULL-POPULATION BENCHMARK HAS NOT YET BEEN EXECUTED.**  
> Execution is strictly gated until all verification gates pass and explicit human approval is granted.

---

## 1. Executive Summary

Milestone M5 Phase 10 scales the verified deterministic experiment skeleton (validated during Phase 9 diagnostic study) across the full 84-scenario benchmark population under a balanced 2×2 factorial design:
- **Architecture Dimension**: `DETERMINISTIC_EXPERIMENT_SKELETON` vs. `BASELINE_EXISTING_ARCHITECTURE`
- **Context Dimension**: `TRACK_A` (Minimal Structural) vs. `TRACK_D` (Full Cascade + RAG Pack)
- **Population**: 84 scenarios (36 vulnerable variants + 48 negative controls)
- **Planned Calls**: 84 × 4 = 336 sequential, single-attempt live model calls (zero retries, zero repairs).

All engineering components (hard runtime control, authoritative benchmark harness, fail-closed preflight checker, and 25-point unit test suite) have been implemented and verified.

---

## 2. Starting State & Historical Immutability Freeze

All four immutable historical artifacts were verified bit-for-bit via SHA-256 before any Phase 10 changes were introduced:

| Artifact Path | Expected Pre-Registered SHA-256 | Verified Status |
| :--- | :--- | :--- |
| `data/eval/m5_phase7_benchmark_final.json` | `1e0ed90c4aa672f135d2d2f2240a14d22fa0037c03efda33634f4bf10ff0b125` | **MATCH (BIT-FOR-BIT)** |
| `data/eval/m5_phase8_semantic_study.json` | `b1df9a62fb07d76e0abf6e3935ccbabdaa1713f4c594019ae30c9e59567a45c6` | **MATCH (BIT-FOR-BIT)** |
| `data/eval/m5_phase9_semantic_budget_study.json` | `3c0d3e503c7ed24470b14dfde0bd763c631a9b5dbf70c047bbca72cfaab07f95` | **MATCH (BIT-FOR-BIT)** |
| `src/eval/scenarios.py` | `102789655bfb04041de9259d1bf6db7f088979e5bce9bac9eb050564ef0110a8` | **MATCH (BIT-FOR-BIT)** |

Historical datasets remain strictly read-only and immutable throughout the task.

---

## 3. Phase 10.1 — Hard Runtime Control Implementation

The local execution engine now enforces hard wall-clock ceilings and structured latency telemetry across inference operations:

### A. Failure Taxonomy & Precedence
- Added `PrimaryFailureCategory.RUNTIME_TIMEOUT` to `src/engine/models.py`.
- Updated `classify_primary_failure`: When a timeout occurs (`is_timeout=True` or `TimeoutError`), the failure is strictly classified as `RUNTIME_TIMEOUT`.
- **Precedence Rule**: Timeouts never masquerade as `PARSER_FAILURE`, `SCHEMA_VALIDITY_FAILURE`, or `SEMANTIC_GROUNDING_FAILURE`.

### B. Dual Timeout Ceiling & Socket Cancellation
- **HTTP Timeout**: `httpx.Timeout(timeout=30.0, connect=5.0, read=30.0, write=5.0)` enforced in `OllamaRunner.generate_raw`.
- **Wall-Clock Deadline**: `deadline = time.perf_counter() + 30.0` enforced before dispatch and around inference.
- **Connection Abort**: On timeout, `client.close()` is immediately called, dropping the TCP connection to abort the runner slot in the Ollama Go server.
- **Teardown Tolerance**: Hard ceiling of 30,000 ms with $\le 500$ ms tolerance. Any response taking $>30,500$ ms is aborted and classified as `RUNTIME_TIMEOUT`.

### C. Structured Telemetry Breakdown
`M5ExecutionResult` exposes the following structured latency fields:
- `timed_out: bool`
- `prompt_build_latency_ms: float`
- `inference_latency_ms: Union[float, str]` (derived from Ollama `eval_duration` ns → ms; strictly `"unavailable"` when absent or on timeout, never fabricated)
- `response_parse_latency_ms: Optional[float]`
- `validation_latency_ms: Optional[float]`
- `total_latency_ms: float`

---

## 4. Phase 10.2 — Authoritative Benchmark Engine

**File**: [`src/eval/run_m5_phase10_benchmark.py`](file:///c:/Projects/Bug%20Bounty%20AI/src/eval/run_m5_phase10_benchmark.py)

### Architectural Features:
1. **Factorial Conditions**:
   - `C1`: Deterministic Skeleton + Track A (Minimal Structural)
   - `C2`: Deterministic Skeleton + Track D (Full Cascade + RAG Pack)
   - `C3`: Baseline Architecture + Track A (Minimal Structural)
   - `C4`: Baseline Architecture + Track D (Full Cascade + RAG Pack)
2. **Deterministic Pseudo-Randomized Condition Ordering**:
   - Seed: `FROZEN_ORDER_RANDOMIZATION_SEED = "M5_PHASE10_FACTORIAL_ORDER_SEED_42"`
   - Algorithm: `order_seed = int(SHA256(f"{FROZEN_ORDER_RANDOMIZATION_SEED}:{scenario_id}")[:16], 16)` with `random.Random(order_seed).shuffle([C1, C2, C3, C4])`.
   - Methodological Rationale: Prevents runtime-state, model runner caching, and daemon warm-up order biases across conditions while guaranteeing 100% determinism, non-adaptiveness, and exact coverage of all 4 conditions per scenario.
   - Scenario Loop: Outer loop iterates over 84 scenarios (alphabetically sorted by `scenario_id`); inner loop executes conditions in the scenario's deterministic pseudo-random order.
   - Telemetry Recorded: `scenario_condition_order`, `condition_order_index` (1-4), and `order_randomization_seed`.

   **Example Generated Scenario Condition Orders**:
   | Scenario ID | Scheduled Condition Order |
   | :--- | :--- |
   | `SCEN-SAAS_BILLING-INV-DETAILS-VULN-01` | `['C1', 'C2', 'C3', 'C4']` |
   | `SCEN-SAAS_BILLING-INV-DETAILS-PATCH-01` | `['C2', 'C3', 'C1', 'C4']` |
   | `SCEN-SAAS_BILLING-SUB-DETAILS-VULN-02` | `['C4', 'C1', 'C3', 'C2']` |
   | `SCEN-SAAS_BILLING-SUB-DETAILS-PATCH-02` | `['C3', 'C2', 'C4', 'C1']` |
   | `SCEN-SAAS_BILLING-INV-SUMMARY-VULN-03` | `['C4', 'C2', 'C3', 'C1']` |
   | `SCEN-SAAS_BILLING-INV-SUMMARY-PATCH-03` | `['C4', 'C3', 'C1', 'C2']` |
   | `SCEN-SAAS_BILLING-SUB-SUMMARY-VULN-04` | `['C1', 'C3', 'C2', 'C4']` |
   | `SCEN-SAAS_BILLING-SUB-SUMMARY-PATCH-04` | `['C2', 'C3', 'C1', 'C4']` |

3. **Deterministic Causal Input Hashing**:
   - `canonical_evidence_hash`
   - `target_context_hash`
   - `prompt_hash`
   - `skeleton_config_hash`
   - `runtime_config_hash`
4. **Crash-Safe Resume & Duplicate Prevention**:
   - Checkpoint: `data/eval/m5_phase10_checkpoint.json`
   - Atomic writes via temporary file `.tmp` replacement
   - Completed `(condition_id, scenario_id)` pairs are permanently skipped on restart
5. **Raw Output Freezing**:
   - Final dataset: `data/eval/m5_phase10_full_population_validation.json`
   - Sidecar SHA-256: `data/eval/m5_phase10_full_population_validation.json.sha256`
6. **Fail-Closed Safety Gate**:
   - CLI execution requires explicit `--execute-live-benchmark` argument; otherwise halts safely with zero model calls.

---

## 5. Phase 10.3 — Deterministic Skeleton Invariants

1. **Deterministic Action Resolution**: Engine maps category to legal action predicate (`ExperimentSkeletonBuilder.build_skeleton`).
2. **Flat Unpartitioned Vocabulary**: `legal_outcomes` contains the combined union of breach and safe outcomes in alphabetical order. Zero partition markers (`breach_outcomes`, `safe_outcomes`) are exposed to the model.
3. **Action Override Rejection**: LLM attempts to alter the experiment action are strictly rejected by `validate_skeleton_compliance`.
4. **Authoritative Polarity Enforcement**: `ExperimentPolarityValidator.validate_tuple` validates whether supporting outcome indicates breach and disproving outcome indicates safe state.

---

## 6. Phase 10.4 — Preflight Verification Gates

**File**: [`src/eval/verify_m5_phase10_preflight.py`](file:///c:/Projects/Bug%20Bounty%20AI/src/eval/verify_m5_phase10_preflight.py)

All 10 preflight gates are machine-readable and fail closed:

| Gate | Verification Check | Status |
| :--- | :--- | :--- |
| **Gate A** | Git repository status, branch `master`, clean working tree | **PASS** |
| **Gate B** | 4 historical artifact SHA-256 digests match bit-for-bit | **PASS** |
| **Gate C** | Ollama version == 0.34.1, model `qwen2.5-coder:7b`, digest `dae161e2...` | **PASS (Configured)** |
| **Gate D** | Runtime parameters (`num_ctx=2048`, `num_predict=300`, `temp=0.0`, `seed=42`, `timeout=30s`, `retries=0`) | **PASS** |
| **Gate E** | Deterministic skeleton builds across all 10 scenario categories, override rejected | **PASS** |
| **Gate F** | Zero ground-truth tokens leaked in LLM-visible prompts | **PASS** |
| **Gate G** | Zero breach/safe outcome partition leakage in skeleton prompt blocks | **PASS** |
| **Gate H** | Zero credential/API key leakage in prompts | **PASS** |
| **Gate I** | Gold set population is exactly 84 scenarios (36 vulnerable, 48 controls) | **PASS** |
| **Gate J** | Factorial design matrix: exactly 336 calls (4 × 84), deterministic pseudo-random condition ordering, zero duplicates, verified order diversity | **PASS** |

---

## 7. Phase 10.5 — Test Suite Verification

**File**: [`tests/unit/test_m5_phase10_runtime_and_skeleton.py`](file:///c:/Projects/Bug%20Bounty%20AI/tests/unit/test_m5_phase10_runtime_and_skeleton.py)

Targeted test suite coverage:
- **Total Tests**: 28
- **Passed**: 28
- **Failed**: 0
- **Duration**: ~5.85s

### Test Matrix Breakdown:
1. `test_01_http_timeout_configuration` — Enforces 30.0s timeout in `httpx.Timeout` and `OllamaConfig`
2. `test_02_absolute_wall_clock_timeout` — Enforces wall-clock deadline ceiling
3. `test_03_timeout_cancellation` — Enforces clean cancellation on timeout exception
4. `test_04_connection_socket_closure_behavior` — Enforces `client.close()` socket closure on abort
5. `test_05_runtime_timeout_classification` — Enforces `PrimaryFailureCategory.RUNTIME_TIMEOUT`
6. `test_06_timeout_precedence_over_all_failures` — Enforces timeout precedence over parser, schema, grounding errors
7. `test_07_total_latency_telemetry` — Enforces `total_latency_ms` tracking
8. `test_08_prompt_build_latency_telemetry` — Enforces `prompt_build_latency_ms >= 0.0`
9. `test_09_response_parse_latency_telemetry` — Enforces `response_parse_latency_ms >= 0.0`
10. `test_10_validation_latency_telemetry` — Enforces `validation_latency_ms >= 0.0`
11. `test_11_eval_duration_conversion` — Enforces `eval_duration` ns → ms conversion
12. `test_12_exact_unavailable_fallback` — Enforces exact `"unavailable"` string when missing or timed out
13. `test_13_deterministic_category_action_mapping` — Enforces 10-category deterministic action binding
14. `test_14_llm_action_override_blocked` — Enforces validator rejection of model action overrides
15. `test_15_flat_legal_outcomes_vocabulary` — Enforces flat alphabetically sorted legal outcomes
16. `test_16_breach_safe_partition_never_exposed` — Enforces zero partition leakage in prompts
17. `test_17_ground_truth_never_exposed_in_prompts` — Enforces zero ground-truth tokens in prompts
18. `test_18_evidence_equivalence_across_paired_conditions` — Enforces input parity across tracks
19. `test_19_checkpoint_determinism_and_atomic_write` — Enforces crash-safe atomic checkpointing
20. `test_20_duplicate_call_prevention` — Enforces duplicate execution prevention on resume under per-scenario condition ordering
21. `test_21_semantic_protocol_failure_separation` — Enforces failure separation between protocol and semantics
22. `test_22_historical_artifact_immutability` — Enforces 4 historical artifact digests
23. `test_23_population_integrity` — Enforces 84 scenarios (36 vulnerable, 48 controls)
24. `test_24_336_call_matrix_integrity` — Enforces 4 conditions × 84 scenarios = 336 calls
25. `test_25_hard_teardown_tolerance_boundary` — Enforces teardown tolerance ceiling (>30,500ms failure)
26. `test_26_deterministic_condition_order_reproducibility` — Enforces identical scenario + seed => 100% reproducible condition ordering
27. `test_27_deterministic_condition_order_diversity` — Enforces condition order permutations vary across scenarios and first-position conditions are distributed
28. `test_28_deterministic_condition_order_completeness_and_no_duplicates` — Enforces every scenario receives all 4 conditions {C1, C2, C3, C4} exactly once (336 total calls, 0 duplicates, 0 omissions)

---

## 8. Known Deviations & Unresolved Risks

### Deviations:
- **None**: All implementations strictly adhere to the frozen Phase 10 design, preregistration, and runtime parameters.

### Unresolved Risks:
1. **Ollama Daemon Memory Growth Across 336 Calls**:
   - Risk: Ollama running 336 sequential inferences might experience VRAM fragmentation.
   - Mitigation: `keep_alive="60m"` keeps model resident; atomic checkpointing (`data/eval/m5_phase10_checkpoint.json`) ensures that if the daemon needs a restart, execution resumes seamlessly from the exact next call with zero loss of progress.
2. **Local Machine Load During Execution**:
   - Risk: High CPU/GPU load on the host could trigger false-positive wall-clock timeouts.
   - Mitigation: 30.0s deadline is sufficient for 300-token generation on Qwen2.5-Coder:7b (typically 2–4s on GPU). Teardown tolerance provides an additional 500ms buffer. Host machine should avoid running heavy concurrent tasks during benchmark execution.

---

## 9. Final Pre-Benchmark Status

```
================================================================================
PHASE 10 FINAL PRE-BENCHMARK GATE — READY FOR HUMAN APPROVAL
================================================================================
- Code Implementation: COMPLETE
- Condition Order Hardening: COMPLETE (DETERMINISTIC PSEUDO-RANDOMIZED)
- Hard Runtime Control: VERIFIED
- Preflight Gate: VERIFIED & FAIL-CLOSED (10/10 GATES PASS)
- Historical Digests: VERIFIED (4/4 IMMUTABLE MATCHES)
- Targeted Test Suite: 28/28 PASSED (100%)
- Full Regression: PASSED (ZERO REGRESSIONS)
- Full-Population Benchmark: NOT EXECUTED (PENDING HUMAN APPROVAL)
================================================================================
```
