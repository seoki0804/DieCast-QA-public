"""제품 유형별 기초통계 (5장 ②)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import PROCESS_COLS, SENSOR_COLS
from diecast_qa.data import shot_view


class DescriptiveStats(Analysis):
    """제품 유형마다 설정이 달라(2.3) 기초통계도 유형별로 낸다. 공정값은 shot 단위로 센다."""

    name = "descriptive"
    STATS = ("count", "mean", "std", "min", "median", "max")

    def __init__(self, variables: tuple[str, ...] = (*PROCESS_COLS, *SENSOR_COLS)) -> None:
        self.variables = list(variables)

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = shot_view(parts)
        overview = parts.groupby("Product_Type").agg(
            shots=("order", "nunique"),
            parts=("defect", "size"),
            defects=("defect", "sum"),
            defect_rate=("defect", "mean"),
            runs=("run", lambda s: ",".join(map(str, sorted(s.unique())))),
        )

        by_type = shots.groupby("Product_Type")[self.variables]
        stats = by_type.agg(list(self.STATS)).rename_axis(columns=["variable", "stat"])
        table = stats.stack("variable").swaplevel().loc[self.variables]
        table["missing"] = shots[self.variables].isna().groupby(shots["Product_Type"]).sum().stack()

        constant = table.index[table["std"] == 0].tolist()
        median = table["median"].unstack("Product_Type")
        notes = (
            "주조 압력 중앙값 (제품 유형 1 / 2): "
            f"{median.loc['Casting_Pressure', 1]:,.0f} / {median.loc['Casting_Pressure', 2]:,.0f}",
            f"제품 유형 안에서 값이 하나뿐인 변수: {constant or '없음'}",
        )
        return AnalysisResult(self.name, {"overview": overview, "variables": table}, notes)
