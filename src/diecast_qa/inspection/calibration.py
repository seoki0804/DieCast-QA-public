"""확률 보정 (8.7): 모델 점수를 실제 불량 비율에 맞춘다.

보정된 확률 p에서는 '검사 비용 < 기대 미검 비용', 즉 p ≥ 1/비용 비율이면 검사하는 것이 최적이다.
Class Weight로 학습한 모델은 확률이 부풀어 있어 보정 없이 1/비용 비율을 쓰면 과검사가 된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-4


class Calibrator(ABC):
    label: str

    @abstractmethod
    def fit(self, score: np.ndarray, y: np.ndarray) -> Calibrator: ...

    @abstractmethod
    def transform(self, score: np.ndarray) -> np.ndarray: ...


class Uncalibrated(Calibrator):
    """점수를 그대로 확률로 본다 (비교 기준)."""

    label = "보정 없음"

    def fit(self, score, y):
        return self

    def transform(self, score):
        return np.clip(np.asarray(score, float), 0, 1)


class PlattScaling(Calibrator):
    """logit(점수) 하나를 입력으로 하는 로지스틱 회귀 (단조 증가, S자 형태)."""

    label = "Platt scaling"

    def fit(self, score, y):
        self.model_ = LogisticRegression(C=1e6).fit(self._x(score), np.asarray(y))
        return self

    def transform(self, score):
        return self.model_.predict_proba(self._x(score))[:, 1]

    @staticmethod
    def _x(score) -> np.ndarray:
        return logit(np.clip(np.asarray(score, float), EPS, 1 - EPS)).reshape(-1, 1)


class IsotonicCalibration(Calibrator):
    """단조 증가 계단 함수 (형태 가정 없음, 데이터가 적으면 계단이 거칠다)."""

    label = "Isotonic regression"

    def fit(self, score, y):
        self.model_ = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(
            np.asarray(score, float), np.asarray(y, float))  # fmt: skip
        return self

    def transform(self, score):
        return self.model_.predict(np.asarray(score, float))


CALIBRATORS = {"raw": Uncalibrated, "platt": PlattScaling, "isotonic": IsotonicCalibration}


def brier_score(prob: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(prob) - np.asarray(y)) ** 2))


def reliability(prob: np.ndarray, y: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """예측 확률 분위수 구간마다 평균 예측 확률과 실제 불량률 (신뢰도 그림용)."""
    frame = pd.DataFrame({"prob": prob, "y": y})
    frame["bin"] = pd.qcut(frame["prob"].rank(method="first"), bins, labels=False)
    return frame.groupby("bin").agg(mean_prob=("prob", "mean"), observed=("y", "mean"),
                                    n=("y", "size"))  # fmt: skip


def expected_calibration_error(prob: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """구간별 |평균 예측 - 실제 비율|을 구간 크기로 가중 평균."""
    table = reliability(prob, y, bins)
    return float(np.average((table["mean_prob"] - table["observed"]).abs(), weights=table["n"]))
