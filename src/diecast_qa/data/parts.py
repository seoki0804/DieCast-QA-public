"""shot 테이블을 제품(캐비티) 단위로 펼치고 목표 변수를 붙인다 (2.4, 3.1 순서 4·5)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.config import (
    CAVITIES,
    DEFECT_GROUPS,
    DEFECT_TYPES,
    NORMAL,
    PROCESS_COLS,
    SENSOR_COLS,
    DefectGroup,
)


class DefectLabeler:
    """캐비티 하나의 불량 값(0~3)으로 불량 여부(defect)와 5개 유형(type5)을 정한다."""

    def __init__(self, groups: tuple[DefectGroup, ...] = DEFECT_GROUPS) -> None:
        self.groups = groups

    def label(self, counts: pd.DataFrame) -> pd.DataFrame:
        scores = self.group_scores(counts)
        defect = scores.gt(0).any(axis=1)
        # idxmax는 최댓값이 여럿이면 앞 열을 고르므로, groups의 순서가 그대로 동점 우선순위가 된다
        type5 = scores.idxmax(axis=1).where(defect, NORMAL)
        return pd.DataFrame({"defect": defect.astype(int), "type5": type5}, index=counts.index)

    def group_scores(self, counts: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({g.code: self._score(counts, g) for g in self.groups})

    @staticmethod
    def _score(counts: pd.DataFrame, group: DefectGroup) -> pd.Series:
        values = counts[list(group.members)]
        if group.score == "presence":
            return values.gt(0).sum(axis=1)
        return values.sum(axis=1)


class PartsBuilder:
    """shot 한 행을 캐비티 1·2 두 행으로 복제하고, 각 행에는 그 캐비티의 불량 값만 남긴다."""

    SHOT_COLS = ("id", "order", "run", "Product_Type", "Shot", "is_abnormal",
                 *PROCESS_COLS, *SENSOR_COLS)  # fmt: skip

    def __init__(self, labeler: DefectLabeler | None = None) -> None:
        self.labeler = labeler or DefectLabeler()

    def build(self, shots: pd.DataFrame) -> pd.DataFrame:
        parts = pd.concat([self._cavity_rows(shots, cav) for cav in CAVITIES], ignore_index=True)
        return parts.sort_values(["order", "Cavity"], ignore_index=True)

    def _cavity_rows(self, shots: pd.DataFrame, cavity: int) -> pd.DataFrame:
        base = shots[list(self.SHOT_COLS)].copy()
        base.insert(base.columns.get_loc("Shot") + 1, "Cavity", cavity)
        counts = shots[[f"{t}_{cavity}" for t in DEFECT_TYPES]].set_axis(list(DEFECT_TYPES), axis=1)
        return pd.concat([base, self.labeler.label(counts), counts], axis=1)
