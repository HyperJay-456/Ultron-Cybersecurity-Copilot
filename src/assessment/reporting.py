"""Formal Security Assessment Report Generator for M6.

Enforces:
1. Complete Report Structure:
   - Executive Summary
   - Assessment Scope
   - Authorization Details
   - Methodology
   - Attack Surface & Asset Inventory
   - Confirmed Findings (HUMAN VERIFIED ONLY)
   - Out-of-Scope Observations
   - Unverified Hypotheses & Evidence Gaps
   - Testing Limitations
2. INVARIANT: Unverified hypotheses are NEVER presented as confirmed findings.
   Only findings passing all 13 FindingValidator checks and marked HUMAN_VERIFIED
   are included in the confirmed findings section.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.assessment.models import (
    AssessmentFinding,
    AssessmentHypothesis,
    AssessmentRecord,
    AssessmentScopeStatus,
    AssetRecord,
    AuthorizationRecord,
    CanonicalObservation,
    FindingVerificationStatus,
)
from src.assessment.attack_surface import AttackSurfaceMap


class AssessmentReportContext(BaseModel):
    """Encapsulates all assessment context necessary for report rendering."""
    assessment: AssessmentRecord
    authorization: AuthorizationRecord
    assets: List[AssetRecord] = Field(default_factory=list)
    observations: List[CanonicalObservation] = Field(default_factory=list)
    attack_surface: Optional[Dict[str, Any]] = None
    hypotheses: List[AssessmentHypothesis] = Field(default_factory=list)
    findings: List[AssessmentFinding] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class AssessmentReportGenerator:
    """Renders comprehensive, auditable security assessment reports."""

    @classmethod
    def generate_markdown(cls, ctx: AssessmentReportContext) -> str:
        """Generates GitHub-flavored markdown report."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Partition findings: HUMAN_VERIFIED vs others
        confirmed_findings = [f for f in ctx.findings if f.verification_status == FindingVerificationStatus.HUMAN_VERIFIED]
        unverified_hypotheses = [h for h in ctx.hypotheses if h.epistemic_status == "MODEL_HYPOTHESIS"]
        out_of_scope_obs = [o for o in ctx.observations if o.scope_decision != AssessmentScopeStatus.IN_SCOPE]

        md = []
        md.append(f"# Authorized Security Assessment Report: {ctx.assessment.assessment_name}\n")
        md.append(f"**Organization:** {ctx.assessment.organization}  ")
        md.append(f"**Assessment ID:** `{ctx.assessment.assessment_id}`  ")
        md.append(f"**Date Generated:** `{now_iso}`  ")
        md.append(f"**Status:** {ctx.assessment.state.value}\n")

        # 1. Executive Summary
        md.append("## 1. Executive Summary\n")
        md.append(
            f"This authorized security assessment was conducted for **{ctx.assessment.organization}** "
            f"covering defined target assets under explicit rules of engagement. "
            f"A total of **{len(ctx.assets)}** assets were inventoried, producing **{len(ctx.observations)}** "
            f"canonical observations. Testing resulted in **{len(confirmed_findings)}** human-verified security findings "
            f"and **{len(unverified_hypotheses)}** unverified hypotheses requiring further manual investigation.\n"
        )

        # 2. Authorization
        md.append("## 2. Authorization Details\n")
        md.append(f"- **Authorization ID:** `{ctx.authorization.authorization_id}`")
        md.append(f"- **Authorized By:** {ctx.authorization.authorized_by}")
        md.append(f"- **Engagement Type:** {ctx.authorization.authorization_type.value}")
        md.append(f"- **Validity Window:** `{ctx.authorization.valid_from}` to `{ctx.authorization.valid_until}`")
        md.append(f"- **Authorization Status:** `{ctx.authorization.status.value}`")
        if ctx.authorization.restrictions:
            md.append(f"- **Restrictions:** {', '.join(ctx.authorization.restrictions)}")
        md.append("")

        # 3. Assessment Scope
        md.append("## 3. Assessment Scope\n")
        md.append(f"- **Scope Reference:** `{ctx.authorization.scope_reference}`")
        md.append(f"- **Total Discovered Assets:** {len(ctx.assets)}")
        in_scope_assets = [a for a in ctx.assets if a.scope_status == AssessmentScopeStatus.IN_SCOPE]
        md.append(f"- **In-Scope Targets:** {len(in_scope_assets)}")
        md.append("")

        # 4. Methodology
        md.append("## 4. Methodology\n")
        md.append(
            "Testing adhered strictly to the M6 Authorized Security Assessment Framework:\n"
            "1. **Deterministic Scope & Authorization:** All target interactions fail-closed on unverified targets.\n"
            "2. **Passive Telemetry Normalization:** Network traffic and tool exports normalized into canonical observations.\n"
            "3. **Attack Surface Mapping:** Comprehensive inventory of endpoints, auth boundaries, and exposed services.\n"
            "4. **Hypothesis Formulation & Negative Controls:** Plausible vulnerabilities modeled against formal invariants.\n"
            "5. **Safe Manual Experiments:** Protocols executed exclusively by human researchers (zero autonomous exploit actions).\n"
            "6. **13-Point Finding Validation:** Deterministic checklist required before finding confirmation.\n"
        )

        # 5. Attack Surface & Assets
        md.append("## 5. Attack Surface Summary\n")
        if ctx.attack_surface:
            md.append(f"- **Total Attack Surface Nodes:** {ctx.attack_surface.get('total_nodes', 0)}")
            md.append(f"- **Discovered Technologies:** {', '.join(ctx.attack_surface.get('discovered_technologies', [])) or 'None'}")
            md.append(f"- **Exposed Services:** {ctx.attack_surface.get('exposed_services_count', 0)}")
            md.append(f"- **Endpoints Discovered:** {ctx.attack_surface.get('endpoints_count', 0)}")
        md.append("")

        # 6. Confirmed Findings (HUMAN VERIFIED ONLY)
        md.append("## 6. Confirmed Findings (Human Verified Only)\n")
        if not confirmed_findings:
            md.append("*No security findings have been human-verified and confirmed for this assessment.*\n")
        else:
            for idx, f in enumerate(confirmed_findings, start=1):
                md.append(f"### 6.{idx}. [{f.severity.value}] {f.title}\n")
                md.append(f"- **Finding ID:** `{f.finding_id}`")
                md.append(f"- **Affected Asset:** `{f.asset}`")
                md.append(f"- **Affected Component:** `{f.affected_component}`")
                md.append(f"- **Verification Status:** **{f.verification_status.value}** (Verified by: `{f.verified_by}` at `{f.verified_at}`)")
                md.append(f"- **Security Invariant Violated:** `{f.security_invariant}`")
                md.append(f"\n**Description:**\n{f.description}\n")
                md.append(f"**Security Impact:**\n{f.impact}\n")
                md.append(f"**Root Cause Analysis:**\n{f.root_cause}\n")
                md.append(f"**Remediation Guidance:**\n{f.remediation}\n")
                md.append(f"**Supporting Evidence Lineage:** {', '.join(f.evidence)}\n")

        # 7. Unverified Hypotheses & Evidence Gaps
        md.append("## 7. Unverified Hypotheses & Open Evidence Gaps\n")
        md.append(
            "> [!NOTE]\n"
            "> The following items represent plausible technical hypotheses or observed anomalies that have NOT "
            "> been verified by a human researcher. They MUST NOT be treated as confirmed security findings.\n"
        )
        if not unverified_hypotheses:
            md.append("*No open unverified hypotheses.*\n")
        else:
            for idx, h in enumerate(unverified_hypotheses, start=1):
                md.append(f"### 7.{idx}. [HYPOTHESIS - UNVERIFIED] {h.title}\n")
                md.append(f"- **Hypothesis ID:** `{h.hypothesis_id}`")
                md.append(f"- **Domain:** {h.domain} | **Confidence:** {h.confidence:.2f}")
                md.append(f"- **Description:** {h.description}")
                if h.evidence_gaps:
                    md.append(f"- **Required Open Evidence:** {'; '.join(h.evidence_gaps)}")
                if h.negative_control:
                    md.append(f"- **Negative Control:** {h.negative_control}")
                md.append("")

        # 8. Out-of-Scope Observations
        md.append("## 8. Out-of-Scope Observations (Excluded)\n")
        md.append(
            f"A total of **{len(out_of_scope_obs)}** observations were recorded outside program scope "
            f"and were strictly quarantined from analysis and findings.\n"
        )

        # 9. Testing Limitations
        md.append("## 9. Testing Limitations & Constraints\n")
        limits = ctx.limitations or [
            "Testing was restricted to non-destructive manual verification.",
            "Denial-of-service and state-destructive testing were strictly prohibited.",
            "All autonomous exploitation was disabled by safety invariants.",
        ]
        for lim in limits:
            md.append(f"- {lim}")
        md.append("")

        return "\n".join(md)
