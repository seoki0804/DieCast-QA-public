from diecast_qa.interpret.checklist import DefectTypeChecklist
from diecast_qa.interpret.explain import (
    INTERP_FEATURES,
    ProductTypeModel,
    TreeShap,
    fit_by_product_type,
    importance_share,
)
from diecast_qa.interpret.importance import ShapAnalysis
from diecast_qa.interpret.ranges import ControlRangeAnalysis, OperatingRange, RangeCheck

# 실행 순서: 중요도 → 관리 범위 → 유형별 점검 항목
ANALYSES = (ShapAnalysis, ControlRangeAnalysis, DefectTypeChecklist)

__all__ = [
    "ANALYSES",
    "INTERP_FEATURES",
    "ControlRangeAnalysis",
    "DefectTypeChecklist",
    "OperatingRange",
    "ProductTypeModel",
    "RangeCheck",
    "ShapAnalysis",
    "TreeShap",
    "fit_by_product_type",
    "importance_share",
]
