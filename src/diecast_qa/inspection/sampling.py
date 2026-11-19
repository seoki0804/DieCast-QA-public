"""단일 샘플링 검사 계획 (8.6, 10장).

로트 N개에서 n개를 뽑아 불량이 c개 이하면 합격, 넘으면 로트 전체를 검사한다(선별형 검사).
합격 로트에서 뽑지 않은 제품의 불량은 놓친다. 기대값은 초기하분포로 정확히 계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np
from scipy.stats import binom, hypergeom

from diecast_qa.inspection.costs import Outcome


@dataclass(frozen=True)
class SamplingPlan:
    n: int
    c: int

    @property
    def label(self) -> str:
        return f"n={self.n}, c={self.c}"

    def outcome(self, y) -> Outcome:
        """로트 하나(y: 제품별 불량 0/1)의 기대 검사 수·놓친 불량 수."""
        y = np.asarray(y)
        inspected, missed = _lot_outcome(self.n, self.c, len(y), int(y.sum()))
        return Outcome(len(y), float(y.sum()), inspected, missed)

    def oc(self, p: np.ndarray, lot_size: int | None = None) -> np.ndarray:
        """OC curve: 로트 불량률 p일 때 합격 확률.

        lot_size를 주면 그 크기 로트의 초기하분포(A형), 없으면 이항 근사(B형, 큰 로트).
        """
        p = np.asarray(p, float)
        if lot_size is None:
            return binom.cdf(self.c, self.n, p)
        defects = np.round(p * lot_size).astype(int)
        return hypergeom.cdf(self.c, lot_size, defects, min(self.n, lot_size))


@cache
def _lot_outcome(n: int, c: int, lot: int, defects: int) -> tuple[float, float]:
    n = min(n, lot)
    x = np.arange(0, min(c, defects, n) + 1)
    pmf = hypergeom.pmf(x, lot, defects, n)
    accept = pmf.sum()
    return float(n * accept + lot * (1 - accept)), float(pmf @ (defects - x))


# 고전적 설계의 가정: 공정 평균 수준(10%)의 로트는 95% 합격, 고불량 시기 수준(25%)의 로트는
# 10%만 합격. 이 공정의 불량률이 높아 일반적인 AQL(1~2.5%)로는 거의 모든 로트가 불합격한다
AQL, LTPD = 0.10, 0.25

PLAN_GRID = tuple(SamplingPlan(n, c) for n in (5, 10, 15, 20, 30, 50) for c in range(6) if c < n)


def design_plan(aql: float, ltpd: float, alpha: float = 0.05, beta: float = 0.10,
                max_n: int = 100) -> SamplingPlan:  # fmt: skip
    """생산자 위험 α(AQL 로트를 불합격시킬 확률)와 소비자 위험 β(LTPD 로트를 합격시킬 확률)를
    만족하는 가장 작은 표본 계획."""
    for n in range(1, max_n + 1):
        for c in range(n):
            if binom.cdf(c, n, ltpd) > beta:
                break
            if binom.cdf(c, n, aql) >= 1 - alpha:
                return SamplingPlan(n, c)
    raise ValueError(f"n ≤ {max_n}에서 AQL {aql}, LTPD {ltpd}을 만족하는 계획이 없다")


CLASSICAL_PLAN = design_plan(AQL, LTPD)
