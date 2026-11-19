"""검사 방식 평가 데이터와 평가 절차.

평가 데이터는 ③ 50 shot 재학습 예측(4단계 predictions.csv.gz, 평가 구간 = ②의 블록 2~5)이다.
③의 50 shot 묶음(chunk, 제품 약 100개)을 검사 로트로 보고, 제품 유형마다 생산 순서대로
'과거 로트로 조정 → 현재 로트 검사'를 반복한다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd

from diecast_qa.inspection.costs import Outcome
from diecast_qa.inspection.strategies import InspectionStrategy
from diecast_qa.modeling.designs import TimeOrderDesign
from diecast_qa.modeling.retraining import ChartAlarmTrigger
from diecast_qa.spc.charts import CUSUMChart
from diecast_qa.spc.monitoring import monitored_shots

DESIGN = "retrain_50"
SCORERS = ("et", "rf", "recent_rate")
SCORER_LABELS = {"et": "Extra Trees", "rf": "Random Forest", "recent_rate": "최근 불량률 규칙"}


class UpwardCUSUM(CUSUMChart):
    """불량률이 오르는 쪽(상측 누적합) 경보만 낸다. 검사를 강화할 신호다."""

    def evaluate(self, shots: pd.DataFrame) -> pd.DataFrame:
        points = super().evaluate(shots)
        return points[points["statistic"] == "cusum_upper"].reset_index(drop=True)


@dataclass(frozen=True)
class AlarmSwitch:
    """불량률 CUSUM(8.2와 같은 k·h, 직전 200 shot 기준) 상측 경보가 나면 다음 shot부터
    window shot 동안 검사 강화(전수검사). 불량률은 검사 뒤에 알므로 경보는 다음 shot부터 반영."""

    window: int = 50
    k: float = 0.25
    h: float = 8.0

    def alarms(self, parts: pd.DataFrame) -> dict[int, list[int]]:
        """제품 유형별 검사 강화 시작 shot의 order (평가 구간 안)."""
        trigger = ChartAlarmTrigger(lambda: [UpwardCUSUM("defect_rate", k=self.k, h=self.h,
                                                         sigma_method="binomial")],
                                    lag=1, min_gap=1)  # fmt: skip
        block = TimeOrderDesign().blocks(parts).groupby(parts["order"]).first()
        starts = {}
        for ptype, stream in monitored_shots(parts, exclude_abnormal=False).groupby("Product_Type"):
            stream = stream.reset_index(drop=True)
            start = int(np.argmax(stream["order"].map(block).to_numpy() >= 2))
            positions = trigger.retrain_positions(stream, start)[1:]
            starts[int(ptype)] = stream["order"].iloc[positions].tolist()
        return starts

    def tightened(self, parts: pd.DataFrame) -> pd.Series:
        """shot(order)마다 검사 강화 구간인지."""
        orders = np.sort(parts["order"].unique())
        flag = pd.Series(False, index=orders)
        types = parts.groupby("order")["Product_Type"].first()
        for ptype, starts in self.alarms(parts).items():
            stream = orders[types.reindex(orders).to_numpy() == ptype]
            for first in starts:
                i = np.searchsorted(stream, first)
                flag[stream[i : i + self.window]] = True
        return flag


def evaluation_stream(
    predictions: pd.DataFrame, parts: pd.DataFrame, design: str = DESIGN,
    scorers: tuple[str, ...] = SCORERS, switch: AlarmSwitch = AlarmSwitch(),
) -> pd.DataFrame:  # fmt: skip
    """제품 한 행: order, Cavity, Product_Type, run, chunk, y, 점수 열(scorers), tightened."""
    p = predictions[(predictions["design"] == design) & predictions["model"].isin(scorers)]
    keys = ["order", "Cavity", "Product_Type", "run", "chunk", "y"]
    wide = p.pivot_table(index=keys, columns="model", values="p_defect")[list(scorers)]
    wide = wide.reset_index().sort_values(["order", "Cavity"], ignore_index=True)
    wide["tightened"] = wide["order"].map(switch.tightened(parts)).fillna(False).astype(bool)
    return wide


@dataclass(frozen=True)
class ChunkedEvaluation:
    """로트마다 과거 로트로 fit → 현재 로트 검사. 과거가 min_parts개·불량 min_defects개에 못 미치는
    처음 로트는 준비 구간(전수검사로 결과를 모은다)으로 두고 모든 방식의 평가에서 똑같이 뺀다."""

    min_parts: int = 200
    min_defects: int = 10

    def steps(self, stream: pd.DataFrame) -> Iterator[tuple[int, pd.DataFrame, pd.DataFrame, bool]]:
        """(제품 유형, 과거 로트, 현재 로트, 평가 여부)를 제품 유형별 생산 순서대로."""
        for ptype, g in stream.groupby("Product_Type"):
            chunks = list(dict.fromkeys(g["chunk"]))
            for i, chunk in enumerate(chunks):
                past = g[g["chunk"].isin(chunks[:i])]
                ready = len(past) >= self.min_parts and past["y"].sum() >= self.min_defects
                yield int(ptype), past, g[g["chunk"] == chunk], ready

    def evaluated(self, stream: pd.DataFrame) -> pd.DataFrame:
        """평가에 들어가는 제품만."""
        return pd.concat([cur for _, _, cur, ready in self.steps(stream) if ready])

    def run(
        self, stream: pd.DataFrame, strategies: dict[str, Callable[[], InspectionStrategy]],
        ratios: tuple[float, ...],
    ) -> pd.DataFrame:  # fmt: skip
        """로트별 결과: 비용 비율·방식·제품 유형·로트마다 Outcome 값과 그때 정한 조정값."""
        rows = []
        for ratio in ratios:
            for name, make in strategies.items():
                strategy, current_type = None, None
                for ptype, past, current, ready in self.steps(stream):
                    if ptype != current_type:
                        strategy, current_type = make(), ptype
                        strategy.reset()
                    if not ready:
                        strategy.warm_up(current)
                        continue
                    outcome = strategy.fit(past, ratio).outcome(current)
                    rows.append({"ratio": ratio, "strategy": name, "Product_Type": ptype,
                                 "chunk": current["chunk"].iloc[0], **vars(outcome),
                                 **strategy.params()})  # fmt: skip
        return pd.DataFrame(rows)


def summarize(chunks: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """로트별 결과를 합쳐 검사 비율·포착률·제품당 비용(전수검사 = 1)을 낸다."""
    cols = ["parts", "defects", "inspected", "missed"]
    rows = []
    for key, g in chunks.groupby(by, sort=False):
        total = Outcome(*g[cols].sum())
        ratio = g["ratio"].iloc[0]
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key, strict=True)), **vars(total),
                     "inspect_rate": total.inspect_rate, "capture": total.capture,
                     "cost_per_part": total.cost_per_part(ratio)})  # fmt: skip
    return pd.DataFrame(rows)
