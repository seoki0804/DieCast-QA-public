"""정상/불량 shot의 공정·센서 변수 비교 (5장 ②)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import CAUSE_CATEGORIES, PROCESS_COLS, SENSOR_COLS
from diecast_qa.data import shot_view
from diecast_qa.eda.stats import (
    hedges_g,
    rank_biserial,
    rank_biserial_by_group,
    weighted_effect,
)


class ProcessComparison(Analysis):
    """제품 유형별로, 불량이 나온 shot과 정상 shot의 변수 분포를 비교한다.

    공정값은 shot 단위로 같으므로 shot 하나를 관측치 하나로 센다
    (불량 제품이 하나라도 있으면 불량 shot).
    구간마다 불량률과 공정 조건이 함께 달라지므로, 전체 비교(rank_biserial) 외에 같은 구간 안에서만
    비교한 효과 크기(rank_biserial_within)를 함께 낸다. 둘의 차이가 크면 그 변수는 원인이라기보다
    시기를 나타내는 표시일 가능성이 크다. 생산 순서에 따른 자기상관 때문에 p-value는 실제보다 작게
    나오므로 효과 크기를 중심으로 해석한다.
    """

    name = "process_compare"
    EFFECT_COLS = ("hedges_g", "rank_biserial", "p_welch", "p_mwu")

    def __init__(
        self,
        variables: tuple[str, ...] = (*PROCESS_COLS, *SENSOR_COLS),
        exclude_abnormal: bool = True,
        min_group: int = 10,
        top_n: int = 5,
    ) -> None:
        self.variables = list(variables)
        self.exclude_abnormal = exclude_abnormal
        # 구간 내 비교에서 불량·정상 shot이 각각 이보다 적은 구간은 뺀다
        self.min_group = min_group
        self.top_n = top_n

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = shot_view(parts)
        if self.exclude_abnormal:
            shots = shots[~shots["is_abnormal"]]

        frames = [self._compare(group, ptype) for ptype, group in shots.groupby("Product_Type")]
        table = pd.concat(frames, ignore_index=True)
        category = {v: c for c, members in CAUSE_CATEGORIES.items() for v in members}
        table.insert(2, "category", table["variable"].map(category))

        notes = tuple(
            f"제품 유형 {ptype} 효과 크기 상위 {self.top_n}개 (전체 → 구간 내 rank-biserial): "
            + ", ".join(f"{r.variable} {r.rank_biserial:+.2f}→{r.rank_biserial_within:+.2f}"
                        for r in g.head(self.top_n).itertuples())
            for ptype, g in table.groupby("Product_Type")
        )  # fmt: skip
        return AnalysisResult(self.name, {"tests": table}, notes)

    def _compare(self, shots: pd.DataFrame, product_type: int) -> pd.DataFrame:
        table = pd.DataFrame(
            [{"variable": v, **self._split_compare(shots, v), "rank_biserial_within":
              self._within_run_effect(shots, v)} for v in self.variables]
        )  # fmt: skip
        table.insert(0, "Product_Type", product_type)

        tested = table["p_mwu"].notna()
        for col in ("p_welch", "p_mwu"):
            table.loc[tested, f"{col}_holm"] = multipletests(table.loc[tested, col], method="holm")[
                1
            ]
        return table.sort_values("rank_biserial", key=np.abs, ascending=False, ignore_index=True)

    @classmethod
    def _split_compare(cls, shots: pd.DataFrame, variable: str) -> dict:
        bad, good = cls._split(shots, variable)
        row = {
            "n_defect": len(bad),
            "n_normal": len(good),
            "mean_defect": bad.mean(),
            "mean_normal": good.mean(),
            "median_defect": np.median(bad),
            "median_normal": np.median(good),
        }
        if np.unique(np.concatenate([bad, good])).size < 2:
            return row | dict.fromkeys(cls.EFFECT_COLS, np.nan)
        u = stats.mannwhitneyu(bad, good)
        return row | {
            "hedges_g": hedges_g(bad, good),
            "rank_biserial": rank_biserial(u.statistic, len(bad), len(good)),
            "p_welch": stats.ttest_ind(bad, good, equal_var=False).pvalue,
            "p_mwu": u.pvalue,
        }

    def _within_run_effect(self, shots: pd.DataFrame, variable: str) -> float:
        """구간별 rank-biserial을 비교 쌍 수(n_불량 × n_정상)로 가중 평균한다."""
        by_run = rank_biserial_by_group(shots[variable], shots["shot_defect"] == 1, shots["run"],
                                        self.min_group)  # fmt: skip
        return weighted_effect(by_run)

    @staticmethod
    def _split(shots: pd.DataFrame, variable: str) -> tuple[np.ndarray, np.ndarray]:
        values = shots[variable]
        is_bad = shots["shot_defect"] == 1
        return (values[is_bad].dropna().to_numpy(float), values[~is_bad].dropna().to_numpy(float))
