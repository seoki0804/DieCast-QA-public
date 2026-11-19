"""4단계 1단계 모델: 검증 분할의 누수 방지, 지표, 규칙, 기획서 7장 재현."""

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin

from diecast_qa.modeling import (
    LABEL_COLS,
    MODELS,
    RULES,
    Experiment,
    ModelSpec,
    RetrainDesign,
    SameTermDesign,
    TimeOrderDesign,
)
from diecast_qa.modeling.estimators import GroupRateRule, RecentRateRule
from diecast_qa.modeling.metrics import (
    best_f1_threshold,
    capture_rate,
    fold_metrics,
    summarize,
)


@pytest.fixture(scope="module")
def parts(result):
    return result.parts


def test_same_term_keeps_shot_together(parts):
    for split in SameTermDesign(n_repeats=2).splits(parts):
        train, test = set(parts["order"].iloc[split.train]), set(parts["order"].iloc[split.test])
        assert not train & test
        assert len(test) / parts["order"].nunique() == pytest.approx(0.2, abs=0.01)
        assert set(split.inner_train) | set(split.inner_val) == set(split.train)


def test_time_order_blocks_and_folds(parts):
    design = TimeOrderDesign()
    blocks = design.blocks(parts)
    sizes = parts.drop_duplicates("order").groupby(["Product_Type", blocks.loc[
        parts.drop_duplicates("order").index]]).size()  # fmt: skip
    assert sizes.groupby(level=0).agg(lambda s: s.max() - s.min()).max() <= 1

    splits = list(design.splits(parts))
    assert [s.fold for s in splits] == [2, 3, 4, 5]
    for s in splits:
        assert (blocks.iloc[s.train] < s.fold).all()
        assert (blocks.iloc[s.test] == s.fold).all()
        # 내부 검증 구간은 유형마다 학습 데이터의 가장 최근 부분이다
        fit, val = parts.iloc[s.inner_train], parts.iloc[s.inner_val]
        for ptype in (1, 2):
            assert fit.loc[fit["Product_Type"] == ptype, "order"].max() < val.loc[
                val["Product_Type"] == ptype, "order"].min()  # fmt: skip


def test_retrain_trains_only_on_the_past(parts):
    design = RetrainDesign(every=500)
    tested = []
    for s in design.splits(parts):
        test_orders = parts["order"].iloc[s.test]
        assert parts["order"].iloc[s.train].max() < test_orders.min()
        assert test_orders.nunique() <= 500
        tested.append(s.test)
    blocks = TimeOrderDesign().blocks(parts)
    assert set(np.concatenate(tested)) == set(np.flatnonzero(blocks >= 2))


def test_capture_rate_handles_ties():
    y = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    assert capture_rate(y, np.linspace(1, 0, 10), 0.1) == 0.5
    assert capture_rate(y, np.ones(10), 0.2) == pytest.approx(0.2)  # 전부 동점이면 무작위와 같다
    assert capture_rate(y, np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0.0]), 0.2) == 1.0


def test_best_f1_threshold_separates_perfect_scores():
    y = np.array([0, 0, 1, 1])
    assert best_f1_threshold(y, np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(0.8)


class _Spy(BaseEstimator, ClassifierMixin):
    seen: list = []

    def fit(self, X, y):
        _Spy.seen.append(set(X.columns))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        return np.full((len(X), 2), 0.5)


def test_experiment_never_passes_labels(parts):
    spec = ModelSpec("spy", "spy", lambda _: _Spy())
    Experiment(TimeOrderDesign(), [spec]).run(parts)
    assert _Spy.seen
    assert all(not cols & set(LABEL_COLS) for cols in _Spy.seen)


def test_imputer_uses_training_median(parts):
    train = parts[parts["run"] <= 2]
    model = MODELS["rf"].build().fit(train.drop(columns=list(LABEL_COLS)), train["defect"])
    imputer = model.named_steps["impute"]
    stats = dict(zip(imputer.feature_names_in_, imputer.statistics_, strict=True))
    assert stats["Factory_Temp"] == pytest.approx(train["Factory_Temp"].median())


def test_rules():
    X = pd.DataFrame({"Cavity": [1, 1, 2, 2], "Product_Type": [1, 1, 1, 1],
                      "hist_cav_rate_10": [0.3, np.nan, 0.1, 0.0]})  # fmt: skip
    y = pd.Series([1, 0, 0, 0])
    assert GroupRateRule(("Cavity",)).fit(X, y).score(X).tolist() == [0.5, 0.5, 0, 0]
    assert RecentRateRule().fit(X, y).score(X).tolist() == [0.3, 0.25, 0.1, 0.0]


def test_time_order_reproduces_plan(parts):
    """기획서 7.1·7.3의 ② 시간 순서 수치 (ROC-AUC 평균)."""
    specs = [MODELS["rf"], RULES["cavity_rate"], RULES["recent_rate"]]
    pred = Experiment(TimeOrderDesign(), specs).run(parts)
    auc = summarize(fold_metrics(pred, ["model"]), ["model"])["roc_auc_mean"]
    assert auc["rf"] == pytest.approx(0.59, abs=0.02)
    assert auc["cavity_rate"] == pytest.approx(0.60, abs=0.02)
    assert auc["recent_rate"] == pytest.approx(0.69, abs=0.02)


def test_tuner_inner_splits_are_expanding_and_time_ordered(parts):
    from diecast_qa.modeling.tuning import TimeOrderTuner

    train = parts.iloc[next(TimeOrderDesign().splits(parts)).train].reset_index(drop=True)
    splits = TimeOrderTuner(n_inner=3).inner_splits(train)
    sizes = [len(fit) for fit, _ in splits]
    assert sizes == sorted(sizes)
    for fit, val in splits:
        for ptype in (1, 2):
            f, v = train.iloc[fit], train.iloc[val]
            assert f.loc[f["Product_Type"] == ptype, "order"].max() < v.loc[
                v["Product_Type"] == ptype, "order"].min()  # fmt: skip


def test_fold_metrics_mixes_runs_with_and_without_threshold():
    rng = np.random.default_rng(0)
    pred = pd.DataFrame({
        "model": ["a"] * 40 + ["b"] * 40, "fold": [1] * 80,
        "y": np.tile([0, 1, 0, 0], 20), "p_defect": rng.random(80),
        "threshold": [0.5] * 40 + [np.nan] * 40,
    })  # fmt: skip
    folds = fold_metrics(pred, ["model"])
    assert isinstance(folds, pd.DataFrame)
    assert np.isnan(folds.loc[("b", 1), "f1"])
    assert not np.isnan(folds.loc[("a", 1), "f1"])
