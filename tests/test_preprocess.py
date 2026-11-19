"""기획서 2.3~2.5의 점검 수치 재현과 3.2 누수 방지 규칙 확인."""

import numpy as np
import pandas as pd
import pytest

from diecast_qa.config import DEFECT_TYPES, KEY_VARS, NORMAL, SPEC_COLS
from diecast_qa.data import DefectLabeler
from diecast_qa.features import InspectionHistoryFeatures, ProcessDriftFeatures


def test_cleaning_matches_plan(result):
    report = result.report
    assert (report.raw_rows, report.duplicate_rows, report.shots) == (7535, 2918, 4617)
    assert report.run_sizes == {1: 1099, 2: 1157, 3: 397, 4: 600, 5: 725, 6: 4, 7: 635}
    assert len(report.abnormal_orders) == 8
    assert report.missing_shots["Factory_Temp"] == report.missing_shots["Factory_Humidity"] == 45


def test_parts_labels_match_plan(result):
    parts = result.parts
    assert len(parts) == 9234
    assert parts["defect"].sum() == 1144
    cavity_rate = parts.groupby("Cavity")["defect"].mean().round(3)
    assert cavity_rate.to_dict() == {1: 0.170, 2: 0.078}
    type5 = parts.loc[parts["defect"] == 1, "type5"].value_counts().to_dict()
    expected = {"short_shot": 391, "exfoliation": 209, "porosity": 253, "deformation": 171,
                "other": 120}  # fmt: skip
    assert type5 == expected
    assert (parts.loc[parts["defect"] == 0, "type5"] == NORMAL).all()


def test_multi_type_products(result):
    scores = DefectLabeler().group_scores(result.parts[list(DEFECT_TYPES)])
    assert (scores.gt(0).sum(axis=1) >= 2).sum() == 24


def test_type_counts_by_run_match_plan(result):
    """2.5 '생산 구간별 유형 발생 수' 표 (제품 단위, 유형 중복 포함).

    기획서 표의 기타 열만은 최종 지정 유형(type5) 기준이다. 중복을 포함하면 6/38/93으로 137개.
    """
    parts = result.parts
    present = DefectLabeler().group_scores(parts[list(DEFECT_TYPES)]).gt(0)
    present["other"] = parts["type5"] == "other"
    table = present.groupby(parts["run"]).sum()
    table.insert(0, "n_parts", parts.groupby("run").size())
    expected = pd.DataFrame(
        [[2198, 104, 116, 52, 172, 5], [2314, 64, 91, 11, 0, 0], [794, 0, 3, 2, 0, 0],
         [1200, 3, 0, 7, 0, 37], [1450, 108, 0, 136, 0, 78], [8, 2, 0, 0, 0, 0],
         [1270, 111, 0, 49, 0, 0]],
        index=pd.Index(range(1, 8), name="run"), columns=table.columns,
    )  # fmt: skip
    pd.testing.assert_frame_equal(table, expected, check_dtype=False)


def test_abnormal_shots_are_idle_or_stalled(result):
    shots = result.parts.drop_duplicates("order")
    abnormal = shots[shots["is_abnormal"]]
    assert abnormal["Cycle_Time"].max() == pytest.approx(218.6)
    assert (abnormal["Biscuit_Thickness"] == 0).sum() == 2


def test_columns_follow_shared_format(result):
    parts = result.parts
    assert not set(SPEC_COLS) & set(parts.columns)
    assert list(parts.columns[-(2 + len(DEFECT_TYPES)) :]) == ["defect", "type5", *DEFECT_TYPES]
    for names in result.feature_sets.values():
        assert set(names) <= set(parts.columns)


def test_labeler_tie_break_and_other_presence():
    rows = [
        {"Short_Shot": 1, "Stain": 2},  # 기타는 유형 개수(1)로 셈 → 동점 → 미성형
        {"Short_Shot": 1, "Blow_Hole": 1, "Bubble": 1},  # 기공 2 > 미성형 1
        {"Exfoliation": 1, "Deformation": 1},  # 동점 → 박리 우선
        {},  # 정상
        {"Short_Shot": 1, "Stain": 1, "Dent": 1},  # 기타 2 > 미성형 1
    ]
    counts = pd.DataFrame(rows, columns=list(DEFECT_TYPES)).fillna(0)
    labels = DefectLabeler().label(counts)
    assert labels["type5"].tolist() == ["short_shot", "porosity", "exfoliation", NORMAL, "other"]
    assert labels["defect"].tolist() == [1, 1, 1, 0, 1]


def test_history_uses_only_previous_shots(result):
    parts = result.parts
    shot = parts.groupby("order").agg(run=("run", "first"), rate=("defect", "mean"))
    expected = shot.groupby("run")["rate"].shift()
    actual = parts.drop_duplicates("order").set_index("order")["hist_rate_1"]
    pd.testing.assert_series_equal(actual, expected, check_names=False)


@pytest.mark.parametrize("builder", [ProcessDriftFeatures(), InspectionHistoryFeatures()])
def test_features_ignore_future_shots(base_parts, builder):
    """미래 shot의 공정값·검사 결과를 바꿔도 과거 행의 변수는 그대로여야 한다."""
    cutoff = 2000
    future = base_parts["order"] > cutoff
    perturbed = base_parts.astype({col: float for col in KEY_VARS})
    rng = np.random.default_rng(0)
    for col in KEY_VARS:
        perturbed.loc[future, col] = rng.normal(size=future.sum())
    perturbed.loc[future, "defect"] = 1 - perturbed.loc[future, "defect"]

    before = builder.transform(base_parts).loc[~future, builder.names]
    after = builder.transform(perturbed).loc[~future, builder.names]
    pd.testing.assert_frame_equal(before, after)


def test_drift_dev_med_excludes_current_shot(result):
    parts = result.parts[result.parts["Cavity"] == 1]
    col = "Casting_Pressure"
    run_start = parts.groupby("run").head(2)
    first, second = run_start.iloc[0], run_start.iloc[1]
    assert np.isnan(first[f"{col}__dev_med"])
    assert second[f"{col}__dev_med"] == pytest.approx(second[col] - first[col])
