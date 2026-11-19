"""6단계: 기획서 8장 추가 실험.

사용: uv run python scripts/06_experiments.py e81_synthetic [다른 실험 이름 ...]
      (이름을 빼면 전체 실행)
결과: results/experiments/<실험>_*.csv, results/experiments/<실험>_summary.md,
results/figures/<실험>_*.png
"""

import argparse
import time

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.experiments import EXPERIMENTS
from diecast_qa.viz.experiments import ExperimentCharts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*", help=f"실험 이름: {', '.join(EXPERIMENTS)}")
    names = parser.parse_args().names or list(EXPERIMENTS)
    if unknown := set(names) - set(EXPERIMENTS):
        parser.error(f"알 수 없는 실험: {sorted(unknown)}")

    paths = Paths()
    parts = load_parts(paths)
    out_dir = paths.results_dir / "experiments"
    charts = ExperimentCharts()
    for name in names:
        start = time.time()
        result = EXPERIMENTS[name]().run(parts)
        result.save(out_dir)
        summary = "\n".join([f"# {name}", "", *(f"- {n}" for n in result.notes)])
        (out_dir / f"{name}_summary.md").write_text(summary, encoding="utf-8")
        print(summary)
        for path in charts.render(result, paths.figures_dir):
            print(f"그림: {path.relative_to(paths.root)}")
        print(f"[{name}] {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
