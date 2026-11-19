"""2단계 유형 분류 실험, 유형 지표, 1·2단계 연결 평가 (6.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_recall_fscore_support,
)

from diecast_qa.config import NORMAL
from diecast_qa.modeling.designs import Split
from diecast_qa.modeling.estimators import ModelSpec
from diecast_qa.modeling.experiment import ID_COLS, Experiment
from diecast_qa.modeling.metrics import CAPTURE_FRACS, inclusion_probability
from diecast_qa.modeling.type_models import TYPE_CLASSES, TYPE_CODE, type_proba

P_TYPE_COLS = [f"p_type_{c}" for c in TYPE_CLASSES]
TYPE_METRIC_COLS = ("accuracy", "macro_f1", "balanced_accuracy")


class TypeExperiment(Experiment):
    """분할은 1단계와 같게 쓰되, 학습 데이터에서 불량 제품만 골라 유형을 학습한다.

    평가 데이터는 양품을 포함한 모든 제품에 유형 확률을 낸다. 운영에서는 1단계가 검사 대상으로
    고른 제품에 예상 유형을 붙이므로, 1단계 예측과 같은 fold에서 바로 연결 평가를 할 수 있다.
    유형 지표는 실제 불량 제품에서만 계산한다.
    """

    @staticmethod
    def target(parts: pd.DataFrame) -> pd.Series:
        return parts["type5"].map(TYPE_CODE)  # 양품은 NaN

    def _fit_predict(self, parts, X, y, split: Split, spec: ModelSpec) -> pd.DataFrame:
        train = split.train[parts["defect"].to_numpy()[split.train] == 1]
        model = spec.build().fit(X.iloc[train], y.iloc[train].astype(int))
        test = split.test
        proba = type_proba(model, X.iloc[test])
        out = parts.iloc[test][ID_COLS].assign(
            design=self.label, fold=split.fold, chunk=split.chunk, model=spec.name,
            y_type=parts["type5"].iloc[test].to_numpy(),
            pred_type=np.asarray(TYPE_CLASSES)[proba.argmax(axis=1)],
        )  # fmt: skip
        out[P_TYPE_COLS] = proba
        return out


def type_scores(y_true, y_pred) -> dict:
    return {
        "n": len(y_true),
        "accuracy": accuracy_score(y_true, y_pred),
        # 평가 구간에 없는 유형은 빼고 평균한다(sklearn 기본). 기획서 7.6 예비 실험과 같은 방식
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
    }


def defective(predictions: pd.DataFrame) -> pd.DataFrame:
    return predictions[predictions["y_type"] != NORMAL]


def type_fold_metrics(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return (
        defective(predictions)
        .groupby([*keys, "fold"])
        .apply(lambda g: pd.Series(type_scores(g["y_type"], g["pred_type"])), include_groups=False)
    )


def type_pooled_metrics(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return (
        defective(predictions)
        .groupby(keys)
        .apply(lambda g: pd.Series(type_scores(g["y_type"], g["pred_type"])), include_groups=False)
    )


def per_class_scores(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """유형별 precision·recall·F1. 행: keys + 유형.

    precision·recall·f1·support는 fold를 합쳐 계산한다. f1_fold_mean은 fold마다 계산해 평균한
    값으로, 그 유형이 실제나 예측에 나온 fold만 평균한다(기획서 7.6 예비 실험과 비교용).
    """

    def scores(g: pd.DataFrame) -> pd.DataFrame:
        p, r, f, n = precision_recall_fscore_support(
            g["y_type"], g["pred_type"], labels=list(TYPE_CLASSES), zero_division=0
        )
        by_fold = []
        for _, fold in g.groupby("fold"):
            present = set(fold["y_type"]) | set(fold["pred_type"])
            f1 = f1_score(fold["y_type"], fold["pred_type"], labels=list(TYPE_CLASSES),
                          average=None, zero_division=0)  # fmt: skip
            pairs = zip(TYPE_CLASSES, f1, strict=True)
            by_fold.append([v if c in present else np.nan for c, v in pairs])
        return pd.DataFrame(
            {"precision": p, "recall": r, "f1": f, "support": n,
             "f1_fold_mean": np.nanmean(by_fold, axis=0)},
            index=pd.Index(TYPE_CLASSES, name="type"),
        )  # fmt: skip

    return defective(predictions).groupby(keys).apply(scores, include_groups=False)


def confusion(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """실제 유형 × 예측 유형 건수 (fold 합산). 행: keys + 실제 유형, 열: 예측 유형."""
    d = defective(predictions)
    table = pd.crosstab([*(d[k] for k in keys), d["y_type"]], d["pred_type"])
    return table.reindex(columns=list(TYPE_CLASSES), fill_value=0)


def joint_capture(stage1: pd.DataFrame, stage2: pd.DataFrame, fracs=CAPTURE_FRACS) -> pd.DataFrame:
    """1·2단계 연결 평가 (6.2). 1단계 위험도 상위 frac을 검사할 때, fold마다

    capture: 전체 불량 중 검사 대상에 든 비율, type_hit: 그중 유형까지 맞힌 비율,
    end_to_end: 전체 불량 중 검사 대상에 들고 유형까지 맞힌 비율. 결과는 fold 평균.
    stage1: predictions.csv 형식(design, fold, order, Cavity, model, p_defect, y)
    stage2: TypeExperiment 결과(design, fold, order, Cavity, model, y_type, pred_type)
    """
    on = ["design", "fold", "order", "Cavity"]
    s1 = stage1[[*on, "model", "p_defect", "y"]].rename(columns={"model": "stage1_model"})
    s2 = stage2[[*on, "model", "y_type", "pred_type"]].rename(columns={"model": "stage2_model"})
    merged = s1.merge(s2, on=on)
    merged["correct"] = (merged["y_type"] == merged["pred_type"]).astype(float)

    rows = []
    keys = ["design", "stage1_model", "stage2_model", "fold"]
    for key, g in merged.groupby(keys):
        defect = g["y"].to_numpy(float)
        for frac in fracs:
            found = inclusion_probability(g["p_defect"].to_numpy(), frac) * defect
            hit = found @ g["correct"].to_numpy()
            rows.append(dict(zip(keys, key, strict=True)) | {
                "frac": frac, "capture": found.sum() / defect.sum(),
                "type_hit": hit / found.sum(), "end_to_end": hit / defect.sum(),
            })  # fmt: skip
    folds = pd.DataFrame(rows)
    return folds.groupby(["design", "stage1_model", "stage2_model", "frac"])[
        ["capture", "type_hit", "end_to_end"]
    ].mean()
