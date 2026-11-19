"""2단계 탐색 분석: 기획서 9장·7.7 수치 재현과 검정·그림 동작 확인."""

import pandas as pd
import pytest

from diecast_qa.data import shot_view
from diecast_qa.eda import DEFAULT_ANALYSES
from diecast_qa.eda.stats import chi_square_test, rank_biserial
from diecast_qa.viz import EdaCharts


@pytest.fixture(scope="module")
def eda(result):
    return {r.name: r for r in (cls().run(result.parts) for cls in DEFAULT_ANALYSES)}


def test_pareto_matches_plan(eda):
    types = eda["pareto"].tables["types"]
    assert types["count"].sum() == 1209
    top = types[types["vital"]]
    assert list(top.index) == ["Short_Shot", "Exfoliation", "Blow_Hole", "Deformation"]
    assert top["share"].round(3).tolist() == [0.332, 0.177, 0.170, 0.144]
    assert top["cum_share"].iloc[-1] == pytest.approx(0.823, abs=5e-4)
    assert types.loc["Stain", ["count", "cavity_1", "cavity_2"]].tolist() == [106, 106, 0]


def test_strata_match_plan(eda):
    tables = eda["strata"].tables
    run_rate = tables["rates"].loc["run", "rate"].round(3).to_dict()
    assert run_rate == {1: 0.204, 2: 0.071, 3: 0.006, 4: 0.039, 5: 0.219, 6: 0.25, 7: 0.126}
    chi = tables["chi_square"]
    assert chi.loc["Cavity", "p_value"] < 0.001
    assert chi.loc["run", "n"] == 9234 - 8  # 제품 8개뿐인 구간 6은 검정에서 제외
    # 구간을 통제해도 캐비티1의 불량 오즈가 더 높다
    assert tables["cmh"].loc["run", "ci_low"] > 1


def test_type_mix_counts(eda):
    tables = eda["type_mix"].tables
    expected = {"short_shot": 391, "exfoliation": 209, "porosity": 253, "deformation": 171,
                "other": 120}  # fmt: skip
    assert tables["by_run"].sum().to_dict() == expected
    assert tables["chi_square"].loc["run", "n"] == 1144 - 5 - 2  # 구간 3·6 제외


def test_process_comparison(eda, result):
    tests = eda["process_compare"].tables["tests"]
    shots = shot_view(result.parts)
    n_shots = shots[~shots["is_abnormal"]].groupby("Product_Type").size()
    casting = tests[tests["variable"] == "Casting_Pressure"].set_index("Product_Type")
    assert (casting["n_defect"] + casting["n_normal"]).to_dict() == n_shots.to_dict()

    assert tests["rank_biserial"].between(-1, 1).all()
    assert (tests["p_mwu_holm"] >= tests["p_mwu"]).all()
    # 2단계 핵심 발견: 같은 구간 안에서는 정상/불량 shot의 공정값 차이가 작다
    assert tests["rank_biserial"].abs().max() > 0.3
    assert tests["rank_biserial_within"].abs().max() < 0.15


def test_chi_square_switches_to_monte_carlo_for_sparse_table():
    res = chi_square_test(pd.DataFrame([[3, 1], [1, 4]]))
    assert res["method"] == "monte_carlo"
    assert 0 <= res["p_value"] <= 1


def test_rank_biserial_bounds():
    assert rank_biserial(0, 4, 5) == -1
    assert rank_biserial(20, 4, 5) == 1
    assert rank_biserial(10, 4, 5) == 0


def test_eda_charts_render(eda, tmp_path):
    paths = EdaCharts().render(eda, tmp_path)
    assert len(paths) == 4
    assert all(p.stat().st_size > 10_000 for p in paths)
