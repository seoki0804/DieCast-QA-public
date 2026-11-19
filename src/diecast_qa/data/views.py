"""정제 데이터(parts.csv)를 읽고 분석 단위에 맞게 다시 묶는다."""

from __future__ import annotations

import pandas as pd

from diecast_qa.config import Paths


def load_parts(paths: Paths | None = None) -> pd.DataFrame:
    return pd.read_csv((paths or Paths()).parts_csv)


def shot_view(parts: pd.DataFrame) -> pd.DataFrame:
    """제품 테이블 → shot 테이블. 공정·센서 값은 shot마다 같으므로 첫 행을 쓴다.

    n_defect: 그 shot에서 나온 불량 제품 수(0~2), shot_defect: 하나라도 불량이면 1.
    """
    shots = parts.drop_duplicates("order").set_index("order").drop(columns=["Cavity"])
    shots["n_defect"] = parts.groupby("order")["defect"].sum()
    shots["shot_defect"] = shots["n_defect"].gt(0).astype(int)
    return shots
