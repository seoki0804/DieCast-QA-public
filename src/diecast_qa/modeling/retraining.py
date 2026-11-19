"""관리도 경보 기반 재학습 (8.2).

③ 주기적 재학습과 같은 평가 구간(②의 블록 2~5)에서, 고정 주기 대신 관리도가 경보를 낼 때마다
그 시점 이전에 생산된 모든 데이터로 다시 학습한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator

import numpy as np
import pandas as pd

from diecast_qa.modeling.designs import Split, TimeOrderDesign, ValidationDesign
from diecast_qa.spc.charts import ControlChart
from diecast_qa.spc.monitoring import monitored_shots


class RetrainTrigger(ABC):
    """한 제품 유형의 shot 흐름에서 재학습 시점(그 shot 직전에 다시 학습)을 정한다."""

    @abstractmethod
    def retrain_positions(self, shots: pd.DataFrame, start: int) -> list[int]:
        """shots: 한 유형의 shot(생산 순서), start: 평가 시작 위치(iloc). 첫 원소는 start."""


class ChartAlarmTrigger(RetrainTrigger):
    """관리도 경보가 나면 다시 학습한다.

    make_charts가 만든 관리도를 직전 window shot으로 fit하고 그 뒤를 evaluate해 첫 경보를 찾는다.
    경보가 나면 그 지점에서 관리도 기준도 다시 잡는다(새 상태를 기준으로 다음 변화를 본다).
    lag: 경보 shot에서 재학습까지의 간격. 불량률은 검사 결과가 나온 뒤에 알 수 있으므로 1,
    공정 변수는 측정 즉시 알 수 있으므로 0. min_gap: 재학습 사이 최소 shot 수.
    """

    def __init__(
        self, make_charts: Callable[[], list[ControlChart]], lag: int, window: int = 200,
        min_gap: int = 10,
    ) -> None:  # fmt: skip
        self.make_charts, self.lag, self.window, self.min_gap = make_charts, lag, window, min_gap

    def retrain_positions(self, shots: pd.DataFrame, start: int) -> list[int]:
        positions, current = [start], start
        while True:
            alarm = self._first_alarm(shots, current)
            if alarm is None:
                return positions
            current = max(alarm + self.lag, current + self.min_gap)
            if current >= len(shots):
                return positions
            positions.append(current)

    def _first_alarm(self, shots: pd.DataFrame, current: int) -> int | None:
        reference = shots.iloc[max(0, current - self.window) : current]
        future = shots.iloc[current:]
        first = None
        for chart in self.make_charts():
            points = chart.fit(reference).evaluate(future)
            hits = points.loc[points["signal"], "order"]
            if not hits.empty:
                first = hits.min() if first is None else min(first, hits.min())
        if first is None:
            return None
        return int(np.searchsorted(shots["order"].to_numpy(), first))


class AlarmRetrainDesign(ValidationDesign):
    """③과 같은 평가 구간에서, trigger가 정한 시점마다 그 이전 데이터로 다시 학습한다."""

    name = "alarm_retrain"
    selects_threshold = False

    def __init__(self, trigger: RetrainTrigger, n_blocks: int = 5) -> None:
        self.trigger = trigger
        self.time_order = TimeOrderDesign(n_blocks)

    def splits(self, parts: pd.DataFrame) -> Iterator[Split]:
        block = self.time_order.blocks(parts).to_numpy()
        order = parts["order"].to_numpy()
        shots = monitored_shots(parts, exclude_abnormal=False)
        shot_block = pd.Series(block, index=order).groupby(level=0).first()
        chunk_id = 0
        for _, stream in shots.groupby("Product_Type"):
            stream = stream.reset_index(drop=True)
            start = int(np.argmax(stream["order"].map(shot_block).to_numpy() >= 2))
            positions = [*self.trigger.retrain_positions(stream, start), len(stream)]
            for lo, hi in zip(positions[:-1], positions[1:], strict=True):
                first, last = stream["order"].iloc[lo], stream["order"].iloc[hi - 1]
                test = np.flatnonzero((order >= first) & (order <= last) & (block >= 2))
                fold = int(block[test[0]])
                yield Split(fold, np.flatnonzero(order < first), test, chunk=chunk_id)
                chunk_id += 1
