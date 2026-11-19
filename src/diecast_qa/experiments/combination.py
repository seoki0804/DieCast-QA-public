"""8.3 규칙 + 모델 결합: 최근 불량률 규칙과 모델 점수를 합치면 둘 각각보다 나은가?"""

from __future__ import annotations

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.modeling import MODELS, RULES, Experiment, ModelSpec, RetrainDesign, TimeOrderDesign
from diecast_qa.modeling.combine import RankAverage, StackedRule
from diecast_qa.modeling.estimators import RecentRateRule
from diecast_qa.modeling.metrics import fold_metrics, pooled_metrics, summarize

MODEL = "et"
LABELS = {
    "et": "Extra Trees",
    "recent_rate": "규칙: 최근 10 shot 불량률",
    "rank_avg": "결합: 순위 평균",
    "stacked": "결합: Stacking (로지스틱 회귀)",
    "et_history": "결합: 최근 불량률을 입력 변수로",
}


def specs() -> list[ModelSpec]:
    model = MODELS[MODEL]
    return [
        model,
        RULES["recent_rate"],
        ModelSpec("rank_avg", LABELS["rank_avg"],
                  lambda cols: RankAverage(model.factory(cols), RecentRateRule())),
        ModelSpec("stacked", LABELS["stacked"],
                  lambda cols: StackedRule(model.factory(cols), RecentRateRule())),
        model.with_(name="et_history", label=LABELS["et_history"], features="history"),
    ]  # fmt: skip


class RuleModelCombinationExperiment(Analysis):
    """② 시간 순서(fold 평균)와 ③ 100 shot마다 재학습(평가 구간 합산)에서 비교한다."""

    name = "e83_combination"

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        second = Experiment(TimeOrderDesign(), specs()).run(parts)
        third = Experiment(RetrainDesign(100), specs(), "retrain_100").run(parts)
        tables = {
            "time_order": summarize(fold_metrics(second, ["model"]), ["model"]),
            "retrain_100": pooled_metrics(third, ["model"]),
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    @staticmethod
    def notes(tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        second, third = tables["time_order"], tables["retrain_100"]
        return tuple(
            f"{LABELS[m]}: ② ROC-AUC {second.loc[m, 'roc_auc_mean']:.3f} "
            f"/ 포착률 {second.loc[m, 'capture_20_mean']:.0%}, "
            f"③ 100 shot 재학습 {third.loc[m, 'roc_auc']:.3f} / {third.loc[m, 'capture_20']:.0%}"
            for m in LABELS
        )
