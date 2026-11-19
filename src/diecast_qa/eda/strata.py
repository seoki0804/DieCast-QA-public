"""층별 불량률과 독립성 검정 (9장 층별 검정)."""

from __future__ import annotations

import pandas as pd
from statsmodels.stats.contingency_tables import StratifiedTable

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.eda.stats import chi_square_test, format_p


class StratifiedRates(Analysis):
    """캐비티·제품 유형·생산 구간별 제품 불량률.

    캐비티 차이가 구간이나 제품 유형 차이 때문인지 보려고 Cochran-Mantel-Haenszel 검정을 더한다.
    """

    name = "strata"
    FACTORS = ("Cavity", "Product_Type", "run")

    def __init__(self, min_parts: int = 50) -> None:
        # 제품 수가 이보다 적은 층(구간 6, 8개)은 검정에서 뺀다
        self.min_parts = min_parts

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        rates = pd.concat(
            {f: self._rates(parts, f) for f in self.FACTORS}, names=["factor", "level"]
        )
        tables = {
            "rates": rates,
            "run_cavity": self._rates(parts, ["run", "Product_Type", "Cavity"]).unstack("Cavity"),
            "type_cavity": self._rates(parts, ["Product_Type", "Cavity"]).unstack("Cavity"),
            "chi_square": pd.DataFrame(
                {f: chi_square_test(self._crosstab(parts, f)) for f in self.FACTORS}
            ).T.rename_axis("factor"),
            "cmh": pd.DataFrame(
                {s: self._cmh(parts, s) for s in ("run", "Product_Type")}
            ).T.rename_axis("stratum"),
        }
        return AnalysisResult(self.name, tables, self._notes(tables))

    @staticmethod
    def _rates(parts: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
        return parts.groupby(by)["defect"].agg(n="size", defects="sum", rate="mean")

    def _crosstab(self, parts: pd.DataFrame, factor: str) -> pd.DataFrame:
        table = pd.crosstab(parts[factor], parts["defect"])
        return table[table.sum(axis=1) >= self.min_parts]

    def _cmh(self, parts: pd.DataFrame, stratum: str) -> dict:
        """층마다 캐비티1 대 캐비티2의 2×2 표(행: 캐비티 1·2, 열: 불량·양품)를 합친다."""
        tables = [
            pd.crosstab(g["Cavity"], g["defect"])
            .reindex(index=[1, 2], columns=[1, 0], fill_value=0)
            .to_numpy()
            for _, g in parts.groupby(stratum)
            if len(g) >= self.min_parts
        ]
        pooled = StratifiedTable(tables)
        low, high = pooled.oddsratio_pooled_confint()
        return {
            "strata": len(tables),
            "pooled_odds_ratio": pooled.oddsratio_pooled,
            "ci_low": low,
            "ci_high": high,
            "p_value": pooled.test_null_odds(correction=True).pvalue,
            # Breslow-Day: 층마다 오즈비가 같은지 (작으면 캐비티 효과 크기가 층마다 다름)
            "homogeneity_p": pooled.test_equal_odds().pvalue,
        }

    @staticmethod
    def _notes(tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        cav = tables["rates"].loc["Cavity", "rate"]
        chi = tables["chi_square"]
        cmh = tables["cmh"].loc["run"]
        run_rates = tables["rates"].loc["run", "rate"]
        return (
            f"캐비티1 {cav[1]:.1%} vs 캐비티2 {cav[2]:.1%} "
            f"(χ² {format_p(chi.loc['Cavity', 'p_value'])}, "
            f"V={chi.loc['Cavity', 'cramers_v']:.2f})",
            f"구간을 통제한 캐비티1 불량 오즈비 {cmh['pooled_odds_ratio']:.2f} "
            f"[{cmh['ci_low']:.2f}, {cmh['ci_high']:.2f}], CMH {format_p(cmh['p_value'])}, "
            f"구간별 오즈비 동질성 {format_p(cmh['homogeneity_p'])}",
            "구간별 불량률 " + ", ".join(f"{k}:{v:.1%}" for k, v in run_rates.items())
            + f" (χ² V={chi.loc['run', 'cramers_v']:.2f})",
        )  # fmt: skip
