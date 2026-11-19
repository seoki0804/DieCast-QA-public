"""2단계: 탐색 분석·통계 검정 (기획서 5장 ②, 9장).

결과: results/eda/*.csv, results/eda/summary.md, results/figures/eda_*.png
"""

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.eda import DEFAULT_ANALYSES
from diecast_qa.viz import EdaCharts


def main() -> None:
    paths = Paths()
    parts = load_parts(paths)
    out_dir = paths.results_dir / "eda"

    results = {}
    for analysis in (cls() for cls in DEFAULT_ANALYSES):
        result = analysis.run(parts)
        result.save(out_dir)
        results[result.name] = result

    lines = ["# 탐색 분석 요약", ""]
    for result in results.values():
        lines += [f"## {result.name}", *(f"- {note}" for note in result.notes), ""]
    summary = "\n".join(lines)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    for path in EdaCharts().render(results, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
