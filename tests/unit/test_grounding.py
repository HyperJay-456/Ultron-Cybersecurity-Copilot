"""Unit tests for Grounding Validator: ID validation, relationship checks, and claim checks."""

from pathlib import Path
from src.database.manager import DatabaseManager
from src.engine.models import HypothesisDecision, HypothesisModelOutput
from src.validation.grounding import GroundingValidator, ValidationStatus


def setup_test_database(db: DatabaseManager):
    """Seed test database with known assets, parameters, identities, and facts."""
    db.insert_asset({
        "asset_id": "ASSET-REAL-1",
        "method": "GET",
        "host": "api.target.com",
        "raw_path": "/users/10",
        "normalized_path": "/users/{id}",
    })
    db.insert_asset({
        "asset_id": "ASSET-REAL-2",
        "method": "POST",
        "host": "api.target.com",
        "raw_path": "/orders",
        "normalized_path": "/orders",
    })

    db.insert_parameter({
        "param_id": "PARAM-USER-ID",
        "asset_id": "ASSET-REAL-1",
        "param_name": "id",
        "location": "path",
    })
    db.insert_parameter({
        "param_id": "PARAM-ORDER-ID",
        "asset_id": "ASSET-REAL-2",
        "param_name": "order_id",
        "location": "body",
    })

    db.insert_identity({"identity_id": "user_alice", "role": "user"})
    db.insert_identity({"identity_id": "user_bob", "role": "user"})

    db.insert_evidence_item({
        "fact_id": "FACT-REAL-01",
        "certainty": "OBSERVED",
        "statement": "Valid observed invoice fact",
        "source_tool": "burp",
    })


def test_grounding_valid_hypothesis(tmp_path: Path):
    """Verify completely grounded and structurally valid hypothesis passes."""
    db_manager = DatabaseManager(db_path=tmp_path / "ground_test.db")
    db_manager.initialize_schema()
    setup_test_database(db_manager)

    validator = GroundingValidator(db_manager)

    output = HypothesisModelOutput(
        reasoning_summary="All parameters, identities, and evidence exist and match.",
        decision=HypothesisDecision.HYPOTHESIS,
        category="API-BOLA-001",
        asset_id="ASSET-REAL-1",
        parameter_ids=["PARAM-USER-ID"],
        actor_identity_id="user_alice",
        target_identity_id="user_bob",
        supporting_evidence_ids=["FACT-REAL-01"],
    )

    result = validator.validate(output)
    assert result.valid is True
    assert result.status == ValidationStatus.VALID
    assert result.final_decision == HypothesisDecision.HYPOTHESIS


def test_grounding_hallucinated_asset(tmp_path: Path):
    """Verify nonexistent asset_id causes DISCARD."""
    db_manager = DatabaseManager(db_path=tmp_path / "ground_test.db")
    db_manager.initialize_schema()
    setup_test_database(db_manager)

    validator = GroundingValidator(db_manager)

    output = HypothesisModelOutput(
        reasoning_summary="Invented asset.",
        decision=HypothesisDecision.HYPOTHESIS,
        category="API-BOLA-001",
        asset_id="ASSET-NONEXISTENT",
    )
    result = validator.validate(output)
    assert result.valid is False
    assert result.status == ValidationStatus.DISCARD
    assert "hallucinated_asset" in result.reason


def test_grounding_parameter_asset_mismatch(tmp_path: Path):
    """Verify parameter belonging to ASSET-2 cited against ASSET-1 causes DISCARD."""
    db_manager = DatabaseManager(db_path=tmp_path / "ground_test.db")
    db_manager.initialize_schema()
    setup_test_database(db_manager)

    validator = GroundingValidator(db_manager)

    # PARAM-ORDER-ID belongs to ASSET-REAL-2, but model cites it under ASSET-REAL-1!
    output = HypothesisModelOutput(
        reasoning_summary="Mismatched parameter.",
        decision=HypothesisDecision.HYPOTHESIS,
        category="API-BOLA-001",
        asset_id="ASSET-REAL-1",
        parameter_ids=["PARAM-ORDER-ID"],
        supporting_evidence_ids=["FACT-REAL-01"],
    )
    result = validator.validate(output)
    assert result.valid is False
    assert result.status == ValidationStatus.DISCARD
    assert "parameter_asset_mismatch" in result.reason


def test_grounding_required_evidence_unmet_causes_downgrade(tmp_path: Path):
    """Verify missing distinct identity pair for BOLA downgrades HYPOTHESIS to INSUFFICIENT_EVIDENCE."""
    db_manager = DatabaseManager(db_path=tmp_path / "ground_test.db")
    db_manager.initialize_schema()
    setup_test_database(db_manager)

    validator = GroundingValidator(db_manager)

    # Model omits target_identity_id
    output = HypothesisModelOutput(
        reasoning_summary="BOLA without comparison victim identity.",
        decision=HypothesisDecision.HYPOTHESIS,
        category="API-BOLA-001",
        asset_id="ASSET-REAL-1",
        parameter_ids=["PARAM-USER-ID"],
        actor_identity_id="user_alice",
        target_identity_id=None, # Missing comparison identity!
        supporting_evidence_ids=["FACT-REAL-01"],
    )
    result = validator.validate(output)
    assert result.valid is True
    assert result.status == ValidationStatus.DOWNGRADE
    assert result.final_decision == HypothesisDecision.INSUFFICIENT_EVIDENCE
    assert "required_evidence_unmet" in result.reason
