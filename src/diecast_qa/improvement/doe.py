"""개선 가설을 확인하는 실험 계획 (추가 연구).

관측 데이터에서는 공정 조건과 시기가 함께 바뀌어 원인을 가를 수 없다. 그래서 7단계 관리 범위
후보와 최우수 구간 조건을 요인으로 하는 2수준 부분요인실험(2^(4-1), 해상도 IV)을 제안한다.
요인 4개의 주효과는 2요인 교호작용과 섞이지 않는다.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import CONTROL_VARS, SEED, VARIABLE_LABELS
from diecast_qa.data import shot_view
from diecast_qa.improvement.levers import candidate_ranges, golden_runs


def half_fraction(k: int = 4) -> pd.DataFrame:
    """2^(k-1) 설계: 앞 k-1개 요인은 완전요인, 마지막 요인 = 나머지의 곱 (정의 관계 I = AB…K)."""
    base = np.array(list(itertools.product([-1, 1], repeat=k - 1)))
    return pd.DataFrame(np.c_[base, base.prod(axis=1)], columns=[f"F{i + 1}" for i in range(k)])


def parts_per_run(p_current: float, reduction: float, runs: int, alpha: float = 0.05,
                  power: float = 0.8) -> int:  # fmt: skip
    """주효과 하나(절반 조건 vs 나머지 절반)로 불량률 상대 감소 reduction을 찾는 데 필요한
    조건당 제품 수 (두 비율 비교, 양측 α). 생산 순서 자기상관은 반영하지 않으므로 하한이다."""
    effect = proportion_effectsize(p_current, p_current * (1 - reduction))
    per_half = NormalIndPower().solve_power(effect, alpha=alpha, power=power, ratio=1.0)
    return int(np.ceil(per_half / (runs / 2)))


class ExperimentPlan(Analysis):
    """제품 유형별 요인·수준과 2^(4-1) 실험 순서, 조건당 필요 생산량."""

    name = "doe"

    def __init__(self, proposals: pd.DataFrame, n_factors: int = 4,
                 target_reduction: float = 0.3) -> None:  # fmt: skip
        self.ranges = candidate_ranges(proposals)
        self.n_factors = n_factors
        self.target_reduction = target_reduction

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        clean = parts[~parts["is_abnormal"]]
        factors = self._factors(shot_view(clean).reset_index())
        rates = clean.groupby("Product_Type")["defect"].mean()
        tables = {"factors": factors}
        for ptype, f in factors.groupby(level="Product_Type"):
            tables[f"design_type{ptype}"] = self._design(f.droplevel("Product_Type"), rates[ptype])
        return AnalysisResult(self.name, tables, self.notes(tables))

    def _factors(self, shots: pd.DataFrame) -> pd.DataFrame:
        """관리 범위 후보를 먼저, 남은 자리는 최우수·최악 구간의 표준화 차이가 큰 변수로.

        수준: 관리 범위 변수는 범위 밖 shot의 중앙값(현재) vs 범위 안 shot의 중앙값(개선안),
        구간 조건 변수는 최악 구간 중앙값(현재) vs 최우수 구간 중앙값(개선안)."""
        rows = []
        for ptype, (best, worst) in golden_runs(shots).items():
            g = shots[shots["Product_Type"] == ptype]
            for r in self.ranges.get(ptype, [])[: self.n_factors]:
                inside = r.contains(g[r.variable])
                rows.append({"Product_Type": ptype, "variable": r.variable,
                             "source": f"관리 범위 {r.label()}",
                             "current": g.loc[~inside, r.variable].median(),
                             "improved": g.loc[inside, r.variable].median()})  # fmt: skip
            chosen = {row["variable"] for row in rows if row["Product_Type"] == ptype}
            controls = list(CONTROL_VARS)
            within = g.groupby("run")[controls].std().pow(2).mean().pow(0.5)
            medians = g.groupby("run")[controls].median()
            diff = ((medians.loc[best] - medians.loc[worst]) / within).dropna()
            ranked = diff.drop(list(chosen), errors="ignore").abs().sort_values(ascending=False)
            for v in ranked.index[: self.n_factors - len(chosen)]:
                rows.append({"Product_Type": ptype, "variable": v,
                             "source": f"최우수 구간 {best} vs 최악 구간 {worst}",
                             "current": medians.loc[worst, v],
                             "improved": medians.loc[best, v]})  # fmt: skip
        table = pd.DataFrame(rows)
        table.insert(2, "label", table["variable"].map(VARIABLE_LABELS))
        table["factor"] = table.groupby("Product_Type").cumcount().map(lambda i: f"F{i + 1}")
        return table.set_index(["Product_Type", "factor"])

    def _design(self, factors: pd.DataFrame, defect_rate: float) -> pd.DataFrame:
        """코드값(-1 현재, +1 개선안)과 실제 설정값, 무작위 실행 순서, 조건당 필요 생산량."""
        coded = half_fraction(len(factors))
        design = coded.copy()
        for factor, row in factors.iterrows():
            design[row["variable"]] = np.where(coded[factor] > 0, row["improved"], row["current"])
        n = parts_per_run(defect_rate, self.target_reduction, len(design))
        design.insert(0, "standard_order", np.arange(1, len(design) + 1))
        design["run_order"] = np.random.default_rng(SEED).permutation(len(design)) + 1
        design["parts_per_run"] = n
        design["shots_per_run"] = int(np.ceil(n / 2))
        return design.sort_values("run_order").set_index("run_order")

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        notes = []
        for ptype, f in tables["factors"].groupby(level="Product_Type"):
            d = tables[f"design_type{ptype}"]
            notes.append(
                f"유형 {ptype} 요인: " + ", ".join(
                    f"{r.label} {r.current:.4g}→{r.improved:.4g}" for r in f.itertuples())
                + f". 2^({len(f)}-1) = {len(d)}개 조건, 조건당 {d['shots_per_run'].iloc[0]} shot "
                f"(불량률 {self.target_reduction:.0%} 감소를 검정력 80%로 찾는 최소량), 총 "
                f"{d['shots_per_run'].sum()} shot"
            )  # fmt: skip
        notes.append("조건 순서는 무작위(seed 42). 같은 날·같은 금형 상태에서 연속으로 진행하면 "
                     "시기·환경 효과를 줄일 수 있다")  # fmt: skip
        return tuple(notes)
