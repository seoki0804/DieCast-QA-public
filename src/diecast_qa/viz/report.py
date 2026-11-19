"""보고서용 그림: 특성요인도(9장)와 현장 적용 구성도(11.3).

특성요인도는 데이터 근거가 있는 변수만 뼈 위에 놓고 근거를 아래 줄에 적는다:
★ 관리 범위(안) 후보(7단계, 구간 내 검증 통과), 유형 이름 ↑↓ 같은 구간 정상 대비 그 유형에서
높음·낮음(7단계 점검 항목), 캐비티별 불량률(2단계). 근거가 없는 변수는 뼈 끝에 '그 외'로 묶는다.

두 그림 모두 보고서 본문 폭(16.6cm)에 넣었을 때 글자가 6pt 이상이 되도록 크기를 정했다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from diecast_qa.config import CAUSE_CATEGORIES, TYPE5_LABELS, VARIABLE_LABELS
from diecast_qa.viz.base import ChartBuilder

# (범주, 뼈가 등뼈에 닿는 x, 위 1 / 아래 -1). 근거가 많은 설비 뼈 오른쪽을 넓게 비운다.
BONES = (("설비", 34, 1), ("재료", 60, 1), ("방법", 79, 1), ("환경", 30, -1), ("금형", 60, -1))
# 뼈 길이(y): 근거가 많은 위쪽을 길게. 기울기(x/y)는 같다
BONE_LENGTH = {1: 44, -1: 26}
BONE_SLOPE = 0.32


def evidence_marks(
    checklist: pd.DataFrame, ranges: pd.DataFrame, cavity_rates: pd.Series
) -> dict[str, list[str]]:
    """변수별 근거 문구 목록: {'Biscuit_Thickness': ['★유형1 ≥ 12', '박리↓'], …}."""
    marks: dict[str, list[str]] = {}
    for r in ranges[ranges["verdict"] == "candidate"].itertuples():
        marks.setdefault(r.variable, []).append(f"★유형{r.Product_Type} {r.range_label}")
    for r in checklist.itertuples():
        arrow = "↑" if r.direction == "높음" else "↓"
        marks.setdefault(r.variable, []).append(f"{TYPE5_LABELS[r.type5]}{arrow}")
    if len(cavity_rates) > 1:
        marks["Cavity"] = [" vs ".join(f"캐비티{c} {v:.1%}" for c, v in cavity_rates.items())]
    return {v: list(dict.fromkeys(m)) for v, m in marks.items()}


class ReportCharts(ChartBuilder):
    def render(self, results_dir: Path, out_dir: Path) -> list[Path]:
        checklist = pd.read_csv(results_dir / "interpret" / "checklist_items.csv")
        ranges = pd.read_csv(results_dir / "interpret" / "ranges_proposals.csv")
        parts = pd.read_csv(results_dir.parent / "data" / "processed" / "parts.csv")
        marks = evidence_marks(checklist, ranges, parts.groupby("Cavity")["defect"].mean())
        return self.render_to(out_dir, {
            "report_fishbone": lambda: self.fishbone(marks, parts["defect"].mean()),
            "report_architecture": self.architecture,
        })  # fmt: skip

    # 특성요인도 ------------------------------------------------------------------------
    def fishbone(self, marks: dict[str, list[str]], rate: float) -> Figure:
        fig, ax = self.panels((10, 6.6), header_in=0.85)
        ax.set_xlim(0, 100)
        ax.set_ylim(-35, 62)
        ax.axis("off")
        theme = self.theme
        ax.annotate("", xy=(81, 0), xytext=(1, 0),
                    arrowprops={"arrowstyle": "-|>", "lw": 2.4, "color": theme.ink,
                                "mutation_scale": 20})  # fmt: skip
        ax.add_patch(FancyBboxPatch((82.5, -6.5), 16, 13, boxstyle="round,pad=0.4,rounding_size=2",
                                    fc=theme.critical, ec="none"))  # fmt: skip
        ax.text(90.5, 1.6, "제품 불량", ha="center", va="center", color="#ffffff", fontsize=13,
                fontweight="bold")  # fmt: skip
        ax.text(90.5, -3.2, f"불량률 {rate:.1%}", ha="center", va="center", color="#ffffff",
                fontsize=9.5)  # fmt: skip
        for category, x, side in BONES:
            variables = [v for v in CAUSE_CATEGORIES[category] if v in VARIABLE_LABELS]
            strong = [v for v in variables if v in marks]
            weak = [VARIABLE_LABELS[v] for v in variables if v not in marks]
            self._bone(ax, category, x, side, strong, weak, marks)
        self.header(fig, "불량 특성요인도 (설비·재료·방법·환경·금형)",
                    "뼈 위 = 데이터 근거가 있는 변수(아래 줄이 근거). ★ 관리 범위(안), "
                    "유형↑↓ 같은 구간 정상 대비 그 유형에서 높음·낮음. "
                    "그 외 = 구간 안 근거 없음·검증 불가")  # fmt: skip
        return fig

    def _bone(
        self, ax, category: str, x: float, side: int, strong: list[str], weak: list[str],
        marks: dict[str, list[str]],
    ) -> None:  # fmt: skip
        theme = self.theme
        dy = BONE_LENGTH[side]
        dx = dy * BONE_SLOPE
        end = (x - dx, dy * side)
        ax.plot([x, end[0]], [0, end[1]], color=theme.ink, lw=1.6)
        title_y = end[1] + 2.5 * side
        ax.text(end[0], title_y, category, ha="center", va="bottom" if side > 0 else "top",
                fontsize=12.5, fontweight="bold", color=theme.ink)  # fmt: skip
        if weak:
            # 근거 없는 변수: 범주 이름 오른쪽에 두 개씩 묶어 회색으로
            lines = [" · ".join(weak[k : k + 2]) for k in range(0, len(weak), 2)]
            ax.text(end[0] + 4, title_y, "그 외: " + "\n".join(lines), ha="left",
                    va="bottom" if side > 0 else "top", fontsize=8, color=theme.ink_muted,
                    linespacing=1.35)  # fmt: skip
        for k, v in enumerate(strong):
            frac = (k + 0.75) / (len(strong) + 0.5)
            px, py = x - dx * frac, dy * side * frac
            ax.plot([px - 1, px], [py, py], color=theme.ink, lw=1)
            ax.text(px + 1.6, py + 0.5, VARIABLE_LABELS[v], va="bottom", fontsize=10,
                    fontweight="bold", color=theme.ink)  # fmt: skip
            ax.text(px + 1.6, py - 0.6, " · ".join(marks[v]), va="top", fontsize=8.5,
                    color=theme.ink_secondary)  # fmt: skip

    # 현장 적용 구성도 ------------------------------------------------------------------
    def architecture(self) -> Figure:
        fig, ax = self.panels((9.5, 5.6), header_in=0.85)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 60)
        ax.axis("off")
        accent, ink = self.theme.series[0], self.theme.ink
        w, gap = 16.8, 3.5
        top = [1 + k * (w + gap) for k in range(5)]
        retrain_x = (top[2] + top[3]) / 2  # 저장·전처리와 예측·감시 사이 아래
        # (x, y, 높이, 제목, 본문 줄들, 이번 프로젝트에서 구현했나)
        boxes = (
            (top[0], 33, 19, "다이캐스팅 설비",
             ("OPC-UA 서버", "태그 133개", "(AAS 정보 모델)"), False),
            (top[1], 33, 19, "엣지 게이트웨이", ("100ms 샘플링", "shot 단위로 묶기"), False),
            (top[2], 33, 19, "저장·전처리",
             ("중복 제거·구간", "비정상 shot 표시", "파생·이력 변수"), True),
            (top[3], 33, 19, "예측·감시 (FastAPI)",
             ("위험도·유형 예측", "불량률 CUSUM", "검사 기준(비용 최소)"), True),
            (top[4], 33, 19, "대시보드 (Next.js)",
             ("운영 현황·검사 목록", "알람·조치", "체크리스트"), True),
            (retrain_x, 5, 15, "재학습", ("50 shot마다 또는", "불량률 경보 때"), True),
            (top[4], 5, 15, "작업자·품질 담당", ("검사·점검·설정 조정", "(OCAP)"), False),
        )  # fmt: skip
        for x, y, bh, title, lines, built in boxes:
            bw, body = w, "\n".join(lines)
            ax.add_patch(FancyBboxPatch((x, y), bw, bh, boxstyle="round,pad=0.3,rounding_size=1.5",
                                        fc="#eef4fc" if built else self.theme.surface,
                                        ec=accent if built else self.theme.ink_muted,
                                        lw=1.6 if built else 1.2,
                                        ls="-" if built else (0, (4, 3))))  # fmt: skip
            ax.text(x + bw / 2, y + bh - 3, title, ha="center", va="center", fontsize=10.5,
                    fontweight="bold", color=ink)  # fmt: skip
            ax.text(x + bw / 2, y + (bh - 5) / 2, body, ha="center", va="center", fontsize=9,
                    color=self.theme.ink_secondary, linespacing=1.45)  # fmt: skip
        note = {"fontsize": 8.8, "color": self.theme.ink_secondary}

        def arrow(start, end, rad=0.0):
            ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=13, lw=1.5,
                                         color=ink, connectionstyle=f"arc3,rad={rad}"))  # fmt: skip

        for k in range(4):
            arrow((top[k] + w + 0.5, 42.5), (top[k + 1] - 0.5, 42.5))
        cx_dash = top[4] + w / 2
        arrow((cx_dash, 32.4), (cx_dash, 20.6))  # 화면 → 사람: 경보와 검사 대상
        ax.text(cx_dash + 1, 26.5, "경보·검사 대상", va="center", **note)
        arrow((top[4] - 0.6, 12.5), (retrain_x + w + 0.6, 12.5))  # 사람 → 재학습: 검사 결과 = 라벨
        ax.text((top[4] + retrain_x + w) / 2, 14, "검사 결과\n(라벨)", ha="center", va="bottom",
                linespacing=1.3, **note)  # fmt: skip
        # 저장 → 재학습(학습 데이터), 재학습 → 예측·감시(새 모델): 상자가 겹치는 x의 세로 화살표
        down, up = (retrain_x + top[2] + w) / 2, (top[3] + retrain_x + w) / 2
        arrow((down, 32.4), (down, 20.6))
        ax.text(down - 1, 26.5, "학습 데이터", ha="right", va="center", **note)
        arrow((up, 20.6), (up, 32.4))
        ax.text(up + 1, 26.5, "새 모델", va="center", **note)
        legend = (
            (12.5, "#eef4fc", accent, "-", 1.6,
             "이번 프로젝트에서 구현 (과거 데이터 재생으로 시연)"),
            (6.5, self.theme.surface, self.theme.ink_muted, (0, (4, 3)), 1.2,
             "현장 적용 시 연결 (KAMP 패키지의 OPC-UA·AAS 설정 기준)"),
        )  # fmt: skip
        for y, fc, ec, ls, lw, text in legend:
            ax.add_patch(FancyBboxPatch((1.5, y - 1), 3.5, 2, boxstyle="round,pad=0.2", fc=fc,
                                        ec=ec, lw=lw, ls=ls))  # fmt: skip
            ax.text(6.5, y, text, va="center", fontsize=9)
        self.header(fig, "현장 적용 구성도",
                    "설비 → 수집 → 예측·감시 → 화면 → 검사·조치 → 재학습. 재생 시뮬레이션은 "
                    "저장된 데이터를 shot 순서대로 흘려 실시간 수집을 대신한다")  # fmt: skip
        return fig
