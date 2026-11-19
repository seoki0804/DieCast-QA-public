"""5단계 2단계 유형 분류: 학습 데이터 제한, 확률 열 정렬, 비교 기준, 연결 평가, 7.6 재현."""

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin

from diecast_qa.config import NORMAL
from diecast_qa.modeling import ModelSpec, TimeOrderDesign
from diecast_qa.modeling.metrics import summarize
from diecast_qa.modeling.type_experiment import (
    P_TYPE_COLS,
    TYPE_METRIC_COLS,
    TypeExperiment,
    joint_capture,
    type_fold_metrics,
)
from diecast_qa.modeling.type_models import (
    TYPE_MODELS,
    TYPE_RULES,
    BalancedTypeXGBClassifier,
    TypeDistributionRule,
    type_proba,
)


@pytest.fixture(scope="module")
def parts(result):
    return result.parts


class _Spy(BaseEstimator, ClassifierMixin):
    sizes: list = []

    def fit(self, X, y):
        assert not pd.isna(y).any()
        _Spy.sizes.append(len(y))
        self.classes_ = np.unique(y)
        return self

    def predict_proba(self, X):
        return np.full((len(X), len(self.classes_)), 1 / len(self.classes_))


def test_trains_on_defective_parts_only_and_predicts_all_test_parts(parts):
    design = TimeOrderDesign()
    pred = TypeExperiment(design, [ModelSpec("spy", "spy", lambda _: _Spy())]).run(parts)
    expected = [int(parts["defect"].iloc[s.train].sum()) for s in design.splits(parts)]
    assert _Spy.sizes == expected
    assert len(pred) == sum(len(s.test) for s in design.splits(parts))  # 양품 포함 전체
    assert np.allclose(pred[P_TYPE_COLS].sum(axis=1), 1)


def test_type_proba_keeps_columns_for_missing_classes():
    X = pd.DataFrame({"a": np.arange(30.0)})
    y = np.repeat([0, 2, 4], 10)  # 유형 1·3이 학습 데이터에 없다
    model = BalancedTypeXGBClassifier(n_estimators=5).fit(X, y)
    proba = type_proba(model, X)
    assert proba.shape == (30, 5)
    assert (proba[:, [1, 3]] == 0).all()
    assert proba[:10].argmax(axis=1).tolist() == [0] * 10


def test_type_distribution_rule_groups_and_fallback():
    X = pd.DataFrame({"Product_Type": [1, 1, 1, 2], "Cavity": [1, 1, 2, 1]})
    y = [0, 0, 3, 1]
    rule = TypeDistributionRule(("Product_Type", "Cavity")).fit(X, y)
    new = pd.DataFrame({"Product_Type": [1, 2], "Cavity": [1, 2]})  # (2, 2)는 처음 보는 그룹
    proba = rule.predict_proba(new)
    assert proba[0].tolist() == [1, 0, 0, 0, 0]
    assert proba[1].tolist() == pytest.approx([0.5, 0.25, 0, 0.25, 0])
    assert TypeDistributionRule().fit(X, y).predict(new).tolist() == [0, 0]


def test_joint_capture_counts_type_hits_among_inspected():
    ids = {"design": "d", "fold": 1, "order": range(10), "Cavity": 1}
    stage1 = pd.DataFrame({**ids, "model": "s1", "y": [1, 1, 0, 0, 0, 0, 0, 0, 0, 1],
                           "p_defect": np.linspace(1, 0.1, 10)})  # fmt: skip
    y_type = [*["short_shot"] * 2, *[NORMAL] * 7, "other"]
    stage2 = pd.DataFrame({**ids, "model": "s2", "y_type": y_type,
                           "pred_type": ["short_shot", "porosity", *y_type[2:]]})  # fmt: skip
    r = joint_capture(stage1, stage2, fracs=(0.2,)).iloc[0]
    assert r["capture"] == pytest.approx(2 / 3)  # 상위 2개(불량 2개) 검사, 마지막 불량은 놓침
    assert r["type_hit"] == pytest.approx(1 / 2)  # 검사한 불량 2개 중 1개만 유형 적중
    assert r["end_to_end"] == pytest.approx(1 / 3)


def test_time_order_reproduces_plan(parts):
    """기획서 7.6의 ② 시간 순서 Macro-F1."""
    specs = [TYPE_MODELS["rf"], TYPE_MODELS["xgb"], *TYPE_RULES.values()]
    pred = TypeExperiment(TimeOrderDesign(), specs).run(parts)
    f1 = summarize(type_fold_metrics(pred, ["model"]), ["model"], TYPE_METRIC_COLS)
    f1 = f1["macro_f1_mean"]
    plan = {"rf": 0.34, "xgb": 0.27, "type_mode": 0.14, "type_group_mode": 0.26}
    for model, value in plan.items():
        assert f1[model] == pytest.approx(value, abs=0.03), model
