"""3단계: 공정 안정성 (기획서 9장).

결과: results/spc/*.csv, results/spc/summary.md, results/control_limits.csv(3.3 공유 형식),
results/figures/spc_*.png
"""

import pandas as pd

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.spc import DEFAULT_ANALYSES
from diecast_qa.spc.monitoring import monitored_shots
from diecast_qa.viz.spc import SpcCharts


def main() -> None:
    paths = Paths()
    parts = load_parts(paths)
    out_dir = paths.results_dir / "spc"

    results = {}
    for analysis in (cls() for cls in DEFAULT_ANALYSES):
        result = analysis.run(parts)
        result.save(out_dir)
        results[result.name] = result

    limits = pd.concat(
        [r.tables["limits"] for r in results.values() if "limits" in r.tables], ignore_index=True
    )
    limits.to_csv(paths.results_dir / "control_limits.csv", index=False, float_format="%.6g")

    lines = ["# 공정 안정성 요약", ""]
    for result in results.values():
        lines += [f"## {result.name}", *(f"- {note}" for note in result.notes), ""]
    summary = "\n".join(lines)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)

    shots = monitored_shots(parts, exclude_abnormal=True)
    for path in SpcCharts().render(results, shots, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
