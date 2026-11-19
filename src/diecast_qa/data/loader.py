"""원본 CSV 읽기 (3.1 순서 1)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from diecast_qa.config import CAVITIES, DEFECT_TYPES, PROCESS_COLS, SENSOR_COLS, SPEC_COLS


class RawDataLoader:
    """KAMP 원본을 읽는다. 헤더 2줄 중 두 번째 줄이 열 이름이고, 일부 열 이름에 공백이 붙어 있다."""

    REQUIRED = (
        "id", "Product_Type", "Shot", *PROCESS_COLS, *SENSOR_COLS, *SPEC_COLS,
        *(f"{t}_{c}" for c in CAVITIES for t in DEFECT_TYPES),
    )  # fmt: skip

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> pd.DataFrame:
        raw = pd.read_csv(self.path, header=1)
        raw.columns = raw.columns.str.strip()
        missing = sorted(set(self.REQUIRED) - set(raw.columns))
        if missing:
            raise ValueError(f"원본에 없는 열: {missing}")
        return raw
