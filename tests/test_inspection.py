"""8단계 검사 운영·비용: 비용 계산, 임계값, 샘플링 검사, 보정, 평가 절차의 누수 방지."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import binom

from diecast_qa.inspection.calibration import (
    IsotonicCalibration,
    PlattScaling,
    brier_score,
    reliability,
)
from diecast_qa.inspection.costs import Outcome
from diecast_qa.inspection.evaluation import AlarmSwitch, ChunkedEvaluation
from diecast_qa.inspection.sampling import SamplingPlan, design_plan
from diecast_qa.inspection.strategies import (
    CensoredRecentRate,
    CostMinThreshold,
    FullInspection,
    InspectionStrategy,
    ScoreScreening,
    cost_min_threshold,
)


def test_outcome_cost():
    out = Outcome.from_inspection([1, 0, 1, 0], [1, 1, 0, 0])
    assert (out.inspected, out.missed, out.capture) == (2, 1, 0.5)
    assert out.cost(ratio=10) == 2 + 10 * 1
    total = out + out
    assert total.parts == 8 and total.cost_per_part(10) == pytest.approx(12 / 4)


def test_cost_min_threshold_matches_brute_force():
    rng = np.random.default_rng(0)
    score = rng.integers(0, 20, 300) / 20  # 동점이 많은 점수
    y = (rng.random(300) < score * 0.5).astype(float)

    def cost(th: float, ratio: float) -> float:
        return (score >= th).sum() + ratio * y[score < th].sum()

    for ratio in (1, 5, 20):
        t = cost_min_threshold(score, y, ratio)
        assert cost(t, ratio) == min(cost(th, ratio) for th in [*np.unique(score), np.inf])
    assert cost_min_threshold(score, y, ratio=0.5) == np.inf  # 검사가 미검보다 비싸면 검사 안 함


def test_sampling_plan_edge_cases_and_design():
    lot = np.r_[np.ones(10), np.zeros(90)]
    everything = SamplingPlan(100, 0).outcome(lot)  # 전부 뽑으면 놓치는 불량 없음
    assert everything.missed == pytest.approx(0) and everything.inspected == pytest.approx(100)
    accept_all = SamplingPlan(20, 20).outcome(lot)  # 항상 합격: 뽑지 않은 80%의 불량을 놓침
    assert accept_all.inspected == pytest.approx(20) and accept_all.missed == pytest.approx(8)
    plan = design_plan(0.10, 0.25)
    assert binom.cdf(plan.c, plan.n, 0.10) >= 0.95 and binom.cdf(plan.c, plan.n, 0.25) <= 0.10
    assert plan.oc(np.array([0.0]), lot_size=100)[0] == pytest.approx(1)


def test_sampling_outcome_matches_simulation():
    rng = np.random.default_rng(1)
    lot = np.r_[np.ones(15), np.zeros(85)]
    plan = SamplingPlan(20, 2)
    inspected = missed = 0
    for _ in range(20000):
        sample = rng.choice(100, 20, replace=False)
        if lot[sample].sum() <= plan.c:
            inspected, missed = inspected + 20, missed + lot.sum() - lot[sample].sum()
        else:
            inspected += 100
    out = plan.outcome(lot)
    assert out.inspected == pytest.approx(inspected / 20000, rel=0.02)
    assert out.missed == pytest.approx(missed / 20000, rel=0.05)


def test_calibrators_fix_inflated_scores():
    rng = np.random.default_rng(2)
    p = rng.uniform(0, 0.4, 5000)
    y = (rng.random(5000) < p).astype(float)
    inflated = np.sqrt(p)  # 실제보다 큰 점수
    for calibrator in (PlattScaling(), IsotonicCalibration()):
        prob = calibrator.fit(inflated, y).transform(inflated)
        assert brier_score(prob, y) < brier_score(inflated, y)
        assert np.all(np.diff(prob[np.argsort(inflated)]) >= -1e-12)  # 순서 유지
    table = reliability(inflated, y, bins=5)
    assert (table["mean_prob"] > table["observed"]).all()


def toy_stream(n_chunks: int = 6, size: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    n = n_chunks * size
    order = np.repeat(np.arange(n // 2), 2)
    return pd.DataFrame({
        "order": order, "Cavity": np.tile([1, 2], n // 2), "Product_Type": 1, "run": 1,
        "chunk": np.arange(n) // size, "y": (rng.random(n) < 0.2).astype(int),
        "recent_rate": rng.integers(0, 11, n) / 10, "tightened": False,
    })  # fmt: skip


class Spy(InspectionStrategy):
    """fit에 들어온 과거 데이터가 현재 로트보다 앞서는지 기록한다."""

    def __init__(self):
        self.checks = []

    def fit(self, past, ratio):
        self.last_past = past
        return self

    def outcome(self, current):
        self.checks.append(self.last_past["order"].max() < current["order"].min())
        return Outcome.from_inspection(current["y"], np.ones(len(current)))


def test_chunked_evaluation_uses_only_past_and_skips_warm_up():
    stream, spy = toy_stream(), Spy()
    evaluation = ChunkedEvaluation(min_parts=200, min_defects=10)
    rows = evaluation.run(stream, {"spy": lambda: spy}, (5,))
    assert spy.checks and all(spy.checks)
    assert sorted(rows["chunk"]) == [2, 3, 4, 5]  # 처음 두 로트(200개)는 준비 구간


def test_censored_rule_equals_full_rule_when_everything_is_inspected():
    stream = toy_stream()
    evaluation = ChunkedEvaluation(min_parts=200, min_defects=10)
    strategies = {
        "censored": CensoredRecentRate,
        "full": FullInspection,
        "rule": lambda: ScoreScreening("recent_rate", CostMinThreshold(), ""),
    }
    rows = evaluation.run(stream, strategies, (1000,))
    total = rows.groupby("strategy")[["inspected", "missed"]].sum()
    # 미검 비용이 매우 크면 모두 검사하므로 결과를 모두 관측한다 → 전수검사와 같다
    assert total.loc["censored", "inspected"] == total.loc["full", "inspected"]
    assert total.loc["censored", "missed"] == 0


def test_alarm_switch_flags_follow_alarms(result):
    parts = result.parts
    switch = AlarmSwitch(window=50)
    alarms, flags = switch.alarms(parts), switch.tightened(parts)
    starts = [o for v in alarms.values() for o in v]
    assert starts and flags.loc[starts].all()
    assert flags.sum() <= len(starts) * switch.window
