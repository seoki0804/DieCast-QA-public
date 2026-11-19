"""직전 shot들의 검사 결과로 만든 변수 (3.1 순서 8)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.features.base import FeatureBuilder


class InspectionHistoryFeatures(FeatureBuilder):
    """같은 구간의 직전 shot 불량률과 같은 캐비티의 최근 불량률.

    현재 shot의 결과는 쓰지 않는다. 직전 shot의 검사 결과는 예측 시점에 이미 나와 있다고 가정한다.
    """

    def __init__(self, windows: tuple[int, ...] = (1, 10, 50), cavity_window: int = 10) -> None:
        self.windows = windows
        self.cavity_window = cavity_window

    @property
    def names(self) -> list[str]:
        return [*(f"hist_rate_{w}" for w in self.windows), f"hist_cav_rate_{self.cavity_window}"]

    def transform(self, parts: pd.DataFrame) -> pd.DataFrame:
        # shot마다 제품이 2개이므로 직전 N shot의 제품 불량률 = shot별 불량 비율의 평균
        by_shot = parts.groupby("order").agg(run=("run", "first"), rate=("defect", "mean"))
        shot_rate = by_shot.groupby("run")["rate"]
        shot_hist = pd.DataFrame(
            {f"hist_rate_{w}": self.past_mean(shot_rate, w) for w in self.windows}
        )

        cavity_defect = parts.groupby(["run", "Cavity"], sort=False)["defect"]
        cavity_hist = self.past_mean(cavity_defect, self.cavity_window)

        out = parts.join(shot_hist, on="order")
        out[f"hist_cav_rate_{self.cavity_window}"] = cavity_hist
        return out
