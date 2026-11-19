"""2단계 불량 유형 분류 모델과 비교 기준 (6.2).

유형은 DEFECT_GROUPS 순서의 정수 코드(0~4)로 학습한다. 학습 fold에 없는 유형이 있어도
predict_proba는 항상 5개 유형 열을 갖도록 type_proba로 맞춘다.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from diecast_qa.config import DEFECT_GROUPS, SEED
from diecast_qa.modeling.estimators import ModelSpec, pipeline

TYPE_CLASSES = tuple(g.code for g in DEFECT_GROUPS)
TYPE_CODE = {code: i for i, code in enumerate(TYPE_CLASSES)}


class BalancedTypeXGBClassifier(XGBClassifier):
    """유형 빈도의 역수로 가중한 XGBoost. 학습 fold에 없는 유형이 있어도 학습되도록
    있는 유형만 0..k-1로 다시 번호를 매기고, 원래 코드는 labels_에 둔다."""

    def fit(self, X, y, **kwargs):
        self.labels_, encoded = np.unique(np.asarray(y), return_inverse=True)
        return super().fit(X, encoded, sample_weight=compute_sample_weight("balanced", encoded),
                           **kwargs)  # fmt: skip


class TypeDistributionRule(BaseEstimator, ClassifierMixin):
    """학습 데이터의 유형 분포를 그대로 확률로 쓰는 비교 기준.

    by가 비어 있으면 '가장 흔한 유형', by=(Product_Type, Cavity)면
    '제품 유형·캐비티별 최다 유형'이다. 처음 보는 그룹은 전체 분포를 쓴다.
    """

    def __init__(self, by: Sequence[str] = ()) -> None:
        self.by = by

    def fit(self, X: pd.DataFrame, y):
        y = pd.Series(np.asarray(y), index=X.index)
        self.classes_ = np.arange(len(TYPE_CLASSES))
        self.overall_ = y.value_counts(normalize=True).reindex(self.classes_, fill_value=0.0)
        if self.by:
            counts = pd.crosstab([X[c] for c in self.by], y).reindex(
                columns=self.classes_, fill_value=0)  # fmt: skip
            self.groups_ = counts.div(counts.sum(axis=1), axis=0)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        proba = np.tile(self.overall_.to_numpy(), (len(X), 1))
        if self.by:
            keys = pd.MultiIndex.from_frame(X[list(self.by)])
            found = self.groups_.reindex(keys)
            known = found.notna().all(axis=1).to_numpy()
            proba[known] = found.to_numpy()[known]
        return proba

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.predict_proba(X).argmax(axis=1)


def type_proba(model, X: pd.DataFrame) -> np.ndarray:
    """(행 수, 5) 유형 확률. 모델이 학습하지 못한 유형의 열은 0이다."""
    clf = model[-1] if isinstance(model, Pipeline) else model
    classes = getattr(clf, "labels_", clf.classes_)
    full = np.zeros((len(X), len(TYPE_CLASSES)))
    full[:, classes] = model.predict_proba(X)
    return full


def _forest(cls):
    return lambda cols: pipeline(cols, cls(n_estimators=300, class_weight="balanced",
                                           n_jobs=-1, random_state=SEED))  # fmt: skip


TYPE_MODELS = {
    spec.name: spec
    for spec in (
        ModelSpec("logreg", "Multinomial Logistic Regression", lambda cols: pipeline(
            cols, LogisticRegression(class_weight="balanced", max_iter=5000), scale=True)),
        ModelSpec("rf", "Random Forest", _forest(RandomForestClassifier)),
        ModelSpec("et", "Extra Trees", _forest(ExtraTreesClassifier)),
        ModelSpec("xgb", "XGBoost", lambda cols: pipeline(cols, BalancedTypeXGBClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=4, subsample=0.8,
            colsample_bytree=0.8, n_jobs=-1, random_state=SEED))),
    )
}  # fmt: skip

TYPE_RULES = {
    spec.name: spec
    for spec in (
        ModelSpec("type_mode", "기준: 가장 흔한 유형", lambda _: TypeDistributionRule(),
                  kind="rule"),
        ModelSpec("type_group_mode", "기준: 제품 유형·캐비티별 최다 유형",
                  lambda _: TypeDistributionRule(("Product_Type", "Cavity")), kind="rule"),
    )
}  # fmt: skip
