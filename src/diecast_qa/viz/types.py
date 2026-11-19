"""5단계 2단계 불량 유형 분류 그림."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

from diecast_qa.config import TYPE5_LABELS
from diecast_qa.modeling.stage2 import Stage2Results
from diecast_qa.modeling.type_models import TYPE_CLASSES, TYPE_MODELS, TYPE_RULES
from diecast_qa.viz.models import DESIGN_LABELS, LABELS, ModelCharts

TYPE_LABELS = {name: spec.label for name, spec in {**TYPE_MODELS, **TYPE_RULES}.items()}
STAGE1_LABELS = {"recent_rate": "최근 불량률 규칙", **{m: LABELS[m] for m in ("et", "xgb", "rf")}}


class Stage2Charts(ModelCharts):
    def render(self, results: Stage2Results, out_dir: Path) -> list[Path]:
        return self.render_to(out_dir, {
            "stage2_design_gap": lambda: self.design_gap(results.summary),
            "stage2_class_f1": lambda: self.class_f1(results),
            "stage2_confusion": lambda: self.confusion(results),
            "stage2_joint": lambda: self.joint(results),
            "stage2_retrain": lambda: self.retrain(results.pooled),
        })  # fmt: skip

    def design_gap(self, summary: pd.DataFrame) -> Figure:
        order = summary.xs("time_order", level="design")["macro_f1_mean"].sort_values().index
        metrics = (("macro_f1_mean", "Macro-F1", None),
                   ("balanced_accuracy_mean", "Balanced Accuracy", 0.2))  # fmt: skip
        fig, axes = self.panels((10.5, 4.4), ncols=2, sharey=True)
        for ax, (col, title, chance) in zip(axes, metrics, strict=True):
            values = summary[col].unstack("design").reindex(order)
            self.dumbbell(ax, values, TYPE_LABELS, title, reference=chance)
        self.header(fig, "검증 방식에 따른 2단계 유형 분류 성능 (fold 평균)",
                    "불량 제품 5개 유형. Balanced Accuracy의 세로선은 무작위(1/5) 수준",
                    axes[0])  # fmt: skip
        return fig

    def class_f1(self, results: Stage2Results) -> Figure:
        """② 최고 모델의 유형별 F1: ① → ② (fold 합산)."""
        best = results.best_model("time_order")
        f1 = results.per_class.xs(best, level="model")["f1"].unstack("design")
        support = results.per_class.xs(("time_order", best), level=["design", "model"])["support"]
        values = f1.reindex(list(TYPE_CLASSES)[::-1])
        labels = {t: f"{TYPE5_LABELS[t]} ({support[t]}개)" for t in TYPE_CLASSES}
        fig, ax = self.panels((7.8, 4.4))
        self.dumbbell(ax, values, labels, f"{TYPE_LABELS[best]} 유형별 F1")
        drop = (values["same_term"] - values["time_order"]).idxmax()
        self.header(fig, "유형별 F1: 같은 기간 → 시간 순서",
                    f"괄호는 ② 평가 구간의 불량 수. 가장 크게 떨어진 유형은 {TYPE5_LABELS[drop]}"
                    " (구간마다 유형 분포가 달라짐)", ax)  # fmt: skip
        return fig

    def confusion(self, results: Stage2Results) -> Figure:
        """① ②에서 ② 최고 모델의 혼동행렬 (실제 유형별 비율)."""
        best = results.best_model("time_order")
        fig, axes = self.panels((10.5, 4.8), ncols=2)
        names = [TYPE5_LABELS[t] for t in TYPE_CLASSES]
        cmap = self.sequential_cmap()
        for ax, (design, label) in zip(axes, DESIGN_LABELS.items(), strict=True):
            counts = results.confusion.xs((design, best), level=["design", "model"])
            counts = counts.reindex(index=list(TYPE_CLASSES), fill_value=0)
            share = counts.div(counts.sum(axis=1).replace(0, np.nan), axis=0)
            ax.imshow(share.to_numpy(float), cmap=cmap, vmin=0, vmax=1)
            for (i, j), v in np.ndenumerate(share.to_numpy(float)):
                if not np.isnan(v):
                    color = "#ffffff" if v >= 0.5 else self.theme.ink
                    ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=9, color=color)
            ax.set_xticks(range(5), names)
            ax.set_yticks(range(5), names)
            ax.set_xlabel("예측 유형")
            ax.set_title(label, loc="left", fontsize=11)
            ax.tick_params(length=0)
            ax.spines[:].set_visible(False)
        axes[0].set_ylabel("실제 유형")
        self.header(fig, f"{TYPE_LABELS[best]} 혼동행렬 (실제 유형별 비율, fold 합산)",
                    "대각선이 맞힌 비율. 색이 진할수록 비율이 높다")  # fmt: skip
        return fig

    def joint(self, results: Stage2Results, frac: float = 0.2) -> Figure:
        """상위 frac 검사 시 전체 불량의 구성: 유형까지 적중 / 포착했지만 유형 틀림 / 놓침."""
        fig, axes = self.panels((10.5, 4.2), ncols=2, sharex=True)
        parts = (("유형까지 적중", self.theme.series[0]), ("포착, 유형 틀림", self.theme.series[1]),
                 ("놓침", self.theme.neutral))  # fmt: skip
        for ax, (design, label) in zip(axes, DESIGN_LABELS.items(), strict=True):
            joint = results.joint.xs((design, frac), level=["design", "frac"])["end_to_end"]
            s1, s2 = results.best_joint(design, frac)
            # 1단계 모델(규칙 제외) 중 같은 2단계 모델과 짝지었을 때 가장 나은 것
            models = joint.xs(s2, level="stage2_model").drop("recent_rate", errors="ignore")
            combos = [(s1, s2), ("recent_rate", s2), (models.idxmax(), s2),
                      ("recent_rate", "type_group_mode")]  # fmt: skip
            rows = list(dict.fromkeys(c for c in combos if c in joint.index))[::-1]
            joint = results.joint.xs((design, frac), level=["design", "frac"])
            y = np.arange(len(rows))
            left = np.zeros(len(rows))
            for (name, color), values in zip(parts, self._split(joint, rows), strict=True):
                ax.barh(y, values, left=left, height=0.6, color=color, label=name,
                        edgecolor=self.theme.surface, linewidth=1.5)  # fmt: skip
                for yi, (start, v) in enumerate(zip(left, values, strict=True)):
                    if v >= 0.1:
                        ax.text(start + v / 2, yi, f"{v:.0%}", ha="center", va="center",
                                fontsize=8.5, color=self.theme.label_on(color)
                                if color != self.theme.neutral else self.theme.ink)  # fmt: skip
                left += values
            ax.set_yticks(y, [f"{STAGE1_LABELS.get(a, a)}\n→ {TYPE_LABELS[b]}" for a, b in rows],
                          fontsize=8.5)  # fmt: skip
            ax.set_xlim(0, 1)
            ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.set_title(label, loc="left", fontsize=11)
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        self.header(fig, f"1·2단계 연결 평가: 위험도 상위 {frac:.0%} 검사 시 전체 불량의 행방",
                    "막대 하나가 전체 불량 100%. 1단계 위험도 → 2단계 예상 유형 조합별",
                    axes[0])  # fmt: skip
        return fig

    def retrain(self, pooled: pd.DataFrame) -> Figure:
        retrain = pooled[pooled.index.get_level_values("design").str.startswith("retrain")]
        metrics = (("macro_f1", "Macro-F1"), ("balanced_accuracy", "Balanced Accuracy"))
        fig, axes = self.panels((10.5, 4.6), ncols=2)
        for ax, (col, title) in zip(axes, metrics, strict=True):
            table = self.by_interval(retrain, col)
            self.interval_lines(ax, table, TYPE_LABELS, title)
        self.header(fig, "③ 재학습 주기에 따른 2단계 성능 (평가 구간 합산)",
                    "매번 그 시점 이전에 생산된 불량 제품으로 다시 학습", axes[0])  # fmt: skip
        return fig

    @staticmethod
    def _split(joint: pd.DataFrame, rows: list) -> tuple[np.ndarray, ...]:
        r = joint.loc[rows]
        hit = r["end_to_end"].to_numpy()
        wrong = r["capture"].to_numpy() - hit
        return hit, wrong, 1 - hit - wrong
