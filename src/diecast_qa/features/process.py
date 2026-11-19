"""주요 공정 변수의 흔들림을 나타내는 파생 변수 (3.1 순서 7)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.config import KEY_VARS, PROCESS_COLS, SENSOR_COLS
from diecast_qa.features.base import FeatureBuilder


class ProcessDriftFeatures(FeatureBuilder):
    """변수마다 ① 직전 shot 대비 변화량 ② 최근 shot 표준편차 ③ 직전 shot까지의 중앙값 대비 편차.

    공정값은 검사 전에 측정되므로 현재 shot 값은 써도 된다.
    비교 기준(직전 값, 중앙값)만 과거에서 가져온다. ③은 예비 실험과 달리 구간 전체가 아니라
    구간 시작부터 직전 shot까지의 중앙값을 쓴다.
    """

    def __init__(self, variables: tuple[str, ...] = KEY_VARS, std_window: int = 10) -> None:
        self.variables = list(variables)
        self.std_window = std_window

    @property
    def names(self) -> list[str]:
        suffixes = ("diff1", f"std{self.std_window}", "dev_med")
        return [f"{v}__{s}" for s in suffixes for v in self.variables]

    def transform(self, parts: pd.DataFrame) -> pd.DataFrame:
        grouped = parts.groupby(["run", "Cavity"], sort=False)[self.variables]
        diff = grouped.diff()
        std = grouped.rolling(self.std_window, min_periods=2).std().droplevel([0, 1])
        past_median = grouped.transform(lambda s: s.shift().expanding().median())
        dev = parts[self.variables] - past_median

        blocks = [
            frame.add_suffix(f"__{suffix}")
            for frame, suffix in ((diff, "diff1"), (std, f"std{self.std_window}"), (dev, "dev_med"))
        ]
        return parts.join(pd.concat(blocks, axis=1))


class RunRelativeFeatures(FeatureBuilder):
    """공정·센서 변수 20개를 '구간 시작부터 직전 shot까지의 중앙값 대비 편차'로 바꾼 변수 (6.6절).

    생산 구간마다 설정 수준이 달라 원값은 '어느 시기인가'를 드러낸다. 이 변수만 입력으로 쓰면
    구간 사이의 수준 차이는 지워지고 구간 안의 흔들림만 남는다. 정의는 ProcessDriftFeatures의
    dev_med와 같고, 대상을 주요 8개에서 전체 20개로 넓혔다. 구간 첫 shot은 결측이다
    (학습 데이터 중앙값으로 대체).
    """

    def __init__(self, variables: tuple[str, ...] = (*PROCESS_COLS, *SENSOR_COLS)) -> None:
        self.variables = list(variables)

    @property
    def names(self) -> list[str]:
        return [f"{v}__rel" for v in self.variables]

    def transform(self, parts: pd.DataFrame) -> pd.DataFrame:
        grouped = parts.groupby(["run", "Cavity"], sort=False)[self.variables]
        past_median = grouped.transform(lambda s: s.shift().expanding().median())
        return parts.join((parts[self.variables] - past_median).add_suffix("__rel"))
