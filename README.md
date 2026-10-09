# Local AI-Assisted Bug Bounty Research Platform
### v13.0 Full Security Assessment Workspace

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT%2FApache--2.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1555%2B%20passing-brightgreen.svg)](tests/)
[![Security Invariants](https://img.shields.io/badge/security%20invariants-100%25%20enforced%20(35%2F35)-success.svg)](docs/M13_SECURITY.md)
[![Benchmark Evaluation](https://img.shields.io/badge/M13%20benchmark-100%25%20(360%2F360)-brightgreen.svg)](reports/M13_FINAL_REPORT.md)
[![Hardware Target](https://img.shields.io/badge/hardware-Ryzen%205%205600H%20%7C%20RTX%203050%204GB%20%7C%2024GB%20RAM-orange.svg)](#hardware-aware-phased-scheduling)
[![Local Inference](https://img.shields.io/badge/inference-Ollama%20(Qwen%202.5%20Coder%203B%2F7B)-purple.svg)](#quickstart--installation)

---

An **evidence-grounded, local-first, human-in-the-loop security research assistant** designed to operate strictly on consumer hardware without cloud dependencies, unconstrained autonomous exploitation, or ungrounded hallucinations.

The platform transforms raw passive telemetry (HTTP captures, HAR, PCAPdroid, OpenAPI specs, decompiled APKs/binaries) into mathematically verified security invariants, structured hypotheses, controlled non-destructive experiments, and human-verified findings across a **unified 12-section Security Assessment Workspace**.

---

## Table of Contents
1. [The Research Question & Philosophy](#the-research-question--philosophy)
2. [Governing Architectural Law](#governing-architectural-law)
3. [Zero-Tolerance Security Invariants](#zero-tolerance-security-invariants)
4. [Hardware-Aware Phased Scheduling](#hardware-aware-phased-scheduling)
5. [The 12-Section Assessment Workspace](#the-12-section-assessment-workspace)
6. [Milestone Architecture & Evolution (M0–M13)](#milestone-architecture--evolution-m0m13)
7. [Repository Layout](#repository-layout)
8. [Audited Verification & Benchmark Results](#audited-verification--benchmark-results)
9. [Quickstart & Installation](#quickstart--installation)
10. [Documentation Index](#documentation-index)
11. [Safety, Ethics & Responsible Disclosure](#safety-ethics--responsible-disclosure)

---

## The Research Question & Philosophy

> **"Under a fixed evidence budget, does an explicit Application Model → Security Invariant → Evidence Gap → Hypothesis → Experiment architecture improve security-hypothesis precision, abstention quality, and human investigation efficiency compared to conventional LLM + RAG?"**

This is **not** an automated vulnerability scanner or autonomous exploitation bot. The AI serves exclusively as a **hypothesis generator and analytical reasoning copilot** bound by deterministic code and human authority:

```text
Observe & Ingest (Passive)
       │
       ▼
Normalize & Redact (Zero Secrets Leaked)
       │
       ▼
Evidence Graph (Assets, Identities, State Transitions)
       │
       ▼
Derive Security Invariants (Epistemic Origins Tagged)
       │
       ▼
Identify Evidence Gaps & Formulate Hypotheses (Grounding Validated)
       │
       ▼
Controlled Experimentation (Plane A Safe Lab vs. Plane B Manual Procedures)
       │
       ▼
Authoritative 13-Point Human Review Checklist
       │
       ▼
Human-Verified Security Findings & Executive / Technical Reporting
```

---

## Governing Architectural Law

### **THE WORKSPACE IS A CONTEXT INTERFACE, NEVER AN AUTHORITY.**

- **AI Models Have Zero Verification Authority**: No LLM, heuristic, or retrieval score can approve an assessment, expand scope, fabricate evidence, or verify a security finding.
- **Human-in-the-Loop Supremacy**: Only a human security researcher verifying an authoritative 13-point deterministic checklist can confirm a finding (`HUMAN_VERIFIED`).
- **Fail-Closed Default**: Missing authorization records, unresolvable targets, ambiguous scope definitions, or absent credentials fail closed immediately.
- **Air-Gapped Context Boundaries**: Research memory, MITRE ATT&CK knowledge, PortSwigger materials, and prior art cannot be injected as target facts. Target facts derive exclusively from cryptographically hashed, parsed passive observations.

---

## Zero-Tolerance Security Invariants

The platform enforces **35 formal security invariants** across every subsystem:

| Invariant Family | Core Protections | Implementation |
| :--- | :--- | :--- |
| **Scope Invariant** | Fail-closed DNS TOCTOU defense; IP-level socket pinning; strict blocking of private/reserved CIDRs (RFC 1918, RFC 3927, RFC 4193, loopback, broadcast); redirect re-evaluation on every hop; cross-client rate limiting. | [`src/scope/gate.py`](src/scope/gate.py), [`src/scope/client.py`](src/scope/client.py) |
| **Grounding Invariant** | Absolute rejection of hallucinated IDs. Every referenced asset, parameter, identity, and evidence ID must exist in the canonical registry and satisfy structural hierarchy. | [`src/validation/grounding.py`](src/validation/grounding.py) |
| **Epistemic Segregation** | Strict labeling across 4 origins: `DOCUMENTED` (specs), `OBSERVED` (traffic), `DETERMINISTIC_DERIVATION` (computed code), `MODEL_PROPOSED` (AI hypotheses). Model outputs are never silently promoted to facts. | [`src/invariants/models.py`](src/invariants/models.py), [`src/workspace/models.py`](src/workspace/models.py) |
| **Secret Quarantine** | Raw credentials (JWTs, Bearer tokens, API keys, session cookies) are quarantined into typed placeholders (`[REDACTED_JWT_1]`), preserving cross-identity correlation without exposing secret material to prompts, vectors, or logs. | [`src/evidence/vault.py`](src/evidence/vault.py) |
| **Prompt Injection Defense** | Ingested external data carries `trust: UNTRUSTED` and is wrapped in cryptographic delimiter markers. Telemetry is sanitized against ANSI sequences and log injection. | [`src/evidence/normalizer.py`](src/evidence/normalizer.py), [`src/memory/service.py`](src/memory/service.py) |
| **Memory Isolation** | Memory is context, not authority. Cross-tenant and cross-assessment pre-ranking preclusion prevents data leakage. Zero secret persistence in memory embeddings. | [`src/memory/models.py`](src/memory/models.py), [`src/memory/service.py`](src/memory/service.py) |
| **Human Review Authority** | State transitions to `CONFIRMED` or `HUMAN_VERIFIED` require explicit human reviewer identity and satisfying all 13 checklist criteria. Unverified items remain quarantined as draft hypotheses. | [`src/review/service.py`](src/review/service.py), [`src/assessment/manager.py`](src/assessment/manager.py) |

---

## Hardware-Aware Phased Scheduling

Designed specifically for **budget consumer workstations** (AMD Ryzen 5 5600H, 24 GB RAM, NVIDIA GeForce RTX 3050 Laptop GPU with 4 GB VRAM) to prevent CPU/IO and VRAM thrashing:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Recon & Telemetry Ingestion (100% CPU Allocation)                   │
│ - Burp / Reqable / PCAPdroid / OpenAPI parsing & artifact hashing (SHA-256) │
│ - Secret redaction & typed placeholder assignment (RedactionVault)          │
│ - Evidence Graph node creation & temporal workflow extraction               │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 2: Indexing & Hybrid Retrieval (100% CPU Allocation)                   │
│ - SQLite FTS5 (BM25) full-text indexing & exact-identifier gating           │
│ - ChromaDB local vector embeddings (persisted on disk)                      │
│ - Epistemic invariant synthesis & evidence gap detection                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ PHASE 3: Analytical Reasoning Sweeps (100% GPU Allocation — Single Model)   │
│ - Ollama local inference: Qwen 2.5 Coder 3B (broad triage & drafting)       │
│ - Ollama local inference: Qwen 2.5 Coder 7B (deep reasoning & survivor sets)│
│ - Strict Token Budget Controller (pinned 2048–4096 tokens) preventing swap  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The 12-Section Assessment Workspace

The platform provides a complete web-based security research cockpit (`frontend/` + FastAPI backend) organizing the full assessment lifecycle into 12 dedicated views:

1. **Overview & Lifecycle Dashboard**: Live assessment status, rules of engagement summary, progress gauges, and real-time activity metrics.
2. **Authorization & Scope Boundaries**: Cryptographic authorization records, permitted domains, IP ranges, rate limits, disallowed techniques, and live `ScopeGate` preflight testing.
3. **Target Asset Inventory**: Interactive graph of hostnames, IP addresses, web applications, mobile packages, APIs, and cloud services with criticality ratings.
4. **Attack Surface & Endpoints**: Normalized inventory of discovered HTTP endpoints, methods, authentication requirements, and associated parameters.
5. **Cryptographic Artifact Registry**: Ingested raw files (HAR captures, OpenAPI specs, APKs, binaries, logs) with SHA-256 integrity verification, quarantine states, and metadata.
6. **Research & Prior Art Knowledge**: Hybrid vector and BM25 search over MITRE ATT&CK techniques, CWE definitions, OWASP guidelines, and verified public disclosures.
7. **Hypotheses & Security Invariants**: Active security hypotheses, underlying security invariants, epistemic origin tracking, and evidence gap identification.
8. **Evidence Lineage Graph & Provenance**: Visual directed acyclic graph (DAG) tracing how raw artifacts derive canonical observations and support hypotheses.
9. **Controlled Experiments & Safe PoCs**: Dual-plane experiment execution:
   - *Plane A (Safe Lab)*: Automated deterministic execution against headless sandboxes.
   - *Plane B (Safe PoC)*: Non-destructive, human-guided manual reproduction steps with rollback procedures and curl templates.
10. **Findings Review & 13-Point Checklist**: Authoritative human verification modal enforcing all 13 criteria (scope adherence, reproduction validity, CVSS scoring, remediation verification).
11. **Executive & Technical Reporting**: Export engine producing compliant executive summaries and technical markdown reports with clear quarantine disclaimers.
12. **Memory, Knowledge & Audit Timeline**: Multi-tier research memory browser (episodic, semantic, procedural) alongside an immutable cryptographic audit log.

---

## Milestone Architecture & Evolution (M0–M13)

```text
 M0 ──► M1 ──► M2 ──► M3 ──► M4 ──► M5 ──► M6 ──► M7 ──► M8 ──► M9 ──► M10 ──► M10.5 ──► M11 ──► M11.5 ──► M12 ──► M13
Scope   Ground  3B/7B  VAPT   Proxy   EXP0006 Multi- Consen- Human   Cyber  Deep    Repo    Safe    Reliab-  Memory  Full
Vault   Simul.  Casc.  RAG    Adapt.  Bench.  Agent  sus     Review  KB     Android Clean   PoC     ility UX (Epist) Workspace
```

| Milestone | Version Tag | Core Focus & Breakthroughs |
| :--- | :--- | :--- |
| **M0** | Baseline | Strict `ScopeGate` TOCTOU defense, RFC 1918 blocking, `RedactionVault` secret isolation. |
| **M1** | Baseline | `GroundingValidator`, closed-loop headless simulator with tri-state outcomes. |
| **M2** | Baseline | Two-tier 3B/7B cascade routing, triage escalation, and budget monitoring. |
| **M3** | `m3-v2.3.8-planning-freeze` | VAPT Knowledge Base RAG, methodology retrieval, technique indexing. |
| **M4** | `m4-v1.1.0-planning-freeze` | Multi-adapter passive ingestion (Burp, Reqable, PCAPdroid, OpenAPI). |
| **M5** | `m5-phase10-final-audited` | 5-track comparative ablation benchmark (EXP-0006) across 84 scenarios. |
| **M6** | Baseline | Multi-agent specialized analytical research dispatch. |
| **M7** | Baseline | Collaborative multi-agent consensus and adversarial peer review. |
| **M8** | Baseline | Human-in-the-loop interactive web review platform. |
| **M9** | Baseline | Comprehensive cybersecurity knowledge indexing and hybrid BM25/vector RAG. |
| **M10** | Baseline | Deep Android & Binary Reverse Engineering (APK/DEX, JNI/SO, Frida, Ghidra). |
| **M10.5**| `v10.5.0-repository-clean` | Comprehensive repository cleanup, security audit remediation, reproducibility gate. |
| **M11** | `v11.0.0-controlled-security-experiments` | Controlled Security Experiments (Plane A Safe Lab & Plane B Non-Destructive Safe PoCs). |
| **M11.5**| `v11.5.0-response-reliability-ux` | Response reliability, SSE progressive streaming, multi-turn context caching, collapsible UI. |
| **M12** | `v12.0.0-security-research-memory` | Security Research Memory (Episodic, Semantic, Procedural) with zero prompt injection and epistemic tagging. |
| **M13** | `v13.0.0-full-security-assessment-workspace` | **Unified Full Security Assessment Workspace** across all 12 operational lifecycle tabs with 35 security invariants. |

---

## Repository Layout

```text
Bug Bounty AI/
├── docs/                      # Architectural specifications, security models, ADRs
│   ├── M13_WORKSPACE_ARCHITECTURE.md
│   ├── M13_DOMAIN_MODEL.md
│   ├── M13_ASSESSMENT_WORKFLOW.md
│   ├── M13_SECURITY.md
│   └── M13_API.md
├── reports/                   # Audited engineering reports and benchmark attestations
│   ├── M13_FINAL_REPORT.md
│   ├── M12_FINAL_REPORT.md
│   └── M11.5_FINAL_REPORT.md
├── src/                       # Core Python backend engine
│   ├── assessment/            # Assessment manager, RoE, and lifecycle state engine
│   ├── workspace/             # Unified workspace service, 12-section aggregator, search
│   ├── scope/                 # ScopeGate, DNS TOCTOU, socket IP pinning, client
│   ├── evidence/              # Adapters, RedactionVault, compressor, normalizer
│   ├── graph/                 # Evidence Graph & temporal workflow engine
│   ├── invariants/            # Security invariant engine & epistemic origin tracker
│   ├── hypothesis/            # Hypothesis state machine & grounding validator
│   ├── experiments/           # Plane A Safe Lab & Plane B Non-Destructive PoC generator
│   ├── review/                # 13-point deterministic human verification checklist
│   ├── reporting/             # Compliant executive & technical report generators
│   ├── memory/                # Isolated episodic, semantic, procedural research memory
│   ├── retrieval/             # Hybrid SQLite FTS5 (BM25) & ChromaDB vector store
│   ├── engine/                # Ollama runner, 3B/7B cascade, TokenBudgetController
│   └── dashboard/             # FastAPI REST endpoints, SSE streams, loopback binding
├── frontend/                  # Modern React + TypeScript + Vite + Tailwind dashboard
│   ├── src/
│   │   ├── components/workspace/  # 12 lifecycle tab components & modals
│   │   ├── api.ts                 # Type-safe API client for workspace endpoints
│   │   └── types.ts               # Domain TypeScript interfaces
│   ├── package.json
│   └── vite.config.ts
├── tests/                     # Comprehensive testing suite (1,555+ tests)
│   ├── unit/                  # Hermetic unit tests & security invariant suites
│   └── integration/           # End-to-end lifecycle, isolation, and pipeline tests
└── data/                      # Local data stores (quarantined, ignored by git)
```

---

## Audited Verification & Benchmark Results

### M13 Full Security Assessment Workspace Evaluation
- **Benchmark Suite**: 360 test cases across 24 operational categories (`src/eval/m13_dataset.py`)
- **Pass Rate**: **100.00% (360 / 360 passed)**
- **Hard Security Invariant Violations**: **0 (Zero)**
- **Average Case Latency**: **0.18 ms**

| Benchmark Category | Cases | Pass Rate | Key Invariant Enforced |
| :--- | :---: | :---: | :--- |
| **LIFECYCLE** | 15 | 100% | Valid DAG transitions only; direct DRAFT → COMPLETED blocked. |
| **AUTHORIZATION** | 15 | 100% | Human operator signature required; AI cannot grant authorization. |
| **SCOPE** | 15 | 100% | Fail-closed boundary testing; no autonomous policy mutation. |
| **ASSET_INVENTORY** | 15 | 100% | Cryptographic binding to parent assessment; cross-tenant rejection. |
| **ARTIFACT_REGISTRY** | 15 | 100% | SHA-256 verification; corrupted hash fails closed to QUARANTINED. |
| **LINEAGE_PROVENANCE** | 15 | 100% | Causal DAG unbroken; every finding references valid evidence nodes. |
| **HYPOTHESIS_MANAGEMENT**| 15 | 100% | Grounding validation; hallucinated identifiers strictly rejected. |
| **ANALYTICAL_AGENTS** | 15 | 100% | Epistemic tagging as MODEL_PROPOSED; never elevated to facts. |
| **KNOWLEDGE_SEPARATION** | 15 | 100% | External CVE/CWE cannot be cited as target-specific evidence. |
| **MEMORY_INTEGRATION** | 15 | 100% | Pre-ranking isolation; zero prompt-injection leakage across sessions. |
| **CONTROLLED_EXPERIMENT**| 15 | 100% | Plane A safe lab isolation; fail-closed execution barriers. |
| **MANUAL_PROCEDURES** | 15 | 100% | Plane B strictly forbids autonomous execution; human guided only. |
| **HUMAN_REVIEW** | 15 | 100% | All 13 checklist points must be explicitly satisfied. |
| **FINDING_CONFIRMATION** | 15 | 100% | Verified by human operator; AI verification strictly rejected. |
| **REPORT_GENERATION** | 15 | 100% | Unverified hypotheses quarantined with clear disclaimer section. |
| **AUDIT_LOGGING** | 15 | 100% | Immutable chronological activity trail; append-only integrity. |
| **MULTI_TENANT_ISOLATION**| 15 | 100% | 0.0% cross-tenant and cross-assessment data leakage. |

### Subsystem Reliability Metrics
- **Cross-Assessment Leakage Rate**: **0.0%**
- **Cross-Tenant Leakage Rate**: **0.0%**
- **Secret Persistence Rate**: **0.0%** (Strict unredactable key rejection)
- **Memory Poisoning Resistance**: **100.0%**
- **Prompt Injection Resistance**: **100.0%**
- **Epistemic Integrity Rate**: **100.0%**

---

## Quickstart & Installation

### 1. Prerequisites
- **OS**: Windows 10/11, Linux, or macOS
- **Python**: 3.11+
- **Node.js**: 18.0+
- **Ollama**: Installed locally with models:
  ```bash
  ollama pull qwen2.5-coder:3b
  ollama pull qwen2.5-coder:7b
  ```

### 2. Backend Setup
```powershell
# Clone the repository
git clone https://github.com/HyperJay-456/Bug-Bounty-AI.git
cd "Bug Bounty AI"

# Create and activate Python virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux / macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Verify Test Suites
```powershell
# Run the hermetic offline test suite (1,555+ tests)
pytest tests/unit/ -v

# Run the M13 security invariant verification suite (35/35 invariants)
pytest tests/unit/test_m13_security_invariants.py -v

# Run the M13 benchmark evaluation harness (360/360 cases)
pytest tests/unit/test_m13_eval_benchmark.py -v
```

### 4. Frontend Workspace Setup
```powershell
cd frontend
npm install

# Run frontend tests
npm test -- --watchAll=false

# Build production bundle
npm run build

# Start frontend development server
npm run dev
```

### 5. Launch the Platform
```powershell
# In root directory, start the FastAPI backend
uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8000 --reload
```
Navigate your browser to `http://127.0.0.1:5173` (Vite dev server) or `http://127.0.0.1:8000` (FastAPI backend).

---

## Documentation Index

### Milestone 13 Deliverables
- [`docs/M13_WORKSPACE_ARCHITECTURE.md`](docs/M13_WORKSPACE_ARCHITECTURE.md): Comprehensive architectural specification for the assessment workspace.
- [`docs/M13_DOMAIN_MODEL.md`](docs/M13_DOMAIN_MODEL.md): Domain entities, schemas, and lifecycle models.
- [`docs/M13_ASSESSMENT_WORKFLOW.md`](docs/M13_ASSESSMENT_WORKFLOW.md): Step-by-step 12-phase assessment workflow guide.
- [`docs/M13_SCOPE_AND_ASSETS.md`](docs/M13_SCOPE_AND_ASSETS.md): Scope policy enforcement, asset discovery, and target validation.
- [`docs/M13_EVIDENCE_AND_PROVENANCE.md`](docs/M13_EVIDENCE_AND_PROVENANCE.md): Cryptographic artifact hashing, observation lineage, and DAG design.
- [`docs/M13_RESEARCH_INTEGRATION.md`](docs/M13_RESEARCH_INTEGRATION.md): Knowledge retrieval, external source air-gapping, and prior art indexing.
- [`docs/M13_EXPERIMENT_WORKFLOW.md`](docs/M13_EXPERIMENT_WORKFLOW.md): Plane A safe automated lab vs. Plane B non-destructive manual PoCs.
- [`docs/M13_FINDING_REVIEW_AND_REPORTING.md`](docs/M13_FINDING_REVIEW_AND_REPORTING.md): 13-point human review checklist and report export engine.
- [`docs/M13_API.md`](docs/M13_API.md): Full REST and SSE API endpoint reference.
- [`docs/M13_SECURITY.md`](docs/M13_SECURITY.md): Formal proof of all 35 security invariants.
- [`docs/M13_TESTING.md`](docs/M13_TESTING.md): Test matrix, coverage, and benchmark methodology.
- [`reports/M13_FINAL_REPORT.md`](reports/M13_FINAL_REPORT.md): Executive engineering report and quantitative benchmark attestation.

### Core Architecture & Foundational Reports
- [`ARCHITECTURE.md`](ARCHITECTURE.md): Foundational v6 system architecture.
- [`DECISIONS.md`](DECISIONS.md): Architectural Decision Records (ADRs).
- [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md): Reproduction setup guide and benchmark execution.
- [`docs/SECURITY_VAULT.md`](docs/SECURITY_VAULT.md): Secret quarantine boundaries and typed redaction.
- [`reports/M12_FINAL_REPORT.md`](reports/M12_FINAL_REPORT.md): Milestone 12 Security Research Memory Report.
- [`reports/M11.5_FINAL_REPORT.md`](reports/M11.5_FINAL_REPORT.md): Milestone 11.5 Response Reliability & UX Report.

---

## Safety, Ethics & Responsible Disclosure

This platform is strictly engineered for **authorized security research**, penetration testing within explicit written rules of engagement, and official bug bounty programs:

1. **Explicit Authorization Required**: Operating without a cryptographically valid `AuthorizationRecord` signed by authorized human stakeholders is structurally prevented by software invariants.
2. **Deterministic Scope Containment**: `ScopeGate` prevents out-of-scope network traffic, loopback probes, or private subnet probing through fail-closed IP pinning.
3. **No Autonomous Exploitation**: The platform does not exploit vulnerabilities autonomously. Plane B manual reproduction steps are presented strictly to human operators for manual verification.
4. **Responsible Disclosure**: Reports generated emphasize defensive remediation, root cause analysis, and coordinated vulnerability disclosure standards.
