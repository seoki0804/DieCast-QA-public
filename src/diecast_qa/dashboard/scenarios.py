"""재생 시나리오: (제품 유형, 시작 구간) × 재학습 옵션 (기획서 11.2)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

RETRAIN_LABELS = {
    "none": "재학습 없음",
    "every_50": "50 shot마다 재학습",
    "alarm": "관리도 경보 시 재학습",
}
# 시작 전 학습 데이터가 충분하고, 재생 구간에 불량률 변화가 있는 구간
START_POINTS = ((1, 2), (2, 5), (2, 7))


@dataclass(frozen=True)
class Scenario:
    product_type: int
    start_run: int
    retrain: str

    @property
    def id(self) -> str:
        return f"t{self.product_type}_r{self.start_run}_{self.retrain}"

    @property
    def label(self) -> str:
        retrain = RETRAIN_LABELS[self.retrain]
        return f"유형 {self.product_type} · 구간 {self.start_run}부터 · {retrain}"

    def split(self, parts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(시작 이전의 모든 제품: 학습 데이터, 시작부터 그 제품 유형 생산 끝까지: 재생 데이터)."""
        start = parts.loc[parts["run"] == self.start_run, "order"].min()
        replay = parts[(parts["order"] >= start) & (parts["Product_Type"] == self.product_type)]
        return parts[parts["order"] < start], replay


SCENARIOS = tuple(Scenario(pt, run, r) for pt, run in START_POINTS for r in RETRAIN_LABELS)
