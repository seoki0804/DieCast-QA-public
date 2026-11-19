"""불량 개선 방안·이탈 대응 연구 그림."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import NullLocator, PercentFormatter

from diecast_qa.analysis import AnalysisResult
from diecast_qa.viz.base import ChartBuilder

# 경보 규칙의 고정 색 순서 (series 순서대로)
RULE_ORDER = ("defect_cusum", "range_out_1", "range_out_3", "sustained_20", "sudden_shift")
RULE_SHORT = {"defect_cusum": "불량률 CUSUM", "range_out_1": "범위 밖 1 shot",
              "range_out_3": "범위 밖 3 shot 연속", "sustained_20": "범위 밖 지속(20 shot 중 80%)",
              "sudden_shift": "공정 변수 급변"}  # fmt: skip


class ImprovementCharts(ChartBuilder):
    def render(self, results: dict[str, AnalysisResult], out_dir: Path) -> list[Path]:
        levers, alarms = results["levers"].tables, results["alarms"].tables
        charts = {
            "improve_levers": lambda: self.levers(levers),
            "improve_golden": lambda: self.golden(levers["golden"]),
            "improve_alarm_rules": lambda: self.alarm_rules(alarms["rules"]),
            "improve_alarm_diagnosis": lambda: self.diagnosis(alarms["diagnosis"]),
        }
        return self.render_to(out_dir, charts)

    def levers(self, tables: dict[str, pd.DataFrame]) -> Figure:
        cav, ranges, restart = tables["cavity"], tables["ranges"], tables["restart"]
        rows = [("캐비티1을 같은 구간 캐비티2 수준으로", cav["excess"].sum() / cav["defects"].sum(),
                 np.nan, np.nan)]  # fmt: skip
        for ptype, r in ranges.iterrows():
            rows.append((f"관리 범위(안) 준수 · 유형 {ptype}", r["reduction"], r["reduction_low"],
                         r["reduction_high"]))  # fmt: skip
        table = pd.DataFrame(rows, columns=["lever", "value", "low", "high"]).iloc[::-1]
        y = np.arange(len(table))
        fig, ax = self.panels((9.5, 3.6), header_in=0.9)
        ax.barh(y, table["value"], height=0.55, color=self.theme.series[0])
        has = table["low"].notna().to_numpy()
        ax.hlines(y[has], table["low"][has], table["high"][has], color=self.theme.ink,
                  linewidth=1.5)  # fmt: skip
        for yi, (v, hi) in enumerate(zip(table["value"], table["high"], strict=True)):
            x = hi if np.isfinite(hi) else v
            ax.text(x, yi, f"  {v:.0%}", va="center", fontsize=9.5, color=self.theme.ink_secondary)
        ax.set_yticks(y, table["lever"])
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_xlim(0, max(table["high"].max(), table["value"].max()) * 1.2)
        ax.set_xlabel("불량 감소 추정 (선은 50 shot 블록 bootstrap 95% 구간)")
        self.tidy(ax, grid_axis="x")
        ax.spines[["left"]].set_visible(False)
        rs = restart.iloc[0]
        self.header(fig, "개선 수단별 불량 감소 여지 (관측 데이터의 같은 구간 안 비교)",
                    f"재가동·기록 중단 직후 10 shot은 효과 없음(오즈비 {rs['pooled_or']:.2f}, "
                    f"{rs['or_low']:.2f}~{rs['or_high']:.2f}). 인과 확인은 실험 계획으로",
                    )  # fmt: skip
        return fig

    def golden(self, golden: pd.DataFrame, top: int = 6) -> Figure:
        types = list(golden.index.unique("Product_Type"))
        fig, axes = self.panels((11.5, 4.4), ncols=len(types))
        for ax, ptype in zip(axes, types, strict=True):
            g = golden.loc[ptype].head(top).iloc[::-1]
            y = np.arange(len(g))
            sign = np.sign(g["std_diff"]).to_numpy()
            ax.hlines(y, 0, g["std_diff"].abs(), color=self.theme.baseline, linewidth=2)
            ax.scatter(g["std_diff"].abs(), y, s=56, zorder=3,
                       color=[self.increase if s > 0 else self.decrease for s in sign],
                       edgecolors=self.theme.surface, linewidths=1.5)  # fmt: skip
            ax.set_yticks(y, [f"{r.label}  {r.worst:.4g} → {r.best:.4g}" for r in g.itertuples()])
            first = g.iloc[0]
            ax.set_title(f"유형 {ptype}: 최악 구간 {first['worst_run']} → 최우수 구간 "
                         f"{first['best_run']}", loc="left", fontsize=11)  # fmt: skip
            ax.set_xlabel("차이 / 구간 내 표준편차")
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        handles = [Line2D([], [], marker="o", linestyle="", color=self.increase,
                          label="최우수 구간이 더 높음"),
                   Line2D([], [], marker="o", linestyle="", color=self.decrease,
                          label="최우수 구간이 더 낮음")]  # fmt: skip
        self.header(fig, "불량이 가장 적었던 구간의 운전 조건 (가설)",
                    "같은 제품 유형에서 shot 불량률이 가장 낮은 구간과 가장 높은 구간의 중앙값 "
                    "비교. 시기와 함께 바뀐 조건이라 실험으로 확인해야 한다",
                    handles=handles)  # fmt: skip
        return fig

    def alarm_rules(self, rules: pd.DataFrame) -> Figure:
        types = list(rules.index.unique("Product_Type"))
        fig, axes = self.panels((11.5, 4.8), ncols=len(types), sharey=True)
        colors = dict(zip(RULE_ORDER, self.theme.series, strict=False))
        for ax, ptype in zip(axes, types, strict=True):
            g = rules.loc[ptype]
            g = g[g["alarms"] > 0]
            for rule in RULE_ORDER:
                r = g.xs(rule, level="rule") if rule in g.index.get_level_values("rule") else None
                if r is None:
                    continue
                ax.scatter(r["alarms_per_100"], r["lift"], s=50, color=colors[rule], zorder=3,
                           edgecolors=self.theme.surface, linewidths=1.2)  # fmt: skip
                for _, row in r.iterrows():
                    if rule == "defect_cusum" or row["lift"] > 1.5:
                        ax.annotate(row["variable_label"], (row["alarms_per_100"], row["lift"]),
                                    xytext=(5, 3), textcoords="offset points", fontsize=8,
                                    color=self.theme.ink_secondary)  # fmt: skip
            ax.axhline(1, color=self.theme.ink_muted, linewidth=1)
            ax.set_xscale("log")
            ticks = [0.03, 0.1, 0.3, 1, 3, 10, 30]
            ax.set_xticks(ticks, [f"{t:g}" for t in ticks])
            ax.xaxis.set_minor_locator(NullLocator())
            ax.set_xlabel("100 shot당 경보 수")
            ax.set_title(f"제품 유형 {ptype}", loc="left", fontsize=11)
            self.tidy(ax, grid_axis="both")
        axes[0].set_ylabel("경보 뒤 불량률 / 평균 불량률")
        handles = [Line2D([], [], marker="o", linestyle="", color=colors[r], label=RULE_SHORT[r])
                   for r in RULE_ORDER]  # fmt: skip
        self.header(fig, "경보 규칙 비교: 적게 울리고(왼쪽) 울린 뒤 불량이 늘어야(위) 쓸모 있다",
                    "공정 변수 경보는 경보 뒤 10 shot, 불량률 CUSUM은 조치 기간 50 shot. 가로선 = "
                    "평균과 같음", handles=handles)  # fmt: skip
        return fig

    def diagnosis(self, diagnosis: pd.DataFrame) -> Figure:
        types = list(diagnosis.index.unique("Product_Type"))
        fig, axes = self.panels((11.5, 4.6), ncols=len(types))
        axes = np.atleast_1d(axes)
        for ax, ptype in zip(axes, types, strict=True):
            g = diagnosis.loc[ptype].drop("제품 불량률")
            g = g[(g["alarm_window"] > 0) | (g["other"] > 0)]
            g = g.reindex((g["alarm_window"] - g["other"]).sort_values().index)
            y = np.arange(len(g))
            ax.hlines(y, g["other"], g["alarm_window"], color=self.theme.baseline, linewidth=1.5)
            ax.scatter(g["other"], y, s=44, color=self.theme.ink_muted, zorder=3,
                       label="경보 구간 밖")  # fmt: skip
            ax.scatter(g["alarm_window"], y, s=52, color=self.theme.series[0], zorder=3,
                       edgecolors=self.theme.surface, linewidths=1.3,
                       label="경보 뒤 50 shot")  # fmt: skip
            ax.set_yticks(y, g.index)
            ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            rate = diagnosis.loc[(ptype, "제품 불량률")]
            ax.set_title(f"유형 {ptype}: 불량률 {rate['other']:.1%} → {rate['alarm_window']:.1%}",
                         loc="left", fontsize=11)  # fmt: skip
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        self.header(fig, "불량률 경보 때 무엇이 달라지나 (원인 진단)",
                    "경보가 난 구간 안에서 비교. 불량 유형은 불량 제품 중 비중, "
                    "범위 밖은 shot 중 비중",
                    axes[0])  # fmt: skip
        return fig
