"""불량 유형 파레토 (9장)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import CAVITIES, DEFECT_GROUPS, DEFECT_TYPES


class ParetoAnalysis(Analysis):
    """13개 원본 유형의 건수 순위와 누적 비율.

    건수는 기획서 9장처럼 불량 값의 합이다(같은 불량 2~3개는 2~3건). 그 유형이 나온
    제품 수(parts)도 함께 둔다.
    """

    name = "pareto"

    def __init__(self, vital_share: float = 0.8) -> None:
        # 누적 비율이 이 값에 처음 닿는 유형까지를 상위(vital few) 유형으로 본다
        self.vital_share = vital_share

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        counts = parts[list(DEFECT_TYPES)]
        table = pd.DataFrame({
            "count": counts.sum(),
            "parts": counts.gt(0).sum(),
            **{f"cavity_{c}": counts[parts["Cavity"] == c].sum() for c in CAVITIES},
        }).sort_values("count", ascending=False)  # fmt: skip
        table["share"] = table["count"] / table["count"].sum()
        table["cum_share"] = table["share"].cumsum()
        table["vital"] = table["cum_share"].shift(fill_value=0) < self.vital_share
        group_of = {t: g.code for g in DEFECT_GROUPS for t in g.members}
        table.insert(0, "group", table.index.map(group_of))
        table.index.name = "defect_type"

        defective = parts[parts["defect"] == 1]
        groups = defective["type5"].value_counts().rename("parts").to_frame()
        groups["share"] = groups["parts"] / len(defective)
        groups.index.name = "type5"

        vital = table[table["vital"]]
        stain = table.loc["Stain"]
        notes = (
            f"총 {table['count'].sum():,}건 (제품 단위 유형 발생 {table['parts'].sum():,}건)",
            f"상위 {len(vital)}개 유형 {list(vital.index)} 누적 {vital['cum_share'].iloc[-1]:.1%}",
            f"얼룩 {stain['count']}건 중 캐비티1 {stain['cavity_1']}건",
        )
        return AnalysisResult(self.name, {"types": table, "groups": groups}, notes)
