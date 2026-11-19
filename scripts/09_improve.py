"""9단계: 불량 개선 방안과 관리 범위 이탈 대응 연구 (사용자 요청 추가 연구).

7단계 결과(results/interpret/ranges_proposals.csv)가 있어야 한다.
결과: results/improve/*.csv, results/improve/summary.md, results/figures/improve_*.png
"""

import time

import pandas as pd

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.improvement import ANALYSES
from diecast_qa.viz.improvement import ImprovementCharts


def main() -> None:
    paths = Paths()
    parts = load_parts(paths)
    proposals = pd.read_csv(paths.results_dir / "interpret" / "ranges_proposals.csv")
    out_dir = paths.results_dir / "improve"

    results = {}
    for cls in ANALYSES:
        start = time.time()
        result = cls(proposals).run(parts)
        print(f"[{result.name}] {time.time() - start:.0f}s")
        result.save(out_dir)
        results[result.name] = result

    lines = ["# 불량 개선 방안·이탈 대응 요약", ""]
    for result in results.values():
        lines += [f"## {result.name}", *(f"- {note}" for note in result.notes), ""]
    summary = "\n".join(lines)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    for path in ImprovementCharts().render(results, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
