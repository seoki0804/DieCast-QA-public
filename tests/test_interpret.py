"""7단계 해석·관리 범위: SHAP 가법성, PDP·ICE, 관리 범위 탐색과 구간 내 검증, 유형별 점검 항목."""

import numpy as np
import pandas as pd
import pytest
from scipy.special import logit

from diecast_qa.config import CONTROL_VARS
from diecast_qa.eda.stats import rank_biserial_by_group, weighted_effect
from diecast_qa.interpret import DefectTypeChecklist, OperatingRange, RangeCheck, ShapAnalysis
from diecast_qa.interpret.dependence import DependenceCurve, dependence, quantile_grid
from diecast_qa.interpret.explain import fit_by_product_type
from diecast_qa.interpret.ranges import low_risk_range, run_variance_share


@pytest.fixture(scope="module")
def parts(result):
    return result.parts


@pytest.fixture(scope="module")
def type1_model(parts):
    return fit_by_product_type(parts[parts["run"].isin([1, 2])])[1]


def test_shap_values_add_up_to_prediction(type1_model):
    m = type1_model
    total = m.shap_values.sum(axis=1) + m.shap_base
    np.testing.assert_allclose(total, logit(m.proba()), atol=1e-4)


def test_shap_table_has_one_row_per_part(parts):
    values = ShapAnalysis().run(parts).tables["values"]
    assert len(values) == len(parts)
    assert not values.duplicated(["order", "Cavity"]).any()
    assert {"order", "Cavity", "model", "shap_Cavity", "base_value"} <= set(values.columns)


def test_dependence_ice_and_pdp(type1_model):
    m = type1_model
    grid = quantile_grid(m.X["Biscuit_Thickness"])
    curve = dependence(m.model, m.X, "Biscuit_Thickness", grid)
    assert curve.ice.shape == (len(m.X), len(grid))
    np.testing.assert_allclose(curve.pdp, curve.ice.mean(axis=0))
    # 격자 값이 실제 값과 같은 행에서는 ICE가 원래 예측과 같다
    j = 0
    rows = (m.X["Biscuit_Thickness"] == grid[j]).to_numpy()
    np.testing.assert_allclose(curve.ice[rows, j], m.proba()[rows], rtol=1e-6)


def curve(pdp: list[float]) -> DependenceCurve:
    pdp = np.asarray(pdp)
    return DependenceCurve("x", np.arange(len(pdp), dtype=float), np.tile(pdp, (3, 1)))


def test_low_risk_range_picks_widest_run_below_reference():
    rng = low_risk_range(curve([0.20, 0.10, 0.05, 0.05, 0.10, 0.20, 0.08]), reference=0.12)
    assert (rng.low, rng.high, rng.open_low, rng.open_high) == (1, 4, False, False)
    edge = low_risk_range(curve([0.05, 0.06, 0.20, 0.30]), reference=0.12)
    assert edge.open_low and edge.label() == "≤ 1"
    assert low_risk_range(curve([0.10, 0.11, 0.10]), reference=0.105) is None  # 폭 0.01 < 0.02
    assert low_risk_range(curve([0.20, 0.30]), reference=0.1) is None  # 낮은 곳이 없음


def test_operating_range_contains():
    values = pd.Series([1.0, 2.0, 3.0, np.nan])
    assert OperatingRange("x", 1.5, 3.0).contains(values).tolist() == [False, True, True, False]
    assert OperatingRange("x", 0, 2.0, open_low=True).contains(values).tolist()[:3] == [
        True, True, False]  # fmt: skip


def synthetic_shots(within_effect: bool, n_runs: int = 3) -> pd.DataFrame:
    """범위(x ≤ 0) 밖이면 불량이 많은 shot. within_effect=False면 x가 구간마다 고정."""
    rng = np.random.default_rng(0)
    frames = []
    for run in range(n_runs):
        x = rng.normal(size=300) if within_effect else np.full(300, run - 1.0)
        p = np.where(x > 0, 0.4, 0.1)
        frames.append(pd.DataFrame({"run": run, "x": x,
                                    "shot_defect": (rng.random(300) < p).astype(int)}))  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def test_range_check_separates_within_run_effect_from_period_marker():
    check, rng = RangeCheck(), OperatingRange("x", 0.0, 0.0, open_low=True)
    row = check.evaluate(synthetic_shots(within_effect=True), rng) | {"range_label": "≤ 0"}
    assert row["runs_tested"] == 3 and row["cmh_low"] > 1
    assert check.verdict(row) == "candidate"
    marker = check.evaluate(synthetic_shots(within_effect=False), rng) | {"range_label": "≤ 0"}
    assert marker["runs_tested"] == 0 and check.verdict(marker) == "untestable"


def test_run_variance_share():
    shots = synthetic_shots(within_effect=False)
    assert run_variance_share(shots["x"], shots["run"]) == pytest.approx(1.0)


def test_rank_biserial_by_group():
    values = pd.Series([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)
    case = pd.Series([0, 0, 0, 1, 1, 1] * 2).astype(bool)
    groups = pd.Series([1] * 6 + [2] * 6)
    by_group = rank_biserial_by_group(values, case, groups, min_group=3)
    assert by_group["effect"].tolist() == [1.0, 1.0]  # case 값이 모두 큼
    assert weighted_effect(by_group) == 1.0
    assert rank_biserial_by_group(values, case, groups, min_group=4).empty


def test_checklist_items_are_controllable_and_signed(parts):
    tables = DefectTypeChecklist().run(parts[parts["run"].isin([1, 2, 5])]).tables
    items = tables["items"]
    assert set(items["variable"]) <= set(CONTROL_VARS)
    assert ((items["effect"] > 0) == (items["direction"] == "높음")).all()
    assert (items["effect"].abs() >= 0.05).all()
    assert items.groupby(level="type5").size().max() <= 3
