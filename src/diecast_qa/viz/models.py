"""4단계 1단계 모델 그림과, 1·2단계 그림이 함께 쓰는 패널."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from diecast_qa.modeling.estimators import MODELS, RULES
from diecast_qa.modeling.metrics import capture_rate
from diecast_qa.modeling.study import StudyResults
from diecast_qa.viz.base import ChartBuilder

LABELS = {name: spec.label for name, spec in {**MODELS, **RULES}.items()}
DESIGN_LABELS = {"same_term": "① 같은 기간", "time_order": "② 시간 순서"}


class ModelCharts(ChartBuilder):
    """검증 방식 비교(덤벨)와 재학습 주기별 선 그래프 패널."""

    def dumbbell(
        self, ax: Axes, values: pd.DataFrame, labels: dict[str, str], title: str,
        reference: float | None = None, percent: bool = False,
        series: dict[str, str] = DESIGN_LABELS,
    ) -> None:  # fmt: skip
        """values: 행 = 항목(위에서 아래로 그릴 순서의 역순), 열 = series의 두 비교 대상."""
        y = np.arange(len(values))
        first, second = (values[d] for d in series)
        ax.hlines(y, first, second, color=self.theme.baseline, linewidth=1.5)
        for i, (design, label) in enumerate(series.items()):
            ax.scatter(values[design], y, s=52, zorder=3, color=self.theme.series[i],
                       edgecolors=self.theme.surface, linewidths=1.5, label=label)  # fmt: skip
        if reference is not None:
            ax.axvline(reference, color=self.theme.ink_muted, linewidth=1)
        ax.set_yticks(y, [labels.get(k, k) for k in values.index])
        ax.set_title(title, loc="left", fontsize=11)
        if percent:
            ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        self.tidy(ax, grid_axis="x")
        ax.spines[["left", "bottom"]].set_visible(False)

    def interval_lines(
        self, ax: Axes, table: pd.DataFrame, labels: dict[str, str], title: str,
        reference: tuple[float, str] | None = None, percent: bool = False,
    ) -> None:  # fmt: skip
        """table: 행 = 재학습 주기(shot), 열 = 모델."""
        x = np.arange(len(table))
        for i, model in enumerate(table.columns):
            ax.plot(x, table[model], color=self.theme.series[i], marker="o", markersize=6,
                    label=labels.get(model, model))  # fmt: skip
        if reference is not None:
            value, text = reference
            ax.axhline(value, color=self.theme.ink_secondary, linewidth=1)
            ax.text(x[-1], value, f"{text} ", ha="right", va="bottom", fontsize=9,
                    color=self.theme.ink_secondary)  # fmt: skip
        ax.set_xticks(x, [f"{n} shot" for n in table.index])
        ax.set_title(title, loc="left", fontsize=11)
        if percent:
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        self.tidy(ax)

    @staticmethod
    def by_interval(retrain: pd.DataFrame, col: str) -> pd.DataFrame:
        """(design=retrain_N, model) 행의 col을 행 = N, 열 = 모델 표로."""
        table = retrain[col].unstack("model")
        table.index = table.index.str.removeprefix("retrain_").astype(int)
        return table.sort_index()


class Stage1Charts(ModelCharts):
    def render(self, results: StudyResults, out_dir: Path) -> list[Path]:
        return self.render_to(out_dir, {
            "stage1_design_gap": lambda: self.design_gap(results.summary),
            "stage1_capture_curve": lambda: self.capture_curve(results.predictions,
                                                               results.summary),
            "stage1_retrain": lambda: self.retrain(results.pooled),
        })  # fmt: skip

    def design_gap(self, summary: pd.DataFrame) -> Figure:
        """모델·규칙마다 ① 같은 기간 → ② 시간 순서 성능 (덤벨). ② 순으로 정렬."""
        main = summary.xs(("main", "base", ""), level=["experiment", "feature_set", "variant"])
        second = main.xs("time_order", level="design")["roc_auc_mean"]
        order = second.sort_values().index
        metrics = (("roc_auc_mean", "ROC-AUC", 0.5, False),
                   ("capture_20_mean", "상위 20% 검사 시 불량 포착률", 0.2, True))  # fmt: skip
        fig, axes = self.panels((10.5, 5.2), ncols=2, sharey=True)
        for ax, (col, title, chance, percent) in zip(axes, metrics, strict=True):
            values = main[col].unstack("design").reindex(order)
            self.dumbbell(ax, values, LABELS, title, reference=chance, percent=percent)
        best = second.loc[second.index.intersection(list(MODELS))].idxmax()
        verdict = "높다" if second["recent_rate"] > second[best] else "낮다"
        self.header(fig, "검증 방식에 따른 1단계 성능 (fold 평균)",
                    f"세로선은 무작위 검사 수준. ② 시간 순서에서 최근 불량률 규칙"
                    f"({second['recent_rate']:.2f})이 가장 나은 모델 {LABELS[best]}"
                    f"({second[best]:.2f})보다 {verdict}", axes[0])  # fmt: skip
        return fig

    def capture_curve(self, predictions: pd.DataFrame, summary: pd.DataFrame) -> Figure:
        """② 시간 순서 평가 구간 전체(4개 블록 합산)의 검사 비율별 누적 포착률."""
        main = predictions[(predictions["experiment"] == "main")
                           & (predictions["design"] == "time_order")]  # fmt: skip
        models = summary.xs(("main", "time_order", "base", ""),
                            level=["experiment", "design", "feature_set", "variant"])  # fmt: skip
        best = models.loc[models.index.intersection(list(MODELS)), "roc_auc_mean"].idxmax()
        fracs = np.linspace(0.01, 1, 100)
        fig, ax = self.panels((7.6, 5.0))
        for i, name in enumerate((best, "recent_rate", "cavity_rate")):
            g = main[main["model"] == name]
            curve = [capture_rate(g["y"].to_numpy(), g["p_defect"].to_numpy(), f) for f in fracs]
            ax.plot(fracs, curve, color=self.theme.series[i], label=LABELS[name])
        ax.plot([0, 1], [0, 1], color=self.theme.ink_muted, linewidth=1, label="무작위 검사")
        ax.axvline(0.2, color=self.theme.baseline, linewidth=1)
        for axis in (ax.xaxis, ax.yaxis):
            axis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_xlabel("검사 비율 (위험도 높은 순)")
        ax.set_ylabel("찾은 불량 비율")
        self.tidy(ax, grid_axis="both")
        self.header(fig, "② 시간 순서 평가 구간의 불량 포착 곡선",
                    f"모델 중 가장 나은 {LABELS[best]}과 단순 규칙 비교. 세로선은 검사 비율 20%",
                    ax)  # fmt: skip
        return fig

    def retrain(self, pooled: pd.DataFrame) -> Figure:
        """③ 재학습 주기별 성능 (평가 구간 합산).

        ②는 학습 데이터 정의가 달라(각 제품 유형의 이전 블록) 같은 선에 잇지 않는다.
        """
        retrain = pooled.xs(("retrain", "base", ""), level=["experiment", "feature_set", "variant"])
        metrics = (("roc_auc", "ROC-AUC", False), ("capture_20", "상위 20% 포착률", True))
        fig, axes = self.panels((10.5, 4.6), ncols=2)
        for ax, (col, title, percent) in zip(axes, metrics, strict=True):
            table = self.by_interval(retrain, col)
            rule = table.pop("recent_rate").mean()
            self.interval_lines(ax, table, LABELS, title, (rule, "최근 불량률 규칙"), percent)
        self.header(fig, "③ 재학습 주기에 따른 성능 (평가 구간 합산)",
                    "매번 그 시점 이전에 생산된 모든 데이터로 다시 학습. "
                    "가로선은 최근 10 shot 불량률 규칙", axes[0])  # fmt: skip
        return fig
