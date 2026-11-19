"""4단계: 1단계 불량 여부 모델 (기획서 6장, 7장 재현).

결과: results/stage1/*.csv, results/stage1/summary.md, results/predictions.csv.gz (3.3 공유 형식),
results/figures/stage1_*.png

전체 실행은 30~40분 걸린다. --use-cache를 주면 results/stage1/cache에 저장된 실험 예측을
다시 쓰고 지표·그림만 새로 만든다 (코드를 바꾼 뒤에는 쓰지 않는다).
"""

import argparse
import time

from diecast_qa.config import Paths
from diecast_qa.data import PartsBuilder, RawDataLoader, ShotCleaner, load_parts
from diecast_qa.modeling.study import Stage1Study
from diecast_qa.viz.models import Stage1Charts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-cache", action="store_true")
    args = parser.parse_args()

    paths = Paths()
    parts = load_parts(paths)
    raw = RawDataLoader(paths.raw_csv).load()
    with_duplicates = PartsBuilder().build(ShotCleaner(drop_duplicates=False).clean(raw)[0])

    out_dir = paths.results_dir / "stage1"
    start = time.time()
    results = Stage1Study(parts, with_duplicates).run(
        log=lambda msg: print(f"[{time.time() - start:6.0f}s] {msg}", flush=True),
        cache_dir=out_dir / "cache",
        use_cache=args.use_cache,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    results.folds.to_csv(out_dir / "metrics_folds.csv", float_format="%.4f")
    results.summary.to_csv(out_dir / "metrics_summary.csv", float_format="%.4f")
    results.pooled.to_csv(out_dir / "metrics_pooled.csv", float_format="%.4f")
    results.tuning.to_csv(out_dir / "tuning_params.csv", index=False, float_format="%.4f")
    comparison = results.plan_comparison()
    comparison.to_csv(out_dir / "plan_comparison.csv", index=False, float_format="%.3f")

    shared = results.predictions[results.predictions["experiment"].isin(["main", "retrain"])]
    # gzip 머리에 압축 시각이 들어가지 않게 해 같은 결과면 파일도 바이트 단위로 같게 한다
    shared.to_csv(paths.results_dir / "predictions.csv.gz", index=False, float_format="%.5f",
                  compression={"method": "gzip", "mtime": 0})  # fmt: skip

    summary = "\n".join(["# 1단계 모델 요약", "", *(f"- {n}" for n in results.notes())])
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(comparison.round(3).to_string())
    for path in Stage1Charts().render(results, paths.figures_dir):
        print(f"그림: {path.relative_to(paths.root)}")


if __name__ == "__main__":
    main()
