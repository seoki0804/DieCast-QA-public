"""관리도: p, Xbar-R, EWMA, CUSUM (9장, 8.2).

모든 관리도는 Phase I(fit: 기준 데이터로 중심선·관리한계 추정)과 Phase II(evaluate: 판정)를 나눈다.
대시보드는 재생 시작 이전 데이터로 fit하고 재생 구간을 evaluate한다 (11.3).
입력은 한 제품 유형의 shot 테이블(order·run 열 포함, 생산 순서 정렬)이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Self

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from diecast_qa.spc.subgroups import ShewhartConstants, assign_subgroups

POINT_COLS = ["order", "run", "statistic", "value", "center", "lcl", "ucl", "signal"]


@dataclass(frozen=True)
class ControlLimits:
    """control_limits.csv 한 행 (3.3). center·lcl·ucl은 그 관리도 통계량의 단위다.

    CUSUM은 σ 단위 누적합이라 center 0, 한계 ±h이고, 표준화에 쓴 공정 평균은 target에 둔다.
    """

    chart: str
    variable: str
    statistic: str
    center: float
    lcl: float
    ucl: float
    subgroup_size: int
    sigma: float = np.nan
    target: float = np.nan
    params: str = ""


class ControlChart(ABC):
    chart: ClassVar[str]

    def __init__(self, variable: str) -> None:
        self.variable = variable

    @abstractmethod
    def fit(self, shots: pd.DataFrame) -> Self: ...

    @abstractmethod
    def evaluate(self, shots: pd.DataFrame) -> pd.DataFrame:
        """POINT_COLS 형식의 점 테이블. signal은 관리한계 밖이면 True."""

    @property
    @abstractmethod
    def limits(self) -> list[ControlLimits]: ...

    @staticmethod
    def points(order, run, statistic: str, value, center, lcl, ucl) -> pd.DataFrame:
        frame = pd.DataFrame({"order": order, "run": run, "value": value})
        frame["statistic"] = statistic
        frame["center"], frame["lcl"], frame["ucl"] = center, lcl, ucl
        frame["signal"] = (frame["value"] > frame["ucl"]) | (frame["value"] < frame["lcl"])
        return frame[POINT_COLS].reset_index(drop=True)


class PChart(ControlChart):
    """부분군 불량률 관리도. shot subgroup_shots개(제품 subgroup_shots × 캐비티 수)가 한 군."""

    chart = "p"

    def __init__(self, subgroup_shots: int = 50, parts_per_shot: int = 2) -> None:
        super().__init__("defect")
        self.subgroup_shots = subgroup_shots
        self.n = subgroup_shots * parts_per_shot

    def subgroup_ids(self, shots: pd.DataFrame) -> pd.Series:
        return assign_subgroups(shots, self.subgroup_shots)

    def fit(self, shots: pd.DataFrame) -> Self:
        groups = self._groups(shots)
        self.center_ = groups["defects"].sum() / (len(groups) * self.n)
        half = 3 * np.sqrt(self.center_ * (1 - self.center_) / self.n)
        self.lcl_, self.ucl_ = max(0.0, self.center_ - half), self.center_ + half
        return self

    def evaluate(self, shots: pd.DataFrame) -> pd.DataFrame:
        g = self._groups(shots)
        return self.points(g["order"], g["run"], "p", g["defects"] / self.n,
                           self.center_, self.lcl_, self.ucl_)  # fmt: skip

    @property
    def limits(self) -> list[ControlLimits]:
        return [ControlLimits(self.chart, self.variable, "p", self.center_, self.lcl_, self.ucl_,
                              self.n, params=f"{self.subgroup_shots} shot")]  # fmt: skip

    def _groups(self, shots: pd.DataFrame) -> pd.DataFrame:
        ids = self.subgroup_ids(shots)
        kept = shots[ids >= 0]
        return kept.groupby(ids[ids >= 0]).agg(
            order=("order", "first"), run=("run", "first"), defects=("n_defect", "sum")
        )


class XbarRChart(ControlChart):
    """평균(Xbar)·범위(R) 관리도. 부분군은 같은 구간 안의 연속 shot으로만 만든다(합리적 부분군)."""

    chart = "xbar_r"

    def __init__(self, variable: str, subgroup_shots: int = 5) -> None:
        super().__init__(variable)
        self.size = subgroup_shots
        self.const = ShewhartConstants.for_size(subgroup_shots)

    @property
    def sigma_within(self) -> float:
        """군내 표준편차 추정값 R̄/d2."""
        return self.rbar_ / self.const.d2

    def fit(self, shots: pd.DataFrame) -> Self:
        g = self._groups(shots)
        self.xbarbar_, self.rbar_ = g["xbar"].mean(), g["r"].mean()
        return self

    def evaluate(self, shots: pd.DataFrame) -> pd.DataFrame:
        g = self._groups(shots)
        return pd.concat(
            [self.points(g["order"], g["run"], stat, g[stat], *self._limits_of(stat))
             for stat in ("xbar", "r")], ignore_index=True,
        )  # fmt: skip

    @property
    def limits(self) -> list[ControlLimits]:
        return [ControlLimits(self.chart, self.variable, stat, *self._limits_of(stat), self.size,
                              sigma=self.sigma_within) for stat in ("xbar", "r")]  # fmt: skip

    def _limits_of(self, statistic: str) -> tuple[float, float, float]:
        if statistic == "xbar":
            half = self.const.A2 * self.rbar_
            return self.xbarbar_, self.xbarbar_ - half, self.xbarbar_ + half
        return self.rbar_, self.const.D3 * self.rbar_, self.const.D4 * self.rbar_

    def _groups(self, shots: pd.DataFrame) -> pd.DataFrame:
        ids = assign_subgroups(shots, self.size, within=("run",))
        kept = shots[ids >= 0]
        g = kept.groupby(ids[ids >= 0]).agg(
            order=("order", "first"), run=("run", "first"), xbar=(self.variable, "mean"),
            hi=(self.variable, "max"), lo=(self.variable, "min"),
        )  # fmt: skip
        g["r"] = g["hi"] - g["lo"]
        return g.dropna(subset=["xbar"])


class IndividualsChart(ControlChart):
    """shot마다 값 하나를 보는 관리도(EWMA·CUSUM)의 공통 부분: 중심과 σ 추정.

    sigma_method: "binomial"(불량률, trials개 중 비율), "moving_range"(구간 안 이동범위/1.128),
    "overall"(표본 표준편차).
    """

    def __init__(self, variable: str, sigma_method: str = "moving_range", trials: int = 2) -> None:
        super().__init__(variable)
        self.sigma_method = sigma_method
        self.trials = trials

    def fit(self, shots: pd.DataFrame) -> Self:
        x = shots[self.variable]
        self.center_ = x.mean()
        if self.sigma_method == "binomial":
            # 기준 기간에 불량이 하나도 없으면 σ가 0이 되므로 불량률을 0.5%로 두고 σ를 잡는다
            p = min(max(self.center_, 0.005), 0.995)
            self.sigma_ = np.sqrt(p * (1 - p) / self.trials)
        elif self.sigma_method == "moving_range":
            self.sigma_ = x.groupby(shots["run"]).diff().abs().mean() / 1.128
        elif self.sigma_method == "overall":
            self.sigma_ = x.std(ddof=1)
        else:
            raise ValueError(f"알 수 없는 sigma_method: {self.sigma_method}")
        # 기준 기간에 값이 일정하면 σ가 0이다. 그 뒤 값이 바뀌면 경보가 나도록 아주 작게 둔다
        self.sigma_ = max(float(self.sigma_), 1e-9)
        return self


class EWMAChart(IndividualsChart):
    """지수가중이동평균 관리도. 관리한계는 점마다 넓어지다 점근값에 수렴한다."""

    chart = "ewma"

    def __init__(self, variable: str, lam: float = 0.1, L: float = 3.0, **kwargs) -> None:
        super().__init__(variable, **kwargs)
        self.lam, self.L = lam, L

    def evaluate(self, shots: pd.DataFrame) -> pd.DataFrame:
        x = shots[self.variable].to_numpy(float)
        # z_i = λ x_i + (1-λ) z_{i-1}, z_{-1} = 중심
        z, _ = lfilter([self.lam], [1, self.lam - 1], x, zi=[(1 - self.lam) * self.center_])
        i = np.arange(1, len(x) + 1)
        half = (
            self.L
            * self.sigma_
            * np.sqrt(self.lam / (2 - self.lam) * (1 - (1 - self.lam) ** (2 * i)))
        )
        lcl = self.center_ - half
        if self.sigma_method == "binomial":
            lcl = np.maximum(lcl, 0.0)
        return self.points(shots["order"], shots["run"], "ewma", z, self.center_, lcl,
                           self.center_ + half)  # fmt: skip

    @property
    def limits(self) -> list[ControlLimits]:
        half = self.L * self.sigma_ * np.sqrt(self.lam / (2 - self.lam))
        params = f"lambda={self.lam}, L={self.L}, sigma={self.sigma_method}"
        return [ControlLimits(self.chart, self.variable, "ewma", self.center_,
                              self.center_ - half, self.center_ + half, 1, self.sigma_,
                              self.center_, params)]  # fmt: skip


class CUSUMChart(IndividualsChart):
    """표 형식(tabular) CUSUM. 값은 σ 단위이고 하측 누적합은 음수로 그린다.

    reset_on_signal이면 경보 직후 두 누적합을 0으로 되돌린다(경보 → 조치 → 재시작). 이렇게 하면
    경보 하나가 독립된 사건이 되어 경보 횟수를 재학습 신호로 쓸 수 있다 (8.2).
    """

    chart = "cusum"

    def __init__(
        self, variable: str, k: float = 0.5, h: float = 5.0, reset_on_signal: bool = True,
        **kwargs,
    ) -> None:  # fmt: skip
        super().__init__(variable, **kwargs)
        self.k, self.h = k, h
        self.reset_on_signal = reset_on_signal

    def evaluate(self, shots: pd.DataFrame) -> pd.DataFrame:
        s = (shots[self.variable].to_numpy(float) - self.center_) / self.sigma_
        upper, lower = np.zeros_like(s), np.zeros_like(s)
        hi = lo = 0.0
        for i, v in enumerate(s):
            hi, lo = max(0.0, hi + v - self.k), max(0.0, lo - v - self.k)
            upper[i], lower[i] = hi, lo
            if self.reset_on_signal and max(hi, lo) > self.h:
                hi = lo = 0.0
        order, run = shots["order"], shots["run"]
        return pd.concat([
            self.points(order, run, "cusum_upper", upper, 0.0, np.nan, self.h),
            self.points(order, run, "cusum_lower", -lower, 0.0, -self.h, np.nan),
        ], ignore_index=True)  # fmt: skip

    @property
    def limits(self) -> list[ControlLimits]:
        params = f"k={self.k}, h={self.h}, sigma={self.sigma_method}, reset={self.reset_on_signal}"
        return [ControlLimits(self.chart, self.variable, "cusum", 0.0, -self.h, self.h, 1,
                              self.sigma_, self.center_, params)]  # fmt: skip
