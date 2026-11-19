"""부분군 나누기와 Shewhart 관리도 상수."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ShewhartConstants:
    """부분군 크기 n별 관리도 상수 (Montgomery, Introduction to SQC 부록 표)."""

    d2: float
    A2: float
    D3: float
    D4: float

    @classmethod
    def for_size(cls, n: int) -> ShewhartConstants:
        if n not in _TABLE:
            raise ValueError(f"부분군 크기는 2~10만 지원한다: {n}")
        return cls(*_TABLE[n])


_TABLE = {
    2: (1.128, 1.880, 0.0, 3.267),
    3: (1.693, 1.023, 0.0, 2.574),
    4: (2.059, 0.729, 0.0, 2.282),
    5: (2.326, 0.577, 0.0, 2.114),
    6: (2.534, 0.483, 0.0, 2.004),
    7: (2.704, 0.419, 0.076, 1.924),
    8: (2.847, 0.373, 0.136, 1.864),
    9: (2.970, 0.337, 0.184, 1.816),
    10: (3.078, 0.308, 0.223, 1.777),
}


def assign_subgroups(shots: pd.DataFrame, size: int, within: tuple[str, ...] = ()) -> pd.Series:
    """생산 순서대로 size개씩 묶은 부분군 번호(0부터). 다 채우지 못한 군은 -1.

    within에 준 열(예: run)의 값이 바뀌면 새 부분군을 시작한다.
    shots는 생산 순서로 정렬돼 있어야 한다.
    """
    keys = [shots[c] for c in within]
    position = shots.groupby(keys, sort=False).cumcount() if keys else shots.reset_index().index
    block = pd.Series(position, index=shots.index) // size
    grouped = block.groupby([*keys, block], sort=False)
    complete = grouped.transform("size") == size
    ids = pd.Series(-1, index=shots.index)
    ids[complete] = pd.factorize(grouped.ngroup()[complete])[0]
    return ids
