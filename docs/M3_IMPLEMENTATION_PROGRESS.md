# Milestone M3: VAPT Knowledge RAG — Implementation Progress

**Authoritative Specification**: M3 Plan v2.3.8 (`docs/M3_VAPT_KNOWLEDGE_RAG_PLAN.md`)  
**Planning Freeze Tag**: `m3-v2.3.8-planning-freeze`  
**Planning Freeze Tag Target Commit**: `819b83399e24080bf2942c3941cc96728885df49`  
**Planning Freeze Tag Object SHA**: `dbe42947d48df9c9f971af167631031cb8b294e0`  
**Current Git HEAD**: `703768be7b96aa04116ee1103c982d578f4aec94` (`docs(m2): preserve phase 11 research artifacts`)  
**Tag Ancestry**: Verified (`git merge-base --is-ancestor 819b83399e24080bf2942c3941cc96728885df49 HEAD` returns true; parent commit is `819b833`)  
**Implementation Start Timestamp**: `2026-09-20T09:43:33+05:30`  
**Repository Cleanliness**: Working tree verified clean prior to Block A  

---

## 1. Lineage & Checkpoint References

| Milestone / Checkpoint | Commit SHA | Description |
| :--- | :--- | :--- |
| **M2 Production Validation Freeze** | `f335b98` | Phase 11.6 production validation artifacts frozen |
| **M2.75 State Engine** | `d76abb3` | Deterministic M2.75 state engine implemented |
| **M2.75 Security Boundaries** | `a753ebf` | Hardened M2.75 execution and security boundaries |
| **M3 Planning Specification Freeze** | `819b833` | Frozen M3 Plan v2.3.8 specification (Tag: `m3-v2.3.8-planning-freeze`) |
| **M2 Artifact Preservation (HEAD)** | `703768b` | Preserved Phase 11 research artifacts |

---

## 2. Implementation Block Tracker

- [x] **Block A: Storage & Ingestion Foundations (Phases M3.1 → M3.5)** `[COMPLETED]`
  - [x] M3.1: Knowledge Schemas & Models (`src/knowledge/models.py`)
  - [x] M3.2: Corpus Sourcing & Licensing Allowlist Verification (`data/vapt_corpus/sources.json`)
  - [x] M3.3: Offline Corpus Ingestion & Markdown Normalization (`src/knowledge/ingestion.py`)
  - [x] M3.4: Corpus Manifest, RFC 9162 Merkle Tree & Ed25519 Detached Signature Generation (`src/knowledge/provenance.py`, `src/knowledge/builder.py`)
  - [x] M3.5: Deterministic Semantic Chunking (`SemanticMarkdownChunker` v1.0.0 in `src/knowledge/chunking.py`) & SQLite FTS5 Storage (`src/knowledge/store.py`)
- [ ] **Block B: Retrieval Backends, Qualification & Oracle Parity (Phases M3.6 → M3.9)** `[NOT STARTED]`
  - Note: Candidate 2 (Enhanced Pure SQLite FTS5) prioritized first in Block B implementation order per frozen plan.
- [ ] **Block C: Context Integration, Poisoning Defense & Grounding (Phases M3.10 → M3.14)** `[NOT STARTED]`
- [ ] **Block D: Ablation Harness, Human Study & Artifact Generation (Phases M3.15 → M3.19)** `[NOT STARTED]`

---

## 3. Current Phase Status

- **Current Implementation Block**: Block A `[VERIFIED & COMPLETED]`
- **Completed Phases in Block A**:
  - Phase M3.0: Architecture & Experimental Design Freeze (`819b83399e24080bf2942c3941cc96728885df49`)
  - Phase M3.1: Knowledge Schemas & Models (`src/knowledge/models.py` versioned under `v3.0.0`)
  - Phase M3.2: Corpus Sourcing & Redistribution Allowlist (`data/vapt_corpus/sources.json` approved sources: WSTG, ASVS, CWE, Platform Invariants)
  - Phase M3.3: Offline Corpus Ingestion, Normalization & Quarantine Flagging (`src/knowledge/ingestion.py`)
  - Phase M3.4: RFC 9162 Merkle Tree, Canonical JCS & Ed25519 Detached Signing (`src/knowledge/provenance.py`, `data/vapt_corpus/manifest.json`, `manifest.sig`, `trust_root.json`)
  - Phase M3.5: Semantic Chunking (`src/knowledge/chunking.py` with code atomicity & breadcrumb propagation) & SQLite FTS5 Storage (`src/knowledge/store.py` with dual-store isolation)
- **Next Implementation Boundary**: Block B (Phases M3.6 → M3.9) — Retrieval backends, query builders, and qualification harness.

---

## 4. Test Verification Baseline & Block A Results

- **Pre-Implementation Baseline**:
  - Unit Tests Run: 267 passed, 0 failed, 2 warnings in 9.66s
- **Block A Test Run**:
  - Unit Tests Run: 292 passed, 0 failed, 2 warnings in 9.92s
  - New Unit Tests Added (25 total):
    * `tests/unit/test_knowledge_models.py`: 5 passed
    * `tests/unit/test_knowledge_ingestion.py`: 5 passed
    * `tests/unit/test_knowledge_chunking.py`: 4 passed
    * `tests/unit/test_knowledge_provenance.py`: 6 passed
    * `tests/unit/test_knowledge_store.py`: 4 passed
    * `tests/unit/test_knowledge_corpus_integrity.py`: 1 passed (full end-to-end trust chain validation)
  - Regression Status: 100% of pre-existing M2/M2.75 unit tests (267) continue to pass without modification.

---

## 5. Artifact Manifest (Block A Deliverables)

| File / Component | Purpose / Specification Reference |
| :--- | :--- |
| `src/knowledge/models.py` | Schema v3.0.0 definitions (`KnowledgeChunk`, `VaptKnowledgePack`, `EvidenceGapType`, `EpistemicTier`) |
| `src/knowledge/ingestion.py` | Markdown normalization (LF, whitespace collapse) & allowlist verification |
| `src/knowledge/chunking.py` | `SemanticMarkdownChunker v1.0.0` with 4-level recursive subdivision & code atomicity |
| `src/knowledge/provenance.py` | RFC 9162 Merkle tree hash, RFC 8785 JCS serialization, Ed25519 signing/verification |
| `src/knowledge/store.py` | Isolated `vapt_knowledge.db` SQLite FTS5 database with BM25 lexical search & `chunk_id ASC` tie-breaking |
| `src/knowledge/builder.py` | Orchestration pipeline to ingest, chunk, Merkle-hash, sign, and build corpus store |
| `data/vapt_corpus/sources.json` | Redistribution allowlist for WSTG, ASVS, CWE, and Platform Invariants |
| `data/vapt_corpus/*.md` | Curated seed documents (6 documents, 23 chunks) |
| `data/vapt_corpus/manifest.json` | Signed manifest (Merkle root: `bd4abf9c97ad437b1c2d566c53ba4c5b0921108a2309c17a1d7ec948c93a57dd`) |
| `data/vapt_corpus/manifest.sig` | 64-byte detached Ed25519 digital signature |
| `data/vapt_corpus/trust_root.json` | Pinned offline trust root record (`KEY-M3-OFFLINE-ROOT-01`) |
| `data/vapt_corpus/vapt_knowledge.db` | Populated SQLite FTS5 database |

---

## 6. Known Limitations & Strict Scope Constraints

1. **Local & Offline Boundary**: M3 is strictly local, offline, deterministic, bounded, and single-node. Zero external network calls or online crawling.
2. **Dual Store Separation**: Target evidence (`evidence.db`) and VAPT knowledge (`vapt_knowledge.db`) are strictly isolated. No cross-querying.
3. **Epistemic Tier Invariant**: `supporting_evidence_ids` may contain `FACT-xxx` only; `cited_methodology_chunk_ids` may contain `CHK-xxx` only.
4. **Target-Evidence Retriever Preservation**: `src/retrieval/hybrid.py` is the existing Target-Evidence retriever and remains completely untouched.
5. **Fail-Safe Degradation**: If VAPT knowledge fails cryptographic integrity or licensing verification, reasoning falls back safely to un-augmented 7B reasoning with 0 tokens injected into P4.
6. **Implementation Order**: Candidate 2 (Pure SQLite FTS5) will be implemented first in Block B for engineering efficiency, preserving all 3 candidate paths for experimental qualification.

---

## 7. Deviations from Frozen Plan

*None. Implementation strictly conforms to M3 Plan v2.3.8.*
