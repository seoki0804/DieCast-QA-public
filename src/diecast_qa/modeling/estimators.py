"""1단계 모델 7종과 비교 기준 규칙 (6.1).

모델은 모두 '열 선택 → 결측 대체(학습 데이터 중앙값) → (표준화) → 분류기' 파이프라인이라
결측 대체·표준화가 학습 데이터에서만 계산된다 (3.2). 규칙도 같은 fit/predict_proba
인터페이스를 따르므로 모델과 똑같이 평가한다.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from imblearn.pipeline import Pipeline as ImbPipeline
from lightgbm import LGBMClassifier
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

from diecast_qa.config import SEED
from diecast_qa.modeling.features import FEATURE_SETS


class ColumnSelector(BaseEstimator, TransformerMixin):
    def __init__(self, columns: Sequence[str] = ()) -> None:
        self.columns = columns

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return X[list(self.columns)]

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.columns, dtype=object)


class BalancedXGBClassifier(XGBClassifier):
    """학습 데이터의 양품/불량 비율로 scale_pos_weight를 정하는 XGBoost (Class Weight 효과)."""

    def fit(self, X, y, **kwargs):
        y = np.asarray(y)
        self.set_params(scale_pos_weight=(len(y) - y.sum()) / max(y.sum(), 1))
        return super().fit(X, y, **kwargs)


def pipeline(columns: Sequence[str], classifier, scale: bool = False, sampler=None) -> Pipeline:
    """sampler(imbalanced-learn 형식)를 주면 학습할 때만 결측 대체 뒤에 적용한다 (8.1)."""
    steps = [("select", ColumnSelector(columns)), ("impute", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scale", StandardScaler()))
    if sampler is not None:
        steps.append(("sample", sampler))
        return ImbPipeline([*steps, ("clf", classifier)]).set_output(transform="pandas")
    return Pipeline([*steps, ("clf", classifier)]).set_output(transform="pandas")


class _Rule(BaseEstimator, ClassifierMixin):
    """학습이 거의 없는 비교 기준. predict_proba의 두 번째 열이 위험 점수다."""

    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.classes_ = np.array([0, 1])
        self.prior_ = float(np.mean(y))
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        s = self.score(X)
        return np.column_stack([1 - s, s])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.score(X) >= 0.5).astype(int)


class RandomRule(_Rule):
    """무작위 검사. 포착률의 기대값은 검사 비율과 같다."""

    def __init__(self, random_state: int = SEED) -> None:
        self.random_state = random_state

    def score(self, X):
        return np.random.default_rng(self.random_state).random(len(X))


class GroupRateRule(_Rule):
    """학습 데이터의 그룹별 불량률 순 (예: 캐비티별, 캐비티×제품 유형별)."""

    def __init__(self, by: Sequence[str] = ("Cavity",)) -> None:
        self.by = by

    def fit(self, X, y):
        super().fit(X, y)
        self.rates_ = pd.Series(np.asarray(y), index=X.index).groupby(
            [X[c] for c in self.by]
        ).mean()  # fmt: skip
        return self

    def score(self, X):
        keys = pd.MultiIndex.from_frame(X[list(self.by)]) if len(self.by) > 1 else X[self.by[0]]
        return self.rates_.reindex(keys).fillna(self.prior_).to_numpy(float)


class RecentRateRule(_Rule):
    """같은 구간·같은 캐비티의 직전 10 shot 불량률 순. 구간 첫 shot은 학습 데이터 불량률로 채운다.

    두 캐비티를 합친 불량률(hist_rate_10)보다 기획서 7.3·7.4의 규칙 수치와 맞는다.
    """

    def __init__(self, column: str = "hist_cav_rate_10") -> None:
        self.column = column

    def score(self, X):
        return X[self.column].fillna(self.prior_).to_numpy(float)


@dataclass(frozen=True)
class ModelSpec:
    """실험 한 줄: 모델·변수 묶음·학습 데이터 처리 방식."""

    name: str
    label: str
    factory: Callable[[list[str]], BaseEstimator]
    kind: str = "model"
    features: str = "base"
    # 학습 데이터 처리 (experiment.TRAIN_FILTERS·TRAIN_WEIGHTS의 이름). 비어 있으면 그대로
    train_filter: str = ""  # 행 고르기: drop_abnormal, drop_missing, window_500 …
    train_weight: str = ""  # 표본 가중치: halflife_200 …

    @property
    def variant(self) -> str:
        return "+".join(p for p in (self.train_filter, self.train_weight) if p)

    @property
    def key(self) -> str:
        return ":".join(p for p in (self.name, self.features, self.variant) if p)

    def build(self) -> BaseEstimator:
        return self.factory(FEATURE_SETS[self.features])

    def with_(self, **changes) -> ModelSpec:
        return replace(self, **changes)


def _forest(cls):
    return lambda cols: pipeline(cols, cls(n_estimators=300, class_weight="balanced",
                                           n_jobs=-1, random_state=SEED))  # fmt: skip


MODELS = {
    spec.name: spec
    for spec in (
        ModelSpec("logreg", "Logistic Regression", lambda cols: pipeline(
            cols, LogisticRegression(class_weight="balanced", max_iter=5000), scale=True)),
        ModelSpec("tree", "Decision Tree", lambda cols: pipeline(
            cols, DecisionTreeClassifier(max_depth=6, min_samples_leaf=20,
                                         class_weight="balanced", random_state=SEED))),
        ModelSpec("rf", "Random Forest", _forest(RandomForestClassifier)),
        ModelSpec("et", "Extra Trees", _forest(ExtraTreesClassifier)),
        ModelSpec("xgb", "XGBoost", lambda cols: pipeline(cols, BalancedXGBClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=4, subsample=0.8,
            colsample_bytree=0.8, n_jobs=-1, random_state=SEED))),
        ModelSpec("lgbm", "LightGBM", lambda cols: pipeline(cols, LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, class_weight="balanced", random_state=SEED, n_jobs=-1,
            verbose=-1))),
        ModelSpec("mlp", "MLP (64-32)", lambda cols: pipeline(
            cols, MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=1000, random_state=SEED),
            scale=True)),
    )
}  # fmt: skip

RULES = {
    spec.name: spec
    for spec in (
        ModelSpec("random", "규칙: 무작위", lambda _: RandomRule(), kind="rule"),
        ModelSpec("cavity_rate", "규칙: 캐비티별 불량률", lambda _: GroupRateRule(("Cavity",)),
                  kind="rule"),
        ModelSpec("cavity_type_rate", "규칙: 캐비티×제품 유형 불량률",
                  lambda _: GroupRateRule(("Cavity", "Product_Type")), kind="rule"),
        ModelSpec("recent_rate", "규칙: 최근 10 shot 불량률", lambda _: RecentRateRule(),
                  kind="rule"),
    )
}  # fmt: skip
