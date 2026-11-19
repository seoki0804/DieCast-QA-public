"""7단계: 해석·관리 범위 (기획서 5장 ⑦).

결과: results/interpret/*.csv, results/interpret/summary.md, results/shap_values.csv (3.3),
results/figures/interp_*.png
"""

import time

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.interpret import ANALYSES
from diecast_qa.viz.interpret import InterpretCharts


def main() -> None:
    paths = Paths()
    parts = load_parts(paths)
    out_dir = paths.results_dir / "interpret"

    results = {}
    for analysis in (cls() for cls in ANALYSES):
        start = time.time()
        result = analysis.run(parts)
        print(f"[{result.name}] {time.time() - start:.0f}s")
        results[result.name] = result

    shap = results["shap"]
    shap.tables["values"].to_csv(paths.results_dir / "shap_values.csv", index=False,
                                 float_format="%.6g")  # fmt: skip
    for result in results.values():
        result.without("values").save(out_dir)

    lines = ["# 해석·관리 범위 요약", ""]
    for result in results.values():
        lines += [f"## {result.name}", *(f"- {note}" for note in result.notes), ""]
    summary = "\n".join(lines)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    for path in InterpretCharts().render(results, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
