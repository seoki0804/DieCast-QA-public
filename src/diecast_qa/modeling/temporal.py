"""시간에 따른 분포 변화에 대응하는 학습 방법 (6.6절).

- RunInvariantSelector: 학습 데이터에서 구간 간 분산 비율이 큰 변수(생산 시기를 드러내는 변수)를
  뺀다.
  여러 환경(구간)에서 관계가 유지되는 변수만 쓰자는 불변 학습(invariant learning)의 단순한 형태다.
- covariate_shift_weights: 학습 데이터 중 최근 부분과 닮은 표본에 큰 가중치를 준다. 평가 시기의 입력
  분포를 학습 데이터의 가장 최근 부분으로 근사한 공변량 이동 보정(importance weighting)이다.

둘 다 학습 데이터 안에서만 계산하므로 평가 데이터의 정보를 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from diecast_qa.config import BASE_FEATURES

KEEP_ALWAYS = ("Product_Type", "Cavity")


def run_variance_share(X: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    """변수마다 제품 유형 안에서 구간(run) 평균의 차이가 설명하는 분산 비율(η²). 1에 가까우면
    구간마다 값이 거의 고정이라 그 변수가 '어느 시기인가'를 나타낸다."""
    shares = {}
    for col in columns:
        within_type = X[col] - X.groupby("Product_Type")[col].transform("mean")
        total = float((within_type**2).sum())
        run_mean = X.groupby(["Product_Type", "run"])[col].transform("mean")
        type_mean = X.groupby("Product_Type")[col].transform("mean")
        between = float(((run_mean - type_mean) ** 2).sum())
        shares[col] = between / total if total > 0 else 0.0
    return pd.Series(shares)


class RunInvariantSelector(BaseEstimator, TransformerMixin):
    """입력에 run 열이 있어야 한다. fit에서 η²가 threshold를 넘는 변수를 고르고, transform에서
    그 변수와 run 열을 뺀다."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    def fit(self, X: pd.DataFrame, y=None) -> RunInvariantSelector:
        candidates = [c for c in X.columns if c not in ("run", *KEEP_ALWAYS)]
        frame = X[[*candidates, "run", "Product_Type"]].copy()
        frame[candidates] = frame[candidates].fillna(frame[candidates].median())
        self.shares_ = run_variance_share(frame, candidates)
        self.dropped_ = sorted(self.shares_[self.shares_ > self.threshold].index)
        self.columns_ = [c for c in X.columns if c != "run" and c not in self.dropped_]
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return X[self.columns_]


def covariate_shift_weights(parts: pd.DataFrame, recent_share: float = 0.2,
                            clip: tuple[float, float] = (0.1, 10.0)) -> np.ndarray:  # fmt: skip
    """학습 데이터(parts)의 표본 가중치 w ∝ P(최근 | x) / P(이전 | x), 평균 1.

    최근 = 학습 데이터 생산 순서의 뒤 recent_share. 판별 모델은 표준화한 기본 입력의 로지스틱 회귀.
    극단값은 clip으로 자른다.
    """
    orders = np.sort(parts["order"].unique())
    cut = orders[int(len(orders) * (1 - recent_share))]
    recent = (parts["order"] >= cut).to_numpy().astype(int)
    if recent.min() == recent.max():
        return np.ones(len(parts))
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(max_iter=2000))  # fmt: skip
    X = parts[list(BASE_FEATURES)]
    p = model.fit(X, recent).predict_proba(X)[:, 1]
    p = np.clip(p, 1e-6, 1 - 1e-6)
    odds_prior = recent.mean() / (1 - recent.mean())
    w = np.clip((p / (1 - p)) / odds_prior, *clip)
    return w / w.mean()
