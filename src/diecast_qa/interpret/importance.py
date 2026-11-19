"""SHAP 변수 중요도와 개별 판정 근거 (5장 ⑦, 3.3 shap_values.csv)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import spearmanr

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import CAUSE_CATEGORIES, VARIABLE_LABELS
from diecast_qa.interpret.explain import ProductTypeModel, fit_by_product_type

MODEL_NAME = "xgb_interp"
# 원인이라기보다 생산 시기를 나타내는 변수: 환경(공장 온습도)과 shot 순번
PERIOD_MARKERS = ("Factory_Temp", "Factory_Humidity", "Shot")
GROUPS = {**{v: c for c, members in CAUSE_CATEGORIES.items() for v in members}, "Shot": "순번"}


class ShapAnalysis(Analysis):
    """제품 유형별 해석용 모델의 SHAP 중요도·방향, 제품별 SHAP 값, 고위험 제품의 판정 근거."""

    name = "shap"

    def __init__(self, top_n: int = 5, example_vars: int = 8) -> None:
        self.top_n = top_n
        self.example_vars = example_vars

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        models = fit_by_product_type(parts)
        checks = pd.DataFrame([self._model_check(m) for m in models.values()])
        tables = {
            "importance": pd.concat([self._importance(m) for m in models.values()]),
            "model": checks.set_index("Product_Type"),
            "examples": pd.concat([self._example(m) for m in models.values()], ignore_index=True),
            "values": pd.concat([self._values(m) for m in models.values()], ignore_index=True),
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    @staticmethod
    def _importance(m: ProductTypeModel) -> pd.DataFrame:
        """변수별 평균 |SHAP| 비중과 방향(값과 SHAP의 Spearman 상관: 양수면 클수록 위험)."""
        direction = [spearmanr(m.X[v], m.shap_values[:, i]).statistic
                     for i, v in enumerate(m.features)]  # fmt: skip
        table = pd.DataFrame({
            "label": [VARIABLE_LABELS[v] for v in m.features],
            "group": [GROUPS.get(v, "") for v in m.features],
            "share": np.abs(m.shap_values).mean(axis=0) / np.abs(m.shap_values).mean(axis=0).sum(),
            "direction": direction,
        }, index=pd.Index(m.features, name="variable"))  # fmt: skip
        table["rank"] = table["share"].rank(ascending=False).astype(int)
        return pd.concat({m.product_type: table.sort_values("rank")}, names=["Product_Type"])

    @staticmethod
    def _model_check(m: ProductTypeModel) -> dict:
        return {"Product_Type": m.product_type, "parts": len(m.y), "defect_rate": m.y.mean(),
                "mean_p_defect": m.proba().mean(), "cv_roc_auc": m.cv_auc()}  # fmt: skip

    def _example(self, m: ProductTypeModel) -> pd.DataFrame:
        """가장 위험도가 높은 불량 제품 한 개의 판정 근거: |SHAP| 상위 변수와 나머지 합."""
        p = m.proba()
        i = int(np.argmax(np.where(m.y == 1, p, -1)))
        contrib = pd.Series(m.shap_values[i], index=m.features)
        top = contrib.abs().nlargest(self.example_vars).index
        rest = contrib.drop(top)
        order, cavity = m.X.index[i]
        rows = pd.DataFrame({"variable": [*top, "rest"],
                             "value": [*m.X.iloc[i][top], np.nan],
                             "shap": [*contrib[top], rest.sum()]})  # fmt: skip
        rows.insert(0, "Product_Type", m.product_type)
        return rows.assign(order=order, Cavity=cavity, p_defect=p[i], base_p=expit(m.shap_base),
                           n_rest=len(rest))  # fmt: skip

    @staticmethod
    def _values(m: ProductTypeModel) -> pd.DataFrame:
        """3.3 shap_values.csv: 제품마다 변수별 SHAP(log-odds, 열 이름 shap_변수).

        base_value + SHAP 합 = logit(p_defect).
        """
        meta = pd.DataFrame({"Product_Type": m.product_type, "model": MODEL_NAME, "defect": m.y,
                             "p_defect": m.proba(), "base_value": m.shap_base},
                            index=m.X.index)  # fmt: skip
        shap = pd.DataFrame(m.shap_values, columns=[f"shap_{v}" for v in m.features],
                            index=m.X.index)  # fmt: skip
        return pd.concat([meta, shap], axis=1).reset_index()

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        notes = []
        for ptype, imp in tables["importance"].groupby(level="Product_Type"):
            imp = imp.droplevel("Product_Type")
            check = tables["model"].loc[ptype]
            marker = imp.loc[list(PERIOD_MARKERS), "share"].sum()
            notes.append(
                f"제품 유형 {ptype} (해석용 XGBoost, 5-fold ROC-AUC {check['cv_roc_auc']:.2f}) "
                f"SHAP 상위 {self.top_n}: "
                + ", ".join(f"{r.label} {r.share:.0%}{'↑' if r.direction > 0 else '↓'}"
                            for r in imp.head(self.top_n).itertuples())
                + f". 환경·순번 변수(공장 온습도, shot 순번) 합 {marker:.0%}, "
                f"캐비티 {imp.loc['Cavity', 'share']:.0%}"
            )  # fmt: skip
        for ptype, ex in tables["examples"].groupby("Product_Type"):
            first = ex.iloc[0]
            top = ex[ex["variable"] != "rest"].head(3)
            notes.append(
                f"판정 근거 예시 (제품 유형 {ptype}, order {first['order']}·캐비티 "
                f"{first['Cavity']}, 불량 확률 {first['p_defect']:.0%}, "
                f"평균 {first['base_p']:.0%}): "
                + ", ".join(f"{VARIABLE_LABELS[r.variable]}={r.value:.4g} ({r.shap:+.2f})"
                            for r in top.itertuples())
            )  # fmt: skip
        notes.append("화살표: ↑ 값이 클수록 불량 위험 증가, ↓ 값이 작을수록 증가 "
                     "(변수 값과 SHAP의 순위 상관)")  # fmt: skip
        return tuple(notes)
