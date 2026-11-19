"""분석 요약 화면(정적)과 메타 정보: 2~9단계 결과 파일에서 대시보드에 필요한 부분만 모은다."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from diecast_qa.config import (
    CONTROL_VARS,
    DEFECT_GROUPS,
    TYPE5_LABELS,
    VARIABLE_LABELS,
)
from diecast_qa.dashboard.builder import PROCESS_VARS
from diecast_qa.dashboard.scenarios import RETRAIN_LABELS, SCENARIOS
from diecast_qa.inspection.analyses import STRATEGY_LABELS
from diecast_qa.inspection.costs import COST_RATIOS


def _records(frame: pd.DataFrame) -> list[dict]:
    """JSON용: NaN → None, numpy 값 → 파이썬 값."""
    clean = frame.replace({np.nan: None})
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
            for row in clean.to_dict(orient="records")]  # fmt: skip


class SummaryBuilder:
    def __init__(self, results_dir: Path) -> None:
        self.dir = results_dir

    def _csv(self, *path: str, **kwargs) -> pd.DataFrame:
        return pd.read_csv(self.dir.joinpath(*path), **kwargs)

    def meta(self) -> dict:
        ocap = self._csv("improve", "alarms_ocap.csv")
        return {
            "scenarios": [{"id": s.id, "label": s.label, "product_type": s.product_type,
                           "start_run": s.start_run, "retrain": s.retrain} for s in SCENARIOS],
            "retrain_labels": RETRAIN_LABELS,
            "variables": [{"name": v, "label": VARIABLE_LABELS[v],
                           "group": "controllable" if v in CONTROL_VARS else "context"}
                          for v in (*PROCESS_VARS, "Cavity", "Shot", "Product_Type")],
            "defect_types": [{"code": g.code, "label": g.label} for g in DEFECT_GROUPS],
            "type_labels": TYPE5_LABELS,
            "cost_ratios": list(COST_RATIOS),
            "default_ratio": 10,
            "ocap": _records(ocap),
            "assumptions": [
                "재생은 과거 데이터로 운영을 재현한다. 검사하지 않은 제품의 결과도 안다고 "
                "가정한다(데이터가 전수검사 결과). 실제 선별검사에서는 무작위 감사 검사로 "
                "결과를 모아야 한다",
                "모델은 시작(또는 재학습) 시점 이전 데이터로만 학습했다",
                "비용 단가는 가정값이다. 검사 비용 1, 미검 비용 = 비용 비율",
            ],
        }  # fmt: skip

    def summary(self) -> dict:
        pareto = self._csv("eda", "pareto_groups.csv")
        pareto["label"] = pareto["type5"].map(TYPE5_LABELS)
        ranges = self._csv("interpret", "ranges_proposals.csv")
        checklist = self._csv("interpret", "checklist_items.csv")
        best = self._csv("cost", "cost_best.csv")
        best["label"] = best["best"].map(STRATEGY_LABELS)
        cost = self._csv("cost", "cost_summary.csv")
        cost = cost[cost["strategy"].isin(["full", "none", "model", "rule", "switching",
                                           "sampling"])].copy()  # fmt: skip
        cost["label"] = cost["strategy"].map(STRATEGY_LABELS)
        levers = self._csv("improve", "levers_ranges.csv")
        cavity = self._csv("improve", "levers_cavity.csv")
        return {
            "pareto": _records(pareto),
            "performance": _records(self._performance()),
            "ranges": _records(
                ranges[
                    [
                        "Product_Type",
                        "variable",
                        "label",
                        "category",
                        "shap_share",
                        "range_label",
                        "in_share",
                        "rate_in",
                        "rate_out",
                        "cmh_or",
                        "cmh_low",
                        "cmh_high",
                        "runs_agree",
                        "runs_tested",
                        "verdict",
                        "later_verdict",
                    ]
                ]
            ),  # fmt: skip
            "checklist": _records(checklist),
            "cost_best": _records(best),
            "cost": _records(
                cost[["ratio", "strategy", "label", "cost_per_part", "inspect_rate", "capture"]]
            ),  # fmt: skip
            "levers": {
                "cavity_reduction": float(cavity["excess"].sum() / cavity["defects"].sum()),
                "ranges": _records(
                    levers[
                        [
                            "Product_Type",
                            "actual_rate",
                            "in_range_rate",
                            "reduction",
                            "reduction_low",
                            "reduction_high",
                            "ranges",
                        ]
                    ]
                ),  # fmt: skip
            },
            "doe": _records(self._csv("improve", "doe_factors.csv")),
        }

    def _performance(self) -> pd.DataFrame:
        """1단계 주요 비교: ① 같은 기간·② 시간 순서(fold 평균), ③ 50 shot 재학습(합산)의
        Extra Trees·XGBoost·최근 불량률 규칙·무작위 ROC-AUC와 상위 20% 포착률."""
        models = ["et", "xgb", "recent_rate", "random"]
        summary = self._csv("stage1", "metrics_summary.csv")
        summary = summary[(summary["experiment"] == "main") & summary["model"].isin(models)]
        pooled = self._csv("stage1", "metrics_pooled.csv")
        pooled = pooled[(pooled["design"] == "retrain_50") & pooled["model"].isin(models)]
        return pd.concat([
            summary[["design", "model"]].assign(roc_auc=summary["roc_auc_mean"],
                                                capture_20=summary["capture_20_mean"]),
            pooled[["design", "model", "roc_auc", "capture_20"]],
        ], ignore_index=True)  # fmt: skip
