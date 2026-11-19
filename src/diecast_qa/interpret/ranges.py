"""변수별 관리 범위(안): PDP로 범위를 찾고, 생산 구간 안에서 실제 불량률로 검증한다 (5장 ⑦).

2단계에서 정상/불량 공정값 차이가 대부분 구간(시기) 사이 차이였으므로, 전체 데이터로 학습한
모델의 PDP 범위는 '불량이 많던 시기의 설정값'을 가리킬 수 있다. 그래서 범위마다
같은 구간 안에서도 범위 밖 shot의 불량률이 더 높은지(Mantel-Haenszel 오즈비)를 확인하고,
앞 60% 기간으로 찾은 범위가 뒤 40% 기간에도 맞는지 본다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import StratifiedTable

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import CAUSE_CATEGORIES, SEED, VARIABLE_LABELS
from diecast_qa.data import shot_view
from diecast_qa.interpret.dependence import DependenceCurve, dependence, quantile_grid
from diecast_qa.interpret.explain import ProductTypeModel, fit_by_product_type

CATEGORY = {v: c for c, members in CAUSE_CATEGORIES.items() for v in members}

VERDICTS = {
    "candidate": "관리 범위 후보",
    "not_supported": "구간 안에서 차이 없음",
    "untestable": "구간 안 변동이 작아 검증 불가",
    "no_range": "불량 확률 변화 작음",
}


@dataclass(frozen=True)
class OperatingRange:
    """관리 범위. 격자 끝에 닿은 쪽은 한계가 없다(open)."""

    variable: str
    low: float
    high: float
    open_low: bool = False
    open_high: bool = False

    def contains(self, values: pd.Series) -> pd.Series:
        low = -np.inf if self.open_low else self.low
        high = np.inf if self.open_high else self.high
        return values.between(low, high)

    def label(self) -> str:
        if self.open_low:
            return f"≤ {self.high:.4g}"
        if self.open_high:
            return f"≥ {self.low:.4g}"
        return f"{self.low:.4g} ~ {self.high:.4g}"


def low_risk_range(
    curve: DependenceCurve, reference: float, min_effect: float = 0.02
) -> OperatingRange | None:
    """PDP가 평균 예측 확률(reference) 이하인 연속 구간 중 가장 넓은 것(격자 점 수 기준).

    격자가 분위수라 격자 점 수는 그 범위에 든 생산량에 비례한다. PDP 폭이 min_effect보다 작거나
    전 구간이 낮으면 범위를 정할 이유가 없으므로 None.
    """
    if curve.amplitude < min_effect:
        return None
    low = np.r_[False, curve.pdp <= reference, False].astype(int)
    starts, ends = np.flatnonzero(np.diff(low) == 1), np.flatnonzero(np.diff(low) == -1) - 1
    if len(starts) == 0:
        return None
    i, j = max(zip(starts, ends, strict=True),
               key=lambda r: (r[1] - r[0], -curve.pdp[r[0] : r[1] + 1].mean()))  # fmt: skip
    last = len(curve.grid) - 1
    if i == 0 and j == last:
        return None
    return OperatingRange(curve.variable, float(curve.grid[i]), float(curve.grid[j]),
                          open_low=bool(i == 0), open_high=bool(j == last))  # fmt: skip


def run_variance_share(values: pd.Series, runs: pd.Series) -> float:
    """변수 분산 중 생산 구간 사이 차이로 설명되는 비율(η²). 1에 가까우면 구간마다 값이 고정."""
    within = values - values.groupby(runs).transform("mean")
    return float(1 - within.var() / values.var())


def _table(outside: pd.Series, bad: pd.Series) -> np.ndarray:
    """2×2: 행 = 범위 밖·안, 열 = 불량·정상 shot."""
    return np.array([[(outside & bad).sum(), (outside & ~bad).sum()],
                     [(~outside & bad).sum(), (~outside & ~bad).sum()]])  # fmt: skip


def _odds_ratio(table: np.ndarray) -> float:
    """범위 밖 대 범위 안의 불량 오즈비 (빈 칸은 0.5 보정). 1보다 크면 범위 밖이 더 위험."""
    (a, b), (c, d) = table + 0.5
    return float(a * d / (b * c))


@dataclass(frozen=True)
class RangeCheck:
    """관리 범위 안/밖 shot의 불량률 비교 (shot 단위, 비정상 shot 제외).

    구간 안 검정은 shot이 min_shots 이상이고 범위 안·밖이 각각 min_group 이상인 구간만 쓴다.
    생산 순서 자기상관 때문에 p-value와 신뢰구간은 실제보다 좁게 나오므로, 구간마다 같은 방향인지를
    함께 본다.
    """

    min_shots: int = 50
    min_group: int = 10

    def evaluate(self, shots: pd.DataFrame, rng: OperatingRange) -> dict:
        s = shots.dropna(subset=[rng.variable])
        outside = ~rng.contains(s[rng.variable])
        bad = s["shot_defect"] == 1
        row = {"in_share": float((~outside).mean()), "rate_in": float(bad[~outside].mean()),
               "rate_out": float(bad[outside].mean()),
               "odds_ratio": _odds_ratio(_table(outside, bad))}  # fmt: skip
        tables = [
            _table(outside[g.index], bad[g.index])
            for _, g in s.groupby("run")
            if len(g) >= self.min_shots
            and min(outside[g.index].sum(), (~outside[g.index]).sum()) >= self.min_group
        ]
        row |= {"runs_tested": len(tables),
                "runs_agree": int(sum(_odds_ratio(t) > 1 for t in tables))}  # fmt: skip
        if tables:
            pooled = StratifiedTable(tables)
            low, high = pooled.oddsratio_pooled_confint()
            row |= {"cmh_or": pooled.oddsratio_pooled, "cmh_low": low, "cmh_high": high,
                    "cmh_p": pooled.test_null_odds(correction=True).pvalue}  # fmt: skip
        return row

    @staticmethod
    def verdict(row: dict) -> str:
        if "range_label" not in row:
            return "no_range"
        if row["runs_tested"] < 2:
            return "untestable"
        if row["cmh_low"] > 1 and row["runs_agree"] > row["runs_tested"] / 2:
            return "candidate"
        return "not_supported"


def early_part(parts: pd.DataFrame, share: float) -> pd.DataFrame:
    """생산 순서상 앞쪽 share 비율의 shot (제품 유형 하나 안에서)."""
    orders = np.sort(parts["order"].unique())
    return parts[parts["order"] < orders[int(len(orders) * share)]]


class ControlRangeAnalysis(Analysis):
    """제품 유형마다 SHAP 상위 조정 가능 변수의 PDP·ICE, 관리 범위(안)와 검증."""

    name = "ranges"

    def __init__(self, n_candidates: int = 8, min_effect: float = 0.02, early_share: float = 0.6,
                 ice_rows: int = 60, check: RangeCheck = RangeCheck()) -> None:  # fmt: skip
        self.n_candidates = n_candidates
        self.min_effect = min_effect
        self.early_share = early_share
        self.ice_rows = ice_rows
        self.check = check

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = shot_view(parts)
        shots = shots[~shots["is_abnormal"]]
        rows, pdp, ice = [], [], []
        for ptype, model in fit_by_product_type(parts).items():
            type_parts = parts[parts["Product_Type"] == ptype]
            type_shots = shots[shots["Product_Type"] == ptype]
            early = fit_by_product_type(early_part(type_parts, self.early_share))[ptype]
            sample = np.random.default_rng(SEED).choice(len(model.X), self.ice_rows, replace=False)
            share = model.importance()
            for variable in model.candidates(self.n_candidates):
                curve = self._curve(model, variable)
                row = {"Product_Type": ptype, "variable": variable,
                       "label": VARIABLE_LABELS[variable], "category": CATEGORY.get(variable, ""),
                       "shap_share": share[variable],
                       "run_variance_share": run_variance_share(type_shots[variable],
                                                                type_shots["run"]),
                       **self._range(curve, model.reference(), type_shots),
                       **self._later_check(early, variable, type_shots)}  # fmt: skip
                rows.append(row)
                pdp.append(pd.DataFrame({"Product_Type": ptype, "variable": variable,
                                         "value": curve.grid, "pdp": curve.pdp}))  # fmt: skip
                ice.append(pd.DataFrame({
                    "Product_Type": ptype, "variable": variable,
                    "row": np.repeat(sample, len(curve.grid)),
                    "value": np.tile(curve.grid, len(sample)),
                    "p_defect": curve.ice[sample].ravel(),
                }))  # fmt: skip
        tables = {
            "proposals": pd.DataFrame(rows).set_index(["Product_Type", "variable"]),
            "pdp": pd.concat(pdp, ignore_index=True),
            "ice": pd.concat(ice, ignore_index=True),
        }
        return AnalysisResult(self.name, tables, self.notes(tables["proposals"]))

    @staticmethod
    def _curve(model: ProductTypeModel, variable: str) -> DependenceCurve:
        return dependence(model.model, model.X, variable, quantile_grid(model.X[variable]))

    def _range(self, curve: DependenceCurve, reference: float, shots: pd.DataFrame) -> dict:
        row = {"reference": reference, "pdp_min": curve.pdp.min(), "pdp_max": curve.pdp.max()}
        rng = low_risk_range(curve, reference, self.min_effect)
        if rng is not None:
            row |= {"range_low": None if rng.open_low else rng.low,
                    "range_high": None if rng.open_high else rng.high,
                    "range_label": rng.label(), **self.check.evaluate(shots, rng)}  # fmt: skip
        return row | {"verdict": self.check.verdict(row)}

    def _later_check(self, early: ProductTypeModel, variable: str, shots: pd.DataFrame) -> dict:
        """앞 기간 모델로 찾은 범위를 뒤 기간 shot에서 검증한다."""
        later = shots[shots.index > early.X.index.get_level_values("order").max()]
        row = self._range(self._curve(early, variable), early.reference(), later)
        keep = ("range_label", "in_share", "odds_ratio", "runs_tested", "cmh_or", "verdict")
        return {f"later_{k}": row[k] for k in keep if k in row}

    def notes(self, ranges: pd.DataFrame) -> tuple[str, ...]:
        notes = []
        for ptype, g in ranges.groupby(level="Product_Type"):
            g = g.droplevel("Product_Type")
            counts = g["verdict"].map(VERDICTS).value_counts()
            notes.append(f"제품 유형 {ptype}: SHAP 상위 조정 가능 변수 {len(g)}개 → "
                         + ", ".join(f"{k} {v}개" for k, v in counts.items()))  # fmt: skip
            for variable, r in g.iterrows():
                text = f"유형 {ptype} · {r['label']}({variable}): {VERDICTS[r['verdict']]}"
                if r["verdict"] != "no_range":
                    text += (f", 범위 {r['range_label']} (shot {r['in_share']:.0%}), 불량률 안 "
                             f"{r['rate_in']:.1%} / 밖 {r['rate_out']:.1%}, 구간 무시 오즈비 "
                             f"{r['odds_ratio']:.2f}")  # fmt: skip
                if pd.notna(r.get("cmh_or")):
                    text += (f", 구간 안 오즈비 {r['cmh_or']:.2f} ({r['cmh_low']:.2f}~"
                             f"{r['cmh_high']:.2f}, 같은 방향 {r['runs_agree']:.0f}/"
                             f"{r['runs_tested']:.0f}개 구간)")  # fmt: skip
                text += f", 구간 간 분산 비율 {r['run_variance_share']:.0%}"
                if isinstance(r.get("later_verdict"), str):
                    text += (f" | 뒤 {1 - self.early_share:.0%} 기간 검증: "
                             f"{VERDICTS[r['later_verdict']]}")  # fmt: skip
                notes.append(text)
        return tuple(notes)
