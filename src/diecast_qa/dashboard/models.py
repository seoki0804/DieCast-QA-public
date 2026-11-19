"""대시보드 모델: 1단계 불량 확률(Extra Trees)과 2단계 불량 유형(Random Forest).

1단계는 4단계 ③에서 가장 나은 Extra Trees다. 재생 구간 전체의 SHAP을 미리 계산하려고 잎 최소
크기를 5로 둔다(기본 1보다 TreeSHAP이 5배 빠르고 ② 순위 성능은 같다).

화면의 위험도는 모델 확률을 최근 실제 불량률 기준으로 옮긴 값이다(`prior_shift`). 모델은 Class
Weight(균형 가중)로 학습해 확률이 '불량 50%' 기준으로 나오므로, 승산(odds)에 최근 불량률의 승산을
곱하면 그 불량률 기준 확률이 된다(사전확률 이동, Saerens 외 2002). 따로 맞추는 보정 모델이 없어
재학습 직후에도 바로 쓰고, 시기가 바뀌면 최근 불량률을 따라 수준이 바뀐다. 예전에는 학습 데이터 뒤
20%에 Isotonic을 맞췄는데, 계단 모양이라 시기가 바뀌면 위험도가 몇 개 값(0%·100% 포함)에 붙고 순위
정보를 잃었다(재생 평균 AUC 0.54, 지금 방식 0.64).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import shap
from joblib import Parallel, delayed
from scipy.special import expit, logit

from diecast_qa.modeling.estimators import MODELS
from diecast_qa.modeling.features import FEATURE_SETS
from diecast_qa.modeling.type_models import TYPE_CLASSES, TYPE_CODE, TYPE_MODELS, type_proba

FEATURES = FEATURE_SETS["base"]
EPS = 1e-4


def stage1_model():
    model = MODELS["et"].build()
    return model.set_params(clf__min_samples_leaf=5)


def prior_shift(raw, rate):
    """균형 가중 모델 확률(불량 50% 기준) → 불량률 rate 기준 확률.

    logit⁻¹(logit(raw) + logit(rate)): 승산에 rate의 승산을 곱한다. raw=0.5면 rate 그대로다.
    """
    raw = np.clip(np.asarray(raw, float), EPS, 1 - EPS)
    rate = np.clip(np.asarray(rate, float), EPS, 1 - EPS)
    return expit(logit(raw) + logit(rate))


class DashboardModel:
    """재생 시작(또는 재학습) 시점 이전 데이터로 학습한 1·2단계 모델."""

    def fit(self, train: pd.DataFrame) -> DashboardModel:
        train = train.sort_values(["order", "Cavity"])
        self.stage1_ = stage1_model().fit(train, train["defect"])
        bad = train[train["defect"] == 1]
        self.stage2_ = TYPE_MODELS["rf"].build().fit(bad, bad["type5"].map(TYPE_CODE))
        self.prior_ = float(train["defect"].mean())
        self.trained_until_ = int(train["order"].max())
        self.n_train_ = len(train)
        return self

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        """p_raw: 모델 확률(불량 50% 기준), type_*: 불량 유형 확률(5개).

        화면의 위험도는 p_raw를 `prior_shift`로 그 시점 불량률 기준으로 옮겨 만든다(builder).
        """
        raw = self.stage1_.predict_proba(frame)[:, 1]
        types = type_proba(self.stage2_, frame)
        out = pd.DataFrame({"p_raw": raw}, index=frame.index)
        for k, code in enumerate(TYPE_CLASSES):
            out[f"type_{code}"] = types[:, k]
        return out

    def importance(self) -> pd.Series:
        """불순도 기반 변수 중요도(합 1). 재학습 시나리오에서 SHAP 대신 보여 준다."""
        clf = self.stage1_[-1]
        return pd.Series(clf.feature_importances_, index=FEATURES).sort_values(ascending=False)

    def explain(self, frame: pd.DataFrame, top: int = 6, n_jobs: int = -1) -> list[list]:
        """제품마다 |SHAP| 상위 top개 [변수, 값, SHAP(확률 단위)].

        TreeSHAP을 행 묶음으로 나눠 병렬 계산한다.
        """
        X = self.stage1_[:-1].transform(frame)
        chunks = np.array_split(np.arange(len(X)), max(1, min(len(X), os.cpu_count() or 1)))
        clf = self.stage1_[-1]

        def run(idx: np.ndarray) -> np.ndarray:
            values = np.asarray(shap.TreeExplainer(clf).shap_values(X.iloc[idx]))
            return values[..., 1] if values.ndim == 3 else values

        values = np.vstack(Parallel(n_jobs=n_jobs)(delayed(run)(c) for c in chunks if len(c)))
        rows = []
        for i, row in enumerate(values):
            order = np.argsort(-np.abs(row))[:top]
            rows.append([[FEATURES[j], float(X.iat[i, j]), float(row[j])] for j in order])
        return rows
