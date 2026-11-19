"""9단계 개선 방안·이탈 대응: 실험 계획, 경보 규칙, 개선 여지 계산."""

import numpy as np
import pandas as pd
import pytest

from diecast_qa.config import Paths
from diecast_qa.improvement.alarms import (
    alarm_windows,
    consecutive_alarm,
    evaluate_alarm,
    sudden_shift_alarm,
    sustained_alarm,
)
from diecast_qa.improvement.doe import half_fraction, parts_per_run
from diecast_qa.improvement.levers import ImprovementLevers, candidate_ranges


def test_half_fraction_is_orthogonal_resolution_iv():
    design = half_fraction(4)
    assert design.shape == (8, 4)
    assert (design.sum() == 0).all()  # 각 요인 수준이 반반
    gram = design.T @ design
    assert (gram.to_numpy() == 8 * np.eye(4)).all()  # 주효과끼리 직교
    assert (design["F4"] == design["F1"] * design["F2"] * design["F3"]).all()


def test_parts_per_run_shrinks_for_larger_effects():
    small, large = parts_per_run(0.12, 0.2, 8), parts_per_run(0.12, 0.5, 8)
    assert small > large > 0


def test_consecutive_and_sustained_alarms():
    out = np.array([0, 1, 1, 1, 1, 0, 1, 1, 1], bool)
    runs = np.array([1, 1, 1, 1, 1, 1, 1, 2, 2])
    # 3 shot 연속: 위치 3, 구간이 바뀌면 다시 센다(위치 6·7은 다른 구간)
    assert np.flatnonzero(consecutive_alarm(out, runs, 3)).tolist() == [3]
    sustained = sustained_alarm(np.r_[np.zeros(5), np.ones(10)].astype(bool), np.ones(15),
                                window=5, share=0.8)  # fmt: skip
    assert np.flatnonzero(sustained).tolist() == [8]  # 진입 시점 한 번만


def test_sudden_shift_detects_step_change():
    rng = np.random.default_rng(0)
    values = np.r_[10 + rng.normal(0, 0.1, 60), 12 + rng.normal(0, 0.1, 5)]
    alarm = sudden_shift_alarm(values, np.ones(65))
    assert alarm[60] and not alarm[:60].any()


def test_alarm_windows_stay_in_run_and_lift():
    runs = np.array([1] * 6 + [2] * 6)
    alarm = np.zeros(12, bool)
    alarm[4] = True
    window = alarm_windows(alarm, runs, horizon=3)
    assert np.flatnonzero(window).tolist() == [5]  # 구간 1의 끝까지만
    y = np.zeros(12)
    y[5] = 1
    stats = evaluate_alarm(alarm, y, runs, horizon=3)
    assert stats["coverage"] == 1 and stats["lift"] == pytest.approx(12)


def test_candidate_ranges_reads_open_ends():
    proposals = pd.DataFrame({"Product_Type": [1, 1, 2], "variable": ["a", "b", "c"],
                              "verdict": ["candidate", "not_supported", "candidate"],
                              "range_low": [np.nan, 1.0, 2.0],
                              "range_high": [5.0, 2.0, np.nan]})  # fmt: skip
    ranges = candidate_ranges(proposals)
    assert [r.variable for r in ranges[1]] == ["a"] and ranges[1][0].label() == "≤ 5"
    assert ranges[2][0].contains(pd.Series([1.0, 3.0])).tolist() == [False, True]


def test_cavity_excess_matches_direct_count(result):
    parts = result.parts
    proposals = pd.read_csv(Paths().results_dir / "interpret" / "ranges_proposals.csv")
    table = ImprovementLevers(proposals, n_boot=5).run(parts).tables["cavity"]
    clean = parts[~parts["is_abnormal"]]
    run1 = clean[clean["run"] == 1]
    r1, r2 = (run1.loc[run1["Cavity"] == c, "defect"].mean() for c in (1, 2))
    assert table.loc[1, "excess"] == pytest.approx((r1 - r2) * (run1["Cavity"] == 1).sum())
