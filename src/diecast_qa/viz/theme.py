"""그림 공통 색·글꼴: 대시보드와 같은 디자인 토큰(docs/design/tokens.json)을 읽는다 (12.3).

글꼴은 저장소에 넣은 Pretendard(assets/fonts, OFL)를 등록해 팀원 컴퓨터마다 같은 모양으로 그린다.
파일이 없으면 운영체제의 한글 글꼴(맑은 고딕 등)을 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from matplotlib import font_manager

from diecast_qa.config import PROJECT_ROOT

TOKENS = PROJECT_ROOT / "docs" / "design" / "tokens.json"
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"
FALLBACK_FONTS = ("Malgun Gothic", "Apple SD Gothic Neo", "AppleGothic")


@cache
def register_fonts(font_dir: Path = FONT_DIR) -> tuple[str, ...]:
    """저장소의 글꼴 파일을 matplotlib에 등록하고 글꼴 이름을 돌려준다."""
    names = []
    for path in sorted(font_dir.glob("*.otf")):
        font_manager.fontManager.addfont(str(path))
        names.append(font_manager.FontProperties(fname=str(path)).get_name())
    return tuple(dict.fromkeys(names))


@dataclass(frozen=True)
class ChartTheme:
    surface: str
    ink: str
    ink_secondary: str
    ink_muted: str
    grid: str
    baseline: str
    # 강조하지 않는 막대·선 (파레토의 하위 유형, ICE 선 등)
    neutral: str
    # 범주 색은 이 순서대로만 배정한다. 인접 쌍의 색각 이상 구분(CVD ΔE ≥ 8)을 검증한 순서다.
    series: tuple[str, ...]
    # 상태 색(범주 색과 따로 예약). 관리한계 이탈처럼 상태를 나타낼 때만 쓰고, 라벨과 함께 쓴다
    critical: str
    good: str
    # 크기를 나타내는 단색 순차 팔레트(파랑, 밝음 → 어두움). 히트맵에 쓴다
    sequential: tuple[str, ...]
    # 방향(음·양)을 나타내는 발산 팔레트: 파랑 ← 회색 중립 → 빨강
    diverging: tuple[str, ...]
    fonts: tuple[str, ...] = FALLBACK_FONTS
    # 채움 위 라벨은 흰색, 이 밝은 채움 위에서만 검정
    light_fills: tuple[str, ...] = ("#eda100",)
    dpi: int = 200

    @classmethod
    def from_tokens(cls, path: Path = TOKENS, mode: str = "light") -> ChartTheme:
        tokens = json.loads(path.read_text(encoding="utf-8"))
        sem, prim = tokens["semantic"][mode], tokens["primitive"]
        return cls(
            surface=sem["chart.surface"], ink=sem["text.primary"],
            ink_secondary=sem["text.secondary"], ink_muted=sem["text.muted"],
            grid=sem["chart.grid"], baseline=sem["chart.baseline"],
            neutral=prim["neutral"]["300"] if mode == "dark" else "#d3d1c9",
            series=tuple(prim["series"][mode]), critical=prim["status"]["critical"],
            good=prim["status"]["good"], sequential=tuple(prim["sequential"]),
            diverging=tuple(prim["diverging"][mode]),
            fonts=(*register_fonts(), *FALLBACK_FONTS),
        )  # fmt: skip

    def label_on(self, fill: str) -> str:
        return self.ink if fill in self.light_fills else "#ffffff"

    def rc(self) -> dict:
        installed = {f.name for f in font_manager.fontManager.ttflist}
        return {
            "font.family": [*(f for f in self.fonts if f in installed), "sans-serif"],
            "axes.unicode_minus": False,
            "figure.facecolor": self.surface,
            "axes.facecolor": self.surface,
            "savefig.facecolor": self.surface,
            "text.color": self.ink,
            "axes.labelcolor": self.ink_secondary,
            "axes.edgecolor": self.baseline,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 10,
            "xtick.color": self.ink_muted,
            "ytick.color": self.ink_muted,
            "xtick.labelcolor": self.ink_secondary,
            "ytick.labelcolor": self.ink_secondary,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "legend.frameon": False,
            "grid.color": self.grid,
            "grid.linewidth": 0.8,
            "lines.linewidth": 2,
            "lines.solid_capstyle": "round",
        }


DEFAULT_THEME = ChartTheme.from_tokens()
