"""불량 유형 구성의 층별 차이 (2.5)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import DEFECT_GROUPS
from diecast_qa.eda.stats import chi_square_test, format_p


class TypeMixAnalysis(Analysis):
    """불량 제품의 2단계 유형 구성이 제품 유형·캐비티·구간에 따라 다른지.

    2단계 모델의 시간 순서 성능이 낮은 원인(유형 분포 변화)을 검정으로 확인한다.
    """

    name = "type_mix"
    FACTORS = ("Product_Type", "Cavity", "run")

    def __init__(self, min_defects: int = 20) -> None:
        # 불량 제품이 이보다 적은 층(구간 3: 5개, 구간 6: 2개)은 검정에서 뺀다
        self.min_defects = min_defects

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        defective = parts[parts["defect"] == 1]
        order = [g.code for g in DEFECT_GROUPS]
        tables = {
            f"by_{f}": pd.crosstab(defective[f], defective["type5"]).reindex(
                columns=order, fill_value=0
            )
            for f in self.FACTORS
        }
        tests = pd.DataFrame(
            {f: chi_square_test(self._testable(tables[f"by_{f}"])) for f in self.FACTORS}
        ).T.rename_axis("factor")
        tables["chi_square"] = tests

        notes = tuple(
            f"유형 구성 × {f}: χ² {format_p(row.p_value)}, Cramér's V={row.cramers_v:.2f}"
            for f, row in tests.iterrows()
        )
        return AnalysisResult(self.name, tables, notes)

    def _testable(self, table: pd.DataFrame) -> pd.DataFrame:
        table = table[table.sum(axis=1) >= self.min_defects]
        return table.loc[:, table.sum() > 0]
