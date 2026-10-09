"""Central Assessment Workspace Manager and Isolation Controller for M6.

Enforces:
1. Complete Cross-Assessment Isolation (assessment_id partitioning).
2. Assessment lifecycle progression via AssessmentLifecycleEngine.
3. Integrated access to ScopeGate, AssetGraph, TelemetryPipeline, AttackSurfaceMap,
   LineageGraph, ReviewWorkspace, FindingValidator, and ReportGenerator.
4. INVARIANT: Secrets are redacted and cross-assessment contamination is strictly prevented.
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.assessment.models import (
    AssessmentFinding,
    AssessmentHypothesis,
    AssessmentExperiment,
    AssessmentLifecycleState,
    AssessmentRecord,
    AssessmentScopeStatus,
    AssetRecord,
    AssetType,
    AttackSurfaceState,
    AuthorizationRecord,
    AuthorizationStatus,
    CanonicalObservation,
    ExperimentRiskLevel,
    FindingSeverity,
    FindingVerificationStatus,
)
from src.assessment.authorization import AuthorizationValidator
from src.assessment.lifecycle import AssessmentLifecycleEngine
from src.assessment.assets import AssetGraph
from src.assessment.attack_surface import AttackSurfaceMap
from src.assessment.analysis import SecurityAnalysisEngine
from src.assessment.lineage import EvidenceLineageGraph
from src.assessment.experiments import SafeExperimentEngine
from src.assessment.review import HumanReviewWorkspace
from src.assessment.validation import FindingValidator, AssessmentValidationContext
from src.assessment.reporting import AssessmentReportGenerator, AssessmentReportContext
from src.assessment.observability import AssessmentAuditLogger
from src.scope.gate import ScopeGate
from src.scope.models import ScopePolicy
from src.telemetry.normalizer import TelemetryIngestionPipeline


class AssessmentContainer:
    """Isolated runtime container for a single assessment."""

    def __init__(self, record: AssessmentRecord, scope_policy: Optional[ScopePolicy] = None) -> None:
        self.record = record
        self.authorization: Optional[AuthorizationRecord] = None
        self.scope_gate = ScopeGate(
            policy=scope_policy or ScopePolicy(
                program_name=record.assessment_name,
                platform="M6_ASSESSMENT",
                in_scope=[],
            ),
            allow_private_ranges=True,
            dns_resolver=lambda h: ["93.184.216.34"],
        )
        self.asset_graph = AssetGraph(assessment_id=record.assessment_id)
        self.telemetry_pipeline = TelemetryIngestionPipeline(
            scope_gate=self.scope_gate,
            asset_graph=self.asset_graph,
        )
        self.attack_surface = AttackSurfaceMap(assessment_id=record.assessment_id)
        self.analysis_engine = SecurityAnalysisEngine(assessment_id=record.assessment_id)
        self.lineage_graph = EvidenceLineageGraph(assessment_id=record.assessment_id)
        self.experiment_engine = SafeExperimentEngine(
            assessment_id=record.assessment_id,
            scope_gate=self.scope_gate,
        )
        self.review_workspace = HumanReviewWorkspace(assessment_id=record.assessment_id)
        self.audit_logger = AssessmentAuditLogger(assessment_id=record.assessment_id)
        self.findings: Dict[str, AssessmentFinding] = {}

        self.audit_logger.record_event(
            event_type="ASSESSMENT_CREATED",
            actor="SYSTEM",
            component="AssessmentContainer",
            authorization_state="NONE",
            scope_state="UNCONFIGURED",
        )


class AssessmentManager:
    """Singleton service providing isolated assessment management and REST operations."""

    _instance: Optional["AssessmentManager"] = None

    def __init__(self) -> None:
        self._assessments: Dict[str, AssessmentContainer] = {}
        # Global index of experiment_id -> assessment_id for direct experiment lookups
        self._experiment_to_assessment: Dict[str, str] = {}
        # Global index of finding_id -> assessment_id for direct finding lookups
        self._finding_to_assessment: Dict[str, str] = {}
        # Global index of hypothesis_id -> assessment_id
        self._hypothesis_to_assessment: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> "AssessmentManager":
        if cls._instance is None:
            cls._instance = AssessmentManager()
        return cls._instance

    def create_assessment(self, organization: str, assessment_name: str, created_by: str = "HUMAN_OPERATOR") -> AssessmentRecord:
        seed = f"{organization}:{assessment_name}:{datetime.now(timezone.utc).isoformat()}"
        aid = f"ASM-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12].upper()}"
        rec = AssessmentRecord(
            assessment_id=aid,
            organization=organization,
            assessment_name=assessment_name,
            state=AssessmentLifecycleState.DRAFT,
            created_by=created_by,
        )
        container = AssessmentContainer(rec)
        self._assessments[aid] = container
        return rec

    def get_assessment(self, assessment_id: str) -> Optional[AssessmentRecord]:
        cont = self._assessments.get(assessment_id)
        return cont.record if cont else None

    def get_container(self, assessment_id: str) -> AssessmentContainer:
        if assessment_id not in self._assessments:
            raise KeyError(f"Assessment '{assessment_id}' not found.")
        return self._assessments[assessment_id]

    def get_scope_gate(self, assessment_id: str) -> ScopeGate:
        return self.get_container(assessment_id).scope_gate

    def set_authorization(self, assessment_id: str, auth_record: AuthorizationRecord, actor: str = "HUMAN_AUTHORITY") -> AuthorizationRecord:
        cont = self.get_container(assessment_id)
        is_valid, reason = AuthorizationValidator.validate_authorization(auth_record)
        if not is_valid:
            raise ValueError(f"Cannot accept invalid authorization: {reason}")

        cont.authorization = auth_record
        cont.record.authorization_id = auth_record.authorization_id

        # Advance lifecycle to AUTHORIZED if in DRAFT or AUTHORIZATION_PENDING
        if cont.record.state in (AssessmentLifecycleState.DRAFT, AssessmentLifecycleState.AUTHORIZATION_PENDING):
            AssessmentLifecycleEngine.transition(
                cont.record,
                AssessmentLifecycleState.AUTHORIZED,
                actor=actor,
                reason="Valid AuthorizationRecord bound to assessment.",
                authorization=auth_record,
            )

        cont.audit_logger.record_event(
            event_type="AUTHORIZATION_ACCEPTED",
            actor=actor,
            component="AssessmentManager",
            authorization_state=auth_record.status.value,
            scope_state=auth_record.scope_reference,
            input_reference=auth_record.authorization_id,
        )
        return auth_record

    def set_scope(self, assessment_id: str, scope_policy: ScopePolicy, actor: str = "HUMAN_AUTHORITY") -> ScopePolicy:
        cont = self.get_container(assessment_id)
        cont.scope_gate.policy = scope_policy
        cont.record.scope_policy_id = scope_policy.program_name

        # Advance lifecycle to SCOPE_DEFINED if AUTHORIZED
        if cont.record.state == AssessmentLifecycleState.AUTHORIZED:
            AssessmentLifecycleEngine.transition(
                cont.record,
                AssessmentLifecycleState.SCOPE_DEFINED,
                actor=actor,
                reason="ScopePolicy defined for assessment.",
                authorization=cont.authorization,
                scope_defined=True,
            )

        cont.audit_logger.record_event(
            event_type="SCOPE_DEFINED",
            actor=actor,
            component="AssessmentManager",
            authorization_state=cont.authorization.status.value if cont.authorization else "NONE",
            scope_state=f"in_scope={len(scope_policy.in_scope)}",
        )
        return scope_policy

    set_scope_policy = set_scope

    def activate_assessment(self, assessment_id: str, actor: str = "HUMAN_AUTHORITY") -> AssessmentRecord:
        cont = self.get_container(assessment_id)
        AssessmentLifecycleEngine.transition(
            cont.record,
            AssessmentLifecycleState.ASSESSMENT_ACTIVE,
            actor=actor,
            reason="Assessment activated for testing.",
            authorization=cont.authorization,
            scope_defined=bool(cont.scope_gate.policy.in_scope),
        )
        return cont.record

    def import_telemetry(self, assessment_id: str, format_type: str, raw_payload: Any, tool_name: Optional[str] = None) -> Dict[str, Any]:
        cont = self.get_container(assessment_id)
        # Check if state allows target interaction
        allowed, msg = AssessmentLifecycleEngine.is_target_interaction_allowed(cont.record.state, cont.authorization)
        if not allowed:
            raise PermissionError(f"Cannot ingest telemetry: {msg}")

        report = cont.telemetry_pipeline.ingest(
            assessment_id=assessment_id,
            format_type=format_type,
            raw_payload=raw_payload,
            tool_name=tool_name,
        )

        # Register observations into lineage graph and attack surface
        new_obs = report.get("new_observations", [])
        for obs in new_obs:
            cont.lineage_graph.register_observation(obs)

        cont.attack_surface.process_observations(new_obs, cont.asset_graph)

        cont.audit_logger.record_event(
            event_type="OBSERVATION_IMPORTED",
            actor="TELEMETRY_PIPELINE",
            component="TelemetryIngestionPipeline",
            authorization_state=cont.authorization.status.value if cont.authorization else "UNKNOWN",
            scope_state=f"valid={report.get('valid_observations')}",
            input_reference=format_type,
        )
        return report

    def generate_hypotheses(self, assessment_id: str) -> List[AssessmentHypothesis]:
        cont = self.get_container(assessment_id)
        obs_list = cont.telemetry_pipeline.get_observations(assessment_id=assessment_id)
        hyps = cont.analysis_engine.analyze_attack_surface(cont.attack_surface, obs_list)
        for h in hyps:
            cont.lineage_graph.register_hypothesis(h)
            cont.review_workspace.load_hypothesis(h)
            self._hypothesis_to_assessment[h.hypothesis_id] = assessment_id
            cont.audit_logger.record_event(
                event_type="HYPOTHESIS_CREATED",
                actor="M6_ANALYSIS_ENGINE",
                component="SecurityAnalysisEngine",
                authorization_state="ACTIVE",
                scope_state="VERIFIED",
                epistemic_state="MODEL_HYPOTHESIS",
                input_reference=h.hypothesis_id,
            )
        return hyps

    def propose_experiment(
        self,
        assessment_id: str,
        hypothesis_id: str,
        objective: str,
        target_asset: str,
        steps: List[str],
        expected_secure_result: str,
        expected_vulnerable_result: str,
        falsification_condition: str,
        negative_control: str,
        risk_level: ExperimentRiskLevel = ExperimentRiskLevel.PASSIVE,
    ) -> AssessmentExperiment:
        cont = self.get_container(assessment_id)
        if not cont.authorization:
            raise PermissionError("Cannot propose experiment: Assessment lacks authorization.")

        exp = cont.experiment_engine.propose_experiment(
            hypothesis_id=hypothesis_id,
            objective=objective,
            target_asset=target_asset,
            authorization=cont.authorization,
            steps=steps,
            expected_secure_result=expected_secure_result,
            expected_vulnerable_result=expected_vulnerable_result,
            falsification_condition=falsification_condition,
            negative_control=negative_control,
            risk_level=risk_level,
        )
        cont.lineage_graph.register_experiment(exp)
        cont.review_workspace.load_experiment(exp)
        self._experiment_to_assessment[exp.experiment_id] = assessment_id
        return exp

    def import_experiment_result(self, experiment_id: str, result_payload: Dict[str, Any], executed_by: str) -> AssessmentExperiment:
        aid = self._experiment_to_assessment.get(experiment_id)
        if not aid:
            raise KeyError(f"Experiment '{experiment_id}' not found.")
        cont = self.get_container(aid)
        exp = cont.experiment_engine.import_human_result(experiment_id, result_payload, executed_by)
        cont.audit_logger.record_event(
            event_type="EXPERIMENT_RESULT_IMPORTED",
            actor=executed_by,
            component="SafeExperimentEngine",
            authorization_state="ACTIVE",
            scope_state="VERIFIED",
            input_reference=experiment_id,
        )
        return exp

    def verify_finding(self, finding_id: str, human_reviewer: str, justification: str) -> AssessmentFinding:
        aid = self._finding_to_assessment.get(finding_id)
        if not aid:
            raise KeyError(f"Finding '{finding_id}' not found.")
        cont = self.get_container(aid)
        finding = cont.findings[finding_id]

        # 13-point checklist validation
        context = AssessmentValidationContext(
            assessment=cont.record,
            authorization=cont.authorization,
            scope_gate=cont.scope_gate,
            observations={o.observation_id: o for o in cont.telemetry_pipeline.get_observations()},
            hypotheses=cont.review_workspace.hypotheses,
            experiments=cont.review_workspace.experiments,
        )

        # First mark human verified in workspace
        cont.review_workspace.verify_finding(finding_id, human_reviewer, justification)

        # Deterministic 13-point validation check
        FindingValidator.assert_finding_valid(finding, context)

        cont.audit_logger.record_event(
            event_type="FINDING_VERIFIED",
            actor=human_reviewer,
            component="FindingValidator",
            authorization_state="ACTIVE",
            scope_state="IN_SCOPE",
            epistemic_state="HUMAN_VERIFIED_FINDING",
            input_reference=finding_id,
        )
        return finding

    def register_candidate_finding(self, assessment_id: str, finding: AssessmentFinding) -> AssessmentFinding:
        cont = self.get_container(assessment_id)
        cont.findings[finding.finding_id] = finding
        cont.review_workspace.load_finding(finding)
        cont.lineage_graph.register_finding(finding)
        self._finding_to_assessment[finding.finding_id] = assessment_id
        return finding

    def generate_report(self, assessment_id: str) -> str:
        cont = self.get_container(assessment_id)
        if not cont.authorization:
            raise ValueError("Cannot generate report: Authorization missing.")

        ctx = AssessmentReportContext(
            assessment=cont.record,
            authorization=cont.authorization,
            assets=cont.asset_graph.get_all_assets(),
            observations=cont.telemetry_pipeline.get_observations(assessment_id=assessment_id),
            attack_surface=cont.attack_surface.export_summary(),
            hypotheses=list(cont.review_workspace.hypotheses.values()),
            findings=list(cont.findings.values()),
        )
        return AssessmentReportGenerator.generate_markdown(ctx)
