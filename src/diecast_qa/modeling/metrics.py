"""평가 지표 (6.4)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

CAPTURE_FRACS = (0.1, 0.2, 0.3)
METRIC_COLS = ("roc_auc", "pr_auc", *(f"capture_{int(f * 100)}" for f in CAPTURE_FRACS),
               "precision", "recall", "f1", "recall_at_05", "f1_at_05")  # fmt: skip


def inclusion_probability(score: np.ndarray, frac: float) -> np.ndarray:
    """위험 점수 상위 frac을 검사할 때 제품마다 검사 대상에 들어갈 확률.

    점수가 같은 제품이 검사 경계에 걸리면 남은 자리를 그 제품들이 똑같이 나눠 갖는다고 본다
    (무작위로 고를 때의 기대값). 규칙처럼 동점이 많은 점수도 공정하게 비교하기 위해서다.
    """
    score = np.asarray(score)
    k = frac * len(score)
    cut = np.sort(score)[::-1][int(np.ceil(k)) - 1]
    above, tied = score > cut, score == cut
    prob = above.astype(float)
    prob[tied] = (k - above.sum()) / tied.sum()
    return prob


def capture_rate(y: np.ndarray, score: np.ndarray, frac: float) -> float:
    """위험 점수 상위 frac을 검사했을 때 전체 불량 중 찾은 비율 (기대값)."""
    y = np.asarray(y)
    return float(inclusion_probability(score, frac) @ y / y.sum())


def best_f1_threshold(y: np.ndarray, score: np.ndarray) -> float:
    precision, recall, thresholds = precision_recall_curve(y, score)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)
    return float(thresholds[np.argmax(f1[:-1])])


def score_metrics(y: np.ndarray, score: np.ndarray, threshold: float = np.nan) -> dict:
    y, score = np.asarray(y), np.asarray(score)
    out = {
        "n": len(y),
        "defect_rate": y.mean(),
        "roc_auc": roc_auc_score(y, score),
        "pr_auc": average_precision_score(y, score),
        **{f"capture_{int(f * 100)}": capture_rate(y, score, f) for f in CAPTURE_FRACS},
        "recall_at_05": recall_score(y, score >= 0.5, zero_division=0),
        "f1_at_05": f1_score(y, score >= 0.5, zero_division=0),
    }
    # 임계값이 없는 경우(③)에도 항목은 같게 둔다: 실험마다 항목이 다르면 집계 표가 깨진다
    out |= dict.fromkeys(("precision", "recall", "f1"), np.nan)
    if not np.isnan(threshold):
        pred = score >= threshold
        out |= {
            "precision": precision_score(y, pred, zero_division=0),
            "recall": recall_score(y, pred, zero_division=0),
            "f1": f1_score(y, pred, zero_division=0),
        }
    return out


def fold_metrics(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """keys(예: design, model, ...)와 fold별 지표."""
    return predictions.groupby([*keys, "fold"]).apply(
        lambda g: pd.Series(score_metrics(g["y"], g["p_defect"], g["threshold"].iloc[0])),
        include_groups=False,
    )


def summarize(folds: pd.DataFrame, keys: list[str], metrics=METRIC_COLS) -> pd.DataFrame:
    """fold 지표의 평균과 표준편차 (6.4: 평균±표준편차 표기)."""
    cols = [c for c in metrics if c in folds.columns]
    stats = folds[cols].groupby(level=keys).agg(["mean", "std"])
    stats.columns = [f"{m}_{s}" for m, s in stats.columns]
    stats["folds"] = folds.groupby(level=keys).size()
    return stats


def pooled_metrics(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """fold를 합친 전체 평가 구간 하나로 계산한 지표 (③처럼 예측을 이어 붙인 경우)."""
    return predictions.groupby(keys).apply(
        lambda g: pd.Series(score_metrics(g["y"], g["p_defect"])), include_groups=False
    )
