"""2단계 탐색 분석 그림."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from diecast_qa.analysis import AnalysisResult
from diecast_qa.config import CAUSE_CATEGORIES, DEFECT_GROUPS, DEFECT_TYPE_LABELS
from diecast_qa.viz.base import ChartBuilder


class EdaCharts(ChartBuilder):
    def render(self, results: dict[str, AnalysisResult], out_dir: Path) -> list[Path]:
        def table(name: str, key: str) -> pd.DataFrame:
            return results[name].tables[key]

        return self.render_to(out_dir, {
            "eda_pareto": lambda: self.pareto(table("pareto", "types")),
            "eda_defect_rate_by_run": lambda: self.defect_rate_by_run(
                table("strata", "run_cavity")),
            "eda_type_mix_by_run": lambda: self.type_mix_by_run(table("type_mix", "by_run")),
            "eda_process_effects": lambda: self.process_effects(
                table("process_compare", "tests")),
        })  # fmt: skip

    def pareto(self, types: pd.DataFrame) -> Figure:
        """13개 유형을 건수 순으로. 누적 80%에 닿는 상위 유형만 강조하고 값을 붙인다."""
        fig, ax = self.panels((7.2, 5.0), header_in=0.8)
        y = np.arange(len(types))
        colors = np.where(types["vital"], self.theme.series[0], self.theme.neutral)
        ax.barh(y, types["count"], height=0.62, color=colors)
        ax.set_yticks(y, [DEFECT_TYPE_LABELS[t] for t in types.index])
        ax.invert_yaxis()

        pad = types["count"].max() * 0.01
        for yi, row in zip(y, types.itertuples(), strict=True):
            if row.vital:
                ax.text(row.count + pad, yi, f"{row.count:,}건 · {row.share:.1%}", va="center",
                        fontsize=9, color=self.theme.ink_secondary)  # fmt: skip

        self.tidy(ax, grid_axis="x")
        ax.spines["bottom"].set_visible(False)
        ax.set_xlabel("건수 (같은 불량 2~3개는 2~3건으로 셈)")
        vital = types[types["vital"]]
        self.header(fig, "불량 유형 파레토", f"상위 {len(vital)}개 유형이 전체 "
                    f"{types['count'].sum():,}건의 {vital['cum_share'].iloc[-1]:.1%}")  # fmt: skip
        return fig

    def defect_rate_by_run(self, run_cavity: pd.DataFrame, min_parts: int = 50) -> Figure:
        """구간마다 캐비티 1·2의 제품 불량률을 나란히 놓는다. 제품이 너무 적은 구간은 뺀다."""
        overall = run_cavity["defects"].to_numpy().sum() / run_cavity["n"].to_numpy().sum()
        enough = run_cavity["n"].sum(axis=1) >= min_parts
        dropped = [str(run) for run, _ in run_cavity.index[~enough]]
        rate = run_cavity.loc[enough, "rate"]

        fig, ax = self.panels((8, 4.8))
        x = np.arange(len(rate))
        width = 0.34
        for i, cavity in enumerate(rate.columns):
            ax.bar(x + (i - 0.5) * (width + 0.04), rate[cavity], width=width,
                   color=self.theme.series[i], label=f"캐비티 {cavity}")  # fmt: skip
        ax.axhline(overall, color=self.theme.ink_muted, linewidth=1)

        ax.set_xticks(x, [f"구간 {run}\n제품 {ptype}" for run, ptype in rate.index])
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_ylabel("제품 불량률")
        self.tidy(ax)

        higher = (rate[1] > rate[2]).sum()
        note = f", 구간 {', '.join(dropped)}은 제품 수가 적어 제외" if dropped else ""
        self.header(fig, "생산 구간·캐비티별 불량률",
                    f"캐비티1이 {len(rate)}개 구간 중 {higher}개에서 더 높음. "
                    f"가로선은 전체 불량률 {overall:.1%}{note}", ax)  # fmt: skip
        return fig

    def type_mix_by_run(self, by_run: pd.DataFrame) -> Figure:
        """불량 제품의 유형 구성(100% 누적 가로 막대). 색은 DEFECT_GROUPS 순서로 고정."""
        share = by_run.div(by_run.sum(axis=1), axis=0)
        fig, ax = self.panels((8, 4.8))
        y = np.arange(len(share))
        left = np.zeros(len(share))
        for i, group in enumerate(DEFECT_GROUPS):
            color = self.theme.series[i]
            values = share[group.code].to_numpy()
            ax.barh(y, values, left=left, height=0.62, color=color, label=group.label,
                    edgecolor=self.theme.surface, linewidth=1.5)  # fmt: skip
            for yi, (start, value) in enumerate(zip(left, values, strict=True)):
                if value >= 0.12:
                    ax.text(start + value / 2, yi, f"{value:.0%}", ha="center", va="center",
                            fontsize=8.5, color=self.theme.label_on(color))  # fmt: skip
            left += values

        ax.set_yticks(y, [f"구간 {run} ({total}개)" for run, total in by_run.sum(axis=1).items()])
        ax.invert_yaxis()
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        self.tidy(ax, grid_axis="x")
        ax.spines[["left", "bottom"]].set_visible(False)
        self.header(fig, "구간별 불량 유형 구성",
                    "불량 제품 기준 비율, 괄호는 불량 제품 수", ax)  # fmt: skip
        return fig

    def process_effects(self, tests: pd.DataFrame, top_n: int = 10) -> Figure:
        """제품 유형별 효과 크기 상위 변수: 전체 비교 → 같은 구간 안 비교 (덤벨)."""
        category = {v: c for c, members in CAUSE_CATEGORIES.items() for v in members}
        groups = list(tests.groupby("Product_Type"))
        fig, axes = self.panels((10.5, 5.6), ncols=len(groups))
        pooled_color, within_color = self.theme.series[:2]
        marker = {"s": 52, "zorder": 3, "edgecolors": self.theme.surface, "linewidths": 1.5}

        for ax, (ptype, g) in zip(axes, groups, strict=True):
            top = g.head(top_n).iloc[::-1]
            y = np.arange(len(top))
            ax.hlines(y, top["rank_biserial"], top["rank_biserial_within"],
                      color=self.theme.baseline, linewidth=1.5)  # fmt: skip
            ax.scatter(top["rank_biserial"], y, color=pooled_color, label="전체 비교", **marker)
            ax.scatter(top["rank_biserial_within"], y, color=within_color,
                       label="같은 구간 안에서 비교", **marker)  # fmt: skip
            ax.axvline(0, color=self.theme.baseline, linewidth=1)
            ax.set_yticks(y, [f"{v} ({category[v]})" for v in top["variable"]])
            ax.set_title(f"제품 유형 {ptype}", fontsize=11, loc="left")
            ax.set_xlim(-0.5, 0.5)
            ax.set_xlabel("rank-biserial (양수: 불량 shot의 값이 더 큼)")
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)

        self.header(fig, "정상/불량 shot의 공정 변수 차이 (효과 크기 상위 10개)",
                    "같은 구간 안에서 비교하면 대부분 0 근처로 줄어든다. "
                    "차이의 대부분은 시기(생산 구간) 간 차이", axes[0])  # fmt: skip
        return fig
