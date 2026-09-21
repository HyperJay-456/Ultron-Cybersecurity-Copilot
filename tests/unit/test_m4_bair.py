"""Unit tests for Milestone M4 Phase M4.5: Intervention I4 (BAIR + Deterministic Extraction).

Validates:
- Deterministic upstream evidence-state signal (empirical_evidence_present: bool)
- Strict separation of concerns (parser, validator, mapper)
- Exact 6-case behavior matrix for INSUFFICIENT_EVIDENCE, HYPOTHESIS, and NO_RELEVANT_FUNCTIONALITY
- Robust XML parsing and fail-closed syntax/slot validation
- Bounded complete falsification specification requirement
- Direct deterministic mapping to canonical S0 (HypothesisModelOutput)
- Authoritative KnowledgeGroundingValidator enforcement (anti-fabrication & namespace segregation)
- Strict single-factor isolation (schema=None, no I1/I2/I3/I5/I6 interference)
"""

import json
import os
import pytest
from typing import Any, Dict, List

from src.engine.bair_extractor import (
    ALLOWED_BAIR_SLOTS,
    BairExtractor,
    BairParseError,
    BairSchemaError,
    determine_empirical_evidence_present,
    map_bair_to_s0,
    parse_bair,
    validate_bair,
)
from src.engine.context_builder import (
    ReasoningContextBuilder,
    TRACK_D,
)
from src.engine.models import (
    FailureClassificationResult,
    HypothesisDecision,
    HypothesisModelOutput,
    I4ExecutionResult,
    PrimaryFailureCategory,
)
from src.engine.runner import (
    OllamaRunner,
    ReasoningRunner,
)
from src.evidence.cascade_models import (
    CascadeHandoffPacket,
    DeterministicRoutingDecision,
    LosslessStructuralPack,
)
from src.knowledge.grounding_validator import KnowledgeGroundingValidator


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

def make_bair_xml(
    decision: str = "HYPOTHESIS",
    invariant: str = "Owner authorization check required on /api/resource/{id}",
    evidence_gap: str = "Cross-tenant access token response unverified",
    affected_target: str = "/api/resource/{id}",
    facts: str = "FACT-001, FACT-002",
    methodology: str = "CHK-001",
    falsification: str = "Observation supporting hypothesis: 200 OK with foreign data. Observation disproving hypothesis: 403 Forbidden.",
) -> str:
    parts = ["<bair>"]
    if invariant is not None:
        parts.append(f"  <invariant>{invariant}</invariant>")
    if evidence_gap is not None:
        parts.append(f"  <evidence_gap>{evidence_gap}</evidence_gap>")
    if affected_target is not None:
        parts.append(f"  <affected_target>{affected_target}</affected_target>")
    if decision is not None:
        parts.append(f"  <decision>{decision}</decision>")
    if facts is not None:
        parts.append(f"  <facts>{facts}</facts>")
    if methodology is not None:
        parts.append(f"  <methodology>{methodology}</methodology>")
    if falsification is not None:
        parts.append(f"  <falsification>{falsification}</falsification>")
    parts.append("</bair>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Behavior Matrix: Cases 1 through 6
# ---------------------------------------------------------------------------

def test_case_1_insufficient_evidence_with_empirical_missing_facts_fails():
    """Case 1: decision = INSUFFICIENT_EVIDENCE, empirical_evidence_present = True, facts absent => fail."""
    xml = make_bair_xml(
        decision="INSUFFICIENT_EVIDENCE",
        facts=None,
        falsification="Observation to resolve: request with tenant B token",
    )
    raw_slots = parse_bair(xml)
    with pytest.raises(BairSchemaError, match="requires non-empty <facts> slot"):
        validate_bair(raw_slots, empirical_evidence_present=True)


def test_case_2_insufficient_evidence_with_empirical_valid_facts_passes():
    """Case 2: decision = INSUFFICIENT_EVIDENCE, empirical_evidence_present = True, facts present and valid => accepted."""
    xml = make_bair_xml(
        decision="INSUFFICIENT_EVIDENCE",
        facts="FACT-001",
        falsification="Observation to resolve: request with tenant B token",
    )
    raw_slots = parse_bair(xml)
    validated = validate_bair(raw_slots, empirical_evidence_present=True)
    assert validated["decision"] == "INSUFFICIENT_EVIDENCE"
    assert validated["parsed_facts"] == ["FACT-001"]

    s0 = map_bair_to_s0(validated)
    assert s0.decision == HypothesisDecision.INSUFFICIENT_EVIDENCE
    assert s0.supporting_evidence_ids == ["FACT-001"]


def test_case_3_insufficient_evidence_no_empirical_missing_facts_passes():
    """Case 3: decision = INSUFFICIENT_EVIDENCE, empirical_evidence_present = False, facts absent => accepted."""
    xml = make_bair_xml(
        decision="INSUFFICIENT_EVIDENCE",
        facts=None,
        falsification="Observation to resolve: probe unauthenticated endpoint",
    )
    raw_slots = parse_bair(xml)
    validated = validate_bair(raw_slots, empirical_evidence_present=False)
    assert validated["decision"] == "INSUFFICIENT_EVIDENCE"
    assert validated["parsed_facts"] == []

    s0 = map_bair_to_s0(validated)
    assert s0.decision == HypothesisDecision.INSUFFICIENT_EVIDENCE
    assert s0.supporting_evidence_ids == []


def test_case_4_insufficient_evidence_no_empirical_optional_facts_preserved():
    """Case 4: decision = INSUFFICIENT_EVIDENCE, empirical_evidence_present = False, facts present => accepted, decision unchanged."""
    xml = make_bair_xml(
        decision="INSUFFICIENT_EVIDENCE",
        facts="FACT-001",
        falsification="Observation to resolve: compare role headers",
    )
    raw_slots = parse_bair(xml)
    validated = validate_bair(raw_slots, empirical_evidence_present=False)
    assert validated["decision"] == "INSUFFICIENT_EVIDENCE"
    assert validated["parsed_facts"] == ["FACT-001"]

    s0 = map_bair_to_s0(validated)
    assert s0.decision == HypothesisDecision.INSUFFICIENT_EVIDENCE
    assert s0.supporting_evidence_ids == ["FACT-001"]


def test_case_5_hypothesis_missing_facts_fails_regardless_of_empirical_flag():
    """Case 5: decision = HYPOTHESIS, facts absent => reject regardless of empirical_evidence_present."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        facts=None,
    )
    raw_slots = parse_bair(xml)

    # Must fail when empirical_evidence_present == True
    with pytest.raises(BairSchemaError, match="Mandatory <facts> slot missing"):
        validate_bair(raw_slots, empirical_evidence_present=True)

    # Must fail when empirical_evidence_present == False
    with pytest.raises(BairSchemaError, match="Mandatory <facts> slot missing"):
        validate_bair(raw_slots, empirical_evidence_present=False)


def test_case_6_no_relevant_functionality_facts_handled_separately():
    """Case 6: decision = NO_RELEVANT_FUNCTIONALITY with or without facts does not reuse INSUFFICIENT_EVIDENCE semantics."""
    # NO_RELEVANT_FUNCTIONALITY without facts passes even if empirical_evidence_present == True
    xml_no_facts = make_bair_xml(
        decision="NO_RELEVANT_FUNCTIONALITY",
        evidence_gap=None,
        facts=None,
        methodology=None,
        falsification=None,
    )
    slots_no_facts = parse_bair(xml_no_facts)
    val1 = validate_bair(slots_no_facts, empirical_evidence_present=True)
    assert val1["decision"] == "NO_RELEVANT_FUNCTIONALITY"
    assert val1["parsed_facts"] == []

    # NO_RELEVANT_FUNCTIONALITY with facts passes without forcing facts to be absent or rewriting decision
    xml_with_facts = make_bair_xml(
        decision="NO_RELEVANT_FUNCTIONALITY",
        evidence_gap=None,
        facts="FACT-001",
        methodology=None,
        falsification=None,
    )
    slots_with_facts = parse_bair(xml_with_facts)
    val2 = validate_bair(slots_with_facts, empirical_evidence_present=False)
    assert val2["decision"] == "NO_RELEVANT_FUNCTIONALITY"
    assert val2["parsed_facts"] == ["FACT-001"]


# ---------------------------------------------------------------------------
# Strict Parser Syntax & Structural Integrity Tests
# ---------------------------------------------------------------------------

def test_parse_bair_clean_and_code_fenced():
    """Verify parse_bair extracts slots from clean and markdown-fenced text."""
    clean_xml = make_bair_xml()
    slots = parse_bair(clean_xml)
    assert set(slots.keys()).issubset(set(ALLOWED_BAIR_SLOTS))
    assert slots["decision"] == "HYPOTHESIS"

    fenced_xml = f"```xml\n{clean_xml}\n```"
    slots_fenced = parse_bair(fenced_xml)
    assert slots_fenced == slots


def test_parse_bair_missing_root_tag_fails():
    """Verify missing <bair> or </bair> raises BairParseError."""
    with pytest.raises(BairParseError, match="Missing <bair> or </bair> root tag"):
        parse_bair("<invariant>test</invariant>")


def test_parse_bair_multiple_root_blocks_fail():
    """Verify multiple <bair> blocks are rejected as ambiguous."""
    raw = "<bair><decision>HYPOTHESIS</decision></bair>\n<bair><decision>HYPOTHESIS</decision></bair>"
    with pytest.raises(BairParseError, match="Ambiguous multiple <bair>"):
        parse_bair(raw)


def test_parse_bair_malformed_xml_syntax_fails():
    """Verify unclosed tags or syntax errors raise BairParseError."""
    malformed = "<bair><invariant>unclosed invariant tag<decision>HYPOTHESIS</decision></bair>"
    with pytest.raises(BairParseError, match="XML parse error"):
        parse_bair(malformed)


def test_parse_bair_unknown_slot_fails():
    """Verify eighth/unknown slot raises BairSchemaError."""
    xml_with_extra = "<bair><invariant>inv</invariant><extra_slot>bad</extra_slot><decision>HYPOTHESIS</decision></bair>"
    with pytest.raises(BairSchemaError, match="Unknown slot in BAIR"):
        parse_bair(xml_with_extra)


def test_parse_bair_duplicate_slot_fails():
    """Verify duplicate slot tags raise BairSchemaError."""
    xml_with_dup = "<bair><invariant>first</invariant><invariant>second</invariant><decision>HYPOTHESIS</decision></bair>"
    with pytest.raises(BairSchemaError, match="Duplicate slot in BAIR"):
        parse_bair(xml_with_dup)


def test_parse_bair_attributes_forbidden():
    """Verify XML attributes on root or slot tags raise BairSchemaError."""
    root_attrib = '<bair id="1"><invariant>inv</invariant></bair>'
    with pytest.raises(BairSchemaError, match="Root element <bair> must not contain XML attributes"):
        parse_bair(root_attrib)

    slot_attrib = '<bair><invariant id="1">inv</invariant></bair>'
    with pytest.raises(BairSchemaError, match="must not contain XML attributes"):
        parse_bair(slot_attrib)


def test_parse_bair_nested_elements_forbidden():
    """Verify slot tags containing nested elements raise BairSchemaError."""
    nested = "<bair><invariant><nested>inv</nested></invariant></bair>"
    with pytest.raises(BairSchemaError, match="must contain text only, not nested elements"):
        parse_bair(nested)


# ---------------------------------------------------------------------------
# Falsification Completeness & Decision-Dependent Rules
# ---------------------------------------------------------------------------

def test_confirmed_decision_strictly_forbidden():
    """Verify CONFIRMED decision is rejected fail-closed."""
    xml = make_bair_xml(decision="CONFIRMED")
    slots = parse_bair(xml)
    with pytest.raises(BairSchemaError, match="CONFIRMED decision is strictly forbidden"):
        validate_bair(slots, empirical_evidence_present=True)


def test_hypothesis_falsification_missing_supporting_fails():
    """Verify HYPOTHESIS with falsification lacking supporting observation fails."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        falsification="Observation disproving hypothesis: returns 403 Forbidden.",
    )
    slots = parse_bair(xml)
    with pytest.raises(BairSchemaError, match="missing supporting observation"):
        validate_bair(slots, empirical_evidence_present=True)


def test_hypothesis_falsification_missing_disproving_fails():
    """Verify HYPOTHESIS with falsification lacking disproving/falsifying observation fails."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        falsification="Observation supporting hypothesis: returns 200 OK with expected payload.",
    )
    slots = parse_bair(xml)
    with pytest.raises(BairSchemaError, match="missing disproving/falsifying observation"):
        validate_bair(slots, empirical_evidence_present=True)


def test_placeholder_tokens_in_slots_forbidden():
    """Verify placeholder tokens like 'None' or 'N/A' in facts or methodology are rejected."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        facts="None",
    )
    slots = parse_bair(xml)
    with pytest.raises(BairSchemaError, match="Placeholder token 'None' is strictly forbidden"):
        validate_bair(slots, empirical_evidence_present=True)


# ---------------------------------------------------------------------------
# Upstream Evidence-State Derivation
# ---------------------------------------------------------------------------

def test_determine_empirical_evidence_present_sources():
    """Verify determine_empirical_evidence_present derives exclusively from canonical target evidence."""
    # 1. Explicit signal
    assert determine_empirical_evidence_present(explicit_signal=True) is True
    assert determine_empirical_evidence_present(explicit_signal=False) is False

    # 2. From channel_a LosslessStructuralPack
    pack_with_facts = LosslessStructuralPack(
        asset_id="AST-01",
        endpoint_id="EP-01",
        route_template="/api/test",
        http_method="GET",
        application_mutability="READ_ONLY",
        observed_facts=[{"fact_id": "FACT-001", "statement": "200 OK"}],
    )
    assert determine_empirical_evidence_present(channel_a=pack_with_facts) is True

    pack_empty = LosslessStructuralPack(
        asset_id="AST-01",
        endpoint_id="EP-01",
        route_template="/api/test",
        http_method="GET",
        application_mutability="READ_ONLY",
        observed_facts=[],
    )
    assert determine_empirical_evidence_present(channel_a=pack_empty) is False

    # 3. From retrieved_evidence list
    assert determine_empirical_evidence_present(retrieved_evidence=[{"fact_id": "FACT-01"}]) is True
    assert determine_empirical_evidence_present(retrieved_evidence=[]) is False

    # 4. Default when nothing provided
    assert determine_empirical_evidence_present() is False


def test_extractor_never_derives_empirical_evidence_from_bair_prose():
    """Verify the extractor NEVER infers empirical_evidence_present from natural language inside BAIR."""
    # Text explicitly claims evidence exists, but empirical_evidence_present is passed as False
    xml_prose_claims_evidence = make_bair_xml(
        decision="INSUFFICIENT_EVIDENCE",
        invariant="Evidence observed in response was valid 200 OK but ungrounded",
        evidence_gap="Some evidence was observed and available",
        facts=None,
        falsification="Observation to resolve: probe endpoint",
    )
    raw_slots = parse_bair(xml_prose_claims_evidence)

    # When caller specifies False, extractor respects False and accepts missing facts (Case 3)
    val_false = validate_bair(raw_slots, empirical_evidence_present=False)
    assert val_false["decision"] == "INSUFFICIENT_EVIDENCE"

    # When caller specifies True, extractor respects True and rejects missing facts (Case 1)
    with pytest.raises(BairSchemaError, match="requires non-empty <facts> slot"):
        validate_bair(raw_slots, empirical_evidence_present=True)


# ---------------------------------------------------------------------------
# Determinism & Canonical S0 Idempotency
# ---------------------------------------------------------------------------

def test_repeated_extraction_produces_byte_identical_canonical_s0():
    """Requirement 7: Repeated extraction with same slots and boolean produces byte-identical canonical S0."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        facts="FACT-001, FACT-002",
        methodology="CHK-001",
    )

    _, s0_run1 = BairExtractor.extract_bair(xml, empirical_evidence_present=True)
    _, s0_run2 = BairExtractor.extract_bair(xml, empirical_evidence_present=True)

    json1 = s0_run1.model_dump_json()
    json2 = s0_run2.model_dump_json()

    assert json1 == json2
    assert s0_run1.supporting_evidence_ids == ["FACT-001", "FACT-002"]
    assert s0_run1.methodology_references == ["CHK-001"]
    assert s0_run1.experiment_proposal == (
        "Observation supporting hypothesis: 200 OK with foreign data. "
        "Observation disproving hypothesis: 403 Forbidden."
    )


# ---------------------------------------------------------------------------
# Grounding Validation Integration
# ---------------------------------------------------------------------------

def test_fabricated_fact_ids_fail_knowledge_grounding():
    """Requirement 8: Fabricated fact IDs fail KnowledgeGroundingValidator fail-closed."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        facts="FACT-FABRICATED-999",
    )
    _, canonical = BairExtractor.extract_bair(xml, empirical_evidence_present=True)

    validator = KnowledgeGroundingValidator()
    pack = LosslessStructuralPack(
        asset_id="AST-01",
        endpoint_id="EP-01",
        route_template="/api/test",
        http_method="GET",
        application_mutability="READ_ONLY",
        observed_facts=[{"fact_id": "FACT-001", "statement": "Legitimate observation"}],
    )

    result = validator.validate_grounding(hypothesis=canonical, channel_a=pack)
    assert result.valid is False
    assert result.error_code == "TARGET_EVIDENCE_GROUNDING_FAILURE"
    assert "FACT-FABRICATED-999" in result.invalid_fact_ids


def test_cross_namespace_citation_in_facts_fails_grounding():
    """Verify CHK-xxx placed in <facts> slot fails KnowledgeGroundingValidator."""
    xml = make_bair_xml(
        decision="HYPOTHESIS",
        facts="CHK-001",
    )
    _, canonical = BairExtractor.extract_bair(xml, empirical_evidence_present=True)

    validator = KnowledgeGroundingValidator()
    result = validator.validate_grounding(hypothesis=canonical)
    assert result.valid is False
    assert result.is_namespace_breach is True
    assert result.error_code == "EPISTEMIC_CONFUSION_ERROR"


# ---------------------------------------------------------------------------
# Runner Execution & Single-Factor Isolation
# ---------------------------------------------------------------------------

def test_runner_execute_i4_generation_unconstrained_success():
    """Verify execute_i4_generation executes with schema=None and parses valid BAIR into canonical S0."""
    valid_xml = make_bair_xml(
        decision="HYPOTHESIS",
        facts="FACT-001",
        methodology=None,
    )

    captured_schema = "NOT_CALLED"

    def mock_caller(prompt: str, schema: Any) -> str:
        nonlocal captured_schema
        captured_schema = schema
        return valid_xml

    pack = LosslessStructuralPack(
        asset_id="AST-01",
        endpoint_id="EP-01",
        route_template="/api/test",
        http_method="GET",
        application_mutability="READ_ONLY",
        observed_facts=[{"fact_id": "FACT-001", "statement": "Verified"}],
    )

    runner = ReasoningRunner(llm_caller=mock_caller)
    res = runner.execute_i4_generation(
        prompt="test prompt",
        channel_a=pack,
        grounding_validator=KnowledgeGroundingValidator(),
    )

    # Pure single-factor isolation: schema passed to runner is strictly None!
    assert captured_schema is None
    assert res.classification.is_valid is True
    assert res.classification.primary_category == PrimaryFailureCategory.VALID
    assert res.canonical_hypothesis is not None
    assert res.canonical_hypothesis.decision == HypothesisDecision.HYPOTHESIS
    assert res.canonical_hypothesis.supporting_evidence_ids == ["FACT-001"]


def test_runner_execute_i4_generation_fails_closed_on_xml_syntax():
    """Verify execute_i4_generation fails closed to PARSER_FAILURE on malformed XML."""
    def mock_caller(prompt: str, schema: Any) -> str:
        return "<bair><unclosed>bad xml"

    runner = ReasoningRunner(llm_caller=mock_caller)
    res = runner.execute_i4_generation(prompt="test prompt")

    assert res.classification.is_valid is False
    assert res.classification.primary_category == PrimaryFailureCategory.PARSER_FAILURE
    assert res.canonical_hypothesis is None
    assert res.extracted_bair is None
    assert res.bair_error is not None


def test_runner_execute_i4_generation_fails_closed_on_schema_violation():
    """Verify execute_i4_generation fails closed to SCHEMA_VALIDITY_FAILURE on missing slot."""
    def mock_caller(prompt: str, schema: Any) -> str:
        return "<bair><decision>HYPOTHESIS</decision></bair>"

    runner = ReasoningRunner(llm_caller=mock_caller)
    res = runner.execute_i4_generation(prompt="test prompt")

    assert res.classification.is_valid is False
    assert res.classification.primary_category == PrimaryFailureCategory.SCHEMA_VALIDITY_FAILURE
    assert res.canonical_hypothesis is None


# ---------------------------------------------------------------------------
# Context Builder Integration
# ---------------------------------------------------------------------------

def test_context_builder_enable_i4_bair():
    """Verify ReasoningContextBuilder formats BAIR system policy when enable_i4_bair=True."""
    pack = LosslessStructuralPack(
        asset_id="AST-01",
        endpoint_id="EP-01",
        route_template="/api/test",
        http_method="GET",
        application_mutability="READ_ONLY",
        observed_facts=[{"fact_id": "FACT-001", "statement": "Observed test fact"}],
    )
    handoff = CascadeHandoffPacket(
        channel_a_structural=pack,
        validated_triage=None,
        routing_decision=DeterministicRoutingDecision(
            route_to_7b=True,
            reason="Unit test",
            escalate=False,
            has_high_risk_signal=False,
            fail_safe_triggered=False,
        ),
        provenance_hash="0" * 64,
    )

    ctx = ReasoningContextBuilder.build_context(
        handoff_packet=handoff,
        model_identifier="qwen2.5-coder:7b",
        cascade_mode=TRACK_D,
        enable_i4_bair=True,
    )

    assert "<bair>" in ctx.system_prompt
    assert "</bair>" in ctx.system_prompt
    assert "BOUNDED ANALYTICAL INFERENCE REPRESENTATION" in ctx.system_prompt
    assert ctx.provenance_metadata.get("i4_bair_enabled") is True


# ---------------------------------------------------------------------------
# Live Ollama Sanity Check (Optional under SKIP_LIVE_OLLAMA)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_OLLAMA") == "1",
    reason="Live Ollama execution skipped by environment flag",
)
def test_live_ollama_i4_unconstrained_sanity_check():
    """Lightweight live Ollama sanity check under unconstrained sampling for BAIR."""
    runner = OllamaRunner(num_predict=300, temperature=0.0)
    if not runner.is_available():
        pytest.skip("Local Ollama daemon is not reachable at 127.0.0.1:11434")

    reasoning_runner = ReasoningRunner(ollama_runner=runner)
    prompt = reasoning_runner.build_i4_bair_prompt(
        target_asset={
            "asset_id": "AST-PUBLIC-HEALTH",
            "method": "GET",
            "normalized_path": "/health",
        },
        category_id="API-AUTH-NONE",
        retrieved_evidence=[
            {"fact_id": "FACT-HEALTH-01", "statement": "GET /health returns HTTP 200 with status UP."},
        ],
    )

    pack = LosslessStructuralPack(
        asset_id="AST-PUBLIC-HEALTH",
        endpoint_id="EP-HEALTH",
        route_template="/health",
        http_method="GET",
        application_mutability="READ_ONLY",
        observed_facts=[{"fact_id": "FACT-HEALTH-01", "statement": "GET /health returns HTTP 200 with status UP."}],
    )

    result = reasoning_runner.execute_i4_generation(
        prompt=prompt,
        channel_a=pack,
        category_id="API-AUTH-NONE",
    )
    assert isinstance(result, I4ExecutionResult)
    assert len(result.raw_response) > 0
    assert result.latency_ms > 0
    assert result.classification.primary_category in (
        PrimaryFailureCategory.VALID,
        PrimaryFailureCategory.SCHEMA_VALIDITY_FAILURE,
        PrimaryFailureCategory.MAX_TOKEN_TRUNCATION,
        PrimaryFailureCategory.PARSER_FAILURE,
    )
