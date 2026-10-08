"""Cybersecurity Knowledge & Research Orchestrator (Milestone M9 Phase 18, 19, 31).

Coordinates the two primary operating modes:
    MODE 1: CYBERSECURITY KNOWLEDGE / RESEARCH MODE
    MODE 2: AUTHORIZED SECURITY ASSESSMENT MODE (Preserves M8 architecture)

Implements deterministic 3B -> 7B cascade for knowledge Q&A:
- 3B: Intent, domain, simple explanation, query rewriting, retrieval triage, straightforward synthesis.
- 7B: Complex reasoning, comparisons, multi-source synthesis (>2 sources), conflicts, code security review, CVE analysis, deep research.

Hard Safety Invariants Enforced:
    INV-M9-01: No authorization bypass.
    INV-M9-02: No scope bypass.
    INV-M9-03: No human verification bypass.
    INV-M9-07: No external knowledge -> target evidence.
    INV-M9-08: No model hypothesis -> FACT.
    INV-M9-09: No model hypothesis -> OBSERVATION.
    INV-M9-10: No model hypothesis -> HUMAN_VERIFIED_FINDING.
    INV-M9-11: No fabricated citation.
    INV-M9-14: No knowledge source can modify assessment scope.
    INV-M9-15: No knowledge source can modify authorization state.
    INV-M9-16: No knowledge source can modify report verification state.
"""

from datetime import datetime, timezone
import hashlib
import threading
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.analysis.code_security_analyzer import CodeSecurityAnalyzer
from src.knowledge.canonical_models import (
    AuthorityLevel,
    KnowledgeAnswer,
    KnowledgeCitation,
    KnowledgeClaim,
    KnowledgeFreshnessStatus,
    KnowledgeQuery,
)
from src.knowledge.citation_engine import GroundedCitationEngine
from src.knowledge.claim_extractor import KnowledgeClaimExtractor
from src.knowledge.models import KnowledgeChunk
from src.knowledge.sufficiency_engine import (
    KnowledgeSufficiencyEvaluator,
    KnowledgeSufficiencyState,
    SufficiencyDecision,
)
from src.knowledge.taxonomies import TaxonomyResolver
from src.knowledge.vapt_corpus import VaptDomainCorpus
from src.research.conflicts import SourceConflictEngine
from src.research.research_session import ResearchSessionManager
from src.retrieval.query_rewriter import CybersecurityQueryRewriter


# Global inference mutex enforcing concurrency = 1 for the 4GB VRAM target
INFERENCE_LOCK = threading.Lock()


class KnowledgeEscalationDecision(BaseModel):
    model_tier: str  # "3B" or "7B"
    escalation_reasons: List[str] = Field(default_factory=list)
    complexity_score: float = 0.0


class CybersecurityKnowledgeOrchestrator:
    """Central orchestrator for Cybersecurity Knowledge Q&A, Research, and Code Review."""

    def __init__(self) -> None:
        self.research_manager = ResearchSessionManager()
        self.corpus_chunks = VaptDomainCorpus.get_all_chunks()

    def evaluate_escalation(
        self,
        query: str,
        retrieved_chunks: List[KnowledgeChunk],
        has_code: bool = False,
        has_conflicts: bool = False,
        is_research_mode: bool = False,
        force_7b: bool = False,
    ) -> KnowledgeEscalationDecision:
        """
        Deterministic escalation criteria deciding between 3B and 7B.
        Preserves sequential execution and 4GB VRAM constraints.
        """
        reasons: List[str] = []
        score = 0.0

        if force_7b:
            return KnowledgeEscalationDecision(model_tier="7B", escalation_reasons=["Explicit user request for 7B reasoning."])

        q_lower = query.lower()

        # Check for comparison queries
        if any(w in q_lower for w in ["vs", "compare", "contrast", "difference between"]):
            reasons.append("Multi-concept comparison requires deep reasoning.")
            score += 0.40

        # Check for code analysis
        if has_code or any(w in q_lower for w in ["def ", "class ", "function", "select ", "#include"]):
            reasons.append("Source code analysis requires 7B syntax and security inspection.")
            score += 0.50

        # Check for conflicts
        if has_conflicts:
            reasons.append("Active knowledge conflict requires 7B comparative synthesis.")
            score += 0.40

        # Check for research mode
        if is_research_mode:
            reasons.append("Multi-turn research mode active.")
            score += 0.30

        # Check for multi-source synthesis (> 2 chunks)
        if len(retrieved_chunks) > 2:
            reasons.append(f"Multi-source synthesis across {len(retrieved_chunks)} chunks.")
            score += 0.35

        # Check for attack-chain reasoning
        if any(w in q_lower for w in ["chain", "bypass", "exploit chain", "rop", "deserialization"]):
            reasons.append("Complex vulnerability chain reasoning.")
            score += 0.35

        tier = "7B" if (score >= 0.35 or len(reasons) > 0) else "3B"
        return KnowledgeEscalationDecision(
            model_tier=tier,
            escalation_reasons=reasons,
            complexity_score=score,
        )

    def answer_query(
        self,
        query_text: str,
        session_id: Optional[str] = None,
        code_snippet: Optional[str] = None,
        force_7b: bool = False,
    ) -> KnowledgeAnswer:
        """
        Executes end-to-end knowledge question answering pipeline:
        Query Rewriting -> Retrieval -> Sufficiency Check -> Code Analysis (if present) ->
        Escalation Decision -> Synthesis -> Grounded Citations.
        """
        with INFERENCE_LOCK:
            # 1. Query Analysis & Rewriting
            expansion = CybersecurityQueryRewriter.rewrite_query(query_text)
            
            # 2. Local Retrieval against VAPT Corpus
            retrieved = self._retrieve_relevant_chunks(expansion.rewritten_query, expansion.extracted_domain)
            
            # 3. Code Security Review if code is provided
            code_report = None
            if code_snippet:
                code_report = CodeSecurityAnalyzer.analyze_code(code_snippet)

            # 4. Knowledge Sufficiency Evaluation
            sufficiency = KnowledgeSufficiencyEvaluator.evaluate(
                query=query_text,
                retrieved_chunks=retrieved,
            )

            # Handle insufficient or out-of-domain queries fail-closed without hallucination
            if not sufficiency.can_synthesize_answer:
                return KnowledgeAnswer(
                    answer_id=f"ANS-{uuid.uuid4().hex[:8]}",
                    query_id=f"QRY-{uuid.uuid4().hex[:8]}",
                    answer_text=sufficiency.suggested_fallback_message or "Insufficient knowledge to provide verified response.",
                    claims=[],
                    citations=[],
                    sufficiency_status=sufficiency.state.value,
                    epistemic_tier="GENERAL_VAPT_KNOWLEDGE",
                    escalation_level="3B",
                )

            # 5. Escalation Decision (3B vs 7B)
            escalation = self.evaluate_escalation(
                query=query_text,
                retrieved_chunks=retrieved,
                has_code=(code_snippet is not None),
                has_conflicts=(sufficiency.state == KnowledgeSufficiencyState.CONFLICTING),
                is_research_mode=(session_id is not None),
                force_7b=force_7b,
            )

            # 6. Extract verifiable claims and build grounded citations
            chunk_blob = "\n\n".join([c.content for c in retrieved])
            extraction_res = KnowledgeClaimExtractor.extract_claims(chunk_blob, retrieved)

            candidate_citations = []
            for claim in extraction_res.claims:
                for chk_id in claim.supporting_chunks:
                    candidate_citations.append({"chunk_id": chk_id, "claim_id": claim.claim_id})

            citation_res = GroundedCitationEngine.verify_citations(
                claims=extraction_res.claims,
                candidate_citations=candidate_citations,
                corpus_chunks=retrieved,
            )

            # 7. Synthesize grounded answer
            answer_text = self._format_synthesized_answer(
                query=query_text,
                claims=extraction_res.claims,
                citations=citation_res.valid_citations,
                code_report=code_report,
                expansion=expansion,
            )

            return KnowledgeAnswer(
                answer_id=f"ANS-{uuid.uuid4().hex[:8]}",
                query_id=f"QRY-{uuid.uuid4().hex[:8]}",
                answer_text=answer_text,
                claims=extraction_res.claims,
                citations=citation_res.valid_citations,
                sufficiency_status=sufficiency.state.value,
                epistemic_tier="GENERAL_VAPT_KNOWLEDGE",
                escalation_level=escalation.model_tier,
            )

    def _retrieve_relevant_chunks(self, rewritten_query: str, domain: str) -> List[KnowledgeChunk]:
        """Lexical and semantic scoring over indexed corpus chunks with multi-query formulation."""
        formulations = CybersecurityQueryRewriter.generate_multi_query_formulations(rewritten_query)
        chunk_scores: Dict[str, Tuple[float, KnowledgeChunk]] = {}

        for formulation in formulations:
            words = set(re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", formulation.lower()))
            if not words:
                continue
            for chunk in self.corpus_chunks:
                c_text = (chunk.title + " " + chunk.section_heading + " " + chunk.content + " " + " ".join(chunk.category_tags)).lower()
                matches = sum(1 for w in words if w in c_text)
                if matches > 0:
                    score = matches / (len(words) + 1)
                    if domain.lower() in [t.lower() for t in chunk.category_tags]:
                        score += 0.25
                    cid = chunk.chunk_id
                    if cid not in chunk_scores or score > chunk_scores[cid][0]:
                        chunk_scores[cid] = (score, chunk)

        sorted_scored = sorted(chunk_scores.values(), key=lambda x: x[0], reverse=True)
        return [c for score, c in sorted_scored[:4]]

    def _format_synthesized_answer(
        self,
        query: str,
        claims: List[KnowledgeClaim],
        citations: List[KnowledgeCitation],
        code_report: Optional[Any],
        expansion: Any,
    ) -> str:
        parts: List[str] = [f"### Cybersecurity Knowledge Synthesis: {query.strip()}"]

        if expansion.identified_cwes:
            parts.append(f"**Identified Weaknesses**: {', '.join(expansion.identified_cwes)}")
        if expansion.identified_cves:
            parts.append(f"**Referenced Advisories**: {', '.join(expansion.identified_cves)}")

        parts.append("\n#### Technical Explanation")
        for claim in claims[:5]:
            parts.append(f"- {claim.text}")

        if code_report and code_report.findings:
            parts.append(f"\n#### Static Code Security Review ({code_report.detected_language.value})")
            for f in code_report.findings:
                parts.append(
                    f"- **[{f.severity}] {f.rule_name} ({f.cwe_id})**: {f.risk_description} "
                    f"*(Line {f.line_number or 'N/A'})*\n  *Remediation*: {f.remediation_advice}"
                )
            parts.append(f"\n> **Notice**: {code_report.disclaimer}")

        if citations:
            parts.append("\n#### Grounded References & Citations")
            seen_cites = set()
            for c in citations:
                if c.chunk_id not in seen_cites:
                    seen_cites.add(c.chunk_id)
                    parts.append(f"- [{c.chunk_id}] {c.source_title} ({c.authority_level.value})")

        return "\n".join(parts)


import re
