"""1단계 실험 묶음 (6장)과 기획서 7장 예비 결과와의 비교."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from diecast_qa.modeling.designs import RetrainDesign, SameTermDesign, TimeOrderDesign
from diecast_qa.modeling.estimators import MODELS, RULES
from diecast_qa.modeling.experiment import Experiment
from diecast_qa.modeling.metrics import fold_metrics, pooled_metrics, summarize
from diecast_qa.modeling.tuning import TimeOrderTuner, TunedExperiment

KEYS = ["experiment", "design", "model", "feature_set", "variant"]
# 2.3 "비정상 shot 제외 여부·결측 처리 비교" (학습 데이터 처리)
SENSITIVITY_FILTERS = ("drop_abnormal", "drop_missing")

# 기획서 7장 예비 결과 (ROC-AUC, 상위 20% 포착률). 7.4는 평가 구간 전체를 합산한 값이다.
PLAN_REFERENCE = pd.DataFrame(
    [
        # (실험, 검증, 모델, 변수 묶음, 변형, AUC, 포착률, 기획서 표)
        *((("main", d, m, "base", "", auc, cap, "7.1")
           for m, vals in {
               "logreg": ((0.73, 0.48), (0.58, 0.24)), "tree": ((0.74, 0.50), (0.58, 0.27)),
               "rf": ((0.77, 0.51), (0.59, 0.31)), "et": ((0.77, 0.53), (0.62, 0.34)),
               "xgb": ((0.76, 0.53), (0.58, 0.26)), "lgbm": ((0.77, 0.53), (0.59, 0.29)),
               "mlp": ((0.65, 0.36), (0.48, 0.16)),
           }.items()
           for d, (auc, cap) in zip(("same_term", "time_order"), vals, strict=True))),
        *((("main", d, m, "base", "", auc, cap, "7.3")
           for m, vals in {"cavity_rate": ((0.61, 0.28), (0.60, 0.26)),
                           "recent_rate": ((0.74, 0.48), (0.69, 0.41))}.items()
           for d, (auc, cap) in zip(("same_term", "time_order"), vals, strict=True))),
        *((("features", d, "rf", f, "", auc, cap, "7.3")
           for f, vals in {"drift": ((0.77, 0.53), (0.59, 0.32)),
                           "history": ((0.76, 0.52), (0.61, 0.34))}.items()
           for d, (auc, cap) in zip(("same_term", "time_order"), vals, strict=True))),
        *((("duplicate_leak", "same_term_with_duplicates", m, "base", "", auc, cap, "7.2")
           for m, (auc, cap) in {"logreg": (0.72, 0.46), "tree": (0.73, 0.47),
                                 "rf": (0.91, 0.78), "xgb": (0.78, 0.54)}.items())),
        ("retrain", "retrain_50", "recent_rate", "base", "", 0.72, 0.46, "7.4"),
        *((("retrain", f"retrain_{n}", "rf", "base", "", auc, cap, "7.4")
           for n, (auc, cap) in {50: (0.72, 0.46), 100: (0.70, 0.46), 200: (0.68, 0.44),
                                 500: (0.63, 0.38)}.items())),
    ],
    columns=[*KEYS, "plan_roc_auc", "plan_capture_20", "plan_table"],
)  # fmt: skip


@dataclass(frozen=True)
class StudyResults:
    predictions: pd.DataFrame
    folds: pd.DataFrame
    summary: pd.DataFrame
    pooled: pd.DataFrame
    tuning: pd.DataFrame  # 조정 실험에서 fold·모델마다 고른 파라미터와 내부 AUC

    def plan_comparison(self) -> pd.DataFrame:
        """기획서 수치 옆에 재현 수치를 붙인다. ③(retrain)은 합산 지표, 나머지는 fold 평균."""
        ours = self.summary[["roc_auc_mean", "capture_20_mean"]].set_axis(
            ["roc_auc", "capture_20"], axis=1
        )
        pooled = self.pooled[["roc_auc", "capture_20"]]
        is_retrain = ours.index.get_level_values("experiment") == "retrain"
        ours.loc[is_retrain] = pooled.loc[ours.index[is_retrain]]
        table = PLAN_REFERENCE.join(ours, on=KEYS)
        table["diff_roc_auc"] = table["roc_auc"] - table["plan_roc_auc"]
        return table

    def notes(self) -> tuple[str, ...]:
        s = self.summary

        def get(experiment, design, model, features="base", variant=""):
            return s.loc[(experiment, design, model, features, variant)]

        def fmt(row) -> str:
            return (f"{row['roc_auc_mean']:.3f}±{row['roc_auc_std']:.3f} / "
                    f"{row['capture_20_mean']:.0%}")  # fmt: skip

        notes = []
        for design, label in (("same_term", "① 같은 기간"), ("time_order", "② 시간 순서")):
            models = s.xs(("main", design, "base", ""),
                          level=["experiment", "design", "feature_set", "variant"])  # fmt: skip
            best = models.loc[models.index.intersection(list(MODELS)), "roc_auc_mean"].idxmax()
            rule = models.loc["recent_rate"]
            notes.append(f"{label}: 최고 모델 {MODELS[best].label} {fmt(models.loc[best])}, "
                         f"최근 10 shot 규칙 {fmt(rule)} (ROC-AUC / 상위 20% 포착률)")  # fmt: skip
        for f in ("drift", "history"):
            row = get("features", "time_order", "rf", f)
            notes.append(f"RF + {f} 변수 (② 시간 순서): {fmt(row)}")
        for v in SENSITIVITY_FILTERS:
            row = get("sensitivity", "time_order", "rf", variant=v)
            notes.append(f"RF 학습 데이터 {v} (② 시간 순서): {fmt(row)}")
        retrain = self.pooled.xs(("retrain", "base", ""),
                                 level=["experiment", "feature_set", "variant"])  # fmt: skip
        auc = retrain["roc_auc"].unstack("model")
        auc.index = auc.index.str.removeprefix("retrain_").astype(int)
        for n, row in auc.sort_index().iterrows():
            notes.append(f"③ {n} shot마다 재학습 ROC-AUC (평가 구간 합산): "
                         + ", ".join(f"{m} {v:.3f}" for m, v in row.items()))  # fmt: skip
        leak = s.xs("duplicate_leak", level="experiment")["roc_auc_mean"].droplevel(
            ["design", "feature_set", "variant"])  # fmt: skip
        notes.append("중복 포함 무작위 분할 ROC-AUC: " + ", ".join(
            f"{m} {v:.3f}" for m, v in leak.items()))  # fmt: skip
        if not self.tuning.empty:
            tuned = s.xs(("tuned", "time_order"), level=["experiment", "design"])
            notes.append("② 조정 전 → 후 ROC-AUC: " + ", ".join(
                f"{m} {get('main', 'time_order', m)['roc_auc_mean']:.3f}→"
                f"{tuned.loc[(m, 'base', 'tuned'), 'roc_auc_mean']:.3f}"
                for m in tuned.index.get_level_values("model")))  # fmt: skip
        return tuple(notes)


class Stage1Study:
    """기획서 6장의 1단계 실험을 모두 실행한다.

    parts: 정제 데이터, parts_with_duplicates: 중복 기록을 남긴 데이터(7.2 참고 실험용).
    """

    MAIN_MODELS = ("logreg", "tree", "rf", "et", "xgb", "lgbm", "mlp")

    def __init__(
        self,
        parts: pd.DataFrame,
        parts_with_duplicates: pd.DataFrame,
        retrain_every: tuple[int, ...] = (50, 100, 200, 500),
        retrain_models: tuple[str, ...] = ("rf", "et", "lgbm"),
        leak_models: tuple[str, ...] = ("logreg", "tree", "rf", "xgb"),
        tuned_models: tuple[str, ...] = ("logreg", "tree", "rf", "et", "xgb", "lgbm"),
        tuner: TimeOrderTuner | None = None,
    ) -> None:
        self.parts = parts
        self.parts_with_duplicates = parts_with_duplicates
        self.retrain_every = retrain_every
        self.retrain_models = retrain_models
        self.leak_models = leak_models
        self.tuned_models = tuned_models
        self.tuner = tuner or TimeOrderTuner(n_trials=15)

    def experiments(self) -> Iterator[tuple[str, Experiment, pd.DataFrame]]:
        main = [*(MODELS[m] for m in self.MAIN_MODELS), *RULES.values()]
        rf = MODELS["rf"]
        for design in (SameTermDesign(), TimeOrderDesign()):
            yield "main", Experiment(design, main), self.parts
            yield (
                "features",
                Experiment(design, [rf.with_(features=f) for f in ("drift", "history")]),
                self.parts,
            )
            yield (
                "sensitivity",
                Experiment(design, [rf.with_(train_filter=f) for f in SENSITIVITY_FILTERS]),
                self.parts,
            )
        for n in self.retrain_every:
            specs = [*(MODELS[m] for m in self.retrain_models), RULES["recent_rate"]]
            yield "retrain", Experiment(RetrainDesign(n), specs, f"retrain_{n}"), self.parts
        yield (
            "duplicate_leak",
            Experiment(
                SameTermDesign(), [MODELS[m] for m in self.leak_models], "same_term_with_duplicates"
            ),
            self.parts_with_duplicates,
        )
        # 조정은 핵심 질문인 ② 시간 순서에서만 한다. ①·③은 기본 파라미터
        yield (
            "tuned",
            TunedExperiment(TimeOrderDesign(), [MODELS[m] for m in self.tuned_models], self.tuner),
            self.parts,
        )

    def run(
        self, log: Callable[[str], None] = print, cache_dir: Path | None = None,
        use_cache: bool = False,
    ) -> StudyResults:  # fmt: skip
        """cache_dir을 주면 실험마다 예측을 저장하고, use_cache면 저장된 실험은 다시 돌리지 않는다.

        코드나 데이터를 바꾼 뒤에는 use_cache 없이 다시 실행해야 한다.
        """
        frames, chosen = [], []
        for name, experiment, data in self.experiments():
            path = cache_dir / f"{name}__{experiment.label}.pkl" if cache_dir else None
            if use_cache and path and path.exists():
                log(f"{name} / {experiment.label}: 저장된 예측 사용")
                cached = pd.read_pickle(path)
            else:
                log(f"{name} / {experiment.label} ({len(experiment.specs)} 모델)")
                cached = {"predictions": experiment.run(data).assign(experiment=name),
                          "chosen": getattr(experiment, "chosen", [])}  # fmt: skip
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    pd.to_pickle(cached, path)
            frames.append(cached["predictions"])
            chosen += cached["chosen"]
        predictions = pd.concat(frames, ignore_index=True)
        folds = fold_metrics(predictions, KEYS)
        return StudyResults(predictions, folds, summarize(folds, KEYS),
                            pooled_metrics(predictions, KEYS), pd.DataFrame(chosen))  # fmt: skip
