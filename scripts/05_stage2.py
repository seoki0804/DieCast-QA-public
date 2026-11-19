"""5단계: 2단계 불량 유형 분류와 1·2단계 연결 평가 (기획서 6.2, 7.6 재현).

입력: data/processed/parts.csv, results/predictions.csv.gz (4단계)
결과: results/stage2/*.csv, results/stage2/summary.md, results/predictions_stage2.csv.gz,
results/figures/stage2_*.png
"""

import pandas as pd

from diecast_qa.config import Paths
from diecast_qa.data import load_parts
from diecast_qa.modeling.stage2 import Stage2Study
from diecast_qa.viz.types import Stage2Charts


def main() -> None:
    paths = Paths()
    stage1 = pd.read_csv(paths.results_dir / "predictions.csv.gz")
    results = Stage2Study(load_parts(paths), stage1).run()

    out_dir = paths.results_dir / "stage2"
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "metrics_folds": results.folds, "metrics_summary": results.summary,
        "metrics_pooled": results.pooled, "per_class": results.per_class,
        "confusion": results.confusion, "joint": results.joint,
    }  # fmt: skip
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", float_format="%.4f")
    comparison = results.plan_comparison()
    comparison.to_csv(out_dir / "plan_comparison.csv", index=False, float_format="%.3f")
    results.predictions.to_csv(paths.results_dir / "predictions_stage2.csv.gz", index=False,
                               float_format="%.5f",
                               compression={"method": "gzip", "mtime": 0})  # fmt: skip

    summary = "\n".join(["# 2단계 유형 분류 요약", "", *(f"- {n}" for n in results.notes())])
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(comparison.round(3).to_string())
    for path in Stage2Charts().render(results, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
