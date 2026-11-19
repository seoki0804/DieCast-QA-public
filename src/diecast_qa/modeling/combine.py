"""규칙과 모델 점수 결합 (8.3). 둘 다 fit/predict_proba를 따르는 추정기를 받는다."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import logit
from scipy.stats import rankdata
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.linear_model import LogisticRegression

from diecast_qa.modeling.designs import recent_split


def _score(model, X: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


class RankAverage(BaseEstimator, ClassifierMixin):
    """모델 점수와 규칙 점수를 각각 0~1 순위로 바꿔 weight : (1-weight)로 평균한다.

    순위는 한 번에 예측하는 묶음(평가 블록·재학습 묶음) 안에서 매긴다. 점수 크기가 다른 두
    점수를 섞을 때 한쪽이 지배하지 않게 하기 위해서다.
    """

    def __init__(self, model, rule, weight: float = 0.5) -> None:
        self.model, self.rule, self.weight = model, rule, weight

    def fit(self, X: pd.DataFrame, y):
        self.model_ = clone(self.model).fit(X, y)
        self.rule_ = clone(self.rule).fit(X, y)
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        n = len(X)
        a = rankdata(_score(self.model_, X)) / n
        b = rankdata(_score(self.rule_, X)) / n
        s = self.weight * a + (1 - self.weight) * b
        return np.column_stack([1 - s, s])


class StackedRule(BaseEstimator, ClassifierMixin):
    """학습 데이터의 최근 share 구간(제품 유형별)에서 [logit(모델 점수), 규칙 점수] → 불량
    로지스틱 회귀를 학습한다. 이때 모델은 그 앞부분으로만 학습해 점수를 만든다(평가 데이터는
    쓰지 않는다). 최종 모델과 규칙은 학습 데이터 전체로 다시 학습한다. 최근 구간에 불량이 한
    종류뿐이면 순위 평균으로 대신한다."""

    def __init__(self, model, rule, share: float = 0.2) -> None:
        self.model, self.rule, self.share = model, rule, share

    def fit(self, X: pd.DataFrame, y):
        y = pd.Series(np.asarray(y), index=X.index)
        fit_idx, val_idx = recent_split(X, np.arange(len(X)), self.share)
        self.stack_ = None
        if y.iloc[val_idx].nunique() == 2 and y.iloc[fit_idx].nunique() == 2:
            model = clone(self.model).fit(X.iloc[fit_idx], y.iloc[fit_idx])
            rule = clone(self.rule).fit(X.iloc[fit_idx], y.iloc[fit_idx])
            Z = self._features(model, rule, X.iloc[val_idx])
            self.stack_ = LogisticRegression().fit(Z, y.iloc[val_idx])
        self.fallback_ = RankAverage(self.model, self.rule).fit(X, y)
        self.model_, self.rule_ = self.fallback_.model_, self.fallback_.rule_
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.stack_ is None:
            return self.fallback_.predict_proba(X)
        return self.stack_.predict_proba(self._features(self.model_, self.rule_, X))

    @staticmethod
    def _features(model, rule, X: pd.DataFrame) -> np.ndarray:
        p = np.clip(_score(model, X), 1e-4, 1 - 1e-4)
        return np.column_stack([logit(p), _score(rule, X)])
