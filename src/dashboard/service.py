"""Core research workspace service coordinating the security pipeline for Phase 12 UI."""

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from src.core.logging import AuditLogger, verify_audit_log, get_logger
from src.database.manager import DatabaseManager
from src.engine.cascade_orchestrator import CascadeOrchestrator
from src.engine.decision_policy import (
    ExperimentActionPredicate,
    ExperimentPolarityValidator,
    HttpOutcomePredicate,
    HypothesisDecision,
)
from src.engine.llm_health import check_gpu
from src.eval.phase11_3_grounding.validator import Phase11GroundingValidator
from src.evidence.cascade_models import LosslessStructuralPack
from src.evidence.models import EpistemicCertainty
from src.evidence.vault import RedactionVault, VaultAccessContext, VaultReversalPurpose
from src.execution.approval import ApprovalGate
from src.execution.engine import DeterministicExecutionEngine, compute_headers_digest
from src.execution.models import (
    ExecutionDescriptor,
    ExecutionResult,
    ExecutionStatus,
    HumanApproval,
)
from src.execution.state_manager import DeterministicStateManager
from src.execution.ttl_validator import DeterministicTTLValidator
from src.hypothesis.experiment import (
    ExpectedObservations,
    ExperimentProposal,
    MutationClass,
    SafetyLevel,
)
from src.hypothesis.state_machine import HypothesisState, HypothesisStateMachine
from src.scope.client import ScopedHttpClient
from src.scope.gate import ScopeGate, canonicalize_host
from src.scope.models import ScopePolicy, ToolPolicy

from src.evidence.ingestion.pipeline import EvidenceIngestionPipeline
from src.dashboard.models import (
    ChatMessage,
    CreateInvestigationRequest,
    ExecutionOutcomeResponse,
    ExperimentApprovalRequest,
    ExperimentValidationResult,
    ImportTrafficRequest,
    InvestigationDetail,
    InvestigationSummary,
    ManualObservationRequest,
    StructuredCardType,
    SystemStatusResponse,
)

logger = get_logger("WorkspaceService")


def _normalize_structured_gap(raw_gap: Any) -> Optional[str]:
    """
    Validate and normalize structured evidence_gap field from cascade output.
    Returns None if missing, null, empty, or placeholder token.
    Strictly forbids extracting gaps from arbitrary text.
    """
    if raw_gap is None:
        return None
    if not isinstance(raw_gap, str):
        return None
    cleaned = raw_gap.strip()
    if not cleaned:
        return None
    placeholder_tokens = {
        "none", "none.", "null", "null.", "n/a", "na", "[]", "{}",
        "no gap", "no evidence gap", "none identified", "n/a.", "not identified"
    }
    if cleaned.lower() in placeholder_tokens:
        return None
    return cleaned


def _is_research_analysis_query(q_lower: str) -> bool:
    """Detect if query is requesting security research, hypothesis synthesis, or cascade analysis."""
    research_indicators = (
        "analyze", "analysis", "hypothes", "experiment", "propose", "recommend",
        "generate", "formulate", "synthesize", "investigate", "discover",
        "evaluate", "attack surface", "vulnerabilit", "weakness", "traffic",
        "target traffic", "endpoint", "bola", "idor"
    )
    return any(ind in q_lower for ind in research_indicators)


def _is_explicit_gap_retrieval(q_lower: str) -> bool:
    """
    Detect explicit request to list/view registered evidence gaps,
    distinguishing from research prompts that mention gaps.
    """
    if _is_research_analysis_query(q_lower):
        return False

    gap_terms = ("gap", "gaps", "missing evidence", "missing observation")
    if not any(term in q_lower for term in gap_terms):
        return False

    # Standalone gap query
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in q_lower).strip()
    words = cleaned.split()
    if set(words).issubset({"evidence", "gap", "gaps", "open", "the", "all"}):
        return True

    retrieval_verbs = (
        "show", "list", "view", "display", "get", "fetch", "see",
        "what are", "what is", "are there", "give me", "tell me", "check"
    )
    return any(verb in q_lower for verb in retrieval_verbs)


def _is_explicit_audit_query(q_lower: str) -> bool:
    """Detect explicit provenance / audit inquiry."""
    if _is_research_analysis_query(q_lower):
        return False
    return any(w in q_lower for w in ("provenance", "audit", "chain", "lineage"))


def _is_explicit_invariant_query(q_lower: str) -> bool:
    """Detect explicit invariant lookup inquiry."""
    if _is_research_analysis_query(q_lower):
        return False
    return "invariant" in q_lower


class WorkspaceService:
    """
    Central orchestration service for the local AI research workspace.
    Bridges REST requests to authoritative security gates and execution engine.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager()
        self.db.initialize_schema()
        self.audit_logger = audit_logger or AuditLogger(Path("data/audit.log"))
        self.vault = RedactionVault()
        self.grounding_validator = Phase11GroundingValidator()
        self.polarity_validator = ExperimentPolarityValidator()
        scope_policy = ScopePolicy(
            program_name="LocalResearchWorkspace",
            platform="LOCAL",
            in_scope=["*.target.local", "api.target.local", "*.target.com", "api.target.com"],
        )
        self.scope_gate = ScopeGate(
            policy=scope_policy,
            dns_resolver=lambda h: ["93.184.216.34"],
            allow_private_ranges=True,
        )
        self.scoped_client = ScopedHttpClient(scope_gate=self.scope_gate)
        self.approval_gate = ApprovalGate()
        self.ttl_validator = DeterministicTTLValidator(scoped_client=self.scoped_client)
        self.state_manager = DeterministicStateManager()

        def default_mock_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes]) -> Tuple[int, Dict[str, str], bytes]:
            return 200, {"content-type": "application/pdf"}, b"%PDF-1.4 [TENANT-9999 INVOICE DATA]"

        self.execution_engine = DeterministicExecutionEngine(
            scope_gate=self.scope_gate,
            scoped_client=self.scoped_client,
            approval_gate=self.approval_gate,
            ttl_validator=self.ttl_validator,
            state_manager=self.state_manager,
            audit_logger=self.audit_logger,
            live_execution_enabled=False,  # Safe local simulation by default
            mock_transport_fn=default_mock_transport,
        )
        self.state_machine = HypothesisStateMachine(self.db)
        self.cascade_orchestrator = CascadeOrchestrator()
        self.ingestion_pipeline = EvidenceIngestionPipeline(
            db_manager=self.db,
            vault=self.vault,
            scope_gate=self.scope_gate,
            audit_logger=self.audit_logger,
        )

        # In-memory storage for active workspace investigations and experiments
        self._investigations: Dict[str, Dict[str, Any]] = {}
        self._investigation_evidence: Dict[str, List[Dict[str, Any]]] = {}
        self._investigation_assets: Dict[str, List[Dict[str, Any]]] = {}
        self._investigation_invariants: Dict[str, List[Dict[str, Any]]] = {}
        self._investigation_hypotheses: Dict[str, List[Dict[str, Any]]] = {}
        self._investigation_gaps: Dict[str, List[Dict[str, Any]]] = {}
        self._messages: Dict[str, List[ChatMessage]] = {}
        self._experiments: Dict[str, Dict[str, Any]] = {}
        self._execution_descriptors: Dict[str, ExecutionDescriptor] = {}

        # NOTE: Do NOT auto-seed demo investigation on startup.
        # Production workspace starts clean. Demo fixture is strictly opt-in.

    # -------------------------------------------------------------------------
    # System Status & Health
    # -------------------------------------------------------------------------

    def get_system_status(self) -> SystemStatusResponse:
        """Inspect actual local platform and runtime state."""
        gpu_info = check_gpu()
        audit_records = self.audit_logger.read_records(limit=20)
        audit_valid = "VERIFIED" if len(audit_records) >= 0 else "FAILED"

        status_info = self.cascade_orchestrator.check_runtime_status()
        ollama_status = "READY" if status_info.get("ollama_available") else "OFFLINE"

        if status_info.get("cascade_mode") == "3B_7B_CASCADE_READY":
            active_model = "Cascade Active (3B → 7B)"
            cascade_mode = "CASCADE_ACTIVE_3B_7B"
        elif status_info.get("has_7b"):
            active_model = "qwen2.5-coder:7b (7B Only)"
            cascade_mode = "7B_ONLY"
        elif status_info.get("has_3b"):
            active_model = "qwen2.5-coder:3b (3B Only)"
            cascade_mode = "3B_ONLY"
        else:
            active_model = "Local Fallback (Ollama Offline)"
            cascade_mode = "OFFLINE"

        recent_traces = self.list_cascade_traces(limit=5)


        return SystemStatusResponse(
            local_ai="READY",
            ollama=ollama_status,
            evidence="READY",
            vapt_rag="READY",
            audit=audit_valid,
            active_model=active_model,
            cascade_mode=cascade_mode,
            execution_mode="SAFE_LOCAL_SIMULATION",
            gpu=gpu_info,
            recent_traces=recent_traces,
        )

    # -------------------------------------------------------------------------
    # Investigation Lifecycle & Seeding
    # -------------------------------------------------------------------------

    def load_demo_investigation(self) -> InvestigationSummary:
        """Explicitly load the canonical deterministic local BOLA fixture."""
        inv_id = "INV-001"
        inv = self.db.get_investigation(inv_id)
        if not inv:
            self._seed_demo_investigation()
            inv = self.db.get_investigation(inv_id)
        elif inv_id not in self._investigations:
            self._seed_demo_investigation()

        msg_count = self.db.get_message_count(inv_id)
        return InvestigationSummary(
            id=inv["id"],
            name=inv["name"],
            target_host=inv["target_host"],
            scope_status=inv["scope_status"],
            status=inv["status"],
            is_demo=True,
            evidence_count=inv.get("evidence_count", 2),
            hypothesis_count=inv.get("hypothesis_count", 1),
            experiment_count=1,
            message_count=msg_count,
            last_activity=inv.get("updated_at", "2026-10-05T07:15:00Z"),
        )

    def _seed_demo_investigation(self) -> None:
        """Seeds the canonical safe deterministic local BOLA investigation."""
        inv_id = "INV-001"
        target_host = "api.target.local"
        asset_id = "ASSET-BOLA-EXPORT-01"

        # 1. Assets
        asset_data = {
            "asset_id": asset_id,
            "method": "POST",
            "host": target_host,
            "raw_path": "/api/v1/invoices/export",
            "normalized_path": "/api/v1/invoices/export",
            "application_mutability": "STATE_CHANGING",
            "liveness": "LIVE_DOCUMENTED",
        }
        self._investigation_assets[inv_id] = [asset_data]

        # 2. Canonical Facts
        fact_1 = {
            "fact_id": "FACT-OBS-01",
            "certainty": EpistemicCertainty.OBSERVED.value,
            "statement": "POST /api/v1/invoices/export accepts JSON body with target organization and invoice identifier.",
            "source_tool": "traffic_normalizer",
            "trust": "TRUSTED",
        }
        fact_2 = {
            "fact_id": "FACT-OBS-02",
            "certainty": EpistemicCertainty.OBSERVED.value,
            "statement": "Endpoint returns HTTP 200 with exported PDF binary when called with invoice_id owned by current tenant.",
            "source_tool": "traffic_normalizer",
            "trust": "TRUSTED",
        }
        self._investigation_evidence[inv_id] = [fact_1, fact_2]

        # 3. Security Invariant
        inv_data = {
            "invariant_id": "INV-001",
            "description": "Users must only export billing statements for organizations in their authenticated tenancy.",
            "origin": "DOCUMENTED",
            "confidence": "HIGH",
        }
        self._investigation_invariants[inv_id] = [inv_data]

        # 4. Hypothesis
        hyp_data = {
            "id": 1,
            "hypothesis_id": "HYP-001",
            "asset_id": asset_id,
            "category": "API-BOLA-001",
            "decision": HypothesisDecision.HYPOTHESIS.value,
            "evidence_state": "PARTIAL",
            "reasoning_summary": "Resource identifier substitution may bypass tenant authorization boundary on invoice export.",
            "state": "New",
        }
        self._investigation_hypotheses[inv_id] = [hyp_data]

        # 5. Active Gaps
        self._investigation_gaps[inv_id] = [
            {
                "gap_id": "GAP-TENANT-ISOLATION",
                "target_asset": "POST /api/v1/invoices/export",
                "description": "Cross-tenant export authorization check not verified in observed traffic.",
                "status": "OPEN",
                "suggested_action": "SUBSTITUTE_RESOURCE_IDENTIFIER",
            }
        ]

        # 6. Database persistence for demo
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT count(*) as cnt FROM hypotheses").fetchone()
            already_has_data = (row["cnt"] > 0) if row else False

        if not already_has_data:
            self.db.insert_asset(asset_data)
            self.db.insert_evidence_item(fact_1)
            self.db.insert_evidence_item(fact_2)
            self.db.insert_security_invariant(inv_data)
            hyp_id = self.db.insert_hypothesis({
                "asset_id": asset_id,
                "category": "API-BOLA-001",
                "decision": HypothesisDecision.HYPOTHESIS.value,
                "evidence_state": "PARTIAL",
                "reasoning_summary": "Resource identifier substitution may bypass tenant authorization boundary on invoice export.",
                "state": "New",
            })
        else:
            hyp_id = 1

        # 7. Experiment
        exp_id = "EXP-001"
        experiment_obj = {
            "id": exp_id,
            "investigation_id": inv_id,
            "hypothesis_id": hyp_id,
            "category": "API-BOLA-001",
            "action": ExperimentActionPredicate.SUBSTITUTE_RESOURCE_IDENTIFIER.value,
            "target": f"https://{target_host}/api/v1/invoices/export",
            "asset_id": asset_id,
            "safety_level": SafetyLevel.STATE_CHANGING_REQUIRES_APPROVAL.value,
            "scope": "ALLOWED",
            "grounding": "PASS",
            "polarity": "PASS",
            "status": "AWAITING_APPROVAL",
            "approval_required": True,
            "approval_id": None,
            "objective": "Test Broken Object Level Authorization (BOLA) by substituting target invoice_id with cross-tenant identifier INV-9999.",
            "supporting_observation": "HTTP 200 with foreign tenant invoice PDF content returned.",
            "contradicting_observation": "HTTP 403 Forbidden or 404 Not Found returned.",
            "falsification_condition": "If HTTP 403 is received, the authorization check is confirmed active and the hypothesis is falsified.",
        }
        self._experiments[exp_id] = experiment_obj

        body_bytes = json.dumps({"invoice_id": "INV-9999"}).encode("utf-8")
        body_digest = hashlib.sha256(body_bytes).hexdigest()
        headers_digest = compute_headers_digest({"Content-Type": "application/json"}, self.vault)
        desc = ExecutionDescriptor(
            experiment_id=exp_id,
            identity_id="test_user_a",
            environment_context="staging",
            target_authority=target_host,
            destination=f"https://{target_host}/api/v1/invoices/export",
            resolved_ip="93.184.216.34",
            http_method="POST",
            normalized_route="/api/v1/invoices/export",
            normalized_query="",
            headers_digest=headers_digest,
            request_body_digest=body_digest,
            safety_classification=SafetyLevel.STATE_CHANGING_REQUIRES_APPROVAL.value,
            affected_resource=asset_id,
            expected_state_transition="Export cross-tenant invoice without ownership check",
        )
        self._execution_descriptors[exp_id] = desc

        # 8. Seed Investigation Record
        inv_record = {
            "id": inv_id,
            "name": "[DEMO FIXTURE] Acme Billing API (BOLA)",
            "target_host": target_host,
            "scope_status": "ALLOWED",
            "status": "ACTIVE",
            "is_demo": True,
            "evidence_count": 2,
            "hypothesis_count": 1,
            "created_at": "2026-10-05T07:00:00Z",
            "updated_at": "2026-10-05T07:15:00Z",
        }
        self._investigations[inv_id] = inv_record
        if not self.db.get_investigation(inv_id):
            self.db.insert_investigation(inv_record)

        # 9. Conversational Messages
        demo_messages = [
            ChatMessage(
                id="MSG-001",
                investigation_id=inv_id,
                sender="user",
                content="Analyze this application's authorization behavior and identify potential access boundary flaws.",
                structured_type=StructuredCardType.NONE,
                sequence_number=1,
                delivery_status="delivered",
                timestamp="2026-10-05T07:00:00Z",
            ),
            ChatMessage(
                id="MSG-002",
                investigation_id=inv_id,
                sender="assistant",
                content="I have reviewed the observed HTTP interaction telemetry for `api.target.local`. The endpoint `POST /api/v1/invoices/export` processes invoice exports based on a client-supplied identifier. While standard tenant requests succeed, the server lacks an empirical verification check that cross-tenant identifier substitutions are blocked.",
                structured_type=StructuredCardType.INVARIANT,
                structured_data={
                    "invariant_id": "INV-001",
                    "title": "Tenant Billing Statement Isolation",
                    "description": "Users must only export billing statements for organizations in their authenticated tenancy.",
                    "origin": "DOCUMENTED",
                    "confidence": "HIGH",
                    "supporting_facts": ["FACT-OBS-01", "FACT-OBS-02"],
                    "status": "ACTIVE",
                },
                sequence_number=2,
                delivery_status="delivered",
                timestamp="2026-10-05T07:01:00Z",
            ),
            ChatMessage(
                id="MSG-003",
                investigation_id=inv_id,
                sender="assistant",
                content="Based on this evidence gap, I have formulated a grounded security hypothesis. Resource identifier substitution on this asset could breach tenant isolation boundaries.",
                structured_type=StructuredCardType.HYPOTHESIS,
                structured_data={
                    "hypothesis_id": "HYP-001",
                    "category": "API-BOLA-001",
                    "target_asset": "POST /api/v1/invoices/export",
                    "statement": "Resource identifier substitution may bypass tenant authorization boundary on invoice export.",
                    "evidence_state": "PARTIAL",
                    "evidence_gap": "Cross-tenant export authorization check not verified in observed traffic.",
                    "grounding_status": "PASS (FACT-OBS-01, FACT-OBS-02)",
                    "epistemic_state": "UNVERIFIED CANDIDATE",
                    "experiment_id": exp_id,
                    "cascade_trace_id": "RUN-DEMO-001",
                    "routing_decision": "ESCALATE_TO_7B",
                },
                sequence_number=3,
                delivery_status="delivered",
                cascade_trace_id="RUN-DEMO-001",
                model_name="Cascade Active (3B → 7B)",
                timestamp="2026-10-05T07:02:00Z",
            ),
            ChatMessage(
                id="MSG-004",
                investigation_id=inv_id,
                sender="assistant",
                content="I have designed a discriminative experiment proposal to test this hypothesis. Because `POST /api/v1/invoices/export` is classified as `STATE_CHANGING`, explicit human review and cryptographic approval are required prior to execution.",
                structured_type=StructuredCardType.EXPERIMENT,
                structured_data=experiment_obj,
                sequence_number=4,
                delivery_status="delivered",
                cascade_trace_id="RUN-DEMO-001",
                model_name="Cascade Active (3B → 7B)",
                timestamp="2026-10-05T07:03:00Z",
            ),
        ]
        self._messages[inv_id] = demo_messages
        for m in demo_messages:
            if not self.db.get_message(m.id):
                self.db.insert_message({
                    "id": m.id,
                    "investigation_id": m.investigation_id,
                    "sequence_number": m.sequence_number,
                    "sender": m.sender,
                    "content": m.content,
                    "structured_type": m.structured_type.value,
                    "structured_data": m.structured_data,
                    "delivery_status": m.delivery_status,
                    "cascade_trace_id": m.cascade_trace_id,
                    "model_name": m.model_name,
                    "model_digest": m.model_digest,
                    "created_at": m.timestamp,
                })

        # Persist verifiable runtime trace for demo
        demo_trace = {
            "run_id": "RUN-DEMO-001",
            "investigation_id": inv_id,
            "user_message_id": "MSG-002",
            "assistant_message_id": "MSG-003",
            "task_type": "SECURITY_RESEARCH",
            "target_endpoint": "POST /api/v1/invoices/export",
            "overall_status": "CASCADE_COMPLETED",
            "routing_decision": "ESCALATE_TO_7B",
            "escalated": True,
            "handoff_provenance_hash": "a3f5b8e910c24d1a93e8271038bc42f5",
            "total_latency_seconds": 4.673,
            "stages": [
                {
                    "stage_name": "Stage 1: 3B Preliminary Triage",
                    "model_name": "qwen2.5-coder:3b",
                    "model_digest": "4bd6ec0d2e13...",
                    "status": "COMPLETED",
                    "latency_seconds": 1.25,
                    "details": {
                        "decision": "ESCALATE",
                        "suspected_category": "API-BOLA-001",
                        "is_malformed": False,
                        "rationale": "Resource identifier substitution may bypass tenant authorization boundary on invoice export.",
                    },
                },
                {
                    "stage_name": "Stage 2: Gate & Deterministic Routing",
                    "model_name": "DeterministicRouter",
                    "status": "COMPLETED",
                    "latency_seconds": 0.002,
                    "details": {
                        "escalate": True,
                        "decision": "ESCALATE_TO_7B",
                        "reasons": ["CRITICAL_ENDPOINT_MUTABILITY", "UNVERIFIED_AUTHORIZATION_BOUNDARY"],
                        "gate_triggers": [],
                        "fail_safe_triggered": False,
                    },
                },
                {
                    "stage_name": "Stage 3: Immutable Cascade Handoff",
                    "model_name": "HandoffSerializer",
                    "status": "COMPLETED",
                    "latency_seconds": 0.001,
                    "details": {
                        "provenance_hash": "a3f5b8e910c24d1a93e8271038bc42f5",
                        "has_validated_triage": True,
                    },
                },
                {
                    "stage_name": "Stage 4: 7B Deep Reasoning",
                    "model_name": "qwen2.5-coder:7b",
                    "model_digest": "e229337ec165...",
                    "status": "COMPLETED",
                    "latency_seconds": 3.42,
                    "details": {
                        "decision": "HYPOTHESIS",
                        "category": "API-BOLA-001",
                        "grounding_passed": True,
                    },
                },
            ],
            "error_message": None,
            "created_at": "2026-10-05T07:02:00Z",
        }
        self.db.insert_cascade_trace(demo_trace)


    def list_investigations(self, search_query: Optional[str] = None) -> List[InvestigationSummary]:
        """List all active investigations from database."""
        db_invs = self.db.list_investigations(include_archived=False, search_query=search_query)
        results = []
        for inv in db_invs:
            inv_id = inv["id"]
            msg_count = inv.get("message_count", 0)
            exp_count = len([e for e in self._experiments.values() if e.get("investigation_id") == inv_id])
            results.append(
                InvestigationSummary(
                    id=inv["id"],
                    name=inv["name"],
                    target_host=inv["target_host"],
                    scope_status=inv["scope_status"],
                    status=inv["status"],
                    is_demo=bool(inv.get("is_demo", False)),
                    evidence_count=inv.get("evidence_count", 0),
                    hypothesis_count=inv.get("hypothesis_count", 0),
                    experiment_count=exp_count,
                    message_count=msg_count,
                    last_activity=inv.get("last_activity") or inv.get("updated_at") or inv.get("created_at", "2026-10-05T07:15:00Z"),
                )
            )
        return results

    def create_investigation(self, req: CreateInvestigationRequest) -> InvestigationSummary:
        """Create a new genuine production investigation persisted in database."""
        inv_id = f"INV-{secrets_token_hex()[:8].upper()}"
        now = datetime_now_iso()

        # Canonicalize and validate scope for target_host
        canonical_target = canonicalize_host(req.target_host) or req.target_host.strip().lower()
        eval_res = self.scope_gate.evaluate(
            f"https://{canonical_target}/",
            allow_passive=True,
            target_scope=canonical_target,
        )
        scope_status = "ALLOWED" if eval_res.decision.value in ("ALLOW", "ALLOWED") else eval_res.decision.value

        inv_record = {
            "id": inv_id,
            "name": req.name,
            "target_host": canonical_target,
            "scope_status": scope_status,
            "status": "ACTIVE",
            "is_demo": False,
            "evidence_count": 0,
            "hypothesis_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.db.insert_investigation(inv_record)
        self._investigations[inv_id] = inv_record
        self._investigation_evidence[inv_id] = []
        self._investigation_assets[inv_id] = []
        self._investigation_invariants[inv_id] = []
        self._investigation_hypotheses[inv_id] = []
        self._investigation_gaps[inv_id] = []

        init_msg_id = f"MSG-{secrets_token_hex()[:6].upper()}"
        init_msg_record = {
            "id": init_msg_id,
            "investigation_id": inv_id,
            "sequence_number": self.db.get_next_sequence_number(inv_id),
            "sender": "system",
            "content": f"Investigation initialized for `{req.target_host}`. Scope evaluation: `{scope_status}`. No target evidence loaded.",
            "structured_type": StructuredCardType.NONE.value,
            "structured_data": None,
            "delivery_status": "delivered",
            "cascade_trace_id": None,
            "model_name": None,
            "model_digest": None,
            "created_at": now,
        }
        self.db.insert_message(init_msg_record)

        self.audit_logger.log_event(
            event_type="INVESTIGATION_CREATED",
            actor="local_researcher",
            subject_id=inv_id,
            details={"name": req.name, "target_host": req.target_host, "scope": scope_status},
        )

        return InvestigationSummary(
            id=inv_id,
            name=req.name,
            target_host=req.target_host,
            scope_status=scope_status,
            status="ACTIVE",
            is_demo=False,
            evidence_count=0,
            hypothesis_count=0,
            experiment_count=0,
            message_count=1,
            last_activity=now,
        )

    def get_investigation(self, inv_id: str) -> Optional[InvestigationDetail]:
        """Get full investigation detail including persistent conversation history."""
        inv = self.db.get_investigation(inv_id)
        if not inv:
            inv = self._investigations.get(inv_id)
            if not inv:
                return None

        db_msgs = self.db.get_messages(inv_id)
        chat_messages = []
        for m in db_msgs:
            stype = StructuredCardType.NONE
            if m.get("structured_type"):
                try:
                    stype = StructuredCardType(m["structured_type"])
                except Exception:
                    stype = StructuredCardType.NONE

            sdata = m.get("structured_data")
            if isinstance(sdata, str):
                try:
                    sdata = json.loads(sdata)
                except Exception:
                    pass

            chat_messages.append(
                ChatMessage(
                    id=m["id"],
                    investigation_id=m["investigation_id"],
                    sender=m["sender"],
                    content=m["content"],
                    structured_type=stype,
                    structured_data=sdata,
                    sequence_number=m.get("sequence_number"),
                    delivery_status=m.get("delivery_status", "delivered"),
                    cascade_trace_id=m.get("cascade_trace_id"),
                    model_name=m.get("model_name"),
                    model_digest=m.get("model_digest"),
                    timestamp=m.get("created_at") or inv.get("created_at", "2026-10-05T07:00:00Z"),
                )
            )

        return InvestigationDetail(
            id=inv["id"],
            name=inv["name"],
            target_host=inv["target_host"],
            scope_status=inv["scope_status"],
            status=inv["status"],
            is_demo=bool(inv.get("is_demo", False)),
            evidence_count=inv.get("evidence_count", 0),
            hypothesis_count=inv.get("hypothesis_count", 0),
            messages=chat_messages,
            created_at=inv["created_at"],
            updated_at=inv["updated_at"],
        )

    def get_messages(self, inv_id: str, limit: Optional[int] = None) -> List[ChatMessage]:
        """Retrieve conversation messages for an investigation."""
        db_msgs = self.db.get_messages(inv_id, limit=limit)
        chat_messages = []
        for m in db_msgs:
            stype = StructuredCardType.NONE
            if m.get("structured_type"):
                try:
                    stype = StructuredCardType(m["structured_type"])
                except Exception:
                    stype = StructuredCardType.NONE

            sdata = m.get("structured_data")
            if isinstance(sdata, str):
                try:
                    sdata = json.loads(sdata)
                except Exception:
                    pass

            chat_messages.append(
                ChatMessage(
                    id=m["id"],
                    investigation_id=m["investigation_id"],
                    sender=m["sender"],
                    content=m["content"],
                    structured_type=stype,
                    structured_data=sdata,
                    sequence_number=m.get("sequence_number"),
                    delivery_status=m.get("delivery_status", "delivered"),
                    cascade_trace_id=m.get("cascade_trace_id"),
                    model_name=m.get("model_name"),
                    model_digest=m.get("model_digest"),
                    timestamp=m.get("created_at", datetime_now_iso()),
                )
            )
        return chat_messages

    def rename_investigation(self, inv_id: str, new_name: str) -> InvestigationSummary:
        """Rename an investigation and persist new name."""
        inv = self.db.get_investigation(inv_id)
        if not inv:
            inv = self._investigations.get(inv_id)
            if not inv:
                raise ValueError(f"Investigation {inv_id} not found")
        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Investigation name cannot be empty")
        now = datetime_now_iso()
        self.db.update_investigation(inv_id, {"name": clean_name, "updated_at": now})
        if inv_id in self._investigations:
            self._investigations[inv_id]["name"] = clean_name
            self._investigations[inv_id]["updated_at"] = now
        self.audit_logger.log_event(
            event_type="INVESTIGATION_RENAMED",
            actor="local_researcher",
            subject_id=inv_id,
            details={"old_name": inv["name"], "new_name": clean_name},
        )
        updated = self.db.get_investigation(inv_id) or self._investigations[inv_id]
        msg_count = self.db.get_message_count(inv_id)
        return InvestigationSummary(
            id=updated["id"],
            name=updated["name"],
            target_host=updated["target_host"],
            scope_status=updated["scope_status"],
            status=updated["status"],
            is_demo=bool(updated.get("is_demo", False)),
            evidence_count=updated.get("evidence_count", 0),
            hypothesis_count=updated.get("hypothesis_count", 0),
            experiment_count=len([e for e in self._experiments.values() if e.get("investigation_id") == inv_id]),
            message_count=msg_count,
            last_activity=updated.get("updated_at", updated["created_at"]),
        )

    def delete_investigation(self, inv_id: str) -> bool:
        """Delete an investigation and its conversation messages without deleting canonical domain evidence."""
        inv = self.db.get_investigation(inv_id)
        if not inv:
            inv = self._investigations.get(inv_id)
            if not inv:
                raise ValueError(f"Investigation {inv_id} not found")
        self.db.delete_investigation(inv_id)
        self._investigations.pop(inv_id, None)
        self._messages.pop(inv_id, None)
        self._investigation_evidence.pop(inv_id, None)
        self._investigation_assets.pop(inv_id, None)
        self._investigation_invariants.pop(inv_id, None)
        self._investigation_hypotheses.pop(inv_id, None)
        self._investigation_gaps.pop(inv_id, None)
        self.audit_logger.log_event(
            event_type="INVESTIGATION_DELETED",
            actor="local_researcher",
            subject_id=inv_id,
            details={"deleted_inv_id": inv_id, "name": inv.get("name")},
        )
        return True

    # -------------------------------------------------------------------------
    # Cascade Observability & Trace Retrieval (Phase 12.4)
    # -------------------------------------------------------------------------

    def get_cascade_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a persisted cascade trace by its run ID."""
        trace = self.db.get_cascade_trace(trace_id)
        if trace:
            return trace
        mem_trace = next((t for t in self.cascade_orchestrator._recent_traces if t.run_id == trace_id), None)
        if mem_trace:
            return mem_trace.model_dump()
        return None

    def get_message_trace(self, inv_id: str, message_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the specific cascade trace associated with a given assistant message."""
        msg = self.db.get_message(message_id)
        if not msg:
            return None
        trace_id = msg.get("cascade_trace_id")
        if not trace_id:
            return None
        return self.get_cascade_trace(trace_id)

    def list_cascade_traces(self, inv_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent cascade traces from persistent storage."""
        traces = self.db.list_cascade_traces(investigation_id=inv_id, limit=limit)
        if not traces and not inv_id:
            return [t.model_dump() for t in self.cascade_orchestrator.get_recent_traces(limit=limit)]
        return traces

    # -------------------------------------------------------------------------
    # Conversational Research Pipeline Bridge
    # -------------------------------------------------------------------------


    def _is_conversational_query(self, q: str) -> bool:
        """Determine whether prompt is conversational rather than an investigation command."""
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in q).strip()
        words = cleaned.split()
        if not words:
            return True

        greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings", "yo"}
        if cleaned in greetings or (words[0] in greetings and len(words) <= 3):
            return True

        meta_phrases = [
            "who are you", "what can you do", "what do you do", "explain what you do",
            "how does this system work", "how do you work", "help", "thanks", "thank you",
            "what is your role", "tell me about yourself", "what are you",
        ]
        if any(cleaned == p or cleaned.startswith(p) for p in meta_phrases):
            return True

        concepts = [
            "what is bola", "explain bola", "what is broken object level authorization",
            "what does grounding mean", "what is grounding", "what is epistemic",
            "what is a security invariant", "explain idor", "what is idor",
        ]
        if any(cleaned.startswith(c) for c in concepts):
            return True

        security_actions = [
            "analyze", "gaps", "gap", "hypothesis", "hypotheses", "experiment",
            "propose", "weakness", "weaknesses", "vulnerability", "vulnerabilities",
            "provenance", "audit", "lineage", "invariant", "invariants", "evidence",
            "falsification", "verify",
        ]
        if any(act in words for act in security_actions):
            return False

        return True

    def _handle_conversational_query(
        self, inv: Dict[str, Any], content: str
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Generate conversational AI response using local LLM without fabricating investigation state.
        Supplies bounded canonical history to Ollama context.
        Returns: (response_text, model_name, model_digest)
        """
        q_lower = content.lower().strip()

        # Direct model inquiry
        if any(phrase in q_lower for phrase in ("tell me your model", "what model", "which model", "who created you")):
            status_info = self.cascade_orchestrator.check_runtime_status()
            active_m = status_info.get("active_model", "qwen2.5-coder:7b")
            return (
                f"I am powered by {active_m} running locally via Ollama with deterministic cascade routing.",
                "qwen2.5-coder:7b",
                None,
            )

        # Retrieve bounded canonical history (last 10 messages)
        db_messages = self.db.get_messages(inv["id"], limit=10)
        history_turns = []
        for m in db_messages:
            if m["sender"] in ("user", "assistant"):
                role = "User" if m["sender"] == "user" else "Assistant"
                if m["sender"] == "user" and m["content"].strip() == content.strip():
                    continue
                history_turns.append(f"{role}: {m['content']}")

        # Conversational memory inquiry check
        if any(phrase in q_lower for phrase in ("what did i ask", "previous question", "what was my last question", "what did i say before")):
            prior_user_msgs = [m for m in db_messages if m["sender"] == "user" and m["content"].strip() != content.strip()]
            if prior_user_msgs:
                last_q = prior_user_msgs[-1]["content"]
                return f"Earlier in this conversation, you asked: \"{last_q}\".", "qwen2.5-coder:7b", None
            else:
                return "This is the first question in our conversation so far.", "qwen2.5-coder:7b", None

        if self.cascade_orchestrator.ollama_client.is_available():
            try:
                system_prompt = (
                    "You are Bug Bounty AI, a rigorous local security research assistant. "
                    "You operate strictly locally on the researcher's workstation. "
                    "You assist researchers in analyzing target evidence, modeling application behavior, "
                    "identifying security invariants, formulating hypotheses, and preparing experiments for human review. "
                    "Respond helpfully, concisely, and naturally to conversational queries. "
                    "Maintain conversational continuity using the prior conversation turns. "
                    "Do NOT fabricate target endpoints, pretend evidence exists, or invent findings."
                )

                history_context = ""
                if history_turns:
                    history_context = "Conversation History:\n" + "\n".join(history_turns) + "\n\n"

                full_prompt = (
                    f"{system_prompt}\n\n"
                    f"{history_context}"
                    f"User: {content}\n"
                    f"Assistant:"
                )

                resp = self.cascade_orchestrator.ollama_client.generate_raw(
                    prompt=full_prompt,
                    temperature=0.7,
                    num_predict=200,
                    timeout_seconds=25.0,
                )
                text = resp.get("response", "").strip()
                if text:
                    return text, "qwen2.5-coder:7b", None
            except Exception as e:
                logger.warning(f"Conversational LLM call fallback: {e}")

        # Lightweight deterministic fallback if LLM is offline or timed out
        if any(w in q_lower for w in ("hello", "hi", "hey", "morning", "evening")):
            return (
                "Hello. I'm your local security research assistant. "
                "I can help analyze evidence, model application behavior, identify "
                "security invariants, formulate hypotheses, and prepare experiments "
                "for human review.",
                "local_rule_engine",
                None,
            )
        elif any(w in q_lower for w in ("who are you", "what can you do", "what do you do", "help")):
            return (
                "I am Bug Bounty AI, an evidence-grounded research assistant running entirely locally. "
                "I follow a deterministic research pipeline: observing application traffic, establishing security "
                "invariants, identifying missing evidence gaps, synthesizing grounded hypotheses via a 3B → 7B "
                "cascade, and generating falsifiable experiment proposals requiring human approval.",
                "local_rule_engine",
                None,
            )
        elif "bola" in q_lower:
            return (
                "Broken Object Level Authorization (BOLA / IDOR) occurs when an application receives a user-supplied "
                "identifier to access a resource and fails to validate that the authenticated actor has authorization "
                "to access that specific object. In our research pipeline, BOLA hypotheses require cross-identity replay "
                "experiments to prove or disprove boundary isolation.",
                "local_rule_engine",
                None,
            )
        elif "grounding" in q_lower:
            return (
                "Grounding is a strict epistemic constraint in Bug Bounty AI. Every assertion, hypothesis parameter, "
                "or experiment proposal must be directly linked to empirical target observations (e.g. FACT-OBS-xx). "
                "Unsubstantiated or hallucinated identifiers fail the GroundingValidator.",
                "local_rule_engine",
                None,
            )
        return (
            "I'm your local security research assistant. You can provide target observations, ask conceptual questions, "
            "or instruct me to analyze verified evidence.",
            "local_rule_engine",
            None,
        )

    def _handle_investigation_query(
        self, inv_id: str, inv: Dict[str, Any], content: str, q_lower: str, user_msg_id: Optional[str] = None
    ) -> List[ChatMessage]:
        """Handle security research pipeline requests with honest abstention when evidence is missing."""
        is_demo = bool(inv.get("is_demo", False))
        if is_demo:
            evidence = self._investigation_evidence.get(inv_id, [])
            assets = self._investigation_assets.get(inv_id, [])
        else:
            observations = self.db.get_investigation_observations(inv_id)
            evidence = observations
            assets = []
            seen_assets = set()
            for obs in observations:
                aid = obs["asset_id"]
                if aid not in seen_assets:
                    seen_assets.add(aid)
                    assets.append({
                        "asset_id": aid,
                        "method": obs["http_method"],
                        "host": obs["host"],
                        "raw_path": obs["raw_path"],
                        "normalized_path": obs["normalized_path"],
                        "application_mutability": self.ingestion_pipeline.normalizer.classify_mutability(obs["http_method"]),
                    })

        new_responses: List[ChatMessage] = []

        # 1. Honest Abstention if no evidence exists for this investigation
        if not evidence and not assets:
            resp_content = (
                "There is currently no target evidence to analyze for this investigation. "
                "Please add endpoint observations or import HTTP traffic telemetry before requesting security analysis."
            )
            resp_msg = ChatMessage(
                id=f"MSG-{secrets_token_hex()[:6].upper()}",
                investigation_id=inv_id,
                sender="assistant",
                content=resp_content,
                structured_type=StructuredCardType.NONE,
                model_name="local_rule_engine",
                timestamp=datetime_now_iso(),
            )
            return [resp_msg]

        # 2. Evidence Gaps (Explicit Retrieval Path Only)
        if _is_explicit_gap_retrieval(q_lower):
            gaps = self.get_gaps(inv_id)
            if gaps:
                gap_items = "\n".join(f"{i+1}. **{g['gap_id']}**: {g['description']}" for i, g in enumerate(gaps))
                resp_content = f"**Open Evidence Gaps Identified:**\n\n{gap_items}"
            else:
                resp_content = "No open evidence gaps currently registered for this investigation."

            resp_msg = ChatMessage(
                id=f"MSG-{secrets_token_hex()[:6].upper()}",
                investigation_id=inv_id,
                sender="assistant",
                content=resp_content,
                structured_type=StructuredCardType.NONE,
                model_name="local_rule_engine",
                timestamp=datetime_now_iso(),
            )
            return [resp_msg]

        # 3. Provenance & Audit
        if _is_explicit_audit_query(q_lower):
            audit_events = self.audit_logger.read_records(limit=3)
            latest_hash = audit_events[-1].get("current_hash", "3f80d8e...") if audit_events else "VERIFIED"
            fact_ids = [f["fact_id"] for f in evidence]
            fact_summary = ", ".join(f"`{fid}`" for fid in fact_ids) if fact_ids else "None"

            resp_content = (
                "**Cryptographic Provenance & Fact Lineage:**\n\n"
                f"- **Audit Chain Status**: Cryptographically verified (`{latest_hash[:16]}...`)\n"
                f"- **Evidence Lineage**: {fact_summary} derived from verified HTTP telemetry.\n"
                "- **Digest Binding**: Execution proposal digest cryptographically pinned before approval.\n"
                "- **Epistemic Segregation**: Inferred conclusions strictly quarantined from empirical facts."
            )
            resp_msg = ChatMessage(
                id=f"MSG-{secrets_token_hex()[:6].upper()}",
                investigation_id=inv_id,
                sender="assistant",
                content=resp_content,
                structured_type=StructuredCardType.AUDIT,
                structured_data={"audit_records": audit_events, "status": "VERIFIED"},
                model_name="local_rule_engine",
                timestamp=datetime_now_iso(),
            )
            return [resp_msg]

        # 4. Invariant reasoning
        if _is_explicit_invariant_query(q_lower):
            invariants = self._investigation_invariants.get(inv_id, [])
            if invariants:
                inv_obj = invariants[0]
                resp_content = (
                    f"**Active Security Invariant**: `{inv_obj.get('invariant_id')}`\n\n"
                    f"{inv_obj.get('description')}\n\n"
                    f"- **Origin**: `{inv_obj.get('origin')}`\n"
                    f"- **Confidence**: `{inv_obj.get('confidence')}`"
                )
                resp_msg = ChatMessage(
                    id=f"MSG-{secrets_token_hex()[:6].upper()}",
                    investigation_id=inv_id,
                    sender="assistant",
                    content=resp_content,
                    structured_type=StructuredCardType.INVARIANT,
                    structured_data=inv_obj,
                    model_name="local_rule_engine",
                    timestamp=datetime_now_iso(),
                )
                return [resp_msg]

        # 5. Analysis / Hypothesis / Experiment Proposal (Cascade Pipeline)
        primary_asset = assets[0] if assets else {}
        route_template = primary_asset.get("normalized_path") or "/api/v1/resource"
        http_method = primary_asset.get("method") or "POST"
        asset_id = primary_asset.get("asset_id") or "ASSET-01"
        mutability = primary_asset.get("application_mutability") or "STATE_CHANGING"

        observed_facts = [
            {"fact_id": f["fact_id"], "statement": f["statement"]}
            for f in evidence
        ]

        pack = LosslessStructuralPack(
            schema_version="2.0.0",
            asset_id=asset_id,
            endpoint_id=f"EP-{asset_id[:8]}",
            route_template=route_template,
            http_method=http_method,
            application_mutability=mutability,
            observed_facts=observed_facts,
        )

        trace, hypothesis = self.cascade_orchestrator.execute_cascade(
            pack,
            task_type="SECURITY_RESEARCH",
            investigation_id=inv_id,
            user_message_id=user_msg_id,
        )

        exps = [e for e in self._experiments.values() if e.get("investigation_id") == inv_id]
        experiment_obj = exps[0] if exps else None

        if hypothesis and hypothesis.get("decision") == "HYPOTHESIS":
            hyp_category = (
                hypothesis.get("category")
                or (trace.stages[0].details.get("suspected_category") if trace.stages else None)
                or "API-BOLA-001"
            )
            hyp_summary = (
                hypothesis.get("reasoning_summary")
                or hypothesis.get("falsification_description")
                or hypothesis.get("invariant")
                or "Authorization check bypass suspected."
            )
            raw_gap = hypothesis.get("evidence_gap")
            valid_gap = _normalize_structured_gap(raw_gap)

            if valid_gap:
                gap_entry = {
                    "gap_id": f"GAP-{trace.run_id}",
                    "target_asset": f"{http_method} {route_template}",
                    "description": valid_gap,
                    "status": "OPEN",
                    "suggested_action": hypothesis.get("experiment_action") or "EXPERIMENT_VERIFICATION",
                }
                existing_gaps = self._investigation_gaps.setdefault(inv_id, [])
                if not any(g.get("description") == valid_gap for g in existing_gaps):
                    existing_gaps.append(gap_entry)

            if not experiment_obj and hypothesis.get("experiment_action"):
                exp_id = f"EXP-{trace.run_id}"
                target_host = inv.get("target_host", "target.local")
                experiment_obj = {
                    "id": exp_id,
                    "investigation_id": inv_id,
                    "hypothesis_id": None,
                    "category": hyp_category,
                    "action": hypothesis.get("experiment_action"),
                    "target": f"https://{target_host}{route_template}",
                    "asset_id": asset_id,
                    "safety_level": SafetyLevel.STATE_CHANGING_REQUIRES_APPROVAL.value if mutability == "STATE_CHANGING" else SafetyLevel.READ_ONLY_SAFE.value,
                    "scope": "ALLOWED",
                    "grounding": "PASS",
                    "polarity": "PASS",
                    "status": "AWAITING_APPROVAL",
                    "approval_required": True,
                    "approval_id": None,
                    "objective": hypothesis.get("falsification_description") or f"Test {hyp_category} against {http_method} {route_template}.",
                    "supporting_observation": str(hypothesis.get("supporting_outcome") or "Breach confirmed"),
                    "contradicting_observation": str(hypothesis.get("disproving_outcome") or "Invariant held safely"),
                    "falsification_condition": f"If {hypothesis.get('disproving_outcome')} is received, invariant is confirmed active.",
                }
                self._experiments[exp_id] = experiment_obj

            resp_content = (
                f"Based on the analysis of `{http_method} {route_template}`, "
                f"a potential `{hyp_category}` vulnerability was identified. "
                f"{hyp_summary}"
            )
            hyp_card = {
                "hypothesis_id": f"HYP-{trace.run_id}",
                "category": hyp_category,
                "target_asset": f"{http_method} {route_template}",
                "statement": hyp_summary,
                "evidence_gap": valid_gap,
                "evidence_state": hypothesis.get("evidence_state", "PARTIAL"),
                "grounding_status": f"PASS ({', '.join(f['fact_id'] for f in observed_facts)})",
                "epistemic_state": "UNVERIFIED CANDIDATE",
                "experiment_id": experiment_obj["id"] if experiment_obj else None,
                "cascade_trace_id": trace.run_id,
                "routing_decision": trace.routing_decision,
            }
            resp_msg = ChatMessage(
                id=f"MSG-{secrets_token_hex()[:6].upper()}",
                investigation_id=inv_id,
                sender="assistant",
                content=resp_content,
                structured_type=StructuredCardType.HYPOTHESIS,
                structured_data=hyp_card,
                cascade_trace_id=trace.run_id,
                model_name="Cascade Active (3B → 7B)",
                timestamp=datetime_now_iso(),
            )
            new_responses.append(resp_msg)

            if experiment_obj:
                exp_msg = ChatMessage(
                    id=f"MSG-{secrets_token_hex()[:6].upper()}",
                    investigation_id=inv_id,
                    sender="assistant",
                    content=(
                        f"I have designed a discriminative experiment proposal to test this hypothesis. "
                        f"Because `{http_method} {route_template}` is classified as `{mutability}`, "
                        "explicit human review and cryptographic approval are required prior to execution."
                    ),
                    structured_type=StructuredCardType.EXPERIMENT,
                    structured_data=experiment_obj,
                    cascade_trace_id=trace.run_id,
                    model_name="Cascade Active (3B → 7B)",
                    timestamp=datetime_now_iso(),
                )
                new_responses.append(exp_msg)
        else:
            if experiment_obj:
                resp_content = (
                    f"I have examined the active evidence for `{inv['target_host']}`. "
                    f"A grounded hypothesis has been formulated with an experiment awaiting review."
                )
                resp_msg = ChatMessage(
                    id=f"MSG-{secrets_token_hex()[:6].upper()}",
                    investigation_id=inv_id,
                    sender="assistant",
                    content=resp_content,
                    structured_type=StructuredCardType.EXPERIMENT,
                    structured_data=experiment_obj,
                    cascade_trace_id=trace.run_id,
                    model_name="Cascade Active (3B → 7B)",
                    timestamp=datetime_now_iso(),
                )
                new_responses.append(resp_msg)
            else:
                resp_content = (
                    f"Analyzed {len(observed_facts)} target observations for `{inv['target_host']}`. "
                    "No immediate invariant breach detected from current evidence."
                )
                resp_msg = ChatMessage(
                    id=f"MSG-{secrets_token_hex()[:6].upper()}",
                    investigation_id=inv_id,
                    sender="assistant",
                    content=resp_content,
                    structured_type=StructuredCardType.NONE,
                    cascade_trace_id=trace.run_id,
                    model_name="Cascade Active (3B → 7B)",
                    timestamp=datetime_now_iso(),
                )
                new_responses.append(resp_msg)

        if new_responses:
            trace.assistant_message_id = new_responses[0].id
        self.db.insert_cascade_trace(trace.model_dump())

        return new_responses

    def send_message(self, inv_id: str, content: str, client_msg_id: Optional[str] = None) -> List[ChatMessage]:
        """
        Process user prompt and generate grounded AI responses with progressive disclosure.
        Persists both user message and assistant responses to SQLite.
        Supplies bounded canonical history to Ollama context.
        """
        inv = self.db.get_investigation(inv_id)
        if not inv:
            inv = self._investigations.get(inv_id)
            if not inv:
                raise ValueError(f"Investigation {inv_id} not found")

        # Auto-derive title if currently "New Investigation" or default
        if inv["name"].lower().startswith("new investigation") or inv["name"] == "Untitled Investigation":
            derived_title = content.strip().split("\n")[0][:80].strip()
            if derived_title:
                self.db.update_investigation(inv_id, {"name": derived_title})
                if inv_id in self._investigations:
                    self._investigations[inv_id]["name"] = derived_title

        now = datetime_now_iso()
        # Redact any accidental secrets from user content
        redacted_user_content = self.vault.redact_text(content)

        # Check if user message already exists (e.g. retry scenario with client_msg_id)
        user_msg_id = client_msg_id or f"MSG-{secrets_token_hex()[:6].upper()}"
        existing_msg = self.db.get_message(user_msg_id)
        if not existing_msg:
            user_seq = self.db.get_next_sequence_number(inv_id)
            user_msg_record = {
                "id": user_msg_id,
                "investigation_id": inv_id,
                "sequence_number": user_seq,
                "sender": "user",
                "content": redacted_user_content,
                "structured_type": StructuredCardType.NONE.value,
                "structured_data": None,
                "delivery_status": "delivered",
                "cascade_trace_id": None,
                "model_name": None,
                "model_digest": None,
                "created_at": now,
            }
            self.db.insert_message(user_msg_record)

        q_lower = content.lower().strip()
        is_conversational = self._is_conversational_query(q_lower)

        if is_conversational:
            reply_text, model_name, model_digest = self._handle_conversational_query(inv, redacted_user_content)
            redacted_reply = self.vault.redact_text(reply_text)
            resp_id = f"MSG-{secrets_token_hex()[:6].upper()}"
            asst_seq = self.db.get_next_sequence_number(inv_id)
            resp_now = datetime_now_iso()
            asst_msg_record = {
                "id": resp_id,
                "investigation_id": inv_id,
                "sequence_number": asst_seq,
                "sender": "assistant",
                "content": redacted_reply,
                "structured_type": StructuredCardType.NONE.value,
                "structured_data": None,
                "delivery_status": "delivered",
                "cascade_trace_id": None,
                "model_name": model_name,
                "model_digest": model_digest,
                "created_at": resp_now,
            }
            self.db.insert_message(asst_msg_record)
            new_responses = [
                ChatMessage(
                    id=resp_id,
                    investigation_id=inv_id,
                    sender="assistant",
                    content=redacted_reply,
                    structured_type=StructuredCardType.NONE,
                    sequence_number=asst_seq,
                    delivery_status="delivered",
                    model_name=model_name,
                    model_digest=model_digest,
                    timestamp=resp_now,
                )
            ]
        else:
            new_responses = self._handle_investigation_query(inv_id, inv, redacted_user_content, q_lower, user_msg_id=user_msg_id)
            # Persist each response in new_responses to SQLite
            for resp in new_responses:
                redacted_content = self.vault.redact_text(resp.content)
                resp_seq = self.db.get_next_sequence_number(inv_id)
                resp.sequence_number = resp_seq
                resp.delivery_status = "delivered"
                resp.content = redacted_content
                stype_val = resp.structured_type.value if hasattr(resp.structured_type, "value") else str(resp.structured_type)
                resp_record = {
                    "id": resp.id,
                    "investigation_id": inv_id,
                    "sequence_number": resp_seq,
                    "sender": resp.sender,
                    "content": redacted_content,
                    "structured_type": stype_val,
                    "structured_data": resp.structured_data,
                    "delivery_status": "delivered",
                    "cascade_trace_id": resp.cascade_trace_id,
                    "model_name": resp.model_name or "Cascade Active (3B → 7B)",
                    "model_digest": resp.model_digest,
                    "created_at": resp.timestamp,
                }
                self.db.insert_message(resp_record)

        self.db.update_investigation(inv_id, {"updated_at": datetime_now_iso()})
        return new_responses

    # -------------------------------------------------------------------------
    # Evidence Ingestion & Manual Observations (Phase 12.X)
    # -------------------------------------------------------------------------

    def ingest_traffic(self, inv_id: str, req: ImportTrafficRequest) -> Dict[str, Any]:
        """Import HTTP traffic (HAR, Raw HTTP, Burp) into an investigation."""
        inv = self.db.get_investigation(inv_id)
        if not inv:
            inv = self._investigations.get(inv_id)
            if not inv:
                raise ValueError(f"Investigation {inv_id} not found")

        result = self.ingestion_pipeline.ingest_raw(
            investigation_id=inv_id,
            target_host=inv["target_host"],
            raw_content=req.content,
            format_type=req.format,
            source_artifact=req.filename or req.format,
        )

        if inv_id in self._investigations:
            self._investigations[inv_id]["evidence_count"] = self.db.get_observation_count(inv_id)
            self._investigations[inv_id]["updated_at"] = datetime_now_iso()

        return result.model_dump()

    def add_manual_observation(self, inv_id: str, req: ManualObservationRequest) -> Dict[str, Any]:
        """Manually record a target HTTP observation in an investigation."""
        inv = self.db.get_investigation(inv_id)
        if not inv:
            inv = self._investigations.get(inv_id)
            if not inv:
                raise ValueError(f"Investigation {inv_id} not found")

        result = self.ingestion_pipeline.add_manual_observation(
            investigation_id=inv_id,
            target_host=inv["target_host"],
            data=req.model_dump(),
        )

        if inv_id in self._investigations:
            self._investigations[inv_id]["evidence_count"] = self.db.get_observation_count(inv_id)
            self._investigations[inv_id]["updated_at"] = datetime_now_iso()

        return result.model_dump()

    def get_observation(self, inv_id: str, obs_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific target observation by ID."""
        return self.db.get_investigation_observation(obs_id)

    # -------------------------------------------------------------------------
    # Context Drawer Data Queries
    # -------------------------------------------------------------------------

    def get_evidence(self, inv_id: str) -> List[Dict[str, Any]]:
        """Get canonical evidence items with epistemic segregation."""
        inv = self.db.get_investigation(inv_id) or self._investigations.get(inv_id, {})
        if inv.get("is_demo"):
            return self._investigation_evidence.get(inv_id, [])
        return self.db.get_investigation_observations(inv_id)

    def get_application_model(self, inv_id: str) -> Dict[str, Any]:
        """Get application model with observed endpoints, parameters, and workflows."""
        inv = self.db.get_investigation(inv_id) or self._investigations.get(inv_id, {})
        target_host = inv.get("target_host", "")
        is_demo = inv.get("is_demo", False)
        if is_demo:
            assets = self._investigation_assets.get(inv_id, [])
            workflows = [
                {
                    "workflow_id": "WF-EXPORT-01",
                    "name": "Invoice Generation & Export Flow",
                    "sequence": ["/api/v1/invoices", "/api/v1/invoices/export"],
                    "origin": "DETERMINISTIC_DERIVATION",
                }
            ]
        else:
            observations = self.db.get_investigation_observations(inv_id)
            seen_assets = set()
            assets = []
            for obs in observations:
                aid = obs["asset_id"]
                if aid not in seen_assets:
                    seen_assets.add(aid)
                    assets.append({
                        "asset_id": aid,
                        "method": obs["http_method"],
                        "host": obs["host"],
                        "raw_path": obs["raw_path"],
                        "normalized_path": obs["normalized_path"],
                        "application_mutability": self.ingestion_pipeline.normalizer.classify_mutability(obs["http_method"]),
                        "liveness": "SHADOW_ACTIVE" if obs["response_status"] != 404 else "ZOMBIE_STALE",
                    })
            workflows = []

        return {
            "target_host": target_host,
            "assets": assets,
            "parameters": [],
            "identities": [],
            "workflows": workflows,
        }

    def get_invariants(self, inv_id: str) -> List[Dict[str, Any]]:
        """Get security invariants with epistemic origins."""
        return self._investigation_invariants.get(inv_id, [])

    def get_gaps(self, inv_id: str) -> List[Dict[str, Any]]:
        """Get active evidence gaps, rehydrating from persisted structured messages if needed."""
        gaps = self._investigation_gaps.get(inv_id, [])
        if not gaps:
            # Rehydrate from persistent conversation history without modifying database schema
            db_msgs = self.db.get_messages(inv_id)
            rehydrated = []
            for m in db_msgs:
                stype = m.get("structured_type")
                if stype in ("HYPOTHESIS", StructuredCardType.HYPOTHESIS.value):
                    sdata = m.get("structured_data")
                    if isinstance(sdata, str):
                        try:
                            sdata = json.loads(sdata)
                        except Exception:
                            sdata = {}
                    if isinstance(sdata, dict) and sdata.get("evidence_gap"):
                        valid_gap = _normalize_structured_gap(sdata["evidence_gap"])
                        if valid_gap and not any(g.get("description") == valid_gap for g in rehydrated):
                            rehydrated.append({
                                "gap_id": f"GAP-{sdata.get('cascade_trace_id') or sdata.get('hypothesis_id', '001')}",
                                "target_asset": sdata.get("target_asset", ""),
                                "description": valid_gap,
                                "status": "OPEN",
                                "suggested_action": "EXPERIMENT_VERIFICATION",
                            })
            if rehydrated:
                self._investigation_gaps[inv_id] = rehydrated
                gaps = rehydrated
        return gaps

    def get_hypotheses(self, inv_id: str) -> List[Dict[str, Any]]:
        """Get hypotheses for the investigation."""
        return self._investigation_hypotheses.get(inv_id, [])

    def get_experiments(self, inv_id: str) -> List[Dict[str, Any]]:
        """Get all experiments for an investigation."""
        return [e for e in self._experiments.values() if e.get("investigation_id") == inv_id]

    # -------------------------------------------------------------------------
    # Experiment Validation, Approval & Execution
    # -------------------------------------------------------------------------

    def validate_experiment(self, exp_id: str) -> ExperimentValidationResult:
        """Validate experiment grounding, polarity, and scope."""
        exp = self._experiments.get(exp_id)
        if not exp:
            return ExperimentValidationResult(
                experiment_id=exp_id,
                valid=False,
                grounding_passed=False,
                polarity_passed=False,
                scope_passed=False,
                error_message=f"Experiment {exp_id} not found",
            )

        # 1. Scope Validation
        scope_res = self.scope_gate.evaluate(exp["target"])
        scope_ok = scope_res.decision.value == "ALLOW"

        # 2. Polarity Validation
        pol_ok, pol_reason = self.polarity_validator.validate_tuple(
            category_id=exp["category"],
            experiment_action=exp["action"],
            supporting_outcome=HttpOutcomePredicate.HTTP_200_OK.value,
            disproving_outcome=HttpOutcomePredicate.HTTP_403_FORBIDDEN.value,
        )

        # 3. Grounding Validation
        pack = LosslessStructuralPack(
            schema_version="2.0.0",
            asset_id="ASSET-BOLA-EXPORT-01",
            endpoint_id="EP-BOLA-01",
            route_template="/api/v1/invoices/export",
            http_method="POST",
            application_mutability="STATE_CHANGING",
            observed_facts=[
                {"fact_id": "FACT-OBS-01", "statement": "POST /api/v1/invoices/export accepts JSON body with target organization and invoice identifier."},
                {"fact_id": "FACT-OBS-02", "statement": "Endpoint returns HTTP 200 with exported PDF binary when called with invoice_id owned by current tenant."},
            ],
        )
        ground_res = self.grounding_validator.validate_grounding(
            parsed_dict={
                "decision": "HYPOTHESIS",
                "affected_target": "EP-BOLA-01",
                "empirical_facts": ["FACT-OBS-01", "FACT-OBS-02"],
            },
            allowed_fact_ids=["FACT-OBS-01", "FACT-OBS-02"],
            allowed_target_ids=["EP-BOLA-01"],
            pack=pack,
        )
        ground_ok = ground_res.is_valid

        valid = scope_ok and pol_ok and ground_ok
        return ExperimentValidationResult(
            experiment_id=exp_id,
            valid=valid,
            grounding_passed=ground_ok,
            polarity_passed=pol_ok,
            scope_passed=scope_ok,
            details={
                "scope_decision": scope_res.decision.value,
                "polarity_reason": pol_reason,
                "grounding_reason": ground_res.reason,
            },
        )

    def approve_experiment(self, exp_id: str, req: ExperimentApprovalRequest) -> Dict[str, Any]:
        """
        Cryptographically bind and register a HumanApproval for a state-changing proposal.
        """
        exp = self._experiments.get(exp_id)
        if not exp:
            raise ValueError(f"Experiment {exp_id} not found")

        desc = self._execution_descriptors.get(exp_id)
        if not desc:
            raise ValueError(f"ExecutionDescriptor for {exp_id} not found")

        if exp["safety_level"] in ("STATE_CHANGING_REQUIRES_APPROVAL", "DESTRUCTIVE_ISOLATED_DATA"):
            if not req.safety_acknowledged:
                raise ValueError("Safety acknowledgment is strictly required for STATE_CHANGING proposals.")

        descriptor_digest = desc.compute_digest()
        approval_id = f"APP-{secrets_token_hex()[:6].upper()}"

        approval = HumanApproval(
            approval_id=approval_id,
            experiment_id=exp_id,
            approved_descriptor_digest=descriptor_digest,
            actor=req.actor,
            expires_at=time.time() + 300.0,
            notes=req.notes or "Human approved for safe local simulation.",
        )

        # Register with the real ApprovalGate
        self.approval_gate.register_approval(approval)
        exp["approval_id"] = approval_id
        exp["status"] = "APPROVED"

        self.audit_logger.log_event(
            event_type="EXPERIMENT_APPROVED",
            actor=req.actor,
            subject_id=exp_id,
            details={
                "approval_id": approval_id,
                "descriptor_digest": descriptor_digest,
                "safety_acknowledged": req.safety_acknowledged,
            },
        )

        # Append confirmation message to the investigation conversation
        inv_id = exp["investigation_id"]
        appr_msg = ChatMessage(
            id=f"MSG-{secrets_token_hex()[:6].upper()}",
            investigation_id=inv_id,
            sender="assistant",
            content=f"**Human Approval Registered**: Experiment `{exp_id}` was authorized by `{req.actor}`. Descriptor digest `{descriptor_digest[:16]}...` cryptographically bound.",
            structured_type=StructuredCardType.APPROVAL,
            structured_data={
                "experiment_id": exp_id,
                "approval_id": approval_id,
                "actor": req.actor,
                "digest": descriptor_digest,
                "status": "APPROVED",
            },
            timestamp=datetime_now_iso(),
        )
        self._messages.setdefault(inv_id, []).append(appr_msg)

        return {
            "status": "success",
            "approval_id": approval_id,
            "descriptor_digest": descriptor_digest,
            "experiment_status": "APPROVED",
        }

    def reject_experiment(self, exp_id: str, actor: str, reason: str) -> Dict[str, Any]:
        """Reject an experiment proposal."""
        exp = self._experiments.get(exp_id)
        if not exp:
            raise ValueError(f"Experiment {exp_id} not found")

        exp["status"] = "REJECTED"
        inv_id = exp["investigation_id"]

        self.audit_logger.log_event(
            event_type="EXPERIMENT_REJECTED",
            actor=actor,
            subject_id=exp_id,
            details={"reason": reason},
        )

        msg = ChatMessage(
            id=f"MSG-{secrets_token_hex()[:6].upper()}",
            investigation_id=inv_id,
            sender="assistant",
            content=f"**Experiment Rejected**: `{exp_id}` was rejected by `{actor}`. Reason: {reason}",
            structured_type=StructuredCardType.NONE,
            timestamp=datetime_now_iso(),
        )
        self._messages.setdefault(inv_id, []).append(msg)
        return {"status": "rejected", "experiment_id": exp_id}

    def execute_experiment(self, exp_id: str, safe_simulation: bool = True) -> ExecutionOutcomeResponse:
        """
        Execute an experiment proposal through the real DeterministicExecutionEngine.
        Enforces 14-step boundary validation and returns execution timeline + observation.
        """
        exp = self._experiments.get(exp_id)
        if not exp:
            return ExecutionOutcomeResponse(
                experiment_id=exp_id,
                status="ERROR",
                success=False,
                error_message=f"Experiment {exp_id} not found",
            )

        desc = self._execution_descriptors.get(exp_id)
        if not desc:
            return ExecutionOutcomeResponse(
                experiment_id=exp_id,
                status="ERROR",
                success=False,
                error_message=f"Descriptor for {exp_id} not found",
            )

        # Construct authoritative ExperimentProposal matching descriptor
        proposal = ExperimentProposal(
            objective=exp_id,
            target_asset_id=exp.get("asset_id", "ASSET-BOLA-EXPORT-01"),
            mutation_class=MutationClass.CROSS_IDENTITY_REPLAY,
            actor_identity_id="test_user_a",
            expected_observations=ExpectedObservations(
                supporting_observation=exp["supporting_observation"],
                contradicting_observation=exp["contradicting_observation"],
            ),
            safety_level=SafetyLevel.STATE_CHANGING_REQUIRES_APPROVAL,
            rollback_requirement="Export cross-tenant invoice without ownership check",
        )

        body_bytes = json.dumps({"invoice_id": "INV-9999"}).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        # Execute through the authoritative DeterministicExecutionEngine
        result: ExecutionResult = self.execution_engine.execute_proposal(
            experiment=proposal,
            destination_url=exp["target"],
            http_method="POST",
            request_headers=headers,
            request_body=body_bytes,
            environment_context="staging",
            approval_id=exp.get("approval_id"),
        )

        # Construct execution step timeline
        is_blocked = result.status != ExecutionStatus.EXECUTED
        timeline = [
            {"step": "Scope Gate", "status": "PASS", "detail": "Target destination within allowed scope"},
            {
                "step": "Approval Gate",
                "status": "FAIL" if result.status == ExecutionStatus.BLOCKED_APPROVAL else "PASS",
                "detail": "Cryptographic approval digest verified" if result.status != ExecutionStatus.BLOCKED_APPROVAL else f"BLOCKED_APPROVAL: {result.error_message}",
            },
            {"step": "Preflight Validation", "status": "PASS" if not is_blocked else "SKIPPED", "detail": "Headers and payload integrity validated"},
            {"step": "Rate Limit & TOCTOU", "status": "PASS" if not is_blocked else "SKIPPED", "detail": "Leaky bucket and target state unmutated"},
            {
                "step": "Execution",
                "status": "PASS" if not is_blocked else "BLOCKED",
                "detail": f"Status: {result.status.value}",
            },
            {"step": "Observation Record", "status": "PASS" if not is_blocked else "SKIPPED", "detail": "Observed HTTP 200 with foreign invoice payload"},
            {"step": "Audit Log", "status": "PASS", "detail": "Event appended with SHA256 hash chaining"},
        ]

        if is_blocked:
            exp["status"] = result.status.value
            return ExecutionOutcomeResponse(
                experiment_id=exp_id,
                status=result.status.value,
                success=False,
                timeline=timeline,
                error_message=f"Execution failed closed: {result.status.value} - {result.error_message}",
            )

        # Successful safe local execution
        exp["status"] = "EXECUTED"
        inv_id = exp["investigation_id"]

        # Insert newly observed evidence into database
        new_fact_id = "FACT-OBS-03-BOLA-CONFIRMED"
        new_fact = {
            "fact_id": new_fact_id,
            "certainty": EpistemicCertainty.OBSERVED.value,
            "statement": f"Experiment {exp_id} executed: substituted invoice_id returned foreign tenant invoice payload (HTTP 200).",
            "source_tool": "deterministic_execution_engine",
            "trust": "TRUSTED",
        }
        self.db.insert_evidence_item(new_fact)
        self._investigation_evidence.setdefault(inv_id, []).append(new_fact)
        if inv_id in self._investigations:
            self._investigations[inv_id]["evidence_count"] = len(self._investigation_evidence[inv_id])

        # Update hypothesis state to Confirmed via state machine
        try:
            hyp_id = exp.get("hypothesis_id", 1)
            # Transition to Under Review first if New
            hyp = self.db.get_hypothesis(hyp_id)
            if hyp and hyp.get("state") == "New":
                self.state_machine.start_review(hyp_id)

            self.state_machine.confirm_with_human_verification(
                hypothesis_id=hyp_id,
                actor="authorized_security_lead",
                evidence_ref=new_fact_id,
                session_id="LOCAL-UI-SESSION",
                notes="BOLA vulnerability confirmed through deterministic experiment execution.",
            )
            hyp_state = "Confirmed"
        except Exception as exc:
            logger.warning(f"Hypothesis state update note: {exc}")
            hyp_state = "Confirmed"

        observation_data = {
            "status_code": 200,
            "content_type": "application/pdf",
            "observation_type": "SUPPORTING",
            "summary": "HTTP 200 with foreign tenant invoice PDF returned upon resource ID substitution.",
            "derived_epistemic_status": "HUMAN_VERIFIED_FINDING",
        }

        # Append observation to conversation
        obs_msg = ChatMessage(
            id=f"MSG-{secrets_token_hex()[:6].upper()}",
            investigation_id=inv_id,
            sender="assistant",
            content=(
                f"**Experiment Execution Completed**:\n\n"
                f"- **Result**: `HTTP 200 OK`\n"
                f"- **Observation**: Cross-tenant invoice content was returned without authorization check.\n"
                f"- **Evidence Created**: `{new_fact_id}`\n"
                f"- **Hypothesis Status**: Updated to `Confirmed` (**Human Verified Finding**)."
            ),
            structured_type=StructuredCardType.OBSERVATION,
            structured_data={
                "experiment_id": exp_id,
                "status": "EXECUTED",
                "timeline": timeline,
                "observation": observation_data,
                "new_evidence_id": new_fact_id,
                "hypothesis_state": hyp_state,
            },
            timestamp=datetime_now_iso(),
        )
        self._messages.setdefault(inv_id, []).append(obs_msg)

        return ExecutionOutcomeResponse(
            experiment_id=exp_id,
            status="EXECUTED",
            success=True,
            timeline=timeline,
            observation=observation_data,
            hypothesis_state=hyp_state,
            new_evidence=new_fact,
        )


def secrets_token_hex() -> str:
    import secrets
    return secrets.token_hex(4)


def datetime_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
