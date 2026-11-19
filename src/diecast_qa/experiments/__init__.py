"""기획서 8장 추가 실험. 실험마다 Analysis를 상속해 표와 요약 문장(AnalysisResult)을 낸다."""

from diecast_qa.experiments.combination import RuleModelCombinationExperiment
from diecast_qa.experiments.drift import DriftDiagnosisExperiment
from diecast_qa.experiments.retraining import AlarmRetrainingExperiment, RecencyExperiment
from diecast_qa.experiments.synthetic import SyntheticDataExperiment
from diecast_qa.experiments.temporal import TemporalLearningExperiment

# 기획서 8장 우선순위 순서
EXPERIMENTS = {
    cls.name: cls
    for cls in (
        SyntheticDataExperiment,
        AlarmRetrainingExperiment,
        RuleModelCombinationExperiment,
        DriftDiagnosisExperiment,
        RecencyExperiment,
        TemporalLearningExperiment,  # 보고서 6.6절 (시간 정보를 활용한 학습, 기획서 밖 추가)
    )
}

__all__ = [
    "EXPERIMENTS",
    "AlarmRetrainingExperiment",
    "DriftDiagnosisExperiment",
    "RecencyExperiment",
    "RuleModelCombinationExperiment",
    "SyntheticDataExperiment",
    "TemporalLearningExperiment",
]
