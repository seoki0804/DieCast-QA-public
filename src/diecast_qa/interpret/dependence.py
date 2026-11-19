"""부분 의존도(PDP)와 개별 조건부 기대(ICE): 변수 하나를 바꿀 때 불량 확률이 어떻게 변하나."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DependenceCurve:
    """grid의 값마다 모든 행의 예측 확률. ice[i, j] = i번째 행에서 변수를 grid[j]로 바꾼 예측."""

    variable: str
    grid: np.ndarray
    ice: np.ndarray

    @property
    def pdp(self) -> np.ndarray:
        return self.ice.mean(axis=0)

    @property
    def amplitude(self) -> float:
        """PDP 최대 - 최소 (변수 하나로 움직일 수 있는 평균 불량 확률의 폭)."""
        return float(np.ptp(self.pdp))


def quantile_grid(values: pd.Series, low: float = 0.05, high: float = 0.95,
                  size: int = 25) -> np.ndarray:  # fmt: skip
    """관측값의 분위수 격자(중복 제거). 양 끝 5%는 데이터가 드물어 뺀다."""
    return np.unique(np.quantile(values.dropna(), np.linspace(low, high, size)))


def dependence(model, X: pd.DataFrame, variable: str, grid: np.ndarray) -> DependenceCurve:
    """격자 값마다 X 전체의 변수를 그 값으로 바꿔 한 번에 예측한다."""
    stacked = pd.concat([X.assign(**{variable: value}) for value in grid], ignore_index=True)
    proba = model.predict_proba(stacked)[:, 1].reshape(len(grid), len(X)).T
    return DependenceCurve(variable, np.asarray(grid, float), proba)
