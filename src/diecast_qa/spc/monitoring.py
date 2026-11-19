"""관리도를 제품 유형별로 적용하는 분석 (9장, 8.2)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict

import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import KEY_VARS, PROCESS_COLS, SENSOR_COLS
from diecast_qa.data import shot_view
from diecast_qa.eda.stats import hedges_g
from diecast_qa.spc.charts import ControlChart, CUSUMChart, EWMAChart, PChart, XbarRChart


def monitored_shots(parts: pd.DataFrame, exclude_abnormal: bool) -> pd.DataFrame:
    """관리도 입력용 shot 테이블: order 열, shot 불량률(defect_rate = 불량 제품 수 / 2)."""
    shots = shot_view(parts).reset_index()
    shots["defect_rate"] = shots["n_defect"] / 2
    return shots[~shots["is_abnormal"]] if exclude_abnormal else shots


def apply_charts(
    shots: pd.DataFrame, make_charts
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, list[ControlChart]]]:
    """제품 유형마다 make_charts()의 관리도를 새로 만들어 fit·evaluate 한다."""
    frames, limits, fitted = [], [], {}
    for ptype, stream in shots.groupby("Product_Type"):
        fitted[ptype] = []
        for chart in make_charts():
            points = chart.fit(stream).evaluate(stream)
            frames.append(points.assign(Product_Type=ptype, chart=chart.chart,
                                        variable=chart.variable))  # fmt: skip
            limits += [asdict(lim) | {"Product_Type": ptype} for lim in chart.limits]
            fitted[ptype].append(chart)
    lead = ["Product_Type", "chart", "variable"]
    points = pd.concat(frames, ignore_index=True)
    points = points[lead + [c for c in points.columns if c not in lead]]
    limits = pd.DataFrame(limits)
    return points, limits[["Product_Type", *limits.columns.drop("Product_Type")]], fitted


def signal_summary(points: pd.DataFrame) -> pd.DataFrame:
    """관리도·통계량별 점 수, 이탈 점 수와 비율, 경보 횟수(이탈이 새로 시작된 횟수)."""
    keys = ["Product_Type", "chart", "variable", "statistic"]

    def episodes(signal: pd.Series) -> int:
        return int((signal & ~signal.shift(fill_value=False)).sum())

    grouped = points.groupby(keys, sort=False)["signal"]
    summary = grouped.agg(points="size", signals="sum", signal_share="mean")
    summary["episodes"] = grouped.apply(episodes)
    return summary


class DefectRateMonitoring(Analysis):
    """제품 불량률 관리도: p-chart(9장)와 EWMA·CUSUM(8.2 재학습 신호 후보).

    p-chart는 검사한 모든 제품을 세야 하므로 비정상 shot도 포함한다. EWMA·CUSUM은 shot마다
    불량률(0, 0.5, 1)을 이항 σ로 본다. 기본값은 불량률이 두 배 정도로 오르는 변화(약 0.5σ)를
    겨냥했고, 8.2 실험에서 조정한다.
    """

    name = "spc_defect"

    def __init__(
        self,
        subgroup_shots: int = 50,
        ewma: tuple[float, float] = (0.05, 3.0),
        cusum: tuple[float, float] = (0.25, 8.0),
    ) -> None:
        self.subgroup_shots = subgroup_shots
        self.ewma, self.cusum = ewma, cusum

    def charts(self) -> Iterator[ControlChart]:
        yield PChart(self.subgroup_shots)
        yield EWMAChart("defect_rate", *self.ewma, sigma_method="binomial")
        yield CUSUMChart("defect_rate", *self.cusum, sigma_method="binomial")

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = monitored_shots(parts, exclude_abnormal=False)
        points, limits, fitted = apply_charts(shots, self.charts)
        summary = signal_summary(points)
        profile = self._ooc_profile(shots, fitted)
        tables = {"points": points, "limits": limits, "summary": summary, "ooc_profile": profile}
        return AnalysisResult(self.name, tables, self._notes(points, summary, profile))

    @staticmethod
    def _ooc_profile(shots: pd.DataFrame, fitted: dict[int, list[ControlChart]]) -> pd.DataFrame:
        """p-chart 상한 이탈 부분군과 관리 상태 부분군의 공정 조건 비교 (부분군 평균 기준).

        9장 '관리한계를 벗어난 구간과 그렇지 않은 구간의 공정 조건을 비교해 원인 후보를 찾는다'.
        """
        variables = [*PROCESS_COLS, *SENSOR_COLS]
        rows = []
        for ptype, stream in shots.groupby("Product_Type"):
            pchart = next(c for c in fitted[ptype] if isinstance(c, PChart))
            ids = pchart.subgroup_ids(stream)
            means = stream[ids >= 0].groupby(ids[ids >= 0])[[*variables, "n_defect"]].mean()
            rate = means["n_defect"] / 2
            high, normal = means[rate > pchart.ucl_], means[rate.between(pchart.lcl_, pchart.ucl_)]
            for v in variables:
                a, b = high[v].dropna().to_numpy(), normal[v].dropna().to_numpy()
                rows.append({
                    "Product_Type": ptype, "variable": v, "n_high": len(high),
                    "n_in_control": len(normal), "mean_high": a.mean(),
                    "mean_in_control": b.mean(), "hedges_g": hedges_g(a, b),
                })  # fmt: skip
        profile = pd.DataFrame(rows)
        strength = profile["hedges_g"].abs().rename("strength")
        order = pd.concat([profile["Product_Type"], strength], axis=1).sort_values(
            ["Product_Type", "strength"], ascending=[True, False]
        )
        return profile.loc[order.index].reset_index(drop=True)

    @staticmethod
    def _notes(points, summary, profile) -> tuple[str, ...]:
        notes = []
        for ptype, s in summary.groupby(level="Product_Type"):
            counts = s.droplevel(["Product_Type", "variable", "statistic"])
            n_groups, n_out = (int(v) for v in counts.loc["p", ["points", "signals"]])
            pts = points[(points["Product_Type"] == ptype) & (points["chart"] == "p")]
            above = int((pts["value"] > pts["ucl"]).sum())
            ewma = int(counts.loc["ewma", "episodes"])
            cusum = int(counts.loc["cusum", "episodes"].sum())
            top = profile[profile["Product_Type"] == ptype].head(3)
            notes.append(
                f"제품 유형 {ptype}: p-chart {n_groups}개 군 중 {n_out}개 이탈 "
                f"(상한 {above}, 하한 {n_out - above}), EWMA 경보 {ewma}회, CUSUM 경보 {cusum}회"
            )
            notes.append(
                f"제품 유형 {ptype} 상한 이탈 군의 공정 조건 차이(Hedges g) 상위: "
                + ", ".join(f"{r.variable} {r.hedges_g:+.2f}" for r in top.itertuples())
                + " (이탈 군이 특정 구간에 몰려 있어 구간 효과와 겹침, 원인 후보로만 본다)"
            )
        return tuple(notes)


class ProcessMonitoring(Analysis):
    """주요 공정 변수 관리도: Xbar-R(9장)과 EWMA·CUSUM(8.2). 비정상 shot은 뺀다.

    공정 변수는 shot 사이에서 천천히 흘러가(자기상관) 군내 변동이 작다. 그래서 군내 변동으로
    잡은 관리한계가 좁아 이탈이 많아진다. 이를 해석하려고 구간 안 lag-1 자기상관과
    군내/전체 표준편차 비를 함께 낸다.
    """

    name = "spc_process"

    def __init__(
        self,
        variables: tuple[str, ...] = KEY_VARS,
        subgroup_shots: int = 5,
        ewma: tuple[float, float] = (0.2, 3.0),
        cusum: tuple[float, float] = (0.5, 5.0),
    ) -> None:
        self.variables = variables
        self.subgroup_shots = subgroup_shots
        self.ewma, self.cusum = ewma, cusum

    def charts(self) -> Iterator[ControlChart]:
        for v in self.variables:
            yield XbarRChart(v, self.subgroup_shots)
            yield EWMAChart(v, *self.ewma, sigma_method="moving_range")
            yield CUSUMChart(v, *self.cusum, sigma_method="moving_range")

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        shots = monitored_shots(parts, exclude_abnormal=True)
        points, limits, fitted = apply_charts(shots, self.charts)
        summary = signal_summary(points)
        diagnostics = self._diagnostics(shots, fitted)
        tables = {
            # shot 단위 EWMA·CUSUM 점은 양이 많아 요약만 저장한다
            "xbar_r": points[points["chart"] == "xbar_r"].reset_index(drop=True),
            "limits": limits,
            "summary": summary,
            "diagnostics": diagnostics,
        }
        return AnalysisResult(self.name, tables, self._notes(summary, diagnostics))

    def _diagnostics(self, shots, fitted) -> pd.DataFrame:
        rows = []
        for ptype, stream in shots.groupby("Product_Type"):
            xbar_r = {c.variable: c for c in fitted[ptype] if isinstance(c, XbarRChart)}
            for v in self.variables:
                x = stream[v]
                centered = x - x.groupby(stream["run"]).transform("mean")
                lagged = centered.groupby(stream["run"]).shift()
                rows.append({
                    "Product_Type": ptype, "variable": v,
                    "lag1_autocorr": centered.corr(lagged),
                    "sigma_within": xbar_r[v].sigma_within, "sigma_overall": x.std(),
                })  # fmt: skip
        table = pd.DataFrame(rows)
        table["within_to_overall"] = table["sigma_within"] / table["sigma_overall"]
        return table

    @staticmethod
    def _notes(summary, diagnostics) -> tuple[str, ...]:
        xbar = summary.xs(("xbar_r", "xbar"), level=["chart", "statistic"])
        share = xbar["signal_share"]
        return (
            f"Xbar 관리도 이탈 비율: 변수·제품 유형별 {share.min():.0%}~{share.max():.0%} "
            f"(중앙값 {share.median():.0%})",
            f"구간 안 lag-1 자기상관 중앙값 {diagnostics['lag1_autocorr'].median():.2f}, "
            f"군내/전체 표준편차 비 중앙값 {diagnostics['within_to_overall'].median():.2f}: "
            "구간마다 공정값 수준이 다르고(설정 변경) 구간 안에서도 천천히 흘러가(드리프트) "
            "군내 변동으로 잡은 관리한계가 좁다. Shewhart 관리도의 독립성 전제가 성립하지 않는다",
        )
