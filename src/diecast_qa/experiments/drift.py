"""8.4 기간별 변화 진단: 구간 사이에 어떤 변수가 달라졌나? 주요 변수가 구간마다 바뀌나?"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shap
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import PROCESS_COLS, SEED, SENSOR_COLS
from diecast_qa.data import shot_view
from diecast_qa.modeling import TimeOrderDesign

VARIABLES = [*PROCESS_COLS, *SENSOR_COLS]
# 같은 제품 유형 안의 인접 구간. 구간 6은 4 shot뿐이라 뺀다
RUN_PAIRS = ((1, 2), (2, 3), (4, 5), (5, 7))
MIN_DEFECTS = 50  # 구간별 SHAP을 구할 최소 불량 제품 수
TOP_K = 5


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index. 구간은 reference의 분위수로 나눈다.

    0.1 미만 안정, 0.1~0.25 중간 변화, 0.25 초과 큰 변화(관례적 기준).
    """
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))[1:-1]
    p = np.bincount(np.searchsorted(edges, reference, side="right"), minlength=len(edges) + 1)
    q = np.bincount(np.searchsorted(edges, current, side="right"), minlength=len(edges) + 1)
    p, q = (p + 1e-4) / (p.sum() + 1e-4), (q + 1e-4) / (q.sum() + 1e-4)
    return float(np.sum((q - p) * np.log(q / p)))


def adversarial(a: pd.DataFrame, b: pd.DataFrame) -> tuple[float, pd.Series]:
    """두 기간을 구별하는 RF의 5-fold ROC-AUC와 변수 중요도(불순도 감소, 합 1)."""
    X = pd.concat([a, b], ignore_index=True)
    y = np.r_[np.zeros(len(a)), np.ones(len(b))]
    rf = RandomForestClassifier(200, min_samples_leaf=5, n_jobs=-1, random_state=SEED)
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    auc = roc_auc_score(y, cross_val_predict(rf, X, y, cv=cv, method="predict_proba")[:, 1])
    importance = pd.Series(rf.fit(X, y).feature_importances_, index=X.columns)
    return auc, importance.sort_values(ascending=False)


def mean_abs_shap(X: pd.DataFrame, y: np.ndarray) -> pd.Series:
    """구간 안에서 학습한 RF로 구한 변수별 평균 |SHAP| (불량 클래스, 합 1로 정규화)."""
    rf = RandomForestClassifier(300, min_samples_leaf=5, class_weight="balanced", n_jobs=-1,
                                random_state=SEED).fit(X, y)  # fmt: skip
    values = np.asarray(shap.TreeExplainer(rf).shap_values(X))
    values = values[..., 1] if values.ndim == 3 else values  # (행, 변수, 클래스)
    share = np.abs(values).mean(axis=0)
    return pd.Series(share / share.sum(), index=X.columns)


class DriftDiagnosisExperiment(Analysis):
    """인접 구간 사이의 분포 변화(adversarial validation, PSI)와 구간별 주요 변수(SHAP)를 본다.

    공정 변수는 shot 단위(비정상 shot 제외)로, SHAP은 제품 단위(캐비티 포함)로 계산한다.
    """

    name = "e84_drift"

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = shot_view(parts)
        shots = shots[~shots["is_abnormal"]]
        filled = shots[VARIABLES].fillna(shots[VARIABLES].median())

        pairs, psi_cols = [], {}
        for a, b in RUN_PAIRS:
            ra, rb = filled[shots["run"] == a], filled[shots["run"] == b]
            auc, imp = adversarial(ra, rb)
            # 천천히 변하는 환경 변수(온습도)만으로도 시기는 구별되므로 공정 변수만으로도 본다
            process_auc, _ = adversarial(ra[list(PROCESS_COLS)], rb[list(PROCESS_COLS)])
            pairs.append({"pair": f"{a}→{b}", "adversarial_auc": auc,
                          "adversarial_auc_process": process_auc,
                          **{f"top{i + 1}": v for i, v in enumerate(imp.index[:3])}})  # fmt: skip
            psi_cols[f"{a}→{b}"] = {v: psi(ra[v].to_numpy(), rb[v].to_numpy()) for v in VARIABLES}
        psi_table = pd.DataFrame(psi_cols).rename_axis("variable")

        tables = {
            "adversarial_runs": pd.DataFrame(pairs).set_index("pair"),
            "adversarial_folds": self._fold_drift(parts, shots, filled),
            "psi": psi_table,
            "shap_by_run": self._shap_by_run(parts),
        }
        tables["shap_stability"] = self._stability(tables["shap_by_run"])
        return AnalysisResult(self.name, tables, self.notes(tables))

    @staticmethod
    def _fold_drift(parts, shots, filled) -> pd.DataFrame:
        """② 각 fold에서 학습 구간과 평가 구간을 구별하는 AUC (제품 유형별)."""
        block = TimeOrderDesign().blocks(parts).groupby(parts["order"]).first()
        shot_block = shots.index.map(block)
        rows = []
        for ptype in (1, 2):
            in_type = (shots["Product_Type"] == ptype).to_numpy()
            for k in range(2, 6):
                past = filled[in_type & (shot_block < k)]
                now = filled[in_type & (shot_block == k)]
                auc, imp = adversarial(past, now)
                rows.append({"Product_Type": ptype, "fold": k, "adversarial_auc": auc,
                             "top1": imp.index[0], "top2": imp.index[1]})  # fmt: skip
        return pd.DataFrame(rows).set_index(["Product_Type", "fold"])

    @staticmethod
    def _shap_by_run(parts: pd.DataFrame) -> pd.DataFrame:
        features = [*VARIABLES, "Cavity"]
        columns = {}
        for run, g in parts.groupby("run"):
            if g["defect"].sum() < MIN_DEFECTS:
                continue
            X = g[features].fillna(g[features].median())
            columns[run] = mean_abs_shap(X, g["defect"].to_numpy())
        return pd.DataFrame(columns).rename_axis("variable")

    @staticmethod
    def _stability(shap_by_run: pd.DataFrame) -> pd.DataFrame:
        """구간 쌍마다 SHAP 중요도 순위 상관(Spearman)과 상위 TOP_K 변수 겹침 수."""
        runs = list(shap_by_run.columns)
        rows = []
        for i, a in enumerate(runs):
            for b in runs[i + 1 :]:
                top_a = set(shap_by_run[a].nlargest(TOP_K).index)
                top_b = set(shap_by_run[b].nlargest(TOP_K).index)
                rows.append({"pair": f"{a}·{b}",
                             "spearman": spearmanr(shap_by_run[a], shap_by_run[b]).statistic,
                             "top_overlap": len(top_a & top_b)})  # fmt: skip
        return pd.DataFrame(rows).set_index("pair")

    @staticmethod
    def notes(tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        notes = []
        psi_table = tables["psi"]
        for pair, r in tables["adversarial_runs"].iterrows():
            big = psi_table[pair][psi_table[pair] > 0.25].sort_values(ascending=False)
            notes.append(f"구간 {pair}: 구별 AUC {r['adversarial_auc']:.2f} "
                         f"(공정 변수만 {r['adversarial_auc_process']:.2f}, 기여 상위 {r['top1']}, "
                         f"{r['top2']}, {r['top3']}), PSI 0.25 초과 변수 {len(big)}개 "
                         f"{list(big.index[:3])}")  # fmt: skip
        folds = tables["adversarial_folds"]["adversarial_auc"]
        notes.append(f"② fold별 학습 구간 vs 평가 구간 구별 AUC: 중앙값 {folds.median():.2f}, "
                     f"최소 {folds.min():.2f}")  # fmt: skip
        shap_table = tables["shap_by_run"]
        for run in shap_table.columns:
            top = shap_table[run].nlargest(3)
            notes.append(f"구간 {run} SHAP 상위: "
                         + ", ".join(f"{v} {s:.0%}" for v, s in top.items()))  # fmt: skip
        stab = tables["shap_stability"]
        notes.append(f"구간 사이 SHAP 순위 상관(Spearman) 중앙값 "
                     f"{stab['spearman'].median():.2f}, 상위 {TOP_K}개 겹침 중앙값 "
                     f"{stab['top_overlap'].median():.0f}개")  # fmt: skip
        return tuple(notes)
