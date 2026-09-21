"""Bounded Analytical Inference Representation (BAIR) Extractor & Validator.

Milestone M4 Phase M4.5 (Intervention I4):
Deterministic AST/slot extractor for BAIR XML markup mapping directly into the
canonical downstream S0 schema (HypothesisModelOutput).

Strict Separation of Concerns:
- parser: syntax/structure only (XML integrity, slot grammar)
- validator: decision-dependent structural rules + supplied empirical_evidence_present state
- mapper: deterministic field mapping only (zero semantic rewriting, zero citation substitution)
"""

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from src.engine.models import (
    HypothesisDecision,
    HypothesisModelOutput,
)

# Canonical 7-slot BAIR vocabulary (zero eighth slot permitted)
ALLOWED_BAIR_SLOTS = (
    "invariant",
    "evidence_gap",
    "affected_target",
    "decision",
    "facts",
    "methodology",
    "falsification",
)


class BairParseError(ValueError):
    """Raised when BAIR raw text contains invalid XML syntax or malformed markup structure."""
    pass


class BairSchemaError(ValueError):
    """Raised when BAIR content violates decision-dependent structural rules or slot constraints."""
    pass


def parse_bair(raw_text: str) -> Dict[str, str]:
    """
    Parse BAIR XML markup from raw model output.
    Enforces syntactic structure only:
    - Exactly one <bair>...</bair> block
    - Balanced XML tags
    - Zero unknown slots
    - Zero duplicate slots
    - Children must not contain nested elements or attributes

    Returns raw string content for each extracted slot.
    """
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        raise BairParseError("Empty or non-string BAIR input")

    cleaned = raw_text.strip()
    # Strip optional markdown code fences
    if cleaned.startswith("```xml"):
        cleaned = cleaned[6:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Verify exactly one <bair> opening and </bair> closing tag
    opening_count = len(re.findall(r"<bair[\s>]", cleaned, re.IGNORECASE))
    closing_count = len(re.findall(r"</bair>", cleaned, re.IGNORECASE))

    if opening_count == 0 or closing_count == 0:
        raise BairParseError("Missing <bair> or </bair> root tag")
    if opening_count > 1 or closing_count > 1:
        raise BairParseError("Ambiguous multiple <bair>...</bair> root blocks detected")

    # Locate the exact boundary of the <bair>...</bair> block
    match = re.search(r"(<bair[\s>].*?</bair>)", cleaned, re.DOTALL | re.IGNORECASE)
    if not match:
        raise BairParseError("Failed to extract bounded <bair>...</bair> block")
    bair_block = match.group(1).strip()

    # Parse XML via standard library ElementTree
    try:
        root = ET.fromstring(bair_block)
    except Exception as exc:
        raise BairParseError(f"XML parse error in BAIR block: {exc}") from exc

    if root.tag.lower() != "bair":
        raise BairParseError(f"Expected root element <bair>, got <{root.tag}>")

    if root.attrib:
        raise BairSchemaError("Root element <bair> must not contain XML attributes")

    seen_slots = set()
    raw_slots: Dict[str, str] = {}

    for child in root:
        slot_name = child.tag.strip().lower()

        # Reject unknown slot
        if slot_name not in ALLOWED_BAIR_SLOTS:
            raise BairSchemaError(f"Unknown slot in BAIR representation: <{child.tag}>")

        # Reject duplicate slot
        if slot_name in seen_slots:
            raise BairSchemaError(f"Duplicate slot in BAIR representation: <{child.tag}>")
        seen_slots.add(slot_name)

        # Reject attributes on slot tags
        if child.attrib:
            raise BairSchemaError(f"Slot <{child.tag}> must not contain XML attributes")

        # Reject nested child elements within slot tags
        if len(child) > 0:
            raise BairSchemaError(f"Slot <{child.tag}> must contain text only, not nested elements")

        text_content = (child.text or "").strip()
        raw_slots[slot_name] = text_content

    return raw_slots


def _check_falsification_completeness(falsification_text: str) -> None:
    """
    Validate that <falsification> is a bounded complete experiment specification containing:
    1. A concrete observation that would support the hypothesis.
    2. A concrete observation that would disprove/falsify the hypothesis.
    """
    if not falsification_text or not falsification_text.strip():
        raise BairSchemaError("Falsification slot must not be empty")

    lower = falsification_text.lower()
    has_supporting = any(term in lower for term in ["support", "confirm", "positive", "observed", "expected"])
    has_disproving = any(term in lower for term in ["disprov", "falsif", "reject", "refut", "negative", "403", "404", "400", "block"])

    if not has_supporting:
        raise BairSchemaError("Falsification slot missing supporting observation specification")
    if not has_disproving:
        raise BairSchemaError("Falsification slot missing disproving/falsifying observation specification")


def determine_empirical_evidence_present(
    channel_a: Optional[Any] = None,
    retrieved_evidence: Optional[Any] = None,
    explicit_signal: Optional[bool] = None,
) -> bool:
    """
    Deterministically derive whether empirical target evidence exists from canonical
    target evidence representations available in the execution context.

    Source of truth:
    - If explicit boolean signal provided, respect it.
    - If channel_a is provided (LosslessStructuralPack), check bool(channel_a.observed_facts).
    - If retrieved_evidence is provided (List/Sequence), check bool(retrieved_evidence).
    - Otherwise, default to False.

    MUST NOT be:
    - generated by the LLM
    - parsed from <facts>
    - inferred from <decision>
    - inferred from prose
    - inferred from <evidence_gap>
    - inferred from <falsification>
    - inferred from methodology references
    """
    if explicit_signal is not None:
        return bool(explicit_signal)
    if channel_a is not None:
        facts = getattr(channel_a, "observed_facts", None)
        if facts is not None:
            return bool(facts)
        if isinstance(channel_a, dict):
            return bool(channel_a.get("observed_facts"))
    if retrieved_evidence is not None:
        if isinstance(retrieved_evidence, (list, tuple, set)):
            return len(retrieved_evidence) > 0
        if isinstance(retrieved_evidence, dict):
            return bool(retrieved_evidence.get("facts") or retrieved_evidence.get("observed_facts"))
        return bool(retrieved_evidence)
    return False


def validate_bair(
    slots: Dict[str, str],
    empirical_evidence_present: bool,
) -> Dict[str, Any]:
    """
    Apply decision-dependent structural validation rules to parsed BAIR slots.
    Preserves exact behavior matrix:
    - HYPOTHESIS: invariant, evidence_gap, affected_target, decision, facts, falsification (supporting+disproving) required.
    - INSUFFICIENT_EVIDENCE: invariant, evidence_gap, affected_target, decision, falsification required.
      facts is REQUIRED if empirical_evidence_present==True, OPTIONAL if False.
    - NO_RELEVANT_FUNCTIONALITY: invariant, affected_target, decision required. facts/evidence_gap/falsification optional.
    - CONFIRMED: Strictly rejected.
    """
    decision_raw = slots.get("decision", "").strip().upper()
    if not decision_raw:
        raise BairSchemaError("Missing mandatory <decision> slot")

    if decision_raw == "CONFIRMED":
        raise BairSchemaError("CONFIRMED decision is strictly forbidden in reasoning engine")

    valid_decisions = {d.value for d in HypothesisDecision}
    if decision_raw not in valid_decisions:
        raise BairSchemaError(f"Invalid decision value: {decision_raw!r}")

    # Parse entity IDs strictly preserving exact strings
    facts_raw = slots.get("facts", "")
    parsed_facts = [s for s in re.split(r"[,;\s]+", facts_raw.strip()) if s] if facts_raw else []

    methodology_raw = slots.get("methodology", "")
    parsed_methodology = [s for s in re.split(r"[,;\s]+", methodology_raw.strip()) if s] if methodology_raw else []

    # Disallow synthetic placeholder tokens in facts or methodology
    placeholder_tokens = {"none", "n/a", "na", "null", "[]", "{}"}
    for fid in parsed_facts:
        if fid.lower() in placeholder_tokens:
            raise BairSchemaError(f"Placeholder token {fid!r} is strictly forbidden in <facts> slot")
    for mid in parsed_methodology:
        if mid.lower() in placeholder_tokens:
            raise BairSchemaError(f"Placeholder token {mid!r} is strictly forbidden in <methodology> slot")

    invariant = slots.get("invariant", "").strip()
    evidence_gap = slots.get("evidence_gap", "").strip()
    affected_target = slots.get("affected_target", "").strip()
    falsification = slots.get("falsification", "").strip()

    # Decision-dependent validation rules
    if decision_raw == HypothesisDecision.HYPOTHESIS.value:
        if not invariant:
            raise BairSchemaError("Mandatory <invariant> slot missing or empty for HYPOTHESIS")
        if not evidence_gap:
            raise BairSchemaError("Mandatory <evidence_gap> slot missing or empty for HYPOTHESIS")
        if not affected_target:
            raise BairSchemaError("Mandatory <affected_target> slot missing or empty for HYPOTHESIS")
        if not parsed_facts:
            raise BairSchemaError("Mandatory <facts> slot missing or empty for HYPOTHESIS")
        _check_falsification_completeness(falsification)

    elif decision_raw == HypothesisDecision.INSUFFICIENT_EVIDENCE.value:
        if not invariant:
            raise BairSchemaError("Mandatory <invariant> slot missing or empty for INSUFFICIENT_EVIDENCE")
        if not evidence_gap:
            raise BairSchemaError("Mandatory <evidence_gap> slot missing or empty for INSUFFICIENT_EVIDENCE")
        if not affected_target:
            raise BairSchemaError("Mandatory <affected_target> slot missing or empty for INSUFFICIENT_EVIDENCE")
        if not falsification:
            raise BairSchemaError("Mandatory <falsification> slot missing or empty for INSUFFICIENT_EVIDENCE")

        # Empirical evidence state rule:
        # Case 1: empirical_evidence_present == True and facts absent => BairSchemaError
        # Case 2: empirical_evidence_present == True and facts present => accepted
        # Case 3: empirical_evidence_present == False and facts absent => accepted
        # Case 4: empirical_evidence_present == False and facts present => accepted (optional slot)
        if empirical_evidence_present and not parsed_facts:
            raise BairSchemaError(
                "Decision INSUFFICIENT_EVIDENCE with empirical_evidence_present=True requires non-empty <facts> slot"
            )

    elif decision_raw == HypothesisDecision.NO_RELEVANT_FUNCTIONALITY.value:
        if not invariant:
            raise BairSchemaError("Mandatory <invariant> slot missing or empty for NO_RELEVANT_FUNCTIONALITY")
        if not affected_target:
            raise BairSchemaError("Mandatory <affected_target> slot missing or empty for NO_RELEVANT_FUNCTIONALITY")

    return {
        "invariant": invariant,
        "evidence_gap": evidence_gap or None,
        "affected_target": affected_target,
        "decision": decision_raw,
        "parsed_facts": parsed_facts,
        "parsed_methodology": parsed_methodology,
        "falsification": falsification or None,
        "raw_slots": slots,
    }


def map_bair_to_s0(validated: Dict[str, Any]) -> HypothesisModelOutput:
    """
    Deterministic mapping from validated BAIR slots to canonical S0 HypothesisModelOutput.
    Zero semantic inference, zero citation substitution, zero vulnerability inference.
    """
    invariant = validated["invariant"]
    evidence_gap = validated["evidence_gap"]
    affected_target = validated["affected_target"]
    decision = HypothesisDecision(validated["decision"])
    facts = validated["parsed_facts"]
    methodology = validated["parsed_methodology"]
    falsification = validated["falsification"]

    # experiment_proposal is copied directly from falsification without semantic rewriting
    experiment_proposal = falsification or "None required"
    reasoning_summary = f"BAIR evaluation: {invariant}. Evidence gap: {evidence_gap or 'None'}."

    return HypothesisModelOutput(
        invariant=invariant,
        evidence_gap=evidence_gap,
        affected_target=affected_target,
        decision=decision,
        supporting_evidence_ids=facts,
        methodology_references=methodology,
        reasoning_summary=reasoning_summary,
        experiment_proposal=experiment_proposal,
    )


class BairExtractor:
    """Deterministic AST/slot extractor and validator for BAIR representations."""

    @classmethod
    def extract_bair(
        cls,
        raw_text: str,
        empirical_evidence_present: bool,
    ) -> Tuple[Dict[str, Any], HypothesisModelOutput]:
        """
        Execute full BAIR extraction pipeline:
        parse_bair -> validate_bair -> map_bair_to_s0.
        Fails closed on any structural or schema failure.
        """
        raw_slots = parse_bair(raw_text)
        validated = validate_bair(raw_slots, empirical_evidence_present=empirical_evidence_present)
        canonical = map_bair_to_s0(validated)
        return validated, canonical
