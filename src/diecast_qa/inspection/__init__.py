from diecast_qa.inspection.analyses import (
    STRATEGIES,
    STRATEGY_LABELS,
    CalibrationAnalysis,
    InspectionCostAnalysis,
    SamplingComparison,
)
from diecast_qa.inspection.costs import COST_RATIOS, Outcome, cost_params

# 실행 순서: 10장 비용 비교 → 8.6 샘플링 검사 → 8.7 확률 보정
ANALYSES = (InspectionCostAnalysis, SamplingComparison, CalibrationAnalysis)

__all__ = [
    "ANALYSES",
    "COST_RATIOS",
    "STRATEGIES",
    "STRATEGY_LABELS",
    "CalibrationAnalysis",
    "InspectionCostAnalysis",
    "Outcome",
    "SamplingComparison",
    "cost_params",
]
