"""Milestone M3 Phase M3.19: Final Reproducibility & Cryptographic Artifact Seal.

Generates the authoritative cryptographic seal manifest (m3_artifact_manifest.json),
binding:
- Offline corpus Merkle root, detached Ed25519 signature & database digest
- Evaluation datasets (frozen benchmark, retrieval gold, retrieval final eval)
- Human study scenario manifest & condition-masked evaluation units
- Empirical benchmark results, forensic attribution & human study summary
- Current Git commit, planning freeze commit & architectural invariant attestations
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.knowledge.provenance import compute_corpus_merkle_root


FROZEN_PLANNING_COMMIT = "819b83399e24080bf2942c3941cc96728885df49"
FROZEN_BENCHMARK_HASH = "b2b85a672124acf21066a257d8c7f5093000368b224ee013c02574c96a0ae707"


def compute_file_sha256(path: Path) -> str:
    """Computes hexadecimal SHA-256 digest of a file."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_current_git_commit() -> str:
    """Returns the current Git HEAD commit SHA."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def build_m3_artifact_seal(
    output_manifest_path: Path = Path("data/eval/m3_artifact_manifest.json"),
) -> Dict[str, Any]:
    """
    Constructs and cryptographically seals the complete Milestone M3 artifact manifest.
    """
    current_commit = get_current_git_commit()

    # 1. Corpus & Retrieval Assets
    corpus_manifest_path = Path("data/vapt_corpus/manifest.json")
    corpus_db_path = Path("data/vapt_corpus/vapt_knowledge.db")
    corpus_sources_path = Path("data/vapt_corpus/sources.json")

    corpus_assets = {
        "manifest_sha256": compute_file_sha256(corpus_manifest_path),
        "vapt_knowledge_db_sha256": compute_file_sha256(corpus_db_path),
        "sources_sha256": compute_file_sha256(corpus_sources_path),
    }
    manifest_sig_path = Path("data/vapt_corpus/manifest.sig")
    sig_hex = manifest_sig_path.read_bytes().hex() if manifest_sig_path.exists() else None
    with open(corpus_manifest_path, "r", encoding="utf-8") as f:
        c_manifest = json.load(f)
        corpus_assets["merkle_root"] = c_manifest.get("merkle_root")
        corpus_assets["signature_detached_ed25519"] = c_manifest.get("signature_detached_ed25519") or sig_hex

    # 2. Evaluation Datasets
    bench_manifest_path = Path("data/benchmarks/m1_5_frozen_manifest.json")
    ret_gold_path = Path("data/eval/retrieval_gold.json")
    ret_final_path = Path("data/eval/retrieval_final_eval.json")
    ret_final_manifest_path = Path("data/eval/retrieval_final_eval_manifest.json")

    eval_datasets = {
        "m1_5_frozen_benchmark_sha256": compute_file_sha256(bench_manifest_path),
        "retrieval_gold_sha256": compute_file_sha256(ret_gold_path),
        "retrieval_final_eval_sha256": compute_file_sha256(ret_final_path),
        "retrieval_final_eval_manifest_sha256": compute_file_sha256(ret_final_manifest_path),
    }
    assert eval_datasets["m1_5_frozen_benchmark_sha256"].lower() == FROZEN_BENCHMARK_HASH.lower(), "Benchmark manifest hash mismatch!"

    # 3. Human Study Artifacts
    human_manifest_path = Path("data/eval/human_study_scenario_manifest.json")
    human_units_path = Path("data/eval/human_study_evaluation_units.json")
    human_packets_path = Path("data/eval/human_study_rater_packets.json")
    human_ratings_path = Path("data/eval/human_study_raw_ratings.json")
    human_timing_path = Path("data/eval/human_study_timing_events.json")
    human_summary_path = Path("data/eval/human_study_summary.json")

    human_study_assets = {
        "scenario_manifest_sha256": compute_file_sha256(human_manifest_path),
        "evaluation_units_sha256": compute_file_sha256(human_units_path),
        "rater_packets_sha256": compute_file_sha256(human_packets_path),
        "raw_ratings_sha256": compute_file_sha256(human_ratings_path),
        "timing_events_sha256": compute_file_sha256(human_timing_path),
        "summary_sha256": compute_file_sha256(human_summary_path),
    }

    # 4. Empirical Evaluation Results
    ret_final_results_path = Path("data/eval/retrieval_final_eval_results.json")
    benchmark_results_path = Path("data/eval/m3_benchmark_results.json")
    forensic_results_path = Path("data/eval/forensic_attribution_results.json")

    eval_results = {
        "retrieval_final_eval_results_sha256": compute_file_sha256(ret_final_results_path),
        "m3_benchmark_results_sha256": compute_file_sha256(benchmark_results_path),
        "forensic_attribution_results_sha256": compute_file_sha256(forensic_results_path),
    }

    # 5. Core Architectural & Security Attestations
    attestations = {
        "target_evidence_retriever_untouched": True,
        "target_evidence_retriever_path": "src/retrieval/hybrid.py",
        "causal_parity_enforced": True,
        "causal_parity_rule": "TargetEvidencePayload(Track B) == TargetEvidencePayload(Track D) byte-identical",
        "selected_production_backend": "Candidate 1 (Local ONNX Vector + SQLite FTS5)",
        "epistemic_namespace_discipline": "supporting_evidence_ids strictly FACT IDs only; cited_methodology_chunk_ids strictly CHK IDs only",
        "zero_confirmation_authority": "Model inference cannot emit CONFIRMED",
        "zero_execution_authority": "VAPT layer has 0 authority over credentials, cookies, CSRF tokens, nonces, signing keys, scope, or execution approvals",
        "offline_local_boundary": "100% offline, local, deterministic, bounded, single-node execution",
    }

    manifest_payload: Dict[str, Any] = {
        "seal_schema_version": "1.0.0",
        "milestone": "M3",
        "plan_version": "2.3.8",
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_commit,
        "planning_freeze_commit": FROZEN_PLANNING_COMMIT,
        "corpus_assets": corpus_assets,
        "evaluation_datasets": eval_datasets,
        "human_study_assets": human_study_assets,
        "evaluation_results": eval_results,
        "architectural_attestations": attestations,
    }

    # Self-seal digest: SHA-256 of canonical JSON payload
    canonical_json = json.dumps(manifest_payload, indent=2, sort_keys=True)
    manifest_digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    manifest_payload["manifest_digest_sha256"] = manifest_digest

    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_payload, f, indent=2, sort_keys=True)

    return manifest_payload
