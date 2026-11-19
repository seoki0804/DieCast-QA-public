"""분석 단계(탐색 분석·공정 안정성 등)의 공통 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pandas as pd


@dataclass(frozen=True)
class AnalysisResult:
    """분석 하나의 결과: 저장할 표와 보고서에 옮길 요약 문장."""

    name: str
    tables: dict[str, pd.DataFrame]
    notes: tuple[str, ...] = ()

    def without(self, *keys: str) -> AnalysisResult:
        """keys 표를 뺀 결과 (다른 위치에 따로 저장하는 큰 표 등)."""
        return AnalysisResult(self.name, {k: v for k, v in self.tables.items() if k not in keys},
                              self.notes)  # fmt: skip

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for key, table in self.tables.items():
            table.to_csv(out_dir / f"{self.name}_{key}.csv", float_format="%.6g")


class Analysis(ABC):
    """제품 테이블(parts.csv)을 받아 AnalysisResult를 만든다."""

    name: ClassVar[str]

    @abstractmethod
    def run(self, parts: pd.DataFrame) -> AnalysisResult: ...
