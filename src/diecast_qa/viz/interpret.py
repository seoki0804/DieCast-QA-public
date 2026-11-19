"""7단계 해석·관리 범위 그림."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import MaxNLocator, NullLocator, PercentFormatter

from diecast_qa.analysis import AnalysisResult
from diecast_qa.config import TYPE5_LABELS, VARIABLE_LABELS
from diecast_qa.interpret.importance import PERIOD_MARKERS
from diecast_qa.interpret.ranges import VERDICTS
from diecast_qa.modeling.type_models import TYPE_CLASSES
from diecast_qa.viz.base import ChartBuilder

# 특성요인도 분류의 고정 색 순서 (series 순서대로)
GROUP_ORDER = ("설비", "재료", "방법", "환경", "금형", "순번")


class InterpretCharts(ChartBuilder):
    def render(self, results: dict[str, AnalysisResult], out_dir: Path) -> list[Path]:
        shap, ranges = results["shap"].tables, results["ranges"].tables
        checklist = results["checklist"].tables
        charts = {
            "interp_shap_importance": lambda: self.importance(shap["importance"], shap["model"]),
            "interp_local_examples": lambda: self.local_examples(shap["examples"]),
            "interp_range_check": lambda: self.range_check(ranges["proposals"]),
            "interp_type_effects": lambda: self.type_effects(checklist),
        }
        for ptype in ranges["proposals"].index.unique("Product_Type"):
            charts[f"interp_pdp_ice_type{ptype}"] = lambda p=ptype: self.dependence(ranges, p)
        return self.render_to(out_dir, charts)

    # SHAP 중요도 -------------------------------------------------------------------------
    def importance(self, importance: pd.DataFrame, model: pd.DataFrame, top: int = 12) -> Figure:
        types = list(importance.index.unique("Product_Type"))
        fig, axes = self.panels((10.5, 5.6), ncols=len(types))
        colors = dict(zip(GROUP_ORDER, self.theme.series, strict=False))
        for ax, ptype in zip(axes, types, strict=True):
            t = importance.loc[ptype].head(top).iloc[::-1]
            y = np.arange(len(t))
            ax.barh(y, t["share"], height=0.7, color=[colors[g] for g in t["group"]])
            for yi, (share, direction) in enumerate(zip(t["share"], t["direction"], strict=True)):
                arrow = "↑" if direction > 0 else "↓"
                ax.text(share, yi, f" {share:.0%} {arrow}", va="center", fontsize=8.5,
                        color=self.theme.ink_secondary)  # fmt: skip
            ax.set_yticks(y, t["label"])
            ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.set_xlim(0, importance["share"].max() * 1.25)
            auc = model.loc[ptype, "cv_roc_auc"]
            ax.set_title(f"제품 유형 {ptype}  (5-fold ROC-AUC {auc:.2f})", loc="left", fontsize=11)
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        markers = importance.loc[(slice(None), list(PERIOD_MARKERS)), "share"].groupby(
            level="Product_Type").sum()  # fmt: skip
        marker_text = ", ".join(f"유형 {p} {s:.0%}" for p, s in markers.items())
        self.header(fig, f"SHAP 변수 중요도 (평균 |SHAP| 비중, 상위 {top}개)",
                    "제품 유형마다 따로 학습한 해석용 XGBoost. ↑ 값이 클수록 불량 위험 증가, "
                    f"↓ 작을수록 증가. 환경·순번(공장 온습도, shot 순번) 합: {marker_text}",
                    handles=[Patch(color=colors[g], label=g) for g in GROUP_ORDER])  # fmt: skip
        return fig

    # 개별 판정 근거 ----------------------------------------------------------------------
    def local_examples(self, examples: pd.DataFrame) -> Figure:
        groups = list(examples.groupby("Product_Type"))
        fig, axes = self.panels((10.5, 4.8), ncols=len(groups))
        for ax, (ptype, ex) in zip(axes, groups, strict=True):
            ex = ex.iloc[::-1]
            y = np.arange(len(ex))
            colors = [self.increase if v > 0 else self.decrease for v in ex["shap"]]
            ax.barh(y, ex["shap"], height=0.7, color=colors)
            ax.axvline(0, color=self.theme.baseline, linewidth=1)
            labels = [f"나머지 {int(r.n_rest)}개 변수" if r.variable == "rest"
                      else f"{VARIABLE_LABELS[r.variable]} = {r.value:.4g}"
                      for r in ex.itertuples()]  # fmt: skip
            ax.set_yticks(y, labels)
            for yi, v in zip(y, ex["shap"], strict=True):
                ax.text(v, yi, f" {v:+.2f} " if v > 0 else f" {v:+.2f} ", va="center",
                        ha="left" if v > 0 else "right", fontsize=8.5,
                        color=self.theme.ink_secondary)  # fmt: skip
            low, high = min(ex["shap"].min(), 0), max(ex["shap"].max(), 0)
            ax.set_xlim(low - (high - low) * 0.15, high + (high - low) * 0.2)
            first = ex.iloc[0]
            ax.set_title(f"제품 유형 {ptype}: 평균 {first['base_p']:.0%} → 이 제품 "
                         f"{first['p_defect']:.0%}", loc="left", fontsize=11)  # fmt: skip
            ax.set_xlabel("불량 위험 기여 (log-odds)")
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        signs = np.sign(examples["shap"])
        handles = [Patch(color=c, label=t) for c, t, present in (
            (self.increase, "위험을 높임", (signs > 0).any()),
            (self.decrease, "위험을 낮춤", (signs < 0).any())) if present]  # fmt: skip
        self.header(fig, "개별 판정 근거 예시: 위험도가 가장 높은 불량 제품",
                    "SHAP 값의 합 = 이 제품의 예측 log-odds - 평균. 변수 이름 옆은 그 제품의 "
                    "실제 값",
                    handles=handles)  # fmt: skip
        return fig

    # PDP·ICE ---------------------------------------------------------------------------
    def dependence(self, tables: dict[str, pd.DataFrame], ptype: int, ncols: int = 4) -> Figure:
        ranges = tables["proposals"].loc[ptype]
        pdp = tables["pdp"][tables["pdp"]["Product_Type"] == ptype]
        ice = tables["ice"][tables["ice"]["Product_Type"] == ptype]
        nrows = int(np.ceil(len(ranges) / ncols))
        fig, axes = self.panels((12.5, 3.0 * nrows + 1.2), nrows=nrows, ncols=ncols, sharey=True)
        top = min(1.0, ice["p_defect"].quantile(0.95) * 1.1)
        for ax, (variable, r) in zip(axes.flat, ranges.iterrows(), strict=False):
            curves = ice[ice["variable"] == variable]
            for _, c in curves.groupby("row"):
                ax.plot(c["value"], c["p_defect"], color=self.theme.neutral, linewidth=0.6,
                        alpha=0.7)  # fmt: skip
            curve = pdp[pdp["variable"] == variable]
            ax.plot(curve["value"], curve["pdp"], color=self.theme.series[0], linewidth=2.2)
            ax.axhline(r["reference"], color=self.theme.ink_muted, linewidth=1)
            if isinstance(r.get("range_label"), str):
                low = curve["value"].min() if pd.isna(r["range_low"]) else r["range_low"]
                high = curve["value"].max() if pd.isna(r["range_high"]) else r["range_high"]
                fill = (self.theme.sequential[1] if r["verdict"] == "candidate"
                        else self.theme.diverging[3])  # fmt: skip
                ax.axvspan(low, high, color=fill, zorder=0, linewidth=0)
            ax.set_ylim(0, top)
            ax.xaxis.set_major_locator(MaxNLocator(5))
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            has_range = isinstance(r.get("range_label"), str)
            ax.set_title(r["label"] + (f"  {r['range_label']}" if has_range else ""), loc="left",
                         fontsize=10.5, pad=16)  # fmt: skip
            ax.text(0.0, 1.015, VERDICTS[r["verdict"]], transform=ax.transAxes, fontsize=8.5,
                    va="bottom", color=(self.theme.ink if r["verdict"] == "candidate"
                                        else self.theme.ink_muted),
                    fontweight="bold" if r["verdict"] == "candidate" else "normal")  # fmt: skip
            self.tidy(ax)
        for ax in axes.flat[len(ranges) :]:
            ax.set_visible(False)
        handles = [
            Line2D([], [], color=self.theme.series[0], linewidth=2.2, label="PDP (평균)"),
            Line2D([], [], color=self.theme.neutral, linewidth=1,
                   label=f"ICE (제품 {ice['row'].nunique()}개)"),
            Line2D([], [], color=self.theme.ink_muted, linewidth=1, label="평균 예측 확률"),
            Patch(color=self.theme.sequential[1], label="관리 범위(안): 구간 내 검증 통과"),
            Patch(color=self.theme.diverging[3], label="PDP 범위: 검증 안 됨"),
        ]  # fmt: skip
        self.header(fig, f"제품 유형 {ptype}: 변수별 불량 확률 변화 (PDP·ICE)",
                    f"SHAP 상위 조정 가능 변수 {len(ranges)}개. 가로축은 관측값의 5~95% 범위. "
                    "관리 범위(안)는 PDP가 평균 예측 확률 이하인 가장 넓은 연속 구간",
                    handles=handles)  # fmt: skip
        return fig

    # 관리 범위 검증 --------------------------------------------------------------------
    def range_check(self, ranges: pd.DataFrame) -> Figure:
        types = list(ranges.index.unique("Product_Type"))
        fig, axes = self.panels((11.5, 5.0), ncols=len(types), sharex=True)
        for ax, ptype in zip(axes, types, strict=True):
            r = ranges.loc[ptype].dropna(subset=["range_label"]).iloc[::-1]
            y = np.arange(len(r))
            has = r["cmh_or"].notna().to_numpy()
            ax.hlines(y[has], r["cmh_low"][has], r["cmh_high"][has], color=self.theme.series[0],
                      linewidth=1.5)  # fmt: skip
            ax.scatter(r["cmh_or"][has], y[has], s=56, zorder=3, color=self.theme.series[0],
                       edgecolors=self.theme.surface, linewidths=1.5,
                       label="같은 구간 안 (Mantel-Haenszel, 95% CI)")  # fmt: skip
            ax.scatter(r["odds_ratio"], y, s=56, zorder=3, facecolors=self.theme.surface,
                       edgecolors=self.theme.ink_secondary, linewidths=1.5,
                       label="구간 무시 (전체 비교)")  # fmt: skip
            ax.axvline(1, color=self.theme.ink_muted, linewidth=1)
            ax.set_xscale("log")
            labels = [f"{row.label}  {row.range_label}" for row in r.itertuples()]
            ax.set_yticks(y, labels)
            for yi, row in zip(y, r.itertuples(), strict=True):
                text = f"구간 {row.runs_agree:.0f}/{row.runs_tested:.0f}"
                weight = "bold" if row.verdict == "candidate" else "normal"
                ax.text(1.0, yi, f" {text}", transform=ax.get_yaxis_transform(), va="center",
                        fontsize=8.5, fontweight=weight,
                        color=self.theme.ink_secondary)  # fmt: skip
            ax.set_title(f"제품 유형 {ptype}", loc="left", fontsize=11)
            ax.set_xlabel("범위 밖 대 범위 안 불량 오즈비 (로그 축)")
            self.tidy(ax, grid_axis="x")
            ax.spines[["left", "bottom"]].set_visible(False)
        ticks = [0.5, 1, 2, 4, 8, 16]
        for a in axes:
            a.set_xlim(0.4, 20)
            a.xaxis.set_minor_locator(NullLocator())
            a.set_xticks(ticks, [f"{t:g}" for t in ticks])
        self.header(fig, "관리 범위(안) 검증: 범위 밖 shot이 더 위험한가?",
                    "1보다 크면 범위 밖 불량 오즈가 높다. 오른쪽 '구간 m/n'은 같은 방향인 구간 수 "
                    "(굵게 = 관리 범위 후보: 구간 안 CI 하한 > 1, 과반 구간 같은 방향)",
                    axes[0])  # fmt: skip
        return fig

    # 유형별 점검 항목 ------------------------------------------------------------------
    def type_effects(self, tables: dict[str, pd.DataFrame]) -> Figure:
        effects, runs, items = tables["effects"], tables["effect_runs"], tables["items"]
        fig, ax = self.panels((7.6, 8.4), header_in=0.9)
        values = effects[list(TYPE_CLASSES)]
        vmax = 0.35
        ax.imshow(values.to_numpy(float), cmap=self.diverging_cmap(), vmin=-vmax, vmax=vmax,
                  aspect="auto")  # fmt: skip
        for (i, j), v in np.ndenumerate(values.to_numpy(float)):
            if np.isnan(v):
                continue
            color = "#ffffff" if abs(v) >= vmax * 0.6 else self.theme.ink
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=8, color=color)
        row = {v: i for i, v in enumerate(values.index)}
        for (code, _), item in items.iterrows():
            j = TYPE_CLASSES.index(code)
            ax.add_patch(Rectangle((j - 0.5, row[item["variable"]] - 0.5), 1, 1, fill=False,
                                   edgecolor=self.theme.ink, linewidth=1.6))  # fmt: skip
        ax.set_yticks(range(len(values)), [VARIABLE_LABELS[v] for v in values.index])
        max_runs = runs[list(TYPE_CLASSES)].max()
        labels = [f"{TYPE5_LABELS[c]}\n(구간 {max_runs[c]:.0f}개)" for c in TYPE_CLASSES]
        ax.set_xticks(range(len(TYPE_CLASSES)), labels)
        ax.xaxis.tick_top()
        ax.tick_params(length=0)
        ax.spines[:].set_visible(False)
        self.header(fig, "불량 유형별 공정값 차이 (같은 구간의 정상 shot 대비)",
                    "구간 내 rank-biserial. 빨강 = 그 유형에서 값이 높음, 파랑 = 낮음. "
                    "테두리 = 점검 항목(조정 가능 변수 상위 3개)")  # fmt: skip
        return fig
