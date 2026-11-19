"""8단계: 검사 운영·비용 분석 (기획서 10장), 샘플링 검사 비교 (8.6), 확률 보정 (8.7).

4단계 결과(results/predictions.csv.gz)가 있어야 한다.
결과: results/cost/*.csv, results/cost/summary.md, results/cost_params.csv (3.3),
results/figures/cost_*.png, sampling_*.png, calibration_*.png
"""

import time

import pandas as pd

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.inspection import ANALYSES, cost_params
from diecast_qa.viz.inspection import InspectionCharts


def main() -> None:
    paths = Paths()
    parts = load_parts(paths)
    predictions = pd.read_csv(paths.results_dir / "predictions.csv.gz")
    out_dir = paths.results_dir / "cost"
    cost_params().to_csv(paths.results_dir / "cost_params.csv", index=False)

    results = {}
    for cls in ANALYSES:
        start = time.time()
        result = cls(predictions).run(parts)
        print(f"[{result.name}] {time.time() - start:.0f}s")
        result.save(out_dir)
        results[result.name] = result

    lines = ["# 검사 운영·비용 분석 요약", ""]
    for result in results.values():
        lines += [f"## {result.name}", *(f"- {note}" for note in result.notes), ""]
    summary = "\n".join(lines)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    for path in InspectionCharts().render(results, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
