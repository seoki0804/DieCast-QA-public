"""12단계: 보고서용 그림 (특성요인도, 현장 적용 구성도).

7단계 결과가 있어야 한다. 결과: results/figures/report_*.png
"""

from diecast_qa.config import Paths
from diecast_qa.viz.report import ReportCharts


def main() -> None:
    paths = Paths()
    for path in ReportCharts().render(paths.results_dir, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
