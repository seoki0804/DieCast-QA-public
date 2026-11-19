"""2단계 실험 묶음 (6.2)과 기획서 7.6 예비 결과와의 비교."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pandas as pd

from diecast_qa.modeling.designs import RetrainDesign, SameTermDesign, TimeOrderDesign
from diecast_qa.modeling.metrics import summarize
from diecast_qa.modeling.type_experiment import (
    TYPE_METRIC_COLS,
    TypeExperiment,
    confusion,
    joint_capture,
    per_class_scores,
    type_fold_metrics,
    type_pooled_metrics,
)
from diecast_qa.modeling.type_models import TYPE_MODELS, TYPE_RULES

KEYS = ["design", "model"]
DESIGN_LABELS = {"same_term": "① 같은 기간", "time_order": "② 시간 순서"}

# 기획서 7.6 (Accuracy, Macro-F1)
PLAN_REFERENCE = pd.DataFrame(
    [(d, m, acc, f1)
     for m, vals in {"rf": ((0.54, 0.56), (0.44, 0.34)), "xgb": ((0.54, 0.55), (0.43, 0.27)),
                     "type_mode": ((0.35, 0.10), (0.33, 0.14)),
                     "type_group_mode": ((0.41, 0.27), (0.29, 0.26))}.items()
     for d, (acc, f1) in zip(DESIGN_LABELS, vals, strict=True)],
    columns=[*KEYS, "plan_accuracy", "plan_macro_f1"],
)  # fmt: skip


@dataclass(frozen=True)
class Stage2Results:
    predictions: pd.DataFrame
    folds: pd.DataFrame
    summary: pd.DataFrame
    pooled: pd.DataFrame
    per_class: pd.DataFrame
    confusion: pd.DataFrame
    joint: pd.DataFrame

    def plan_comparison(self) -> pd.DataFrame:
        ours = self.summary[["accuracy_mean", "macro_f1_mean"]].set_axis(
            ["accuracy", "macro_f1"], axis=1
        )
        table = PLAN_REFERENCE.join(ours, on=KEYS)
        table["diff_macro_f1"] = table["macro_f1"] - table["plan_macro_f1"]
        return table

    def best_model(self, design: str) -> str:
        models = self.summary.xs(design, level="design")["macro_f1_mean"]
        return models.loc[models.index.intersection(list(TYPE_MODELS))].idxmax()

    def notes(self) -> tuple[str, ...]:
        notes = []
        for design, label in DESIGN_LABELS.items():
            s = self.summary.xs(design, level="design")
            best = self.best_model(design)
            notes.append(
                f"{label}: 최고 모델 {TYPE_MODELS[best].label} Macro-F1 "
                f"{s.loc[best, 'macro_f1_mean']:.3f}±{s.loc[best, 'macro_f1_std']:.3f} "
                f"(Accuracy {s.loc[best, 'accuracy_mean']:.3f}), 기준 최다 유형 "
                f"{s.loc['type_mode', 'macro_f1_mean']:.3f}, 제품 유형·캐비티별 "
                f"{s.loc['type_group_mode', 'macro_f1_mean']:.3f}"
            )
            f1 = self.per_class.xs((design, best), level=KEYS)["f1"]
            notes.append(f"{label} {best} 유형별 F1 (fold 합산): "
                         + ", ".join(f"{t} {v:.2f}" for t, v in f1.items()))  # fmt: skip
        retrain = self.pooled[self.pooled.index.get_level_values("design").str.startswith("re")]
        if not retrain.empty:
            f1 = retrain["macro_f1"].unstack("model")
            f1.index = f1.index.str.removeprefix("retrain_").astype(int)
            for n, row in f1.sort_index().iterrows():
                notes.append(f"③ {n} shot마다 재학습 Macro-F1 (평가 구간 합산): "
                             + ", ".join(f"{m} {v:.3f}" for m, v in row.items()))  # fmt: skip
        at20 = self.joint.xs(0.2, level="frac")
        for design, label in DESIGN_LABELS.items():
            joint = at20.xs(design, level="design")
            s1, s2 = joint["end_to_end"].idxmax()
            for model in (s2, "type_group_mode"):
                r = joint.loc[(s1, model)]
                notes.append(
                    f"{label} 연결 평가(상위 20% 검사, 1단계 {s1} → 2단계 {model}): 불량 포착 "
                    f"{r['capture']:.0%}, 그중 유형 적중 {r['type_hit']:.0%}, "
                    f"전체 불량 대비 {r['end_to_end']:.0%}"
                )
        return tuple(notes)

    def best_joint(self, design: str, frac: float = 0.2) -> tuple[str, str]:
        """전체 불량 대비(end_to_end)가 가장 높은 (1단계, 2단계) 조합."""
        return self.joint.xs((design, frac), level=["design", "frac"])["end_to_end"].idxmax()


class Stage2Study:
    """① ②에서 유형 모델·기준을 비교하고, ③ 재학습 효과와 1·2단계 연결 평가를 낸다.

    stage1_predictions: 4단계의 results/predictions.csv.gz (연결 평가에 쓴다).
    """

    def __init__(
        self,
        parts: pd.DataFrame,
        stage1_predictions: pd.DataFrame,
        retrain_every: tuple[int, ...] = (50, 100, 200, 500),
        retrain_models: tuple[str, ...] = ("rf", "et"),
        stage1_scorers: tuple[str, ...] = ("recent_rate", "et", "xgb"),
    ) -> None:
        self.parts = parts
        self.stage1 = stage1_predictions
        self.retrain_every = retrain_every
        self.retrain_models = retrain_models
        self.stage1_scorers = stage1_scorers

    def experiments(self) -> Iterator[TypeExperiment]:
        specs = [*TYPE_MODELS.values(), *TYPE_RULES.values()]
        for design in (SameTermDesign(), TimeOrderDesign()):
            yield TypeExperiment(design, specs)
        retrain = [*(TYPE_MODELS[m] for m in self.retrain_models), *TYPE_RULES.values()]
        for n in self.retrain_every:
            yield TypeExperiment(RetrainDesign(n), retrain, f"retrain_{n}")

    def run(self, log: Callable[[str], None] = print) -> Stage2Results:
        frames = []
        for experiment in self.experiments():
            log(f"{experiment.label} ({len(experiment.specs)} 모델)")
            frames.append(experiment.run(self.parts))
        predictions = pd.concat(frames, ignore_index=True)
        folds = type_fold_metrics(predictions, KEYS)

        main = predictions[predictions["design"].isin(list(DESIGN_LABELS))]
        stage1 = self.stage1[(self.stage1["experiment"] == "main")
                             & self.stage1["design"].isin(list(DESIGN_LABELS))
                             & self.stage1["model"].isin(self.stage1_scorers)]  # fmt: skip
        return Stage2Results(
            predictions=predictions,
            folds=folds,
            summary=summarize(folds, KEYS, TYPE_METRIC_COLS),
            pooled=type_pooled_metrics(predictions, KEYS),
            per_class=per_class_scores(main, KEYS),
            confusion=confusion(main, KEYS),
            joint=joint_capture(stage1, main),
        )
