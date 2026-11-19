"""검사 비용 모델 (10장).

총비용 = 놓친 불량 수 × 미검 비용 + 검사 수 × 검사 비용. 양품을 검사한 비용도 검사 비용에 들어간다.
단가는 가정값이므로 검사 비용을 1(상대 단위)로 두고 미검 비용을 그 배수(비용 비율)로 바꿔 가며 본다.
비용 비율이 1/불량률보다 작으면 아무것도 검사하지 않는 편이 전수검사보다 싸다.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np
import pandas as pd

COST_RATIOS = (1, 2, 3, 5, 8, 10, 15, 20)
INSPECT_COST = 1.0


@dataclass(frozen=True)
class Outcome:
    """검사 결과 집계 (기대값이라 소수일 수 있다)."""

    parts: float = 0.0
    defects: float = 0.0
    inspected: float = 0.0
    missed: float = 0.0

    @classmethod
    def from_inspection(cls, y, inspect) -> Outcome:
        """inspect: 제품마다 검사할 확률(0~1). 검사한 불량은 찾고, 검사하지 않은 불량은 놓친다."""
        y, inspect = np.asarray(y, float), np.asarray(inspect, float)
        return cls(len(y), y.sum(), inspect.sum(), float(y @ (1 - inspect)))

    def __add__(self, other: Outcome) -> Outcome:
        return Outcome(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    @property
    def inspect_rate(self) -> float:
        return self.inspected / self.parts

    @property
    def capture(self) -> float:
        """전체 불량 중 검사로 찾은 비율."""
        return 1 - self.missed / self.defects if self.defects else np.nan

    def cost(self, ratio: float, inspect_cost: float = INSPECT_COST) -> float:
        return inspect_cost * (self.inspected + ratio * self.missed)

    def cost_per_part(self, ratio: float) -> float:
        """제품 1개당 비용. 전수검사는 항상 1이므로 '전수검사 대비 비용'으로 읽는다."""
        return self.cost(ratio) / self.parts


def cost_params(ratios: tuple[float, ...] = COST_RATIOS) -> pd.DataFrame:
    """3.3 cost_params.csv: 비용 비율 시나리오 (검사 비용 1 기준 상대 단가)."""
    return pd.DataFrame({
        "scenario": [f"{r}:1" for r in ratios], "inspect_cost": INSPECT_COST,
        "miss_cost": [r * INSPECT_COST for r in ratios], "ratio": ratios,
        "break_even_threshold": [1 / r for r in ratios],
    })  # fmt: skip
