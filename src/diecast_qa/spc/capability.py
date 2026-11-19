"""공정능력 (9장): 규격이 있는 변수의 Cp·Cpk(군내 σ)와 Pp·Ppk(전체 σ)."""

from __future__ import annotations

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import SPEC_LIMITS
from diecast_qa.spc.charts import XbarRChart
from diecast_qa.spc.monitoring import monitored_shots


class CapabilityAnalysis(Analysis):
    """Cp·Cpk는 군내 σ(R̄/d2, 구간 안 연속 shot 부분군), Pp·Ppk는 전체 표준편차로 계산한다.

    공정이 통계적으로 안정돼 있으면 두 값이 비슷하다. 크게 다르면 공정이 시간에 따라 흘러가는
    것이고, 이때는 실제 성능을 나타내는 Pp·Ppk로 판단한다.
    """

    name = "capability"

    def __init__(
        self, specs: dict[str, tuple[float, float]] = SPEC_LIMITS, subgroup_shots: int = 5
    ) -> None:
        self.specs = specs
        self.subgroup_shots = subgroup_shots

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = monitored_shots(parts, exclude_abnormal=True)
        scopes = [("all", shots), *((f"type_{t}", g) for t, g in shots.groupby("Product_Type"))]
        table = pd.DataFrame([
            {"variable": var, "scope": scope, "lsl": lsl, "usl": usl,
             **self._indices(frame, var, lsl, usl)}
            for var, (lsl, usl) in self.specs.items() for scope, frame in scopes
        ])  # fmt: skip

        notes = tuple(
            f"{r.variable}: Pp {r.Pp:.2f} / Ppk {r.Ppk:.2f} (전체 σ), "
            f"Cp {r.Cp:.1f} / Cpk {r.Cpk:.1f} (군내 σ, 군내/전체 σ 비 {r.within_to_overall:.2f})"
            for r in table[table["scope"] == "all"].itertuples()
        )
        return AnalysisResult(self.name, {"indices": table}, notes)

    def _indices(self, shots: pd.DataFrame, var: str, lsl: float, usl: float) -> dict:
        x = shots[var]
        mean, overall = x.mean(), x.std(ddof=1)
        within = XbarRChart(var, self.subgroup_shots).fit(shots).sigma_within
        gap = min(usl - mean, mean - lsl)
        return {
            "n": int(x.count()),
            "mean": mean,
            "sigma_within": within,
            "sigma_overall": overall,
            "within_to_overall": within / overall,
            "Cp": (usl - lsl) / (6 * within),
            "Cpk": gap / (3 * within),
            "Pp": (usl - lsl) / (6 * overall),
            "Ppk": gap / (3 * overall),
        }
