"""검사 운영·비용, 샘플링 검사, 확률 보정 그림 (보고서 8장)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

from diecast_qa.analysis import AnalysisResult
from diecast_qa.inspection.analyses import NOT_COMPARABLE, CalibrationAnalysis
from diecast_qa.inspection.calibration import CALIBRATORS
from diecast_qa.inspection.evaluation import SCORER_LABELS, SCORERS
from diecast_qa.viz.base import ChartBuilder

# 선으로 그리는 검사 방식과 고정 색 순서 (series 순서대로)
LINE_STRATEGIES = ("model", "rule", "switching", "sampling", "cavity")
SHORT = {
    "model": "모델 선별", "rule": "규칙 선별", "switching": "검사 강도 전환",
    "sampling": "샘플링 (비용 최소)", "cavity": "캐비티 규칙", "none": "검사 안 함",
    "full": "전수검사", "perfect": "완벽한 예측", "sampling_classical": "샘플링 (AQL 설계)",
    "rule_censored": "규칙 (검사한 제품만)", "random_matched": "무작위 (같은 검사량)",
}  # fmt: skip


class InspectionCharts(ChartBuilder):
    def render(self, results: dict[str, AnalysisResult], out_dir: Path) -> list[Path]:
        cost, sampling = results["cost"].tables, results["sampling"].tables
        calibration = results["calibration"].tables
        charts = {
            "cost_by_ratio": lambda: self.cost_by_ratio(cost["summary"]),
            "cost_uncertainty": lambda: self.uncertainty(cost["uncertainty"]),
            "sampling_capture": lambda: self.sampling_capture(sampling),
            "sampling_oc": lambda: self.oc_curve(sampling["oc"], sampling["lots"]),
            "calibration_reliability": lambda: self.reliability(calibration),
            "calibration_cost": lambda: self.calibration_cost(calibration["cost"]),
        }
        return self.render_to(out_dir, charts)

    def _colors(self) -> dict[str, str]:
        return dict(zip(LINE_STRATEGIES, self.theme.series, strict=False))

    def _ratio_axis(self, ax, ratios) -> None:
        ax.set_xticks(range(len(ratios)), [f"{r:g}:1" for r in ratios])
        ax.set_xlabel("미검 비용 : 검사 비용")

    # 8장 비용 ---------------------------------------------------------------------------
    def cost_by_ratio(self, summary: pd.DataFrame) -> Figure:
        ratios = list(summary.index.unique("ratio"))
        x = np.arange(len(ratios))
        table = summary["cost_per_part"].unstack("strategy").reindex(ratios)
        rate = summary["inspect_rate"].unstack("strategy").reindex(ratios)
        fig, axes = self.panels((11.5, 4.8), ncols=2)
        ax = axes[0]
        top = 1.3
        ax.axhline(1, color=self.theme.ink_secondary, linewidth=1.2)
        ax.text(x[0], 1, " 전수검사 = 1", va="bottom", fontsize=8.5, color=self.theme.ink_secondary)
        ax.plot(x, table["perfect"], color=self.theme.ink_muted, linewidth=1, linestyle="--")
        ax.text(x[-1], table["perfect"].iloc[-1], "완벽한 예측 ", ha="right", va="bottom",
                fontsize=8.5, color=self.theme.ink_muted)  # fmt: skip
        clipped = table.loc[table["none"] > top, "none"]
        note = ", ".join(f"{r:g}:1 {v:.2f}" for r, v in clipped.items())
        label = "검사 안 함" + (f" ({note}, 축 밖)" if note else "")
        ax.plot(x, table["none"].clip(upper=top), color=self.theme.ink_muted, linewidth=1.2,
                linestyle=":", label=label)  # fmt: skip
        for name, color in self._colors().items():
            ax.plot(x, table[name], color=color, marker="o", markersize=5, label=SHORT[name])
        ax.set_ylim(0, top)
        ax.set_title("제품 1개당 비용 (검사 비용 1 기준)", loc="left", fontsize=11)
        for name, color in self._colors().items():
            if name in ("model", "rule", "switching", "sampling"):
                axes[1].plot(x, rate[name], color=color, marker="o", markersize=5)
        axes[1].yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        axes[1].set_ylim(0, 1.02)
        axes[1].set_title("검사 비율", loc="left", fontsize=11)
        for a in axes:
            self._ratio_axis(a, ratios)
            self.tidy(a)
        full = summary.xs("full", level="strategy").iloc[0]
        rate_total = full["defects"] / full["parts"]
        self.header(fig, "검사 방식별 총비용과 비용 비율 민감도",
                    f"평가 제품 {full['parts']:.0f}개, 불량률 {rate_total:.1%} → 비용 비율 "
                    f"{1 / rate_total:.1f}:1 미만이면 검사 안 함이 전수검사보다 싸다. 조정값은 "
                    "로트마다 과거 데이터로만 다시 정함", axes[0])  # fmt: skip
        return fig

    def uncertainty(self, unc: pd.DataFrame, ratios=(5, 10, 20)) -> Figure:
        ratios = [r for r in ratios if r in unc.index.unique("ratio")]
        fig, axes = self.panels((12.5, 4.6), ncols=len(ratios), header_in=0.8)
        for ax, ratio in zip(axes, ratios, strict=True):
            g = unc.xs(ratio, level="ratio").drop(["perfect", "none"], errors="ignore")
            g = g.sort_values("cost_per_part", ascending=False)
            y = np.arange(len(g))
            tied = ((g["diff_low"] <= 0) & (g["diff_high"] >= 0)).to_numpy()
            tied = tied & ~g.index.isin(NOT_COMPARABLE)
            ax.hlines(y, g["ci_low"], g["ci_high"], color=self.theme.baseline, linewidth=2)
            colors = [self.theme.series[0] if t else self.theme.ink_muted for t in tied]
            ax.scatter(g["cost_per_part"], y, s=48, zorder=3, color=colors,
                       edgecolors=self.theme.surface, linewidths=1.5)  # fmt: skip
            ax.axvline(1, color=self.theme.ink_muted, linewidth=1)
            ax.set_yticks(y, [SHORT[s] for s in g.index])
            for label, t in zip(ax.get_yticklabels(), tied, strict=True):
                label.set_fontweight("bold" if t else "normal")
            ax.set_title(f"{ratio}:1", loc="left", fontsize=11)
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        self.header(fig, "방식별 제품당 비용의 불확실성 (로트 bootstrap 95% 구간)",
                    "굵은 글씨·파란 점 = 그 비율에서 가장 싼 방식과 구별되지 않음"
                    "(차이 구간이 0 포함). 세로선 = 전수검사")  # fmt: skip
        return fig

    # 8.1 샘플링 검사 ---------------------------------------------------------------------
    def sampling_capture(self, tables: dict[str, pd.DataFrame]) -> Figure:
        curves, plans = tables["curves"], tables["plans"]
        switching, points = tables["switching_curve"], tables["points"]
        fig, ax = self.panels((8.2, 6.2))
        ax.plot([0, 1], [0, 1], color=self.theme.ink_muted, linewidth=1, label="무작위")
        ax.plot(curves.index, curves["et"], color=self.theme.series[0], label="모델 선별")
        ax.plot(curves.index, curves["recent_rate"], color=self.theme.series[1], label="규칙 선별")
        sw = switching.sort_values("inspect_rate")
        ax.plot(sw["inspect_rate"], sw["capture"], color=self.theme.series[2],
                label="검사 강도 전환")  # fmt: skip
        grid = plans[~plans["classical"]]
        ax.scatter(grid["inspect_rate"], grid["capture"], s=30, facecolors=self.theme.surface,
                   edgecolors=self.theme.series[3], linewidths=1.3, zorder=3,
                   label="샘플링 계획 (n·c 격자)")  # fmt: skip
        classical = plans[plans["classical"]].iloc[0]
        ax.scatter(
            classical["inspect_rate"],
            classical["capture"],
            s=70,
            zorder=4,
            color=self.theme.series[3],
            edgecolors=self.theme.surface,
            linewidths=1.5,
        )
        ax.annotate(
            f"AQL 설계 {plans.index[plans['classical']][0]}",
            (classical["inspect_rate"], classical["capture"]),
            xytext=(8, -14),
            textcoords="offset points",
            fontsize=8.5,
            color=self.theme.ink_secondary,
        )
        cav = points.loc["cavity_1"]
        ax.scatter(cav["inspect_rate"], cav["capture"], s=70, marker="D", zorder=4,
                   color=self.theme.series[4], edgecolors=self.theme.surface, linewidths=1.5,
                   label="캐비티1만 검사")  # fmt: skip
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("검사 비율")
        ax.set_ylabel("불량 포착률")
        self.tidy(ax, grid_axis="both")
        better = int((grid["capture"] > grid["capture_et"]).sum())
        self.header(fig, "같은 검사량에서 불량을 얼마나 찾나",
                    f"샘플링 계획 {len(grid)}개 중 같은 검사량에서 모델 선별보다 많이 찾는 계획 "
                    f"{better}개. 로트 = 50 shot(제품 약 100개)", ax)  # fmt: skip
        return fig

    def oc_curve(self, oc: pd.DataFrame, lots: pd.DataFrame) -> Figure:
        fig, ax = self.panels((8.2, 4.8))
        for i, plan in enumerate(oc.columns):
            note = " (AQL 설계)" if i == 0 else " (비용 최소로 가장 자주 선택)"
            ax.plot(oc.index, oc[plan], color=self.theme.series[i], label=plan + note)
        ax.plot(lots["rate"], np.full(len(lots), -0.03), "|", color=self.theme.ink_muted,
                markersize=10, label="평가 로트의 실제 불량률")  # fmt: skip
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_ylim(-0.06, 1.02)
        ax.set_xlim(0, oc.index.max())
        ax.set_xlabel("로트 불량률")
        ax.set_ylabel("로트 합격 확률")
        self.tidy(ax, grid_axis="both")
        share = (lots["rate"] > 0.10).mean()
        self.header(fig, "단일 샘플링 검사의 OC curve (로트 100개, 초기하분포)",
                    f"평가 로트 {len(lots)}개 중 불량률 10% 초과가 {share:.0%}. 불합격 로트는 "
                    "전수검사(선별형)", ax)  # fmt: skip
        return fig

    # 8.2 확률 보정 -----------------------------------------------------------------------
    def reliability(self, tables: dict[str, pd.DataFrame]) -> Figure:
        rel, scores = tables["reliability"], tables["scores"]
        fig, axes = self.panels((12.5, 4.6), ncols=len(SCORERS), sharey=True)
        top = float(max(rel["mean_prob"].max(), rel["observed"].max()) * 1.05)
        for ax, scorer in zip(axes, SCORERS, strict=True):
            ax.plot([0, top], [0, top], color=self.theme.ink_muted, linewidth=1)
            for i, method in enumerate(CALIBRATORS):
                r = rel.loc[(scorer, method)]
                ax.plot(r["mean_prob"], r["observed"], color=self.theme.series[i], marker="o",
                        markersize=5, label=CALIBRATORS[method].label)  # fmt: skip
            s = scores.loc[scorer]
            ax.set_title(f"{SCORER_LABELS[scorer]}\nBrier {s.loc['raw', 'brier']:.4f} → "
                         f"{s.loc['platt', 'brier']:.4f} / {s.loc['isotonic', 'brier']:.4f}",
                         loc="left", fontsize=10.5)  # fmt: skip
            ax.set_xlim(0, top)
            ax.set_ylim(0, top)
            ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.set_xlabel("평균 예측 확률 (10분위 구간)")
            self.tidy(ax, grid_axis="both")
        axes[0].set_ylabel("실제 불량률")
        self.header(fig, "신뢰도 그림: 예측 확률과 실제 불량률",
                    "대각선에 가까울수록 보정이 잘 된 것. 보정기는 로트마다 과거 예측으로 "
                    "다시 학습. Brier: 보정 없음 → Platt / Isotonic", axes[0])  # fmt: skip
        return fig

    def calibration_cost(self, cost: pd.DataFrame) -> Figure:
        ratios = list(cost.index.unique("ratio"))
        x = np.arange(len(ratios))
        policies = [*CALIBRATORS, "cost_min"]
        labels = CalibrationAnalysis.POLICIES
        fig, axes = self.panels((12.5, 4.6), ncols=len(SCORERS), sharey=True)
        values = cost["cost_per_part"]
        for ax, scorer in zip(axes, SCORERS, strict=True):
            base = values.xs((scorer, "hindsight"), level=("scorer", "policy")).reindex(ratios)
            ax.axhline(0, color=self.theme.ink_muted, linewidth=1)
            for i, policy in enumerate(policies):
                v = values.xs((scorer, policy), level=("scorer", "policy")).reindex(ratios)
                ax.plot(x, v - base, color=self.theme.series[i], marker="o", markersize=5,
                        label=labels[policy])  # fmt: skip
            ax.set_title(SCORER_LABELS[scorer], loc="left", fontsize=11)
            self._ratio_axis(ax, ratios)
            self.tidy(ax)
        axes[0].set_ylabel("사후 최적 임계값 대비 추가 비용 (제품당)")
        handles = [Line2D([], [], color=self.theme.series[i], marker="o", markersize=5,
                          label=labels[p]) for i, p in enumerate(policies)]  # fmt: skip
        self.header(fig, "보정이 비용 판정을 바꾸나",
                    "0 = 평가 기간 전체를 보고 고른 단일 임계값(실제로는 알 수 없음). 보정 방식은 "
                    "보정 확률 ≥ 1/비용 비율이면 검사", handles=handles)  # fmt: skip
        return fig
