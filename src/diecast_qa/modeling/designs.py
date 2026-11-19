"""검증 방식 (6.3): ① 같은 기간, ② 시간 순서, ③ 주기적 재학습.

각 분할은 평가 데이터와 별도로, 학습 데이터 안의 내부 분할(inner_train/inner_val)을 함께 준다.
판정 임계값은 내부 분할에서만 고른다 (3.2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from diecast_qa.config import SEED

EMPTY = np.array([], dtype=int)


@dataclass(frozen=True)
class Split:
    """parts의 행 위치(iloc) 묶음. fold는 반복 번호(①) 또는 평가 블록 번호(②·③)."""

    fold: int
    train: np.ndarray
    test: np.ndarray
    inner_train: np.ndarray = field(default_factory=lambda: EMPTY)
    inner_val: np.ndarray = field(default_factory=lambda: EMPTY)
    chunk: int = 0


class ValidationDesign(ABC):
    name: ClassVar[str]
    selects_threshold: ClassVar[bool] = True

    @abstractmethod
    def splits(self, parts: pd.DataFrame) -> Iterator[Split]: ...


class SameTermDesign(ValidationDesign):
    """① shot 단위 무작위 80:20 분할을 반복한다. 같은 shot의 두 제품은 항상 같은 쪽에 둔다.

    group을 바꾸면 다른 묶음 기준으로 나눈다 (중복 포함 데이터에서는 원본 행 단위).
    """

    name = "same_term"

    def __init__(
        self, n_repeats: int = 5, test_size: float = 0.2, group: str = "order", seed: int = SEED
    ) -> None:
        self.n_repeats, self.test_size, self.group, self.seed = n_repeats, test_size, group, seed

    def splits(self, parts: pd.DataFrame) -> Iterator[Split]:
        groups = parts[self.group].to_numpy()
        outer = GroupShuffleSplit(self.n_repeats, test_size=self.test_size, random_state=self.seed)
        for fold, (train, test) in enumerate(outer.split(parts, groups=groups), start=1):
            inner = GroupShuffleSplit(1, test_size=self.test_size, random_state=self.seed + fold)
            fit_idx, val_idx = next(inner.split(train, groups=groups[train]))
            yield Split(fold, train, test, train[fit_idx], train[val_idx])


class TimeOrderDesign(ValidationDesign):
    """② 제품 유형마다 생산 순서를 n_blocks개 블록으로 나눈다.

    k번째 블록(k=2..n)을 두 제품 유형에서 함께 평가하고,
    각 유형의 그 이전 블록을 모두 합쳐 학습한다.
    내부 검증 구간은 학습 데이터에서 유형마다 가장 최근 inner_share 비율의 shot이다.
    """

    name = "time_order"

    def __init__(self, n_blocks: int = 5, inner_share: float = 0.2) -> None:
        self.n_blocks, self.inner_share = n_blocks, inner_share

    def blocks(self, parts: pd.DataFrame) -> pd.Series:
        """행마다 소속 블록 번호(1..n_blocks). shot 수가 같도록 나눈다."""
        shots = parts.drop_duplicates("order")[["order", "Product_Type"]]
        position = shots.groupby("Product_Type").cumcount()
        size = shots.groupby("Product_Type")["order"].transform("size")
        block = (position * self.n_blocks // size + 1).set_axis(shots["order"])
        return parts["order"].map(block).rename("block")

    def splits(self, parts: pd.DataFrame) -> Iterator[Split]:
        block = self.blocks(parts).to_numpy()
        for k in range(2, self.n_blocks + 1):
            train = np.flatnonzero(block < k)
            fit_idx, val_idx = recent_split(parts, train, self.inner_share)
            yield Split(k, train, np.flatnonzero(block == k), fit_idx, val_idx)


class RetrainDesign(ValidationDesign):
    """③ 평가 구간(②의 블록 2~5)을 생산 순서대로 every shot씩 끊고, 매번 그 시점 이전에 생산된
    모든 데이터로 다시 학습해 다음 every shot을 예측한다. fold는 ②의 블록 번호다.
    """

    name = "retrain"
    selects_threshold = False

    def __init__(self, every: int, n_blocks: int = 5) -> None:
        self.every = every
        self.time_order = TimeOrderDesign(n_blocks)

    def splits(self, parts: pd.DataFrame) -> Iterator[Split]:
        block = self.time_order.blocks(parts)
        shots = parts.loc[block >= 2, ["order", "Product_Type"]].drop_duplicates("order")
        shots["chunk"] = shots.groupby("Product_Type").cumcount() // self.every
        order = parts["order"].to_numpy()
        for chunk_id, (_, chunk) in enumerate(shots.groupby(["Product_Type", "chunk"])):
            start = chunk["order"].min()
            test = np.flatnonzero(parts["order"].isin(chunk["order"]).to_numpy())
            fold = int(block.iloc[test[0]])
            yield Split(fold, np.flatnonzero(order < start), test, chunk=chunk_id)


def recent_split(parts: pd.DataFrame, idx: np.ndarray, share: float) -> tuple[np.ndarray, ...]:
    """idx 행을 제품 유형마다 생산 순서상 앞쪽(1-share)과 가장 최근 share로 나눈다."""
    rows = parts.iloc[idx]
    cutoff = rows.groupby("Product_Type")["order"].transform(lambda s: s.quantile(1 - share))
    recent = (rows["order"] > cutoff).to_numpy()
    return idx[~recent], idx[recent]
