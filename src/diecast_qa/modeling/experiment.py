"""검증 방식 × 모델 실험 실행."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator

from diecast_qa.modeling.designs import Split, ValidationDesign
from diecast_qa.modeling.estimators import ModelSpec
from diecast_qa.modeling.features import LABEL_COLS
from diecast_qa.modeling.metrics import best_f1_threshold
from diecast_qa.modeling.temporal import covariate_shift_weights

ID_COLS = ["order", "Cavity", "Product_Type", "run"]


def _recent_window(n: int):
    """학습 데이터 중 가장 최근 n shot만 쓴다 (8.5 sliding window)."""
    return lambda parts: parts["order"] > parts["order"].max() - n


def _half_life(h: int):
    """가장 최근 shot에서 h shot 멀어질 때마다 가중치가 절반이 된다 (8.5 시간 가중치)."""
    return lambda parts: (0.5 ** ((parts["order"].max() - parts["order"]) / h)).to_numpy()


TRAIN_FILTERS = {
    "drop_abnormal": lambda parts: ~parts["is_abnormal"],
    "drop_missing": lambda parts: parts[["Factory_Temp", "Factory_Humidity"]].notna().all(axis=1),
    "window_500": _recent_window(500),
    "window_1000": _recent_window(1000),
}
TRAIN_WEIGHTS = {
    "halflife_200": _half_life(200),
    "halflife_500": _half_life(500),
    "shift_weight": covariate_shift_weights,  # 6.6절: 최근 학습 데이터와 닮은 표본에 큰 가중치
}


class Experiment:
    """design의 분할마다 specs의 모델을 학습해 평가 데이터의 불량 확률을 모은다.

    결과는 predictions 형식(3.3)의 DataFrame: 식별 열, design, fold, chunk, model, feature_set,
    variant, y(실제 불량), p_defect(위험 점수), threshold(내부 검증으로 고른 판정 기준).
    """

    def __init__(self, design: ValidationDesign, specs: Sequence[ModelSpec], label: str = ""):
        self.design = design
        self.specs = specs
        self.label = label or design.name

    def run(self, parts: pd.DataFrame) -> pd.DataFrame:
        parts = parts.reset_index(drop=True)
        X = parts.drop(columns=list(LABEL_COLS))
        y = self.target(parts)
        frames = [
            self._fit_predict(parts, X, y, split, spec)
            for split in self.design.splits(parts)
            for spec in self.specs
        ]
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def target(parts: pd.DataFrame) -> pd.Series:
        """학습 목표. 1단계는 불량 여부."""
        return parts["defect"]

    def _fit_predict(self, parts, X, y, split: Split, spec: ModelSpec) -> pd.DataFrame:
        threshold = np.nan
        if self.design.selects_threshold:
            inner = self._fit(spec, parts, X, y, split.inner_train)
            val = split.inner_val
            threshold = best_f1_threshold(y.iloc[val], predict_score(inner, X.iloc[val]))
        model = self._fit(spec, parts, X, y, split.train)
        test = split.test
        return parts.iloc[test][ID_COLS].assign(
            design=self.label, fold=split.fold, chunk=split.chunk, model=spec.name,
            feature_set=spec.features, variant=spec.variant, y=y.iloc[test].to_numpy(),
            p_defect=predict_score(model, X.iloc[test]), threshold=threshold,
        )  # fmt: skip

    @staticmethod
    def _fit(spec: ModelSpec, parts, X, y, idx: np.ndarray) -> BaseEstimator:
        if spec.train_filter:
            idx = idx[TRAIN_FILTERS[spec.train_filter](parts.iloc[idx]).to_numpy()]
        model = spec.build()
        params = {}
        if spec.train_weight:
            # 파이프라인의 마지막 단계(분류기)에 표본 가중치를 넘긴다
            params[f"{model.steps[-1][0]}__sample_weight"] = TRAIN_WEIGHTS[spec.train_weight](
                parts.iloc[idx])  # fmt: skip
        return model.fit(X.iloc[idx], y.iloc[idx], **params)


def predict_score(model: BaseEstimator, X: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(X)[:, 1]
