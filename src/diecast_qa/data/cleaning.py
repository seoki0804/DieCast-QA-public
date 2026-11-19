"""원본 행을 생산 순서대로 정리한 shot 테이블로 바꾼다 (2.3, 3.1 순서 2·3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class CleaningReport:
    """정제 과정에서 확인한 데이터 점검 결과 (2.3 표와 대조용)."""

    raw_rows: int
    duplicate_rows: int
    shots: int
    run_sizes: dict[int, int]
    abnormal_orders: list[int]
    missing_shots: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        runs = ", ".join(f"{run}:{n}" for run, n in self.run_sizes.items())
        missing = ", ".join(f"{col} {n}" for col, n in self.missing_shots.items()) or "없음"
        return "\n".join([
            f"원본 {self.raw_rows:,}행 → 중복 {self.duplicate_rows:,}행 제거 → {self.shots:,} shot",
            f"생산 구간 {len(self.run_sizes)}개 (구간:shot 수) {runs}",
            f"비정상 shot {len(self.abnormal_orders)}개 (order) {self.abnormal_orders}",
            f"결측 shot {missing}",
        ])  # fmt: skip


class ShotCleaner:
    """중복 기록을 지우고 생산 순서(order)·생산 구간(run)·비정상 shot 표시를 붙인다."""

    # 예열·정지 shot에서 0으로 찍히는 공정 변수
    ZERO_MEANS_IDLE = (
        "High_Velocity", "Biscuit_Thickness", "Rapid_Rise_Time", "Pressure_Rise_Time",
    )  # fmt: skip

    def __init__(self, cycle_time_ratio: float = 2.0, drop_duplicates: bool = True) -> None:
        # 사이클 타임이 제품 유형 중앙값의 이 배수를 넘으면 정지 후 재개한 shot으로 본다
        self.cycle_time_ratio = cycle_time_ratio
        # False는 중복이 성능을 얼마나 부풀리는지 보는 참고 실험(6.3, 7.2)에서만 쓴다
        self.drop_duplicates = drop_duplicates

    def clean(self, raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        shots = raw
        if self.drop_duplicates:
            shots = raw.drop_duplicates(subset=raw.columns.drop("id"))
        shots = shots.reset_index(drop=True)
        # 날짜·시각이 없으므로 행 순서를 생산 순서로, shot 번호가 줄어드는 지점을 구간 경계로 쓴다
        shots.insert(0, "order", range(len(shots)))
        shots.insert(1, "run", shots["Shot"].diff().lt(0).cumsum().add(1))
        shots["is_abnormal"] = self._flag_abnormal(shots)

        report = CleaningReport(
            raw_rows=len(raw),
            duplicate_rows=len(raw) - len(shots),
            shots=len(shots),
            run_sizes={int(k): int(v) for k, v in shots["run"].value_counts().sort_index().items()},
            abnormal_orders=shots.loc[shots["is_abnormal"], "order"].tolist(),
            missing_shots={c: int(n) for c, n in shots.isna().sum().items() if n > 0},
        )
        return shots, report

    def _flag_abnormal(self, shots: pd.DataFrame) -> pd.Series:
        idle = shots[list(self.ZERO_MEANS_IDLE)].eq(0).any(axis=1)
        typical_cycle = shots.groupby("Product_Type")["Cycle_Time"].transform("median")
        stalled = shots["Cycle_Time"] > self.cycle_time_ratio * typical_cycle
        return idle | stalled
