"""Evaluation harness, headless simulator, and ablation runners."""

from src.eval.synthetic_app import SyntheticApp
from src.eval.simulator import HeadlessSimulator, ExperimentExecutionResult
from src.eval.scenarios import EvaluationScenario, get_gold_set_scenarios
from src.eval.scorer import EvaluationMetrics, DeterministicScorer
from src.eval.ablation import AblationFramework

__all__ = [
    "SyntheticApp",
    "HeadlessSimulator",
    "ExperimentExecutionResult",
    "EvaluationScenario",
    "get_gold_set_scenarios",
    "EvaluationMetrics",
    "DeterministicScorer",
    "AblationFramework",
]
