"""하이퍼파라미터 조정 (6.1): 학습 데이터 안에서 시간 순서를 지킨 교차검증.

평가 데이터는 조정에 쓰지 않는다 (3.2). 학습 데이터를 제품 유형마다 생산 순서로 n_inner+1개
구간으로 나누고, j번째 구간을 그 이전 구간 전체로 학습해 검증한다(확장 창). 점수는 ROC-AUC 평균.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import roc_auc_score

from diecast_qa.config import SEED
from diecast_qa.modeling.designs import Split
from diecast_qa.modeling.estimators import ModelSpec
from diecast_qa.modeling.experiment import Experiment, predict_score

optuna.logging.set_verbosity(optuna.logging.WARNING)

SearchSpace = Callable[[optuna.Trial], dict]


def _forest_space(t: optuna.Trial) -> dict:
    return {
        "clf__max_depth": t.suggest_categorical("max_depth", [None, 4, 8, 16]),
        "clf__min_samples_leaf": t.suggest_int("min_samples_leaf", 1, 100, log=True),
        "clf__max_features": t.suggest_float("max_features", 0.1, 1.0),
    }


SEARCH_SPACES: dict[str, SearchSpace] = {
    "logreg": lambda t: {"clf__C": t.suggest_float("C", 1e-3, 1e2, log=True)},
    "tree": lambda t: {
        "clf__max_depth": t.suggest_int("max_depth", 2, 12),
        "clf__min_samples_leaf": t.suggest_int("min_samples_leaf", 5, 300, log=True),
    },
    "rf": _forest_space,
    "et": _forest_space,
    "xgb": lambda t: {
        "clf__n_estimators": t.suggest_int("n_estimators", 100, 600, step=50),
        "clf__learning_rate": t.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "clf__max_depth": t.suggest_int("max_depth", 2, 8),
        "clf__min_child_weight": t.suggest_float("min_child_weight", 1, 50, log=True),
        "clf__subsample": t.suggest_float("subsample", 0.5, 1.0),
        "clf__colsample_bytree": t.suggest_float("colsample_bytree", 0.3, 1.0),
        "clf__reg_lambda": t.suggest_float("reg_lambda", 1e-3, 10, log=True),
    },
    "lgbm": lambda t: {
        "clf__n_estimators": t.suggest_int("n_estimators", 100, 600, step=50),
        "clf__learning_rate": t.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "clf__num_leaves": t.suggest_int("num_leaves", 4, 64, log=True),
        "clf__min_child_samples": t.suggest_int("min_child_samples", 5, 300, log=True),
        "clf__subsample": t.suggest_float("subsample", 0.5, 1.0),
        "clf__colsample_bytree": t.suggest_float("colsample_bytree", 0.3, 1.0),
        "clf__reg_lambda": t.suggest_float("reg_lambda", 1e-3, 10, log=True),
    },
}


class TimeOrderTuner:
    def __init__(self, n_trials: int = 20, n_inner: int = 3, seed: int = SEED) -> None:
        self.n_trials, self.n_inner, self.seed = n_trials, n_inner, seed

    def inner_splits(self, parts: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
        """parts(학습 데이터) 안의 확장 창 분할. 위치(iloc) 배열 쌍의 목록."""
        shots = parts.drop_duplicates("order")[["order", "Product_Type"]]
        position = shots.groupby("Product_Type").cumcount()
        size = shots.groupby("Product_Type")["order"].transform("size")
        block = (position * (self.n_inner + 1) // size).set_axis(shots["order"])
        row_block = parts["order"].map(block).to_numpy()
        return [(np.flatnonzero(row_block < j), np.flatnonzero(row_block == j))
                for j in range(1, self.n_inner + 1)]  # fmt: skip

    def tune(self, spec: ModelSpec, X: pd.DataFrame, y: pd.Series, parts: pd.DataFrame) -> dict:
        """최적 파라미터(파이프라인 set_params 형식)와 내부 점수를 돌려준다."""
        space = SEARCH_SPACES[spec.name]
        splits = self.inner_splits(parts)

        def objective(trial: optuna.Trial) -> float:
            params = space(trial)
            scores = []
            for fit_idx, val_idx in splits:
                model = spec.build().set_params(**params)
                model.fit(X.iloc[fit_idx], y.iloc[fit_idx])
                scores.append(roc_auc_score(y.iloc[val_idx], predict_score(model, X.iloc[val_idx])))
            return float(np.mean(scores))

        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=self.seed)
        )
        study.optimize(objective, n_trials=self.n_trials)
        return {"params": space(optuna.trial.FixedTrial(study.best_params)),
                "inner_auc": study.best_value}  # fmt: skip


class TunedExperiment(Experiment):
    """분할마다 학습 데이터 안에서 먼저 조정한 뒤, 고른 파라미터로 Experiment와 똑같이 평가한다."""

    def __init__(self, design, specs, tuner: TimeOrderTuner, label: str = "") -> None:
        super().__init__(design, specs, label)
        self.tuner = tuner
        self.chosen: list[dict] = []

    def _fit_predict(self, parts, X, y, split: Split, spec: ModelSpec) -> pd.DataFrame:
        train = split.train
        best = self.tuner.tune(spec, X.iloc[train], y.iloc[train], parts.iloc[train])
        self.chosen.append({"fold": split.fold, "model": spec.name, **best})
        params = best["params"]
        tuned = spec.with_(factory=lambda cols, f=spec.factory: f(cols).set_params(**params))
        return super()._fit_predict(parts, X, y, split, tuned).assign(variant="tuned")
