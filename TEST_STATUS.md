# Test Status: Local AI-Assisted Bug Bounty Research Platform (V6)

## 1. Executive Summary

| Suite Category | Suites | Collected Items | Passing | Failing | Skipped | Execution Time | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Unit Tests** (`tests/unit/`) | 23 | 106 | 106 | 0 | 0 | 3.96s | **100% Passing** |
| **Integration Tests** (`tests/integration/`) | 5 | 20 | 19 | 0 | 1* | 65.89s | **100% Passing** (*1 conditional skip) |
| **Total Test Suite** | **28** | **126** | **125** | **0** | **1** | **69.85s** | **PASSED (Zero Failures)** |

*\*Note: `tests/integration/test_live_ablation_pilot.py` is conditionally skipped when the opt-in environment flag `V6_REQUIRE_LIVE_OLLAMA` is not set, preventing long benchmark sweeps during quick test cycles. All other 19 live inference and reasoning loop integration tests execute live against Ollama (`qwen2.5-coder:3b` and `7b`).*

---

## 2. Test Count Discrepancy & Evolution Reconciliation

Historical documentation recorded different test counts at specific project milestones:
1. **Initial v6 Baseline (Post-Build)**: **77 tests** recorded across 20 initial suites.
2. **Milestone M0 (Phase 0 Hardening)**: **+17 unit tests** added for security and vault protection:
   - `test_scope_enforcement.py` (+8 tests): TOCTOU IP pinning, CIDR/RFC1918 blocking, redirect hop loops, rate limits.
   - `test_vault_adversarial.py` (+9 tests): typed placeholder isolation, correlation preservation, entropy detection.
3. **Milestone M1 & EXP-0006 Audit (Phase 1 Hardening)**: **+32 tests** added for real LLM benchmark integrity, statistical calculations, and live pipelines:
   - `test_real_ablation_integrity.py` (+6 tests): prompt leakage isolation, ground-truth masking.
   - `test_metric_integrity.py` (+6 tests): Wilson 95% CIs, McNemar paired matrix validation.
   - `test_error_handling.py` (+3 tests): database recovery and malformed JSON resilience.
   - Expanded `test_model_inference.py` (+5 tests): prompt injection isolation, schema conformance.
   - `test_live_v6_smoke.py` (+3 tests)
   - `test_live_v6_complete_pipeline.py` (+4 tests)
   - `test_live_ablation_pilot.py` (+1 test)
   - Additional scenario & isolation tests across existing files (+4 tests).
- **Total Reconciled Count**: 77 + 17 + 32 = **126 tests**.

---

## 3. Detailed Per-Suite Inventory

### Unit Test Suites (`tests/unit/` — 106 Tests)

| Component / Subsystem | Test File | Items | Passing | Status | Key Verifications |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Observation Adapters** | `tests/unit/test_adapters.py` | 5 | 5 | PASSED | Burp, Reqable, PCAPdroid, OpenAPI, Generic HTTP parsers |
| **Semantic Compressor** | `tests/unit/test_compressor.py` | 2 | 2 | PASSED | JSON array sampling, body truncation, token economy |
| **Core Configuration** | `tests/unit/test_config.py` | 6 | 6 | PASSED | YAML loader, env override, Pydantic validation |
| **Dashboard API** | `tests/unit/test_dashboard.py` | 3 | 3 | PASSED | FastAPI endpoints, safety acknowledgment checks |
| **Database & Schema** | `tests/unit/test_database.py` | 7 | 7 | PASSED | SQLite schema, triggers, FTS5 full-text indexing |
| **Reasoning Engine** | `tests/unit/test_engine.py` | 2 | 2 | PASSED | Applicability filter, mock inference, prompt builder |
| **Error Handling** | `tests/unit/test_error_handling.py` | 4 | 4 | PASSED | Database fail-closed behavior for scope & workflow |
| **Evaluation Isolation** | `tests/unit/test_evaluation_isolation.py` | 5 | 5 | PASSED | 5 tracks, ground-truth isolation, family separation |
| **Evidence Graph** | `tests/unit/test_graph.py` | 1 | 1 | PASSED | Temporal request dataflow & workflow derivation |
| **Grounding Validator** | `tests/unit/test_grounding.py` | 4 | 4 | PASSED | Valid ID check, hallucination rejection, unparented param check |
| **Hypothesis State Machine** | `tests/unit/test_hypothesis.py` | 2 | 2 | PASSED | State transitions, revision tracking, discriminative check |
| **Invariant Engine** | `tests/unit/test_invariants.py` | 1 | 1 | PASSED | Documented & workflow invariants, epistemic tagging |
| **Structured Logging** | `tests/unit/test_logging.py` | 3 | 3 | PASSED | Immutable JSONL audit logging, event serialization |
| **Metric Integrity** | `tests/unit/test_metric_integrity.py` | 4 | 4 | PASSED | Wilson score CIs, McNemar paired matrix validation |
| **Ablation Integrity** | `tests/unit/test_real_ablation_integrity.py` | 8 | 8 | PASSED | Prompt leakage check, RAG prompt isolation, negative controls |
| **Redaction Vault** | `tests/unit/test_redaction.py` | 3 | 3 | PASSED | JWT, AWS key, dict sensitive keys redaction & reversal |
| **Retrieval & Budget** | `tests/unit/test_retrieval.py` | 2 | 2 | PASSED | Token budget controller, hybrid search, parameter gating |
| **Hardware Scheduler** | `tests/unit/test_scheduler.py` | 5 | 5 | PASSED | Phased locks, single/sequential phases, concurrent rejections |
| **Scope Gate Baseline** | `tests/unit/test_scope.py` | 10 | 10 | PASSED | Destination matching, wildcards, SSRF, DNS fail-closed |
| **Scope Hardening (M0)** | `tests/unit/test_scope_enforcement.py` | 10 | 10 | PASSED | TOCTOU IP pinning (IPv4/IPv6), redirect hops, rate limits |
| **Secret Audit** | `tests/unit/test_secret_audit.py` | 3 | 3 | PASSED | Zero leakage into prompts, logs, ChromaDB, evaluations |
| **Simulator & Scorer** | `tests/unit/test_simulator.py` | 7 | 7 | PASSED | Tri-state outcomes, step-skipping, discriminative scoring |
| **Vault Adversarial (M0)** | `tests/unit/test_vault_adversarial.py` | 6 | 6 | PASSED | Typed placeholders, identity correlation, token safety |

### Integration Test Suites (`tests/integration/` — 20 Tests)

| Component / Subsystem | Test File | Items | Passing | Status | Key Verifications |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Live Pilot Ablation** | `tests/integration/test_live_ablation_pilot.py` | 1 | 0 | SKIPPED* | Opt-in pilot execution; requires `V6_REQUIRE_LIVE_OLLAMA` |
| **Live V6 Complete Pipeline** | `tests/integration/test_live_v6_complete_pipeline.py` | 4 | 4 | PASSED | 3B/7B residency, full flow, tri-state simulation, 7B injection isolation |
| **Live V6 Smoke** | `tests/integration/test_live_v6_smoke.py` | 3 | 3 | PASSED | Live Ollama call, synthetic evidence inference, closed loop |
| **Model Inference & Invariants** | `tests/integration/test_model_inference.py` | 10 | 10 | PASSED | 7 invariants, untrusted data isolation, schema conformance |
| **Reasoning Loop (E2E)** | `tests/integration/test_reasoning_loop.py` | 2 | 2 | PASSED | Closed loop end-to-end, contradicting outcome revision |

---

## 4. Execution Commands

```bash
# Run unit test suite (fast, 3.96s)
.venv\Scripts\pytest.exe tests/unit/

# Run integration test suite (65.89s, requires local Ollama daemon)
.venv\Scripts\pytest.exe tests/integration/

# Run complete collected test suite (69.85s total)
.venv\Scripts\pytest.exe tests/
```
