"""3단계 공정 안정성: 기획서 9장 수치 재현, 관리도 공식, Phase I/II 분리."""

import numpy as np
import pandas as pd
import pytest

from diecast_qa.spc import (
    DEFAULT_ANALYSES,
    CUSUMChart,
    EWMAChart,
    PChart,
    ShewhartConstants,
    XbarRChart,
    assign_subgroups,
)
from diecast_qa.spc.monitoring import monitored_shots
from diecast_qa.viz.spc import SpcCharts


@pytest.fixture(scope="module")
def spc(result):
    return {r.name: r for r in (cls().run(result.parts) for cls in DEFAULT_ANALYSES)}


def stream(values, runs=None, n_defect=None) -> pd.DataFrame:
    """테스트용 shot 테이블."""
    n = len(values)
    return pd.DataFrame({
        "order": range(n), "run": runs if runs is not None else [1] * n, "x": values,
        "n_defect": n_defect if n_defect is not None else [0] * n,
    })  # fmt: skip


def test_assign_subgroups_drops_partial_and_respects_runs():
    shots = stream(range(12), runs=[1] * 7 + [2] * 5)
    assert assign_subgroups(shots, 5).tolist() == [0] * 5 + [1] * 5 + [-1] * 2
    assert assign_subgroups(shots, 5, within=("run",)).tolist() == [0] * 5 + [-1] * 2 + [1] * 5


def test_p_chart_matches_plan(spc):
    summary = spc["spc_defect"].tables["summary"]
    p = summary.xs("p", level="chart")[["points", "signals"]].droplevel(["variable", "statistic"])
    assert p.loc[1].tolist() == [53, 22]
    assert p.loc[2].tolist() == [39, 15]


def test_p_chart_limits_formula():
    shots = stream([0] * 20, n_defect=[1, 0] * 10)  # 부분군 10 shot = 제품 20개 중 5개 불량
    chart = PChart(subgroup_shots=10).fit(shots)
    assert chart.center_ == pytest.approx(0.25)
    assert chart.ucl_ == pytest.approx(0.25 + 3 * np.sqrt(0.25 * 0.75 / 20))


def test_xbar_r_limits_formula():
    shots = stream([1, 2, 3, 4, 5, 3, 3, 3, 3, 3])  # 부분군 평균 3·3, 범위 4·0
    chart = XbarRChart("x", 5).fit(shots)
    const = ShewhartConstants.for_size(5)
    lim = {lim.statistic: lim for lim in chart.limits}
    assert lim["xbar"].center == pytest.approx(3)
    assert lim["xbar"].ucl == pytest.approx(3 + const.A2 * 2)
    assert lim["r"].ucl == pytest.approx(const.D4 * 2)
    assert chart.sigma_within == pytest.approx(2 / const.d2)


def test_ewma_flags_shift_and_limits_converge():
    reference = stream(np.tile([-1.0, 1.0], 50))  # 평균 0, 표준편차 약 1
    chart = EWMAChart("x", lam=0.2, L=3, sigma_method="overall").fit(reference)

    step = stream(np.r_[np.zeros(50), np.full(50, 2.0)])
    points = chart.evaluate(step)
    assert not points["signal"].iloc[:50].any()
    assert points["signal"].iloc[50:].any()
    assert points["ucl"].iloc[-1] == pytest.approx(chart.limits[0].ucl, rel=1e-6)


def test_cusum_resets_after_signal():
    shots = stream(np.r_[np.zeros(10), np.full(40, 2.0)])
    reference = stream(np.tile([0.0, 2.0], 10))  # 평균 1, 표준편차 약 1
    chart = CUSUMChart("x", k=0.5, h=4, sigma_method="overall").fit(reference)
    upper = chart.evaluate(shots).query("statistic == 'cusum_upper'")
    alarms = upper.index[upper["signal"]]
    assert len(alarms) > 1
    # 경보 다음 점은 0에서 다시 쌓기 시작하므로 h를 넘지 않는다
    assert not upper.loc[alarms[0] + 1, "signal"]


def test_phase_two_uses_reference_limits(result):
    """대시보드처럼 재생 이전 데이터로 fit하면, 평가 데이터가 한계를 바꾸지 않는다 (11.3)."""
    shots = monitored_shots(result.parts, exclude_abnormal=False)
    type1 = shots[shots["Product_Type"] == 1]
    reference, replay = type1.iloc[:1000], type1.iloc[1000:]
    chart = PChart().fit(reference)
    before = chart.limits
    points = chart.evaluate(replay)
    assert chart.limits == before
    assert points["order"].min() >= replay["order"].min()
    assert (points["ucl"] == before[0].ucl).all()


def test_capability_matches_plan(spc):
    air = (
        spc["capability"]
        .tables["indices"]
        .set_index(["variable", "scope"])
        .loc[("Air_Pressure", "all")]
    )
    assert air["Pp"] == pytest.approx(1.63, abs=0.005)
    assert air["Ppk"] == pytest.approx(1.55, abs=0.005)
    assert air["Cp"] > 10 * air["Pp"]  # 군내 σ는 공정 드리프트를 놓친다


def test_control_limits_shared_format(spc):
    limits = pd.concat([spc[n].tables["limits"] for n in ("spc_defect", "spc_process")])
    expected = {"Product_Type", "chart", "variable", "statistic", "center", "lcl", "ucl",
                "subgroup_size", "sigma", "target", "params"}  # fmt: skip
    assert set(limits.columns) == expected
    assert (limits["lcl"] <= limits["center"]).all()
    assert (limits["center"] <= limits["ucl"]).all()


def test_spc_charts_render(spc, result, tmp_path):
    shots = monitored_shots(result.parts, exclude_abnormal=True)
    paths = SpcCharts().render(spc, shots, tmp_path)
    assert len(paths) == 6
    assert all(p.stat().st_size > 10_000 for p in paths)
