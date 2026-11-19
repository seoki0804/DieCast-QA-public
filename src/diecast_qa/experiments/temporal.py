"""6.6절 시간 정보를 활용한 학습: 시기에 따라 바뀌는 데이터를 입력이나 학습 방식에 반영하면
시간 순서 평가에서 성능이 오르나?

비교 방법(모두 Extra Trees, 기본 설정은 4장과 같다):
- base: 기준. 공정 14 + 센서 6(공장 온습도 포함) + 제품 유형·캐비티·shot 번호
- time: base + 생산 순서·구간 번호를 그대로 입력
- history: base + 흔들림 파생 변수 + 검사 이력(직전 1·10·50 shot 불량률)
- relative: 공정·센서 원값 대신 구간 기준 편차(구간 시작~직전 shot 중앙값 대비)
- invariant: base에서 구간 간 분산 비율(η²)이 0.5를 넘는 변수를 학습 데이터에서 골라 뺌
- shift_weight: base + 공변량 이동 가중치(학습 데이터 뒤 20%와 닮은 표본에 큰 가중치)
비교 기준은 최근 10 shot 불량률 규칙. 평가: ② 시간 순서(fold 평균), ③ 50·200 shot마다 재학습(합산).
"""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import BASE_FEATURES, SEED, VARIABLE_LABELS
from diecast_qa.features import RunRelativeFeatures
from diecast_qa.modeling import MODELS, RULES, Experiment, ModelSpec, RetrainDesign, TimeOrderDesign
from diecast_qa.modeling.estimators import ColumnSelector
from diecast_qa.modeling.metrics import fold_metrics, pooled_metrics, summarize
from diecast_qa.modeling.temporal import RunInvariantSelector, run_variance_share

THRESHOLD = 0.5
LABELS = {
    "et": "기준 (공정·센서 원값)",
    "et_time": "+ 생산 순서·구간 번호",
    "et_history": "+ 흔들림·검사 이력 변수",
    "et_relative": "구간 기준 편차만",
    "et_invariant": "시기 표시 변수 제외",
    "et_shift": "공변량 이동 가중치",
    "recent_rate": "규칙: 최근 10 shot 불량률",
}
RETRAIN = (50, 200)


def invariant_pipeline(cols: list[str]) -> Pipeline:
    clf = ExtraTreesClassifier(n_estimators=300, class_weight="balanced", n_jobs=-1,
                               random_state=SEED)  # fmt: skip
    return Pipeline([("select", ColumnSelector([*cols, "run"])),
                     ("invariant", RunInvariantSelector(THRESHOLD)),
                     ("impute", SimpleImputer(strategy="median")), ("clf", clf)])  # fmt: skip


def specs() -> list[ModelSpec]:
    et = MODELS["et"]
    return [
        et,
        et.with_(name="et_time", label=LABELS["et_time"], features="time"),
        et.with_(name="et_history", label=LABELS["et_history"], features="history"),
        et.with_(name="et_relative", label=LABELS["et_relative"], features="relative"),
        ModelSpec("et_invariant", LABELS["et_invariant"], invariant_pipeline),
        et.with_(name="et_shift", label=LABELS["et_shift"], train_weight="shift_weight"),
        RULES["recent_rate"],
    ]


class TemporalLearningExperiment(Analysis):
    name = "e88_temporal"

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        parts = RunRelativeFeatures().transform(parts.sort_values(["order", "Cavity"]))
        parts = parts.reset_index(drop=True)
        second = Experiment(TimeOrderDesign(), specs()).run(parts)
        third = pd.concat([Experiment(RetrainDesign(n), specs(), f"retrain_{n}").run(parts)
                           for n in RETRAIN])  # fmt: skip
        tables = {
            "time_order": summarize(fold_metrics(second, ["model"]), ["model"]),
            "retrain": pooled_metrics(third, ["design", "model"]),
            "invariant_shares": self._shares(parts),
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    @staticmethod
    def _shares(parts: pd.DataFrame) -> pd.DataFrame:
        """전체 데이터 기준 변수별 구간 간 분산 비율.

        참고용이다. 실험에서는 fold마다 학습 데이터로 다시 계산한다.
        """
        cols = [c for c in BASE_FEATURES if c not in ("Product_Type", "Cavity")]
        frame = parts[[*cols, "run", "Product_Type"]].copy()
        frame[cols] = frame[cols].fillna(frame[cols].median())
        shares = run_variance_share(frame, cols).sort_values(ascending=False)
        return pd.DataFrame({"label": [VARIABLE_LABELS.get(c, c) for c in shares.index],
                             "share": shares.to_numpy(),
                             "dropped": shares.to_numpy() > THRESHOLD},
                            index=shares.index.rename("variable"))  # fmt: skip

    @staticmethod
    def notes(tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        second, third = tables["time_order"], tables["retrain"]
        notes = []
        for m, label in LABELS.items():
            parts = [f"② ROC-AUC {second.loc[m, 'roc_auc_mean']:.3f} "
                     f"/ 포착률 {second.loc[m, 'capture_20_mean']:.0%}"]  # fmt: skip
            for n in RETRAIN:
                r = third.loc[(f"retrain_{n}", m)]
                parts.append(f"③ {n} shot 재학습 {r.roc_auc:.3f} / {r.capture_20:.0%}")
            notes.append(f"{label}: " + ", ".join(parts))
        shares = tables["invariant_shares"]
        dropped = ", ".join(shares.loc[shares["dropped"], "label"])
        notes.append(f"구간 간 분산 비율 > {THRESHOLD} (전체 데이터 기준): {dropped}")
        return tuple(notes)
