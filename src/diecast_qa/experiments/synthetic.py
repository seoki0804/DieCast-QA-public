"""8.1 합성 데이터 생성 비교: 데이터를 늘리면 성능이 오르나? 안 오른다면 왜인가?"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.neighbors import NearestNeighbors

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import PROCESS_COLS, SEED
from diecast_qa.modeling import FEATURE_SETS, ModelSpec, SameTermDesign, TimeOrderDesign
from diecast_qa.modeling.augment import (
    SAMPLERS,
    ClassBalancer,
    GaussianCopulaSampler,
    NoiseJitter,
    Snapped,
)
from diecast_qa.modeling.estimators import pipeline
from diecast_qa.modeling.experiment import Experiment
from diecast_qa.modeling.metrics import fold_metrics, summarize
from diecast_qa.modeling.type_experiment import TYPE_METRIC_COLS, TypeExperiment, type_fold_metrics

SamplerFactory = Callable[[], object]

TECHNIQUES: dict[str, tuple[str, SamplerFactory | None]] = {
    "none": ("증강 없음", None),
    "class_weight": ("Class Weight", None),
    "ros": ("Random Oversampling", SAMPLERS["ros"]),
    "smote": ("SMOTE", SAMPLERS["smote"]),
    "bsmote": ("Borderline-SMOTE", SAMPLERS["bsmote"]),
    "adasyn": ("ADASYN", SAMPLERS["adasyn"]),
    "noise": ("Noise jitter (5%)", SAMPLERS["noise"]),
    "copula": ("Gaussian Copula", SAMPLERS["copula"]),
    "ctgan": ("CTGAN", SAMPLERS["ctgan"]),
}
# 원인 진단 (② 시간 순서에서만)
DIAGNOSTICS: dict[str, tuple[str, SamplerFactory]] = {
    "noise_shot": ("잡음: shot 번호에만", lambda: NoiseJitter(columns=("Shot",))),
    "noise_process": ("잡음: 공정 변수에만", lambda: NoiseJitter(columns=PROCESS_COLS)),
    "copula_snap": ("Copula + 실제 값으로 맞춤", lambda: Snapped(GaussianCopulaSampler())),
}
STAGE2_TECHNIQUES = ("none", "smote", "copula", "ctgan")
QUALITY_GENERATORS = ("smote", "noise", "copula", "ctgan")
LABELS = {k: v[0] for k, v in {**TECHNIQUES, **DIAGNOSTICS}.items()}

# 기획서 8.1 예비 결과 (ROC-AUC, 상위 20% 포착률, Recall@0.5): ① / ②
PLAN_REFERENCE = {
    "none": ((0.77, 0.52, 0.09), (0.58, 0.31, 0.05)),
    "class_weight": ((0.77, 0.52, 0.48), (0.61, 0.32, 0.37)),
    "ros": ((0.76, 0.51, 0.35), (0.59, 0.31, 0.29)),
    "smote": ((0.76, 0.51, 0.24), (0.57, 0.30, 0.21)),
    "bsmote": ((0.76, 0.51, 0.24), (0.58, 0.28, 0.12)),
    "adasyn": ((0.76, 0.50, 0.24), (0.57, 0.30, 0.16)),
    "noise": ((0.76, 0.50, 0.08), (0.47, 0.14, 0.20)),
    "copula": ((0.76, 0.50, 0.19), (0.43, 0.14, 0.74)),
    "ctgan": ((0.76, 0.50, 0.08), (0.48, 0.15, 0.16)),
}


def rf_spec(name: str, sampler: SamplerFactory | None = None) -> ModelSpec:
    """기획서 8.1처럼 Class Weight 없는 RF. class_weight 기법만 가중치를 준다."""
    weight = "balanced" if name == "class_weight" else None

    def factory(cols):
        rf = RandomForestClassifier(300, class_weight=weight, n_jobs=-1, random_state=SEED)
        return pipeline(cols, rf, sampler=sampler() if sampler else None)

    return ModelSpec(name, LABELS[name], factory)


class SyntheticDataExperiment(Analysis):
    """1단계(RF, ①②)와 2단계(유형, ①②)에서 불균형 처리·합성 기법을 비교하고,
    합성 데이터의 품질(TSTR, 진짜/가짜 판별, 최근접 거리)과 성능 저하 원인을 진단한다."""

    name = "e81_synthetic"

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        keys = ["design", "model"]
        designs = (SameTermDesign(), TimeOrderDesign())
        specs = [rf_spec(n, f) for n, (_, f) in TECHNIQUES.items()]
        stage1 = pd.concat([Experiment(d, specs).run(parts) for d in designs])
        diag = Experiment(TimeOrderDesign(), [rf_spec(n, f) for n, (_, f) in DIAGNOSTICS.items()])
        stage1 = pd.concat([stage1, diag.run(parts)])
        s1 = summarize(fold_metrics(stage1, keys), keys)

        type_specs = [rf_spec(n, TECHNIQUES[n][1]) for n in STAGE2_TECHNIQUES]
        stage2 = pd.concat([TypeExperiment(d, type_specs).run(parts) for d in designs])
        s2 = summarize(type_fold_metrics(stage2, keys), keys, TYPE_METRIC_COLS)

        quality = self.quality(parts)
        tables = {"stage1": s1, "stage2": s2, "quality": quality,
                  "plan_comparison": self.plan_comparison(s1)}  # fmt: skip
        return AnalysisResult(self.name, tables, self.notes(s1, s2, quality))

    @staticmethod
    def quality(parts: pd.DataFrame) -> pd.DataFrame:
        """① 같은 기간 fold마다, 학습 데이터의 실제 불량과 같은 수의 합성 불량을 만들어 점검한다.

        tstr_auc: 실제 양품 + 합성 불량으로 학습해 실제 평가 데이터로 잰 ROC-AUC
        (real_auc: 실제 불량으로 학습한 같은 기준값), discriminator_auc: 실제 불량과 합성 불량을
        구별하는 RF의 5-fold ROC-AUC(0.5면 구별 못 함), nn_ratio: 합성 → 실제 최근접 거리 중앙값을
        실제 → 다른 실제 최근접 거리 중앙값으로 나눈 값(1보다 크면 실제 분포 밖으로 퍼짐).
        """
        cols = FEATURE_SETS["base"]
        rows = []
        for split in SameTermDesign().splits(parts):
            train, test = parts.iloc[split.train], parts.iloc[split.test]
            imputer = SimpleImputer(strategy="median").set_output(transform="pandas")
            X, Xt = imputer.fit_transform(train[cols]), imputer.transform(test[cols])
            y, yt = train["defect"].to_numpy(), test["defect"].to_numpy()
            real = X[y == 1].reset_index(drop=True)
            real_auc = _rf_auc(X, y, Xt, yt)
            for name in QUALITY_GENERATORS:
                fake = synthesize(SAMPLERS[name](), X, y, len(real))
                labels = np.r_[np.zeros((y == 0).sum()), np.ones(len(fake))]
                tstr = _rf_auc(pd.concat([X[y == 0], fake]), labels, Xt, yt)
                rows.append({"fold": split.fold, "generator": name, "real_auc": real_auc,
                             "tstr_auc": tstr, "discriminator_auc": _discriminator_auc(real, fake),
                             "nn_ratio": _nn_ratio(real, fake)})  # fmt: skip
        return pd.DataFrame(rows).groupby("generator").mean().drop(columns="fold")

    @staticmethod
    def plan_comparison(s1: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for name, values in PLAN_REFERENCE.items():
            for design, (auc, cap, rec) in zip(("same_term", "time_order"), values, strict=True):
                ours = s1.loc[(design, name)]
                rows.append({"design": design, "model": name, "plan_roc_auc": auc,
                             "roc_auc": ours["roc_auc_mean"], "plan_capture_20": cap,
                             "capture_20": ours["capture_20_mean"], "plan_recall_at_05": rec,
                             "recall_at_05": ours["recall_at_05_mean"]})  # fmt: skip
        return pd.DataFrame(rows).set_index(["design", "model"])

    @staticmethod
    def notes(s1, s2, quality) -> tuple[str, ...]:
        def row(design, name):
            r = s1.loc[(design, name)]
            return (f"{r['roc_auc_mean']:.3f} / {r['capture_20_mean']:.0%} / "
                    f"Recall {r['recall_at_05_mean']:.0%}")  # fmt: skip

        notes = [f"{LABELS[n]}: ① {row('same_term', n)}, ② {row('time_order', n)}"
                 for n in TECHNIQUES]  # fmt: skip
        notes += [f"원인 진단 ② {LABELS[n]}: {row('time_order', n)}" for n in DIAGNOSTICS]
        notes += [f"2단계 Macro-F1 {LABELS[n]}: ① {s2.loc[('same_term', n), 'macro_f1_mean']:.3f}"
                  f" / ② {s2.loc[('time_order', n), 'macro_f1_mean']:.3f}"
                  for n in STAGE2_TECHNIQUES]  # fmt: skip
        notes += [f"합성 품질 {LABELS[g]}: TSTR {r.tstr_auc:.3f} (실제 학습 {r.real_auc:.3f}), "
                  f"진짜/가짜 판별 AUC {r.discriminator_auc:.2f}, 최근접 거리 비 {r.nn_ratio:.2f}"
                  for g, r in quality.iterrows()]  # fmt: skip
        return tuple(notes)


def synthesize(sampler, X: pd.DataFrame, y: np.ndarray, n: int) -> pd.DataFrame:
    """sampler로 불량 클래스 행을 n개 만든다."""
    if isinstance(sampler, ClassBalancer):
        sampler.prepare(X)
        real = X[y == 1].reset_index(drop=True)
        return sampler.generate(real, n, np.random.default_rng(SEED))[X.columns]
    Xs, _ = sampler.fit_resample(X, y)  # imblearn은 합성 행을 원래 행 뒤에 붙인다
    fake = Xs.iloc[len(X) :]
    return fake.sample(n, random_state=SEED).reset_index(drop=True)


def _rf_auc(X, y, Xt, yt) -> float:
    rf = RandomForestClassifier(300, n_jobs=-1, random_state=SEED).fit(X, y)
    return roc_auc_score(yt, rf.predict_proba(Xt)[:, 1])


def _discriminator_auc(real: pd.DataFrame, fake: pd.DataFrame) -> float:
    X = pd.concat([real, fake], ignore_index=True)
    y = np.r_[np.zeros(len(real)), np.ones(len(fake))]
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    rf = RandomForestClassifier(200, n_jobs=-1, random_state=SEED)
    return roc_auc_score(y, cross_val_predict(rf, X, y, cv=cv, method="predict_proba")[:, 1])


def _nn_ratio(real: pd.DataFrame, fake: pd.DataFrame) -> float:
    sd = real.std().replace(0, 1)
    r, f = (real - real.mean()) / sd, (fake - real.mean()) / sd
    nn = NearestNeighbors(n_neighbors=2).fit(r)
    real_to_real = nn.kneighbors(r)[0][:, 1]  # 자기 자신 제외
    fake_to_real = nn.kneighbors(f, n_neighbors=1)[0][:, 0]
    return float(np.median(fake_to_real) / np.median(real_to_real))
