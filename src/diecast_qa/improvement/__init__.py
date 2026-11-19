"""불량 개선 방안과 관리 범위 이탈 대응 연구 (사용자 요청 추가 연구).

관리 범위(7단계)를 입력으로 쓴다: 각 분석은 results/interpret/ranges_proposals.csv 표를 받는다.
"""

from diecast_qa.improvement.alarms import AlarmDesign
from diecast_qa.improvement.doe import ExperimentPlan
from diecast_qa.improvement.levers import ImprovementLevers

# 실행 순서: 개선 여지 → 실험 계획 → 경보·대응 계획
ANALYSES = (ImprovementLevers, ExperimentPlan, AlarmDesign)

__all__ = ["ANALYSES", "AlarmDesign", "ExperimentPlan", "ImprovementLevers"]
