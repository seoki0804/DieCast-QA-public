"""차트 클래스의 공통 기능: 테마 적용, 축 정리, 저장."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 파일로만 저장한다

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.artist import Artist  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from diecast_qa.viz.theme import DEFAULT_THEME, ChartTheme  # noqa: E402


class ChartBuilder:
    """하위 클래스는 Figure를 돌려주는 메서드만 만들고, 저장은 render_to로 한다."""

    def __init__(self, theme: ChartTheme = DEFAULT_THEME) -> None:
        self.theme = theme

    def render_to(self, out_dir: Path, charts: dict[str, Callable[[], Figure]]) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        with plt.rc_context(self.theme.rc()):
            for name, draw in charts.items():
                fig = draw()
                path = out_dir / f"{name}.png"
                fig.savefig(path, dpi=self.theme.dpi, bbox_inches="tight")
                plt.close(fig)
                saved.append(path)
        return saved

    def sequential_cmap(self) -> LinearSegmentedColormap:
        return LinearSegmentedColormap.from_list("sequential", self.theme.sequential)

    def diverging_cmap(self) -> LinearSegmentedColormap:
        return LinearSegmentedColormap.from_list("diverging", self.theme.diverging)

    @property
    def increase(self) -> str:
        """발산 팔레트의 양(+) 방향 색 (위험 증가·값이 높음)."""
        return self.theme.diverging[-2]

    @property
    def decrease(self) -> str:
        return self.theme.diverging[1]

    def tidy(self, ax: Axes, grid_axis: str = "y") -> None:
        """위·오른쪽 축선을 지우고, 값 축에만 옅은 가는 격자를 둔다."""
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(self.theme.baseline)
        ax.tick_params(length=0)
        ax.grid(axis=grid_axis)
        ax.set_axisbelow(True)

    def panels(
        self,
        figsize: tuple[float, float],
        nrows: int = 1,
        ncols: int = 1,
        header_in: float = 1.1,
        **subplot_kw,
    ):
        """패널 nrows×ncols개 그림. 위쪽 header_in인치를 제목·부제·범례 자리로 비워 둔다.

        범례가 없는 그림은 header_in=0.8이면 충분하다. subplot_kw는 sharex 등을 넘긴다.
        """
        fig, axes = plt.subplots(nrows, ncols, figsize=figsize, layout="constrained",
                                 **subplot_kw)  # fmt: skip
        fig.get_layout_engine().set(rect=(0, 0, 1, 1 - header_in / figsize[1]), w_pad=0.2)
        return fig, axes

    def header(
        self, fig: Figure, title: str, subtitle: str, ax: Axes | None = None,
        handles: list[Artist] | None = None,
    ) -> None:  # fmt: skip
        """panels로 만든 그림의 제목·부제와 범례를 그림 위쪽에 왼쪽 정렬로 놓는다.

        범례는 ax에 붙은 라벨, 또는 handles(라벨을 단 Patch·Line2D 등)로 만든다.
        """
        height = fig.get_figheight()
        fig.text(0.01, 1 - 0.12 / height, title, va="top", fontsize=13, fontweight="bold")
        fig.text(0.01, 1 - 0.45 / height, subtitle, va="top", fontsize=9.5,
                 color=self.theme.ink_secondary)  # fmt: skip
        if handles is not None:
            labels = [h.get_label() for h in handles]
        elif ax is not None:
            handles, labels = ax.get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper left", ncols=len(labels), handlelength=1,
                       bbox_to_anchor=(0.005, 1 - 0.68 / height))  # fmt: skip
