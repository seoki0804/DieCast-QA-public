"""제품 테이블에 변수를 덧붙이는 단계의 공통 인터페이스 (3.1 순서 7·8, 3.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd
from pandas.core.groupby import DataFrameGroupBy, SeriesGroupBy


class FeatureBuilder(ABC):
    """생산 구간(run) 안에서, 각 shot 시점에 알 수 있는 정보만으로 변수를 만든다.

    입력은 order·Cavity 순으로 정렬된 제품 테이블이다. 공정값은 shot마다 같으므로
    (run, Cavity)로 묶으면 각 묶음이 그 구간의 shot 순서를 그대로 따른다.
    """

    @property
    @abstractmethod
    def names(self) -> list[str]:
        """추가하는 열 이름. 모델 단계에서 변수 묶음으로 쓴다."""

    @abstractmethod
    def transform(self, parts: pd.DataFrame) -> pd.DataFrame:
        """parts에 names 열을 덧붙인 새 DataFrame을 돌려준다."""

    @staticmethod
    def past_mean(grouped: SeriesGroupBy | DataFrameGroupBy, window: int) -> pd.DataFrame:
        """현재 shot을 빼고 직전 window개 shot의 평균. 구간 첫 shot은 결측."""
        return grouped.transform(lambda s: s.shift().rolling(window, min_periods=1).mean())
