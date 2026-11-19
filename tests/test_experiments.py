"""6단계 추가 실험의 구성 요소: 합성 생성기, 재학습 시점, 학습 가중치, 점수 결합, 분포 변화,
시간 정보 학습(구간 기준 편차, 시기 표시 변수 제외, 공변량 이동 가중치)."""

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from diecast_qa.experiments.drift import psi
from diecast_qa.features import RunRelativeFeatures
from diecast_qa.modeling import TimeOrderDesign
from diecast_qa.modeling.augment import (
    AdaptiveSMOTE,
    GaussianCopulaSampler,
    NoiseJitter,
    Snapped,
)
from diecast_qa.modeling.combine import RankAverage, StackedRule
from diecast_qa.modeling.estimators import RecentRateRule, pipeline
from diecast_qa.modeling.experiment import TRAIN_FILTERS, TRAIN_WEIGHTS
from diecast_qa.modeling.retraining import AlarmRetrainDesign, ChartAlarmTrigger
from diecast_qa.modeling.temporal import RunInvariantSelector, covariate_shift_weights
from diecast_qa.spc.charts import CUSUMChart


@pytest.fixture(scope="module")
def parts(result):
    return result.parts


@pytest.fixture
def toy():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=100), "b": rng.integers(0, 5, 100).astype(float),
                      "c": np.ones(100)})  # fmt: skip
    y = np.r_[np.zeros(80), np.ones(20)]
    return X, y


@pytest.mark.parametrize(
    "sampler", [NoiseJitter(), GaussianCopulaSampler(), Snapped(GaussianCopulaSampler())]
)
def test_balancers_fill_minority_only(toy, sampler):
    X, y = toy
    Xs, ys = sampler.fit_resample(X, y)
    assert (ys == 1).sum() == (ys == 0).sum() == 80
    pd.testing.assert_frame_equal(Xs.iloc[:100], X)  # 원래 행은 그대로 앞에 둔다
    new = Xs.iloc[100:]
    assert (new["c"] == 1).all()  # 값이 하나뿐인 열은 그대로


def test_copula_stays_within_observed_range_and_snap_uses_real_values(toy):
    X, y = toy
    minority = X[y == 1]
    new = GaussianCopulaSampler().fit_resample(X, y)[0].iloc[100:]
    assert new["a"].between(minority["a"].min(), minority["a"].max()).all()
    snapped = Snapped(GaussianCopulaSampler()).fit_resample(X, y)[0].iloc[100:]
    assert set(snapped["a"]) <= set(minority["a"])


def test_noise_jitter_touches_only_given_columns(toy):
    X, y = toy
    new = NoiseJitter(columns=("a",)).fit_resample(X, y)[0].iloc[100:]
    assert set(new["b"]) <= set(X.loc[y == 1, "b"])  # b는 실제 값 그대로 복제
    assert not set(new["a"]) <= set(X.loc[y == 1, "a"])


def test_adaptive_smote_handles_tiny_classes():
    X = pd.DataFrame({"a": np.arange(30.0)})
    y = np.r_[np.zeros(25), np.ones(3), np.full(2, 2)]
    _, ys = AdaptiveSMOTE().fit_resample(X, y)
    assert pd.Series(ys).value_counts().nunique() == 1


def test_sampler_applies_only_when_fitting(toy):
    X, y = toy
    model = pipeline(list(X.columns), RandomForestClassifier(20, random_state=0),
                     sampler=NoiseJitter()).fit(X, y)  # fmt: skip
    assert model.predict_proba(X).shape == (100, 2)


def test_alarm_retrain_design_uses_only_past_data(parts):
    trigger = ChartAlarmTrigger(
        lambda: [CUSUMChart("defect_rate", k=0.25, h=8.0, sigma_method="binomial")], lag=1
    )
    splits = list(AlarmRetrainDesign(trigger).splits(parts))
    order = parts["order"]
    for s in splits:
        assert order.iloc[s.train].max() < order.iloc[s.test].min()
    covered = np.concatenate([s.test for s in splits])
    blocks = TimeOrderDesign().blocks(parts)
    assert sorted(covered) == list(np.flatnonzero(blocks >= 2))


def test_recency_filters_and_weights():
    train = pd.DataFrame({"order": np.arange(1000)})
    assert TRAIN_FILTERS["window_500"](train).sum() == 500
    w = TRAIN_WEIGHTS["halflife_200"](train)
    assert w[-1] == pytest.approx(1.0)
    assert w[-201] == pytest.approx(0.5)


def test_rank_average_and_stacking(parts):
    data = parts[parts["run"].isin([1, 2])].reset_index(drop=True)
    X, y = data.drop(columns=["defect", "type5"]), data["defect"]
    model = RandomForestClassifier(30, random_state=0)
    cols = ["Casting_Pressure", "Cavity"]
    combined = RankAverage(pipeline(cols, model), RecentRateRule()).fit(X, y)
    score = combined.predict_proba(X)[:, 1]
    assert score.min() > 0 and score.max() <= 1
    stacked = StackedRule(pipeline(cols, model), RecentRateRule()).fit(X, y)
    assert stacked.stack_ is not None
    assert stacked.predict_proba(X).shape == (len(X), 2)


def test_psi_detects_shift():
    rng = np.random.default_rng(0)
    a = rng.normal(size=2000)
    assert psi(a, rng.normal(size=2000)) < 0.05
    assert psi(a, rng.normal(1, 1, 2000)) > 0.25


def test_run_relative_features_use_only_past_shots_in_the_same_run(parts):
    out = RunRelativeFeatures(("Casting_Pressure",)).transform(parts.head(400))
    first = out.groupby(["run", "Cavity"]).head(1)
    assert first["Casting_Pressure__rel"].isna().all()  # 구간 첫 shot은 비교할 과거가 없다
    g = out[(out["run"] == out["run"].iloc[0]) & (out["Cavity"] == 1)]
    k = 10  # 11번째 shot = 자기 값 - 앞 10개 shot의 중앙값
    expected = g["Casting_Pressure"].iloc[k] - g["Casting_Pressure"].iloc[:k].median()
    assert np.isclose(g["Casting_Pressure__rel"].iloc[k], expected)


def test_invariant_selector_drops_run_level_variables():
    rng = np.random.default_rng(0)
    run = np.repeat([1, 2, 3, 4], 50)
    X = pd.DataFrame({"run": run, "Product_Type": 1, "Cavity": np.tile([1, 2], 100),
                      "marker": run * 10 + rng.normal(0, 0.1, 200),  # 구간마다 수준이 다름
                      "signal": rng.normal(0, 1, 200)})  # fmt: skip
    selector = RunInvariantSelector(0.5).fit(X)
    assert selector.dropped_ == ["marker"]
    assert list(selector.transform(X).columns) == ["Product_Type", "Cavity", "signal"]


def test_covariate_shift_weights_favor_rows_like_the_recent_past(parts):
    train = parts[parts["run"].isin([1, 2])]
    w = covariate_shift_weights(train)
    assert np.isclose(w.mean(), 1) and w.min() > 0
    recent = train["order"] >= np.sort(train["order"].unique())[int(train["order"].nunique() * 0.8)]
    assert w[recent.to_numpy()].mean() > w[~recent.to_numpy()].mean()
    assert TRAIN_WEIGHTS["shift_weight"] is covariate_shift_weights
