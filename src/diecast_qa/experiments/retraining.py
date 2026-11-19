"""8.2 관리도 경보 기반 재학습, 8.5 최근 데이터 가중치: '언제, 어떤 데이터로 다시 학습할지'."""

from __future__ import annotations

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import KEY_VARS
from diecast_qa.modeling import MODELS, RULES, Experiment, RetrainDesign
from diecast_qa.modeling.metrics import pooled_metrics
from diecast_qa.modeling.retraining import AlarmRetrainDesign, ChartAlarmTrigger
from diecast_qa.spc.charts import CUSUMChart, EWMAChart

MODEL = "et"  # ③ 주기적 재학습에서 가장 나았던 모델
NEVER = 10**9  # 평가 구간 시작 때 한 번만 학습

TRIGGERS = {
    "alarm_defect_cusum": ("경보: 불량률 CUSUM", lambda: ChartAlarmTrigger(
        lambda: [CUSUMChart("defect_rate", k=0.25, h=8.0, sigma_method="binomial")], lag=1)),
    "alarm_defect_ewma": ("경보: 불량률 EWMA", lambda: ChartAlarmTrigger(
        lambda: [EWMAChart("defect_rate", lam=0.05, L=3.0, sigma_method="binomial")], lag=1)),
    "alarm_process_cusum": ("경보: 공정 변수 CUSUM", lambda: ChartAlarmTrigger(
        lambda: [CUSUMChart(v, k=0.5, h=5.0, sigma_method="overall") for v in KEY_VARS],
        lag=0)),
}  # fmt: skip
FIXED = {"never": NEVER, "fixed_50": 50, "fixed_100": 100, "fixed_200": 200}
LABELS = {"never": "재학습 없음", "fixed_50": "50 shot마다", "fixed_100": "100 shot마다",
          "fixed_200": "200 shot마다", **{k: v[0] for k, v in TRIGGERS.items()}}  # fmt: skip


def pooled_with_retrains(predictions: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """평가 구간 합산 지표와 재학습 횟수(학습한 묶음 수 - 제품 유형 수: 시작 학습은 빼고 센다)."""
    table = pooled_metrics(predictions, keys)
    chunks = predictions.groupby(keys)["chunk"].nunique()
    table["retrains"] = chunks - predictions["Product_Type"].nunique()
    return table


class AlarmRetrainingExperiment(Analysis):
    """8.2: 고정 주기 대신 관리도 경보가 났을 때 다시 학습하면 적은 재학습으로 비슷한 성능을 내나?

    불량률 경보는 검사 결과가 있어야 하고, 공정 변수 경보는 검사 전에 알 수 있다.
    """

    name = "e82_alarm_retrain"

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        specs = [MODELS[MODEL], RULES["recent_rate"]]
        designs = {name: RetrainDesign(every) for name, every in FIXED.items()}
        designs |= {name: AlarmRetrainDesign(make()) for name, (_, make) in TRIGGERS.items()}
        predictions = pd.concat(
            [Experiment(design, specs, name).run(parts) for name, design in designs.items()]
        )
        table = pooled_with_retrains(predictions, ["design", "model"])
        return AnalysisResult(self.name, {"pooled": table}, self.notes(table))

    @staticmethod
    def notes(table: pd.DataFrame) -> tuple[str, ...]:
        model = table.xs(MODEL, level="model")
        rule = table.xs("recent_rate", level="model")["roc_auc"].mean()
        notes = [f"{LABELS[d]}: ROC-AUC {r.roc_auc:.3f}, 상위 20% 포착률 {r.capture_20:.0%}, "
                 f"재학습 {int(r.retrains)}회"
                 for d, r in model.loc[list(LABELS)].iterrows()]  # fmt: skip
        notes.append(f"비교: 최근 10 shot 불량률 규칙 ROC-AUC {rule:.3f}")
        return tuple(notes)


VARIANTS = {
    "": "전체 누적 (expanding)",
    "window_500": "최근 500 shot만",
    "window_1000": "최근 1,000 shot만",
    "halflife_200": "시간 가중치 (반감기 200 shot)",
    "halflife_500": "시간 가중치 (반감기 500 shot)",
}


class RecencyExperiment(Analysis):
    """8.5: 최근 N shot만 쓰거나 최근 데이터에 가중치를 주면 나은가? (③ 재학습 주기 100·500 shot)"""

    name = "e85_recency"
    intervals = (100, 500)

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        base = MODELS[MODEL]
        specs = [
            base.with_(train_weight=v) if v.startswith("halflife") else base.with_(train_filter=v)
            for v in VARIANTS
        ]
        predictions = pd.concat(
            [Experiment(RetrainDesign(n), specs, f"retrain_{n}").run(parts) for n in self.intervals]
        )
        table = pooled_metrics(predictions, ["design", "variant"])
        return AnalysisResult(self.name, {"pooled": table}, self.notes(table))

    def notes(self, table: pd.DataFrame) -> tuple[str, ...]:
        return tuple(
            f"{n} shot마다 재학습, {VARIANTS[v]}: ROC-AUC {r.roc_auc:.3f}, "
            f"상위 20% 포착률 {r.capture_20:.0%}"
            for n in self.intervals
            for v, r in table.xs(f"retrain_{n}", level="design").loc[list(VARIANTS)].iterrows()
        )
