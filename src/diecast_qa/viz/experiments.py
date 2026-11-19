"""6단계 추가 실험 그림. 실험 이름마다 그리는 메서드를 둔다."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator, PercentFormatter

from diecast_qa.analysis import AnalysisResult
from diecast_qa.experiments import combination, drift, retraining, synthetic, temporal
from diecast_qa.viz.models import LABELS, ModelCharts


class ExperimentCharts(ModelCharts):
    def render(self, result: AnalysisResult, out_dir: Path) -> list[Path]:
        drawers = {
            "e81_synthetic": self.synthetic,
            "e82_alarm_retrain": self.alarm_retrain,
            "e83_combination": self.combination,
            "e84_drift": self.drift,
            "e85_recency": self.recency,
            "e88_temporal": self.temporal,
        }
        charts = drawers[result.name](result.tables)
        return self.render_to(out_dir, {f"{result.name}_{k}": v for k, v in charts.items()})

    # 6.1 합성 데이터 -----------------------------------------------------------------------
    def synthetic(self, tables: dict[str, pd.DataFrame]) -> dict:
        return {
            "stage1": lambda: self._synthetic_stage1(tables["stage1"]),
            "quality": lambda: self._synthetic_quality(tables["quality"]),
        }

    def _synthetic_stage1(self, s1: pd.DataFrame) -> Figure:
        names = list(synthetic.TECHNIQUES)
        order = s1.loc["time_order", "roc_auc_mean"].reindex(names).sort_values().index
        metrics = (("roc_auc_mean", "ROC-AUC", 0.5, False),
                   ("recall_at_05_mean", "Recall (임계값 0.5)", None, True))  # fmt: skip
        fig, axes = self.panels((10.5, 5.0), ncols=2, sharey=True)
        for ax, (col, title, ref, percent) in zip(axes, metrics, strict=True):
            values = s1[col].unstack("design").reindex(order)
            self.dumbbell(ax, values, synthetic.LABELS, title, reference=ref, percent=percent)
        auc = s1["roc_auc_mean"].unstack("design").reindex(names)
        gain = (auc["same_term"] - auc.loc["none", "same_term"]).drop("none").max()
        below = [synthetic.LABELS[n] for n in names if auc.loc[n, "time_order"] < 0.5]
        self.header(fig, "불균형 처리·합성 데이터 비교 (1단계 RF, fold 평균)",
                    f"① 증강 없음 대비 ROC-AUC 최대 변화 {gain:+.3f}. "
                    f"② 시간 순서에서 무작위(0.5)보다 낮은 기법: {', '.join(below) or '없음'}",
                    axes[0])  # fmt: skip
        return fig

    def _synthetic_quality(self, quality: pd.DataFrame) -> Figure:
        q = quality.reindex(list(synthetic.QUALITY_GENERATORS)[::-1])
        y = np.arange(len(q))
        labels = [synthetic.LABELS[g] for g in q.index]
        panels = (("tstr_auc", "TSTR: 합성 불량으로 학습 → 실제로 평가 (ROC-AUC)",
                   q["real_auc"].mean(), "실제 불량으로 학습"),
                  ("discriminator_auc", "진짜/가짜 판별 ROC-AUC (0.5면 구별 못 함)", 0.5,
                   "구별 못 함"))  # fmt: skip
        fig, axes = self.panels((10.5, 3.8), ncols=2, sharey=True, header_in=0.8)
        for ax, (col, title, ref, ref_label) in zip(axes, panels, strict=True):
            ax.scatter(q[col], y, s=60, zorder=3, color=self.theme.series[0],
                       edgecolors=self.theme.surface, linewidths=1.5)  # fmt: skip
            for yi, v in zip(y, q[col], strict=True):
                ax.text(v, yi + 0.22, f"{v:.2f}", ha="center", fontsize=9,
                        color=self.theme.ink_secondary)  # fmt: skip
            ax.axvline(ref, color=self.theme.ink_muted, linewidth=1)
            ax.text(ref, len(q) - 0.45, f" {ref_label} {ref:.2f}", fontsize=8.5,
                    color=self.theme.ink_muted)  # fmt: skip
            ax.set_yticks(y, labels)
            ax.set_ylim(-0.5, len(q) - 0.2)
            ax.set_title(title, loc="left", fontsize=10.5)
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        self.header(
            fig,
            "합성 데이터 품질 (① 같은 기간 5개 fold 평균)",
            "왼쪽: 실제 양품 + 합성 불량으로 학습한 모델의 실제 평가 성능. "
            "오른쪽: 실제 불량과 합성 불량을 구별하는 정도 (1이면 완전히 구별됨)",
        )
        return fig

    # 6.3 관리도 경보 기반 재학습 ------------------------------------------------------------
    def alarm_retrain(self, tables: dict[str, pd.DataFrame]) -> dict:
        return {"compare": lambda: self._alarm_compare(tables["pooled"])}

    def _alarm_compare(self, pooled: pd.DataFrame) -> Figure:
        model = pooled.xs(retraining.MODEL, level="model").reindex(list(retraining.LABELS))
        rule = pooled.xs("recent_rate", level="model")
        order = model["roc_auc"].sort_values().index
        labels = [f"{retraining.LABELS[d]}  (재학습 {int(model.loc[d, 'retrains'])}회)"
                  for d in order]  # fmt: skip
        y = np.arange(len(order))
        metrics = (("roc_auc", "ROC-AUC", False), ("capture_20", "상위 20% 포착률", True))
        fig, axes = self.panels((10.5, 4.6), ncols=2, sharey=True)
        for ax, (col, title, percent) in zip(axes, metrics, strict=True):
            ax.scatter(model.loc[order, col], y, s=60, zorder=3, color=self.theme.series[0],
                       edgecolors=self.theme.surface, linewidths=1.5,
                       label=LABELS[retraining.MODEL])  # fmt: skip
            ref = rule[col].mean()
            ax.axvline(ref, color=self.theme.ink_secondary, linewidth=1, label="최근 불량률 규칙")
            ax.set_yticks(y, labels)
            ax.set_title(title, loc="left", fontsize=11)
            if percent:
                ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        self.header(fig, "재학습 시점: 고정 주기 vs 관리도 경보 (평가 구간 합산)",
                    "같은 평가 구간(②의 블록 2~5)에서 Extra Trees를 다시 학습하는 시점만 바꿨다. "
                    "세로선은 최근 10 shot 불량률 규칙", axes[0])  # fmt: skip
        return fig

    # 6.5 최근 데이터 가중치 ----------------------------------------------------------------
    def recency(self, tables: dict[str, pd.DataFrame]) -> dict:
        return {"compare": lambda: self._recency_compare(tables["pooled"])}

    def _recency_compare(self, pooled: pd.DataFrame) -> Figure:
        series = {"retrain_100": "100 shot마다 재학습", "retrain_500": "500 shot마다 재학습"}
        variants = list(retraining.VARIANTS)
        metrics = (("roc_auc", "ROC-AUC", False), ("capture_20", "상위 20% 포착률", True))
        fig, axes = self.panels((10.5, 4.4), ncols=2, sharey=True)
        for ax, (col, title, percent) in zip(axes, metrics, strict=True):
            values = pooled[col].unstack("design").reindex(variants[::-1])
            self.dumbbell(ax, values, retraining.VARIANTS, title, percent=percent, series=series)
        self.header(fig, "학습 데이터 범위·시간 가중치 (Extra Trees, 평가 구간 합산)",
                    "오래된 데이터를 빼거나 가중치를 줄였을 때의 변화", axes[0])  # fmt: skip
        return fig

    # 6.6 시간 정보를 활용한 학습 -------------------------------------------------------------
    def temporal(self, tables: dict[str, pd.DataFrame]) -> dict:
        return {"compare": lambda: self._temporal_compare(tables)}

    def _temporal_compare(self, tables: dict[str, pd.DataFrame]) -> Figure:
        second, third = tables["time_order"], tables["retrain"]
        series = {"time_order": "② 시간 순서 (fold 평균)", "retrain_200": "③ 200 shot마다 재학습",
                  "retrain_50": "③ 50 shot마다 재학습"}  # fmt: skip
        metrics = (("roc_auc", "ROC-AUC", False), ("capture_20", "상위 20% 포착률", True))
        order = second["roc_auc_mean"].reindex(list(temporal.LABELS)).sort_values().index
        fig, axes = self.panels((11, 4.8), ncols=2, sharey=True)
        for ax, (col, title, percent) in zip(axes, metrics, strict=True):
            retrains = {d: third.xs(d, level="design")[col] for d in ("retrain_200", "retrain_50")}
            values = pd.DataFrame({"time_order": second[f"{col}_mean"], **retrains}).reindex(order)
            y = np.arange(len(values))
            ax.hlines(y, values.min(axis=1), values.max(axis=1), color=self.theme.baseline,
                      linewidth=1.5)  # fmt: skip
            for i, (design, label) in enumerate(series.items()):
                ax.scatter(values[design], y, s=52, zorder=3, color=self.theme.series[i],
                           edgecolors=self.theme.surface, linewidths=1.5, label=label)  # fmt: skip
            ax.set_yticks(y, [temporal.LABELS[k] for k in values.index])
            ax.set_title(title, loc="left", fontsize=11)
            if percent:
                ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
                ax.xaxis.set_major_locator(MultipleLocator(0.05))
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        self.header(fig, "시간 정보를 활용한 학습 (Extra Trees)",
                    "입력 변수와 학습 가중치를 바꾼 여섯 방법과 규칙 비교. 아래에서 위로 "
                    "② ROC-AUC가 높아지는 순서", axes[0])  # fmt: skip
        return fig

    # 6.4 규칙 + 모델 결합 ------------------------------------------------------------------
    def combination(self, tables: dict[str, pd.DataFrame]) -> dict:
        return {"compare": lambda: self._combination_compare(tables)}

    def _combination_compare(self, tables: dict[str, pd.DataFrame]) -> Figure:
        series = {"time_order": "② 시간 순서 (fold 평균)", "retrain_100": "③ 100 shot마다 재학습"}
        second, third = tables["time_order"], tables["retrain_100"]
        metrics = (("roc_auc", "ROC-AUC", False), ("capture_20", "상위 20% 포착률", True))
        order = third["roc_auc"].reindex(list(combination.LABELS)).sort_values().index
        fig, axes = self.panels((10.5, 4.4), ncols=2, sharey=True)
        for ax, (col, title, percent) in zip(axes, metrics, strict=True):
            values = pd.DataFrame({"time_order": second[f"{col}_mean"],
                                   "retrain_100": third[col]}).reindex(order)  # fmt: skip
            self.dumbbell(ax, values, combination.LABELS, title, percent=percent, series=series)
        self.header(fig, "규칙과 모델 점수 결합",
                    "규칙(최근 10 shot 불량률)과 Extra Trees 점수를 합치는 세 가지 방법",
                    axes[0])  # fmt: skip
        return fig

    # 6.2 기간별 변화 진단 ------------------------------------------------------------------
    def drift(self, tables: dict[str, pd.DataFrame]) -> dict:
        return {
            "psi": lambda: self._drift_psi(tables["psi"], tables["adversarial_runs"]),
            "shap": lambda: self._drift_shap(tables["shap_by_run"]),
        }

    def _heatmap(self, ax, table: pd.DataFrame, fmt: str, vmax: float) -> None:
        values = table.to_numpy(float)
        ax.imshow(np.clip(values, 0, vmax), cmap=self.sequential_cmap(), vmin=0, vmax=vmax,
                  aspect="auto")  # fmt: skip
        for (i, j), v in np.ndenumerate(values):
            color = "#ffffff" if v >= vmax * 0.55 else self.theme.ink
            ax.text(j, i, format(v, fmt), ha="center", va="center", fontsize=8.5, color=color)
        ax.set_yticks(range(len(table)), table.index)
        ax.tick_params(length=0)
        ax.spines[:].set_visible(False)

    def _drift_psi(self, psi: pd.DataFrame, runs: pd.DataFrame) -> Figure:
        table = psi.loc[psi.max(axis=1).sort_values(ascending=False).index]
        fig, ax = self.panels((7.8, 7.4), header_in=0.8)
        self._heatmap(ax, table, ".2f", vmax=1.0)
        ax.set_xticks(range(len(table.columns)),
                      [f"구간 {p}\n구별 AUC {runs.loc[p, 'adversarial_auc']:.2f}\n"
                       f"(공정 변수만 {runs.loc[p, 'adversarial_auc_process']:.2f})"
                       for p in table.columns], fontsize=8.5)  # fmt: skip
        ax.xaxis.tick_top()
        self.header(fig, "인접 구간 사이 변수별 분포 변화 (PSI)",
                    "0.1 미만 안정, 0.25 초과 큰 변화. 색은 1 이상에서 가장 진하다")  # fmt: skip
        return fig

    def _drift_shap(self, shap_by_run: pd.DataFrame) -> Figure:
        top = set().union(*(shap_by_run[r].nlargest(drift.TOP_K).index for r in shap_by_run))
        table = shap_by_run.loc[sorted(top, key=lambda v: -shap_by_run.loc[v].max())]
        fig, ax = self.panels((6.8, 6.0), header_in=0.8)
        self._heatmap(ax, table * 100, ".0f", vmax=float(table.max().max() * 100))
        ax.set_xticks(range(len(table.columns)), [f"구간 {r}" for r in table.columns])
        ax.xaxis.tick_top()
        self.header(
            fig,
            "구간별 SHAP 주요 변수 (평균 |SHAP| 비중, %)",
            f"구간마다 따로 학습한 RF. 구간별 상위 {drift.TOP_K}개 변수의 합집합",
        )
        return fig
