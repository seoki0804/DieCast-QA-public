"""3단계 공정 안정성 그림: 관리도와 공정능력."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from diecast_qa.analysis import AnalysisResult
from diecast_qa.viz.base import ChartBuilder


class SpcCharts(ChartBuilder):
    def render(
        self, results: dict[str, AnalysisResult], shots: pd.DataFrame, out_dir: Path
    ) -> list[Path]:
        """shots: 공정능력 히스토그램용 shot 테이블 (비정상 shot 제외)."""
        defect = results["spc_defect"].tables["points"]
        xbar_r = results["spc_process"].tables["xbar_r"]
        indices = results["capability"].tables["indices"]

        def of(chart: str) -> pd.DataFrame:
            return defect[defect["chart"] == chart]

        return self.render_to(out_dir, {
            "spc_p_chart": lambda: self.control_chart(
                of("p"), "불량률 p-chart (50 shot = 제품 100개 부분군)",
                "관리한계는 제품 유형마다 전체 기간으로 추정 (Phase I)", "부분군 불량률",
                percent=True),
            "spc_ewma_defect": lambda: self.control_chart(
                of("ewma"), "불량률 EWMA 관리도 (λ=0.05, L=3)",
                "shot마다 불량률(0, 0.5, 1)을 지수가중 평균. 재학습 신호 후보",
                "EWMA 불량률", percent=True),
            "spc_cusum_defect": lambda: self.cusum_chart(of("cusum")),
            "spc_xbar_r_casting_pressure": lambda: self.xbar_r(xbar_r, "Casting_Pressure",
                                                               "주조 압력"),
            "spc_xbar_r_melting_furnace_temp": lambda: self.xbar_r(
                xbar_r, "Melting_Furnace_Temp", "용탕 온도"),
            "spc_capability_air_pressure": lambda: self.capability(shots, indices,
                                                                   "Air_Pressure", "공기압"),
        })  # fmt: skip

    def control_chart(
        self, points: pd.DataFrame, title: str, subtitle: str, label: str, percent: bool = False
    ) -> Figure:
        """제품 유형마다 한 줄씩: 통계량, 중심선, 관리한계, 이탈 점, 구간 경계."""
        streams = list(points.groupby("Product_Type"))
        fig, axes = self.panels((10, 3.0 * len(streams) + 1.1), nrows=len(streams))
        for ax, (ptype, frame) in zip(np.atleast_1d(axes), streams, strict=True):
            self._draw_limits(ax, frame)
            self._draw_series(ax, frame, self.theme.series[0], label)
            self._draw_signals(ax, frame)
            self._draw_runs(ax, frame)
            self._panel_title(ax, f"제품 유형 {ptype}")
            if percent:
                ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            self.tidy(ax)
        np.atleast_1d(axes)[-1].set_xlabel("생산 순서 (shot)")
        self.header(fig, title, subtitle, np.atleast_1d(axes)[0])
        return fig

    def cusum_chart(self, points: pd.DataFrame) -> Figure:
        """상측 누적합은 위로, 하측 누적합은 아래로. 값은 σ 단위."""
        streams = list(points.groupby("Product_Type"))
        fig, axes = self.panels((10, 3.0 * len(streams) + 1.1), nrows=len(streams))
        labels = {"cusum_upper": "상측 누적합 (불량률 증가)", "cusum_lower": "하측 누적합 (감소)"}
        for ax, (ptype, frame) in zip(axes, streams, strict=True):
            for i, (stat, label) in enumerate(labels.items()):
                part = frame[frame["statistic"] == stat]
                self._draw_series(ax, part, self.theme.series[i], label)
            h = frame["ucl"].max()
            for level in (h, -h):
                ax.axhline(level, color=self.theme.ink_secondary, linewidth=1)
            self._draw_signals(ax, frame)
            self._draw_runs(ax, frame)
            self._panel_title(ax, f"제품 유형 {ptype}")
            ax.set_ylabel("σ 단위")
            self.tidy(ax)
        axes[-1].set_xlabel("생산 순서 (shot)")
        self.header(fig, "불량률 CUSUM 관리도 (k=0.25, h=8)",
                    "누적합이 ±h를 넘으면 경보를 내고 0으로 초기화. "
                    "경보가 촘촘한 구간일수록 불량률이 기준에서 멀다", axes[0])  # fmt: skip
        return fig

    def xbar_r(self, points: pd.DataFrame, variable: str, label: str) -> Figure:
        """열은 제품 유형, 행은 Xbar·R."""
        data = points[points["variable"] == variable]
        types = sorted(data["Product_Type"].unique())
        fig, axes = self.panels((11, 6.6), nrows=2, ncols=len(types), sharex="col")
        for col, ptype in enumerate(types):
            for row, stat in enumerate(("xbar", "r")):
                ax = axes[row, col]
                frame = data[(data["Product_Type"] == ptype) & (data["statistic"] == stat)]
                self._draw_limits(ax, frame)
                self._draw_series(ax, frame, self.theme.series[0], "부분군 통계량", width=1.2)
                self._draw_signals(ax, frame, size=10)
                self._draw_runs(ax, frame)
                name = "평균 (Xbar)" if stat == "xbar" else "범위 (R)"
                self._panel_title(ax, f"제품 유형 {ptype} · {name}")
                self.tidy(ax)
            axes[-1, col].set_xlabel("생산 순서 (shot)")
        share = data[data["statistic"] == "xbar"].groupby("Product_Type")["signal"].mean()
        self.header(fig, f"{label} Xbar-R 관리도 (구간 안 연속 5 shot 부분군)",
                    "Xbar 이탈 비율 " + ", ".join(f"제품 {t} {s:.0%}" for t, s in share.items())
                    + ". 구간마다 수준이 달라(설정 변경·드리프트) 전체 기간 한 쌍의 한계로는 "
                    "이탈이 많다", axes[0, 0])  # fmt: skip
        return fig

    def capability(
        self, shots: pd.DataFrame, indices: pd.DataFrame, variable: str, label: str
    ) -> Figure:
        row = indices[(indices["variable"] == variable) & (indices["scope"] == "all")].iloc[0]
        fig, ax = self.panels((8, 4.6), header_in=0.8)
        values = shots[variable].dropna()
        # 측정 단위(가장 작은 값 간격)에 맞춰 구간을 나눠 빈 구간이 생기지 않게 한다
        step = np.diff(np.unique(values)).min()
        bins = np.arange(values.min() - step / 2, values.max() + step, step)
        ax.hist(values, bins=bins, color=self.theme.series[0], edgecolor=self.theme.surface,
                linewidth=1.5)  # fmt: skip
        marks = (("lsl", "LSL", self.theme.critical), ("usl", "USL", self.theme.critical),
                 ("mean", "평균", self.theme.ink_secondary))  # fmt: skip
        for key, name, color in marks:
            ax.axvline(row[key], color=color, linewidth=1.5 if key != "mean" else 1)
            ax.text(row[key], 1.0, f" {name} {row[key]:.3g}", transform=ax.get_xaxis_transform(),
                    va="top", fontsize=9, color=self.theme.ink_secondary)  # fmt: skip
        span = row["usl"] - row["lsl"]
        ax.set_xlim(row["lsl"] - 0.08 * span, row["usl"] + 0.08 * span)
        ax.set_xlabel(label)
        ax.set_ylabel("shot 수")
        self.tidy(ax)
        self.header(fig, f"{label} 공정능력 (규격 {row['lsl']:g}~{row['usl']:g})",
                    f"Pp {row['Pp']:.2f} · Ppk {row['Ppk']:.2f} (전체 σ) / "
                    f"Cp {row['Cp']:.1f} · Cpk {row['Cpk']:.1f} (군내 σ). "
                    "공정이 흘러가 군내 σ로 보면 크게 과대평가")  # fmt: skip
        return fig

    def _draw_series(
        self, ax: Axes, frame: pd.DataFrame, color: str, label: str, width: float | None = None
    ) -> None:
        dense = len(frame) > 120
        ax.plot(frame["order"], frame["value"], color=color, label=label,
                linewidth=width or (1.2 if dense else 2),
                marker=None if dense else "o", markersize=4)  # fmt: skip

    @staticmethod
    def _panel_title(ax: Axes, title: str) -> None:
        # 제목과 축 사이에 구간 라벨이 들어갈 자리를 둔다
        ax.set_title(title, loc="left", fontsize=11, pad=16)

    def _draw_limits(self, ax: Axes, frame: pd.DataFrame) -> None:
        ax.plot(frame["order"], frame["center"], color=self.theme.ink_muted, linewidth=1,
                label="중심선")  # fmt: skip
        for col, label in (("ucl", "관리한계"), ("lcl", None)):
            if frame[col].notna().any():
                ax.plot(frame["order"], frame[col], color=self.theme.ink_secondary,
                        linewidth=1, drawstyle="steps-post", label=label)  # fmt: skip

    def _draw_signals(self, ax: Axes, frame: pd.DataFrame, size: float = 18) -> None:
        hit = frame[frame["signal"]]
        ax.scatter(hit["order"], hit["value"], s=size, color=self.theme.critical, zorder=3,
                   label="관리한계 이탈", linewidths=0)  # fmt: skip

    def _draw_runs(self, ax: Axes, frame: pd.DataFrame, min_share: float = 0.03) -> None:
        """구간 경계선과 라벨. x 범위의 min_share보다 짧은 구간은 라벨을 생략한다."""
        starts = frame.groupby("run")["order"].min()
        ends = [*starts.iloc[1:], frame["order"].max()]
        span = frame["order"].max() - frame["order"].min()
        for (run, start), end in zip(starts.items(), ends, strict=True):
            if start > frame["order"].min():
                ax.axvline(start, color=self.theme.baseline, linewidth=0.8, zorder=0)
            if end - start >= min_share * span:
                ax.text(start, 1.0, f" 구간 {run}", transform=ax.get_xaxis_transform(),
                        fontsize=8, color=self.theme.ink_muted, va="bottom")  # fmt: skip
