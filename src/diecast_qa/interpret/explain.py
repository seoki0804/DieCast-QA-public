"""해석용 모델과 SHAP 값 (5장 ⑦).

해석용 1단계 모델은 제품 유형마다 따로 학습한다. 두 유형은 설정값이 크게 달라(주조 압력 중앙값
1,052 vs 595) 한 모델로 부분 의존도를 그리면 서로의 범위를 섞게 된다. Class Weight 없이 학습해
예측 확률이 실제 불량률 단위가 되게 한다(PDP를 '불량 확률'로 읽기 위함). 순위 성능은 4단계
XGBoost와 같은 하이퍼파라미터로 비슷하다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property

import numpy as np
import pandas as pd
import shap
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from diecast_qa.config import CONTROL_VARS, PROCESS_COLS, SEED, SENSOR_COLS
from diecast_qa.modeling.estimators import pipeline

# 제품 유형 안에서 학습하므로 Product_Type은 뺀다
INTERP_FEATURES = (*PROCESS_COLS, *SENSOR_COLS, "Cavity", "Shot")


def interpretation_model(features: Sequence[str] = INTERP_FEATURES) -> Pipeline:
    return pipeline(list(features), XGBClassifier(
        n_estimators=300, learning_rate=0.05, max_depth=4, subsample=0.8, colsample_bytree=0.8,
        n_jobs=-1, random_state=SEED))  # fmt: skip


class TreeShap:
    """파이프라인(열 선택 → 결측 대체 → 트리 모델)의 마지막 모델을 TreeSHAP으로 설명한다.

    SHAP 값은 모델 출력 단위(XGBoost: log-odds, Random Forest: 확률)이고,
    결측 대체 뒤의 값을 설명한다.
    """

    def __init__(self, model: Pipeline) -> None:
        self.model = model
        self.explainer = shap.TreeExplainer(model[-1])

    def inputs(self, X: pd.DataFrame) -> pd.DataFrame:
        return self.model[:-1].transform(X)

    def values(self, X: pd.DataFrame) -> np.ndarray:
        """(행, 변수, 클래스). 이진 모델(XGBoost)은 불량 클래스 하나만 있다."""
        values = np.asarray(self.explainer.shap_values(self.inputs(X)))
        return values[..., np.newaxis] if values.ndim == 2 else values

    def base_values(self) -> np.ndarray:
        return np.atleast_1d(self.explainer.expected_value)


def importance_share(values: np.ndarray, features: Sequence[str]) -> pd.Series:
    """변수별 평균 |SHAP|을 합 1로 나눈 비중. values는 (행, 변수)."""
    share = np.abs(values).mean(axis=0)
    return pd.Series(share / share.sum(), index=list(features))


@dataclass
class ProductTypeModel:
    """제품 유형 하나의 해석용 모델과 학습 데이터."""

    product_type: int
    model: Pipeline
    X: pd.DataFrame
    y: np.ndarray

    @property
    def features(self) -> list[str]:
        return list(self.model[0].columns)

    def proba(self, X: pd.DataFrame | None = None) -> np.ndarray:
        return self.model.predict_proba(self.X if X is None else X)[:, 1]

    def reference(self) -> float:
        """평균 예측 불량 확률 (Class Weight가 없으므로 실제 불량률과 거의 같다)."""
        return float(self.proba().mean())

    @cached_property
    def explainer(self) -> TreeShap:
        return TreeShap(self.model)

    @cached_property
    def shap_values(self) -> np.ndarray:
        """(행, 변수) log-odds 단위 SHAP. 합 + shap_base = 예측 log-odds."""
        return self.explainer.values(self.X)[..., 0]

    @property
    def shap_base(self) -> float:
        return float(self.explainer.base_values()[0])

    def importance(self) -> pd.Series:
        return importance_share(self.shap_values, self.features).sort_values(ascending=False)

    def candidates(self, n: int, pool: Sequence[str] = CONTROL_VARS) -> list[str]:
        """관리 범위를 찾을 변수: 조정 가능한 변수 중 SHAP 중요도 상위 n개."""
        return [v for v in self.importance().index if v in pool][:n]

    def cv_auc(self, folds: int = 5) -> float:
        """shot 단위로 묶은 무작위 5-fold ROC-AUC (① 같은 기간 수준의 설명력 확인용)."""
        cv = GroupKFold(folds, shuffle=True, random_state=SEED)
        groups = self.X.index.get_level_values("order")
        p = cross_val_predict(self.model, self.X, self.y, cv=cv, groups=groups,
                              method="predict_proba")[:, 1]  # fmt: skip
        return float(roc_auc_score(self.y, p))


def fit_by_product_type(
    parts: pd.DataFrame, features: Sequence[str] = INTERP_FEATURES
) -> dict[int, ProductTypeModel]:
    """제품 유형마다 해석용 모델을 학습한다. X의 인덱스는 (order, Cavity)."""
    fitted = {}
    for ptype, g in parts.groupby("Product_Type"):
        X = g.set_index(["order", "Cavity"], drop=False)[list(features)].astype(float)
        y = g["defect"].to_numpy()
        fitted[int(ptype)] = ProductTypeModel(int(ptype), interpretation_model(features).fit(X, y),
                                              X, y)  # fmt: skip
    return fitted
