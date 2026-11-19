"""검사 방식 (10장). 모든 방식은 fit(과거 데이터·비용 비율)으로 조정값을 정하고 outcome으로 현재
로트(③의 50 shot 묶음, 제품 약 100개)를 검사한다. 조정에는 과거 데이터만 쓴다 (3.2).

과거 데이터의 점수는 그 시점의 모델이 학습하지 않은 예측(③ 재학습 예측)이므로, 과거 예측으로
임계값·보정을 정하는 것은 '학습 기간에서 정하고 평가 기간에 적용'과 같다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable

import numpy as np
import pandas as pd

from diecast_qa.inspection.calibration import Calibrator
from diecast_qa.inspection.costs import Outcome
from diecast_qa.inspection.sampling import PLAN_GRID, SamplingPlan


class InspectionStrategy(ABC):
    label: str = ""

    def reset(self) -> None:  # noqa: B027 (상태가 있는 방식만 다시 정의)
        """제품 유형이 바뀔 때 (상태가 있는 방식만)."""

    def fit(self, past: pd.DataFrame, ratio: float) -> InspectionStrategy:
        return self

    def warm_up(self, chunk: pd.DataFrame) -> None:  # noqa: B027
        """평가 전 준비 구간(전수검사)의 결과를 본다 (상태가 있는 방식만)."""

    def params(self) -> dict:
        """마지막 fit에서 정한 조정값 (결과 표에 남긴다)."""
        return {}

    @abstractmethod
    def outcome(self, current: pd.DataFrame) -> Outcome: ...


class PartScreening(InspectionStrategy):
    """제품마다 검사 여부(확률)를 정하는 방식."""

    @abstractmethod
    def decide(self, current: pd.DataFrame) -> np.ndarray: ...

    def outcome(self, current: pd.DataFrame) -> Outcome:
        return Outcome.from_inspection(current["y"], self.decide(current))


class FullInspection(PartScreening):
    label = "전수검사"

    def decide(self, current):
        return np.ones(len(current))


class NoInspection(PartScreening):
    label = "검사 안 함"

    def decide(self, current):
        return np.zeros(len(current))


class PerfectInspection(PartScreening):
    """불량만 정확히 골라 검사 (도달 불가능한 하한)."""

    label = "완벽한 예측 (하한)"

    def decide(self, current):
        return current["y"].to_numpy(float)


class RandomInspection(PartScreening):
    def __init__(self, rate: float) -> None:
        self.rate = rate
        self.label = f"무작위 {rate:.0%}"

    def decide(self, current):
        return np.full(len(current), self.rate)


# 위험 점수 → 검사 여부 ---------------------------------------------------------------------
class ScreeningPolicy(ABC):
    """점수에 대한 검사 기준을 과거 점수·불량으로 정한다."""

    @abstractmethod
    def fit(self, score: np.ndarray, y: np.ndarray, ratio: float) -> ScreeningPolicy: ...

    @abstractmethod
    def inspect(self, score: np.ndarray) -> np.ndarray: ...

    def params(self) -> dict:
        return {}


class CostMinThreshold(ScreeningPolicy):
    """과거 데이터에서 총비용이 가장 작은 점수 임계값 (10장). 비용이 같으면 검사가 적은 쪽."""

    def fit(self, score, y, ratio):
        score, y = np.asarray(score, float), np.asarray(y, float)
        self.threshold_ = cost_min_threshold(score, y, ratio)
        return self

    def inspect(self, score):
        return np.asarray(score, float) >= self.threshold_

    def params(self):
        return {"threshold": self.threshold_}


def cost_min_threshold(score: np.ndarray, y: np.ndarray, ratio: float) -> float:
    """'점수 ≥ t면 검사'의 총비용이 가장 작은 t (후보: 관측 점수 + 아무것도 검사 안 함)."""
    candidates = np.r_[np.unique(score), np.inf]
    order = np.argsort(score)
    sorted_score, defects_below = score[order], np.r_[0, np.cumsum(y[order])]
    below = np.searchsorted(sorted_score, candidates, side="left")  # 점수 < t인 제품 수
    cost = (len(score) - below) + ratio * defects_below[below]
    best = np.flatnonzero(cost == cost.min())[-1]
    return float(candidates[best])


class CalibratedThreshold(ScreeningPolicy):
    """과거 데이터로 점수를 보정하고 보정 확률 ≥ 1/비용 비율이면 검사 (8.7)."""

    def __init__(self, make_calibrator: Callable[[], Calibrator]) -> None:
        self.make_calibrator = make_calibrator

    def fit(self, score, y, ratio):
        self.calibrator_ = self.make_calibrator().fit(score, y)
        self.ratio_ = ratio
        return self

    def inspect(self, score):
        return self.calibrator_.transform(score) >= 1 / self.ratio_


class ScoreScreening(PartScreening):
    """위험 점수 열(column)이 기준을 넘는 제품만 검사 (규칙 선별, 모델 선별)."""

    def __init__(self, column: str, policy: ScreeningPolicy, label: str) -> None:
        self.column, self.policy, self.label = column, policy, label

    def fit(self, past, ratio):
        self.policy.fit(past[self.column].to_numpy(), past["y"].to_numpy(), ratio)
        return self

    def decide(self, current):
        return self.policy.inspect(current[self.column].to_numpy()).astype(float)

    def params(self):
        return self.policy.params()


class CavityScreening(PartScreening):
    """과거 캐비티별 불량률 × 비용 비율 ≥ 1인 캐비티만 전수검사 (단순 규칙)."""

    label = "캐비티 규칙"

    def fit(self, past, ratio):
        self.inspect_ = past.groupby("Cavity")["y"].mean() * ratio >= 1
        return self

    def decide(self, current):
        return current["Cavity"].map(self.inspect_).fillna(True).to_numpy(float)

    def params(self):
        return {"cavities": "+".join(str(c) for c, v in self.inspect_.items() if v) or "-"}


class SwitchingInspection(PartScreening):
    """관리도 경보 뒤 검사 강화 구간(tightened 열)은 전수검사, 평상시는 screening (10장)."""

    def __init__(self, screening: PartScreening, label: str) -> None:
        self.screening, self.label = screening, label

    def fit(self, past, ratio):
        self.screening.fit(past, ratio)
        return self

    def decide(self, current):
        return np.maximum(self.screening.decide(current), current["tightened"].to_numpy(float))

    def params(self):
        return self.screening.params()


class CensoredRecentRate(PartScreening):
    """검사한 제품의 결과만 보고 계산한 최근 10 shot 불량률로 선별한다.

    선별검사로 바꾸면 검사하지 않은 제품의 불량 여부를 모르므로, 규칙의 입력(최근 불량률)도
    검사한 제품만으로 계산해야 한다. 같은 구간·같은 캐비티의 직전 window shot 중 검사한 제품의
    불량률이고, 검사한 제품이 없으면 과거 불량률을 쓴다(hist_cav_rate_10과 같은 정의).
    임계값은 전체 결과를 아는 규칙과 같은 방법(과거 비용 최소)으로 정한다.
    """

    def __init__(self, column: str = "recent_rate", window: int = 10,
                 label: str = "규칙 선별 (검사한 제품만 앎)") -> None:  # fmt: skip
        self.column, self.window, self.label = column, window, label
        self.policy = CostMinThreshold()
        self.reset()

    def reset(self):
        self.history_: dict[tuple[int, int], deque] = {}

    def fit(self, past, ratio):
        self.policy.fit(past[self.column].to_numpy(), past["y"].to_numpy(), ratio)
        self.prior_ = float(past["y"].mean())
        return self

    def warm_up(self, chunk):
        for run, cavity, y in zip(chunk["run"], chunk["Cavity"], chunk["y"], strict=True):
            self._observe(run, cavity, y)

    def decide(self, current):
        """shot 순서대로: 두 캐비티의 점수를 이 shot 전까지의 관측으로 계산 → 검사 → 결과 관측."""
        frame = current.reset_index(drop=True)
        inspect = np.zeros(len(frame))
        for _, idx in sorted(frame.groupby("order").indices.items()):
            rows = frame.iloc[idx]
            keys = list(zip(rows["run"], rows["Cavity"], strict=True))
            chosen = self.policy.inspect(np.array([self._score(*k) for k in keys]))
            inspect[idx] = chosen
            for key, y, seen in zip(keys, rows["y"], chosen, strict=True):
                self._observe(*key, y if seen else None)
        return inspect

    def params(self):
        return self.policy.params()

    def _score(self, run: int, cavity: int) -> float:
        seen = [y for y in self.history_.get((run, cavity), ()) if y is not None]
        return float(np.mean(seen)) if seen else self.prior_

    def _observe(self, run: int, cavity: int, y: int | None) -> None:
        self.history_.setdefault((run, cavity), deque(maxlen=self.window)).append(y)


class SamplingInspection(InspectionStrategy):
    """로트(현재 묶음)마다 단일 샘플링 검사.

    plans가 여럿이면 과거 로트에서 총비용이 가장 작은 계획을 쓴다.
    """

    def __init__(self, plans: tuple[SamplingPlan, ...] = PLAN_GRID, label: str = "") -> None:
        self.plans = plans
        self.label = label or ("샘플링 검사" if len(plans) > 1 else f"샘플링 {plans[0].label}")

    def fit(self, past, ratio):
        if len(self.plans) == 1:
            self.plan_ = self.plans[0]
            return self
        lots = [g["y"].to_numpy() for _, g in past.groupby("chunk")]
        costs = [sum((plan.outcome(lot) for lot in lots), Outcome()).cost(ratio)
                 for plan in self.plans]  # fmt: skip
        self.plan_ = self.plans[int(np.argmin(costs))]
        return self

    def outcome(self, current):
        return self.plan_.outcome(current["y"])

    def params(self):
        return {"plan": self.plan_.label}
