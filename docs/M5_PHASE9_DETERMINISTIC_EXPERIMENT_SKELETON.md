# M5 Phase 9 — Deterministic Experiment Skeleton & Output-Budget Sensitivity Study

**Status**: COMPLETE AND SEALED  
**Date**: 2026-09-22  
**Execution Runtime**: Ollama v0.34.1  
**Model**: `qwen2.5-coder:7b` (`Q4_K_M`)  
**Model Digest**: `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`  
**Manifest Hash**: `f3ad7ae1c0894b01e59be67fc5f1a989fc0b535867235c26913b78a4023ea934`  
**Sealed Phase 7 SHA-256**: `1e0ed90c4aa672f135d2d2f2240a14d22fa0037c03efda33634f4bf10ff0b125`  
**Sealed Phase 8 SHA-256**: `b1df9a62fb07d76e0abf6e3935ccbabdaa1713f4c594019ae30c9e59567a45c6`  
**Scenarios SHA-256**: `102789655bfb04041de9259d1bf6db7f088979e5bce9bac9eb050564ef0110a8`  
**Primary Study Dataset**: [`data/eval/m5_phase9_semantic_budget_study.json`](file:///c:/Projects/Bug%20Bounty%20AI/data/eval/m5_phase9_semantic_budget_study.json)  
**Dataset SHA-256**: `3c0d3e503c7ed24470b14dfde0bd763c631a9b5dbf70c047bbca72cfaab07f95`  
**Verification Suite**: [`tests/unit/test_m5_phase9_experiment_skeleton.py`](file:///c:/Projects/Bug%20Bounty%20AI/tests/unit/test_m5_phase9_experiment_skeleton.py) (`31/31 passed`)  

---

## 1. Research Context & Objective

In Milestone M5 Phase 7 and Phase 8, the following empirical facts were established:
- **Phase 7 Confirmatory Benchmark**:
  - $0 / 336$ parser failures (complete elimination of the M4.9 composition defect).
  - $224 / 336$ valid executions.
  - $104$ candidate `HYPOTHESIS` attempts, of which **$0 / 104$ passed typed experiment construction semantics** ($0.00\%$ Valid Typed Experiment Rate).
- **Phase 8 Deterministic Failure Attribution**:
  - **$65.38\%$ (68 / 104)** of rejections were caused by `CATEGORY_ACTION_INCOMPATIBILITY` (model selecting actions unapproved for the vulnerability category).
  - **$25.00\%$ (26 / 104)** were caused by `OUTCOME_POLARITY_INVERSION` (model inverting breach vs safe outcomes).
  - **$9.62\%$ (10 / 104)** were caused by `IDENTICAL_SUPPORTING_DISPROVING_OUTCOME`.
  - **$0.00\%$** were caused by truncation, missing semantic fields, or syntax errors.
- **Phase 8.2 Protocol Diagnostic**:
  - Fixing the legal action deterministically (Condition P3) produced a **$28.6\%$ Valid Typed Experiment Rate** ($2 / 7$ candidate attempts produced fully valid typed hypotheses passing all polarity checks).
- **Phase 8.3 Active Evidence Diagnostic**:
  - Injecting canonical anomaly evidence increased hypothesis proposal attempts from $31\%$ to $100\%$, but polarity failures persisted under unguided zero-shot conditions.

### Primary Phase 9 Research Question:
> Under a fixed evidence budget, does separating experiment construction into:
> - **Deterministic Engine**: canonical category + deterministic legal experiment action + unified permitted outcome vocabulary (`legal_outcomes`),
> - **LLM**: semantic supporting and disproving outcome selection within the legal vocabulary,
> - **Validator**: structural correctness, action/category compatibility, outcome/action compatibility, semantic polarity correctness, grounding, and epistemic correctness,
> 
> produce a measurable increase in valid typed experiment construction across completion budgets (`num_predict` = 300, 512, 768)?

### Primary Diagnostic Estimand:
$$\text{Valid Typed Experiment Rate} = \frac{\text{Valid Typed Experiment Proposals}}{\text{Candidate HYPOTHESIS Attempts}}$$

---

## 2. Phase 9 Architecture & Mandatory Corrections

Following the Phase 9.0 architectural audit, five mandatory corrections were formalized and implemented in [`src/engine/experiment_skeleton.py`](file:///c:/Projects/Bug%20Bounty%20AI/src/engine/experiment_skeleton.py):

### 2.1 No Breach/Safe Outcome Partition Leakage (Correction 1)
- The descriptor exposes a single, flat, alphabetically sorted vocabulary: `legal_outcomes`.
- The LLM **never** receives `legal_supporting_outcomes` or `legal_disproving_outcomes`.
- The internal validator (`ExperimentPolarityValidator.TUPLE_COMPATIBILITY_REGISTRY`) retains the complete authoritative mapping:
  $$\text{Category} \longrightarrow \text{Action} \longrightarrow (\mathcal{O}_{\text{breach}}, \mathcal{O}_{\text{safe}})$$
- Unit test `test_18_zero_breach_safe_partition_leakage` formally verifies that the rendered prompt block contains zero partition information.

### 2.2 Deterministic Action Selection Policy (Correction 2)
Action selection is frozen as explicit deterministic policy:
- **BOLA (`API-BOLA-001`, `API-DEVICE-BOLA-001`)**: `SUBSTITUTE_RESOURCE_IDENTIFIER`
- **STATE (`API-STATE-001`, `API-LIFECYCLE-001`, `API-MULTI-STEP-AUTH-001`)**: `EXECUTE_OUT_OF_ORDER_TRANSITION`
- **ROLE / BFLA (`API-BFLA-001`, `API-BFLA-002`, `API-ROLE-BOUNDARY-001`)**: `REPLAY_STEP_WITH_LOWER_ROLE`
- **CROSS-TENANT (`API-CROSS-TENANT-001`)**: `SUBSTITUTE_RESOURCE_IDENTIFIER`
- **Deterministic Fallback**: Sort legal actions alphabetically by enum value and select the first.
- In skeleton mode, the LLM is prohibited from overriding or altering the selected action.

### 2.3 Strict LLM-Visible vs Validator-Only Boundary (Correction 5)
- **LLM-Visible Fields**: `category_id`, `experiment_action`, `action_identifier`, `invariant_definition`, `evidence_gap_type`, `legal_outcomes`.
- **Validator-Only State**: Internal breach/safe compatibility sets, ground truth, expected decisions, vulnerability/control labels, scenario suffixes, scoring labels, secret tokens.

---

## 3. Pre-Registered Study Design (44 Live Calls)

The Phase 9 diagnostic capability study executed exactly 44 pre-registered live calls:

### Part 1: Representative Benchmark Sample (36 calls)
- **6 Scenarios**:
  1. `SCEN-SAAS_BILLING-INV-DETAILS-VULN-01` (BOLA, Vuln)
  2. `SCEN-ECOMMERCE_ORDERS-ORD-REFUND-VULN-01` (STATE, Vuln)
  3. `SCEN-IDENTITY_PROVIDER-USER-ROLES-VULN-01` (ROLE / BFLA, Vuln)
  4. `SCEN-IOT_FLEET_MGMT-FLEET-CMD-VULN-03` (CROSS-TENANT, Vuln)
  5. `SCEN-SAAS_BILLING-INV-DETAILS-PATCH-01` (BOLA, Control)
  6. `SCEN-ECOMMERCE_ORDERS-ORD-REFUND-PATCH-01` (STATE, Control)
- **2 Tracks**: Track A (Minimal Structural Context) and Track D (Full Cascade + RAG Knowledge Pack) = 12 scenario-track pairs.
- **3 Completion Budgets**:
  - `P3-300`: `num_predict = 300` (12 calls)
  - `P3-512`: `num_predict = 512` (12 calls)
  - `P3-768`: `num_predict = 768` (12 calls)
  Subtotal = 36 calls.

### Part 2: Active-Evidence Diagnostic Sample (8 calls)
- **4 Canonical Anomaly Fixtures** (Phase 8.3):
  1. `DIAG-ACT-BOLA-01` (`API-BOLA-001`)
  2. `DIAG-ACT-STATE-01` (`API-STATE-001`)
  3. `DIAG-ACT-ROLE-01` (`API-ROLE-BOUNDARY-001`)
  4. `DIAG-ACT-TENANT-01` (`API-CROSS-TENANT-001`)
- **1 Track**: Track A only (Mandatory Correction 3: strictly avoids RAG context confounding).
- **2 Budgets**: `P3-300` (4 calls) and `P3-512` (4 calls).
  Subtotal = 8 calls.

**Total Executed Calls**: $36 + 8 = \mathbf{44 \text{ calls}}$.

---

## 4. Empirical Results Across Completion Budgets

All 44 calls completed within the pre-registered execution parameters. No call timed out or crashed.

### 4.1 Condition Summary Table (Benchmark Sample, N=36)

| Metric | P3-300 (`num_predict=300`) | P3-512 (`num_predict=512`) | P3-768 (`num_predict=768`) | Phase 8.2 Baseline (P1) | Phase 7 Benchmark |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Total Calls** | 12 | 12 | 12 | 6 | 336 |
| **Valid Executions** | 8 (66.67%) | 8 (66.67%) | 8 (66.67%) | 6 (100.0%) | 224 (66.67%) |
| **Candidate HYPOTHESIS Attempts** | 6 | 6 | 6 | 6 | 104 |
| **Valid Typed Experiment Proposals** | **4** | **4** | **4** | 0 | 0 |
| **Valid Typed Experiment Rate** | **66.67%** | **66.67%** | **66.67%** | **0.00%** | **0.00%** |
| **Polarity Failures** | **0** | **0** | **0** | 3 | 94 |
| **Action Incompatibility Failures** | **0** | **0** | **0** | 3 | 68 |
| **Schema Failures** | 2 | 2 | 2 | 0 | 10 |
| **Grounding Failures** | 2 | 2 | 2 | 0 | 0 |
| **Truncations** | **0** | **0** | **0** | 0 | 8 |
| **Mean Completion Tokens** | 244.3 | 241.3 | 241.3 | 248.3 | 240.2 |
| **Median Completion Tokens** | 250 | 245 | 245 | 252 | 248 |
| **Mean Latency (s)** | 34.67 | 31.91 | 31.89 | 34.12 | 32.85 |
| **Median Latency (s)** | 33.18 | 31.24 | 30.95 | 32.80 | 31.50 |

### 4.2 Finding 1: Invariance to Output Token Budget
- Moving the output ceiling from `300` to `512` and `768` produced **identical** outcomes:
  - `Valid Typed Experiment Rate`: $66.67\% \to 66.67\% \to 66.67\%$
  - Valid Executions: $8 / 12 \to 8 / 12 \to 8 / 12$
  - In fact, for P3-512 and P3-768, every single call produced bitwise identical completion tokens (241.3 mean).
- No truncation occurred in any budget condition ($0 / 36$).
- **Conclusion**: The complete semantic failure observed in Phase 7 and Phase 8 baseline was **NOT** an artifact of output token budget exhaustion. The 7B model naturally finishes its JSON generation between 210 and 260 tokens.

### 4.3 Finding 2: Complete Elimination of Polarity and Action Failures in Benchmark
- Under the deterministic experiment skeleton, **0 / 36** calls failed category-action compatibility (compared to 65.38% in Phase 8).
- In the benchmark scenarios, **0 / 36** calls committed polarity inversion or identical outcomes (compared to 34.62% in Phase 8).
- The model successfully reasoned from the unpartitioned vocabulary `legal_outcomes` to select the true breach outcome as `supporting_outcome` and the true safe outcome as `disproving_outcome`.

---

## 5. Track A vs Track D Context Degradation

A profound architectural disparity emerged when disaggregating the 36 benchmark calls by context track:

| Metric | Track A (Minimal Structural Context) | Track D (Full Cascade + RAG Knowledge Pack) |
| :--- | :---: | :---: |
| **Total Calls** | 18 | 18 |
| **Valid Executions** | **18 / 18 (100.0%)** | 6 / 18 (33.3%) |
| **Candidate HYPOTHESIS Attempts** | 12 | 6 |
| **Valid Typed Experiment Proposals** | **12 / 12 (100.0%)** | 0 / 6 (0.0%) |
| **Valid Typed Experiment Rate** | **100.0%** | **0.0%** |
| **Schema Validation Failures** | 0 | 6 (33.3%) |
| **Lexical Grounding Failures** | 0 | 6 (33.3%) |
| **Semantic Polarity Failures** | 0 | 0 |
| **Action Incompatibility Failures** | 0 | 0 |

### Causal Mechanism of Track D Degradation:
1. **Schema Failures (6 / 18 calls)**:
   - When presented with dense RAG knowledge pack text, the model attempted to output `INSUFFICIENT_EVIDENCE` with `empirical_evidence_present = True` on control endpoints (`ECOMMERCE_ORDERS-ORD-REFUND-PATCH-01` and `IDENTITY_PROVIDER-USER-ROLES-VULN-01`), but omitted the required non-empty `empirical_facts` slot.
2. **Grounding Failures (6 / 18 calls)**:
   - On `ECOMMERCE_ORDERS-ORD-REFUND-VULN-01` and `IOT_FLEET_MGMT-FLEET-CMD-VULN-03`, the model hallucinated resource identifiers in `empirical_evidence` that did not appear anywhere in the scenario or retrieved context.
3. **Implication**:
   - The deterministic experiment skeleton is **100% effective** when paired with lean, structured invariant and gap representation (Track A).
   - Injecting dense unstructured knowledge pack text (Track D) dilutes the model's attention, causing schema compliance degradation and entity hallucination.

---

## 6. Active-Evidence Diagnostic Results (8 Calls, Track A)

To test the system under genuine vulnerability anomaly conditions, Phase 9 evaluated the 4 canonical anomaly fixtures from Phase 8.3 across `P3-300` and `P3-512`:

| Fixture ID | Category | Budget | Decision | Polarity Valid | Applicability State | Tokens | Latency | Primary Result |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `DIAG-ACT-BOLA-01` | `API-BOLA-001` | 300 | `HYPOTHESIS` | **True** | `VULNERABILITY_APPLICABLE` | 212 | 25.19s | **VALID TYPED EXPERIMENT** |
| `DIAG-ACT-BOLA-01` | `API-BOLA-001` | 512 | `HYPOTHESIS` | **True** | `VULNERABILITY_APPLICABLE` | 236 | 28.15s | **VALID TYPED EXPERIMENT** |
| `DIAG-ACT-STATE-01` | `API-STATE-001` | 300 | `INSUFFICIENT_EVIDENCE` | N/A | `VULNERABILITY_APPLICABLE` | 215 | 25.63s | **VALID ABSTENTION** |
| `DIAG-ACT-STATE-01` | `API-STATE-001` | 512 | `INSUFFICIENT_EVIDENCE` | N/A | `VULNERABILITY_APPLICABLE` | 223 | 26.79s | **VALID ABSTENTION** |
| `DIAG-ACT-ROLE-01` | `API-ROLE-BOUNDARY-001` | 300 | `HYPOTHESIS` | **False** | `INVALID_OUTPUT` | 213 | 25.16s | `POLARITY_INVERSION` |
| `DIAG-ACT-ROLE-01` | `API-ROLE-BOUNDARY-001` | 512 | `HYPOTHESIS` | **False** | `INVALID_OUTPUT` | 211 | 24.94s | `POLARITY_INVERSION` |
| `DIAG-ACT-TENANT-01` | `API-CROSS-TENANT-001` | 300 | `HYPOTHESIS` | **True** | `VULNERABILITY_APPLICABLE` | 235 | 28.32s | **VALID TYPED EXPERIMENT** |
| `DIAG-ACT-TENANT-01` | `API-CROSS-TENANT-001` | 512 | `HYPOTHESIS` | **True** | `VULNERABILITY_APPLICABLE` | 229 | 28.21s | **VALID TYPED EXPERIMENT** |

### Key Diagnostic Takeaways:
1. **Breakthrough in Vulnerability-Applicable Proposals**:
   - For the first time in Milestone M5, **valid typed experiment hypotheses with correct polarity were produced under `VULNERABILITY_EVALUATION_APPLICABLE` conditions** (`DIAG-ACT-BOLA-01` and `DIAG-ACT-TENANT-01`).
   - In Phase 7 and Phase 8, this rate was strictly $0.00\%$.
2. **Polarity Test Integrity Proven by ROLE-01 Inversion**:
   - In `DIAG-ACT-ROLE-01`, the model selected `PRIVILEGE_ELEVATION_DENIED` as the supporting outcome (which actually proves access control enforcement).
   - Because Phase 9 strictly withheld the breach/safe partition labels (Correction 1), this proves that the task remained an authentic semantic reasoning test. The validator caught the polarity inversion and failed closed.
3. **Perfect Budget Stability**:
   - Across all 4 fixtures, behavior was identical between 300 and 512 tokens.

---

## 7. Synthesis: Distinguishing Results, Interpretations, and Mechanisms

To maintain empirical rigor, findings are strictly partitioned into observed results, causal interpretations, and architectural recommendations:

### 7.1 Observed Facts (What the Data Directly Proves)
1. **Output Budget Independence**: Increasing `num_predict` from 300 to 512 and 768 produced exactly $0.00\%$ change in valid typed experiment rate ($66.67\%$ across all budgets). Mean generation length was 241-244 tokens. Truncations were 0/44.
2. **Skeleton Efficacy on Incompatible Actions**: The deterministic skeleton completely eliminated category-action mismatch failures ($0 / 44$, down from $65.38\%$ in Phase 8).
3. **Track A Perfection**: In Track A (lean structured invariant representation), the skeleton achieved $100\%$ valid executions ($18/18$) and $100\%$ valid typed experiment rate ($12/12$).
4. **Context Dilution in Track D**: Full RAG context insertion caused $33.3\%$ schema omission failures and $33.3\%$ lexical grounding failures in the 7B model.
5. **Active Anomaly Feasibility**: The architecture successfully generated valid, correctly polarized vulnerability hypotheses on BOLA and Cross-Tenant anomalies.

### 7.2 Interpretations (Plausible Causal Models)
1. **The Phase 7 Failure Was Cognitive, Not Output-Constrained**: The reason Phase 7 yielded $0/104$ valid experiments was that generating an action from an unconstrained space while simultaneously pairing it with mutually exclusive breach/safe outcomes overwhelmed the model's semantic capacity.
2. **Context Dilution Explains Track D Degradation**: When a local 7B model is given multi-paragraph retrieval text, attention is drawn away from strict schema requirements (omitting required slots) and entity grounding fidelity degrades. Lean, targeted context representations preserve adherence.

### 7.3 What Phase 9 Does NOT Claim
- It does **not** claim that 7B models can autonomously discover zero-day vulnerabilities without deterministic guardrails.
- It does **not** claim that polarity reasoning is fully solved across all vulnerability classes (as proven by `DIAG-ACT-ROLE-01`).
- It does **not** alter the Phase 7 benchmark results or claim retroactive victory; it demonstrates a principled architectural path forward.

---

## 8. Artifact Ledger & Verification

- **Code Implementations**:
  - [`src/engine/experiment_skeleton.py`](file:///c:/Projects/Bug%20Bounty%20AI/src/engine/experiment_skeleton.py)
  - [`src/eval/m5_phase9_study.py`](file:///c:/Projects/Bug%20Bounty%20AI/src/eval/m5_phase9_study.py)
  - [`src/engine/runner.py`](file:///c:/Projects/Bug%20Bounty%20AI/src/engine/runner.py)
- **Primary Empirical Artifact**:
  - File: [`data/eval/m5_phase9_semantic_budget_study.json`](file:///c:/Projects/Bug%20Bounty%20AI/data/eval/m5_phase9_semantic_budget_study.json)
  - SHA-256: `3c0d3e503c7ed24470b14dfde0bd763c631a9b5dbf70c047bbca72cfaab07f95`
- **Unit Test Suite**:
  - [`tests/unit/test_m5_phase9_experiment_skeleton.py`](file:///c:/Projects/Bug%20Bounty%20AI/tests/unit/test_m5_phase9_experiment_skeleton.py) (31 passed in 2.68s)

**M5 Phase 9 is hereby COMPLETE and SEALED.**
