"""3장 처리 순서를 한 번에 실행하고 공유 형식(3.3)으로 저장한다."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from diecast_qa.config import BASE_FEATURES, DEFECT_TYPES, Paths
from diecast_qa.data import CleaningReport, PartsBuilder, RawDataLoader, ShotCleaner
from diecast_qa.features import FeatureBuilder, InspectionHistoryFeatures, ProcessDriftFeatures

LABEL_COLS = ("defect", "type5", *DEFECT_TYPES)


@dataclass(frozen=True)
class PreprocessResult:
    parts: pd.DataFrame
    report: CleaningReport
    feature_sets: dict[str, list[str]]


class PreprocessPipeline:
    """원본 CSV → 제품 단위 테이블(parts.csv).

    결측 대체(3.1 순서 6)는 학습 데이터의 중앙값으로 해야 하므로 여기서 하지 않고
    모델 파이프라인 안에서 한다 (3.2). parts.csv에는 결측이 그대로 남는다.
    """

    def __init__(
        self,
        paths: Paths | None = None,
        cleaner: ShotCleaner | None = None,
        parts_builder: PartsBuilder | None = None,
        features: dict[str, FeatureBuilder] | None = None,
    ) -> None:
        self.paths = paths or Paths()
        self.cleaner = cleaner or ShotCleaner()
        self.parts_builder = parts_builder or PartsBuilder()
        self.features = features or {
            "drift": ProcessDriftFeatures(),
            "history": InspectionHistoryFeatures(),
        }

    def run(self) -> PreprocessResult:
        raw = RawDataLoader(self.paths.raw_csv).load()
        shots, report = self.cleaner.clean(raw)
        parts = self.parts_builder.build(shots)
        for builder in self.features.values():
            parts = builder.transform(parts)

        labels = list(LABEL_COLS)
        parts = parts[[c for c in parts.columns if c not in labels] + labels]
        feature_sets = {"base": list(BASE_FEATURES)}
        feature_sets |= {name: b.names for name, b in self.features.items()}
        return PreprocessResult(parts=parts, report=report, feature_sets=feature_sets)

    def save(self, result: PreprocessResult) -> None:
        self.paths.processed_dir.mkdir(parents=True, exist_ok=True)
        result.parts.to_csv(self.paths.parts_csv, index=False, float_format="%.10g")

        self.paths.results_dir.mkdir(parents=True, exist_ok=True)
        meta = {"cleaning": result.report.to_dict(), "feature_sets": result.feature_sets}
        report_path = self.paths.results_dir / "preprocess_report.json"
        report_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
