"""모델 입력 변수 묶음 (6.1, 7.3)."""

from __future__ import annotations

from diecast_qa.config import BASE_FEATURES, DEFECT_TYPES
from diecast_qa.features import InspectionHistoryFeatures, ProcessDriftFeatures, RunRelativeFeatures

DRIFT = ProcessDriftFeatures().names
HISTORY = InspectionHistoryFeatures().names
RELATIVE = RunRelativeFeatures().names

FEATURE_SETS = {
    "base": list(BASE_FEATURES),  # 공정 14 + 센서 6 + 제품 유형·캐비티·shot 번호
    "drift": [*BASE_FEATURES, *DRIFT],  # + 파생 변수
    "history": [*BASE_FEATURES, *DRIFT, *HISTORY],  # + 검사 이력 변수
    # 6.6절 시간 정보 실험. time: 생산 순서·구간 번호를 그대로 입력, relative: 공정·센서 원값 대신
    # 구간 기준 편차(RunRelativeFeatures가 만든 열, 실험에서 덧붙인다)
    "time": [*BASE_FEATURES, "order", "run"],
    "relative": [*RELATIVE, "Product_Type", "Cavity", "Shot"],
}

# 모델 입력에서 항상 빼는 열. 실험 코드가 이 열을 지운 뒤에만 모델에 넘긴다.
LABEL_COLS = ("defect", "type5", *DEFECT_TYPES)
