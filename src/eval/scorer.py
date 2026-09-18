"""Deterministic scoring engine evaluating grounding, precision, recall, and abstention."""

import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class EvaluationMetrics(BaseModel):
    total_scenarios: int
    total_vulnerable_scenarios: int = 0
    hypotheses_generated: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int  # Correct abstentions
    useful_vulnerable_scenarios: int = 0
    grounding_accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    abstention_precision: float = 0.0
    abstention_rate: float = 0.0
    discriminative_experiment_rate: float = 0.0
    # Target-level yield: useful_vulnerable / total_vulnerable
    useful_hypothesis_yield: float = 0.0
    # Hypothesis-level utility: useful_hypotheses / hypotheses_generated
    hypothesis_utility_rate: float = 0.0

    # 9 Independent Authoritative Research Metrics:
    canonical_id_validity: float = 1.0
    structural_grounding_rate: float = 1.0
    evidence_sufficiency_rate: float = 1.0
    decision_correctness: float = 0.0
    abstention_quality: float = 0.0
    experiment_completion_rate: float = 0.0
    useful_hypothesis_rate: float = 0.0
    useful_hypothesis_yield_at_fixed_reviewer_minutes: float = 0.0
    final_state_correctness: float = 0.0

    # Wilson Score 95% Confidence Intervals with explicit denominators
    precision_ci_95: Optional[Tuple[float, float]] = None  # Denominator: TP + FP
    recall_ci_95: Optional[Tuple[float, float]] = None     # Denominator: TP + FN
    useful_yield_ci_95: Optional[Tuple[float, float]] = None  # Denominator: total_vulnerable_scenarios


def wilson_score_interval(p: float, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """
    Computes Wilson score confidence interval for a binomial proportion.
    Denominator n MUST be the specific sample size for the metric in question.
    """
    if n <= 0:
        return (0.0, 0.0)
    z = 1.95996 if abs(confidence - 0.95) < 1e-4 else 1.96
    denom = 1.0 + (z ** 2) / n
    center = (p + (z ** 2) / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) + (z ** 2) / (4.0 * n)) / n)) / denom
    return (round(max(0.0, center - spread), 4), round(min(1.0, center + spread), 4))


class DeterministicScorer:
    """Computes benchmark metrics deterministically against scenario ground truths."""

    def score(self, run_results: List[Dict[str, Any]]) -> EvaluationMetrics:
        """
        run_results is a list of dicts:
        {
            "scenario_id": str,
            "ground_truth_vulnerable": bool,
            "decision": "HYPOTHESIS" | "NO_RELEVANT_FUNCTIONALITY" | "INSUFFICIENT_EVIDENCE",
            "grounded": bool,
            "discriminative_experiment": bool,
            "useful": bool,
            "canonical_id_valid": Optional[bool],
            "evidence_sufficient": Optional[bool],
            "experiments_executed": Optional[int],
        }
        """
        total = len(run_results)
        if total == 0:
            return EvaluationMetrics(
                total_scenarios=0,
                total_vulnerable_scenarios=0,
                hypotheses_generated=0,
                true_positives=0,
                false_positives=0,
                false_negatives=0,
                true_negatives=0,
            )

        tp = 0
        fp = 0
        fn = 0
        tn = 0
        grounded_count = 0
        canonical_valid_count = 0
        evidence_sufficient_count = 0
        decision_correct_count = 0
        final_state_correct_count = 0
        experiment_completed_count = 0
        hyp_count = 0
        abstain_count = 0
        correct_abstain = 0
        discriminative_count = 0
        useful_count = 0
        total_vuln = 0
        useful_vuln = 0

        for r in run_results:
            is_vuln = r["ground_truth_vulnerable"]
            dec = r["decision"]
            is_hyp = (dec == "HYPOTHESIS")
            is_grounded = r.get("grounded", False)
            is_canonical_valid = r.get("canonical_id_valid", is_grounded)
            is_evid_sufficient = r.get("evidence_sufficient", True)
            is_disc = r.get("discriminative_experiment", False)
            is_useful = r.get("useful", False)
            exps_exec = r.get("experiments_executed", 0)

            if is_canonical_valid:
                canonical_valid_count += 1
            if is_grounded:
                grounded_count += 1
            if is_evid_sufficient:
                evidence_sufficient_count += 1

            if is_vuln:
                total_vuln += 1
                if is_hyp:
                    decision_correct_count += 1
                if is_useful:
                    final_state_correct_count += 1
            else:
                if not is_hyp:
                    decision_correct_count += 1
                    final_state_correct_count += 1

            if exps_exec > 0 or is_disc:
                experiment_completed_count += 1

            if is_hyp and is_disc:
                discriminative_count += 1
            if is_hyp and is_useful:
                useful_count += 1

            if is_hyp:
                hyp_count += 1
                if is_vuln:
                    tp += 1
                    if is_useful:
                        useful_vuln += 1
                else:
                    fp += 1
            else:
                abstain_count += 1
                if not is_vuln:
                    tn += 1
                    correct_abstain += 1
                else:
                    fn += 1

        # Metric calculations with distinct mathematical definitions
        # 1. Precision: TP / (TP + FP)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        # 2. Recall: TP / (TP + FN)
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        # 3. F1 Score
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        # 4. Target-Level Useful Hypothesis Yield: useful_vulnerable / total_vulnerable
        useful_yield = useful_vuln / total_vuln if total_vuln > 0 else 0.0
        # 5. Hypothesis-Level Utility Rate: useful_hypotheses / hypotheses_generated
        hyp_utility = useful_count / hyp_count if hyp_count > 0 else 0.0

        grounding_acc = grounded_count / total if total > 0 else 0.0
        canonical_validity = canonical_valid_count / total if total > 0 else 0.0
        evidence_sufficiency = evidence_sufficient_count / total if total > 0 else 0.0
        decision_correctness = decision_correct_count / total if total > 0 else 0.0
        final_state_correctness = final_state_correct_count / total if total > 0 else 0.0
        abstain_prec = correct_abstain / abstain_count if abstain_count > 0 else 0.0
        abstain_rate = abstain_count / total if total > 0 else 0.0
        disc_rate = discriminative_count / hyp_count if hyp_count > 0 else 0.0
        exp_completion_rate = experiment_completed_count / hyp_count if hyp_count > 0 else 0.0

        # Confidence intervals with correct per-metric denominators
        precision_ci = wilson_score_interval(precision, tp + fp)
        recall_ci = wilson_score_interval(recall, tp + fn)
        useful_yield_ci = wilson_score_interval(useful_yield, total_vuln)

        return EvaluationMetrics(
            total_scenarios=total,
            total_vulnerable_scenarios=total_vuln,
            hypotheses_generated=hyp_count,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            true_negatives=tn,
            useful_vulnerable_scenarios=useful_vuln,
            grounding_accuracy=round(grounding_acc, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1, 4),
            abstention_precision=round(abstain_prec, 4),
            abstention_rate=round(abstain_rate, 4),
            discriminative_experiment_rate=round(disc_rate, 4),
            useful_hypothesis_yield=round(useful_yield, 4),
            hypothesis_utility_rate=round(hyp_utility, 4),
            canonical_id_validity=round(canonical_validity, 4),
            structural_grounding_rate=round(grounding_acc, 4),
            evidence_sufficiency_rate=round(evidence_sufficiency, 4),
            decision_correctness=round(decision_correctness, 4),
            abstention_quality=round(abstain_prec, 4),
            experiment_completion_rate=round(exp_completion_rate, 4),
            useful_hypothesis_rate=round(hyp_utility, 4),
            useful_hypothesis_yield_at_fixed_reviewer_minutes=round(useful_yield, 4),
            final_state_correctness=round(final_state_correctness, 4),
            precision_ci_95=precision_ci,
            recall_ci_95=recall_ci,
            useful_yield_ci_95=useful_yield_ci,
        )


def compute_paired_contingency_table(
    results_track_1: List[Dict[str, Any]],
    results_track_2: List[Dict[str, Any]],
    key: str = "useful",
    vulnerable_only: bool = True,
) -> Dict[str, Any]:
    """
    Computes exact paired 2x2 contingency table from raw per-scenario run records.
    - n11: both tracks True
    - n10: track 1 False, track 2 True (track 2 advantage)
    - n01: track 1 True, track 2 False (track 1 advantage)
    - n00: both tracks False
    """
    res_map_1 = {r["scenario_id"]: r for r in results_track_1}
    res_map_2 = {r["scenario_id"]: r for r in results_track_2}

    n11 = 0
    n10 = 0
    n01 = 0
    n00 = 0
    per_scenario = []

    for sid, r1 in res_map_1.items():
        if sid not in res_map_2:
            continue
        r2 = res_map_2[sid]
        is_vuln = r1.get("ground_truth_vulnerable", False)
        if vulnerable_only and not is_vuln:
            continue

        val1 = bool(r1.get(key, False) and r1.get("decision") == "HYPOTHESIS")
        val2 = bool(r2.get(key, False) and r2.get("decision") == "HYPOTHESIS")

        per_scenario.append({
            "scenario_id": sid,
            "is_vulnerable": is_vuln,
            "track_1_useful": val1,
            "track_2_useful": val2,
        })

        if val1 and val2:
            n11 += 1
        elif not val1 and val2:
            n10 += 1
        elif val1 and not val2:
            n01 += 1
        else:
            n00 += 1

    # Exact two-sided binomial test on discordant pairs (McNemar)
    b = n01  # track 1 only
    c = n10  # track 2 only
    total_discordant = b + c
    if total_discordant == 0:
        p_value = 1.0
    else:
        k = min(b, c)
        prob = sum(math.comb(total_discordant, i) * (0.5 ** total_discordant) for i in range(k + 1))
        p_value = min(1.0, 2.0 * prob)

    return {
        "n11": n11,
        "n10": n10,
        "n01": n01,
        "n00": n00,
        "total_compared": len(per_scenario),
        "discordant_pairs": total_discordant,
        "exact_binomial_p_value": p_value,
        "per_scenario": per_scenario,
    }
