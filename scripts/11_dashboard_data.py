"""11단계: 대시보드 재생 데이터 만들기 (기획서 11장).

7·9단계 결과가 있어야 한다. 시나리오마다 시작(재학습) 시점 이전 데이터로 모델을 학습해 재생 구간을
예측하고, 관리한계·알람을 미리 계산한다. 약 5분.
결과: results/dashboard/{meta,summary}.json.gz, results/dashboard/scenarios/<id>.json.gz,
results/dashboard/replay_eval.csv(재생 비용·AUC, 화면과 같은 검사 규칙),
results/dashboard/replay_calibration.csv(위험도 보정 상태),
models/dashboard_t<유형>_r<구간>.joblib (git 제외, 다시 만들 수 있음)
"""

import argparse
import gzip
import json
import time

import joblib
import pandas as pd

from diecast_qa.config import Paths
from diecast_qa.dashboard import SCENARIOS, DashboardModel, ScenarioBuilder, SummaryBuilder
from diecast_qa.dashboard.evaluate import evaluate_all
from diecast_qa.data import load_parts


def write(path, payload) -> None:
    """gzip JSON. mtime=0으로 같은 내용이면 같은 파일이 되게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
        f.write(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", help="시나리오 id (빼면 전체)")
    ids = parser.parse_args().ids or [s.id for s in SCENARIOS]

    paths = Paths()
    parts = load_parts(paths)
    results = paths.results_dir
    out_dir = results / "dashboard"
    summary = SummaryBuilder(results)
    write(out_dir / "meta.json.gz", summary.meta())
    write(out_dir / "summary.json.gz", summary.summary())

    builder = ScenarioBuilder(
        parts,
        pd.read_csv(results / "interpret" / "ranges_proposals.csv"),
        pd.read_csv(results / "interpret" / "checklist_items.csv"),
        pd.read_csv(results / "improve" / "alarms_ocap.csv"),
    )
    models_dir = paths.root / "models"
    models_dir.mkdir(exist_ok=True)
    for scenario in (s for s in SCENARIOS if s.id in ids):
        start = time.time()
        payload = builder.build(scenario)
        write(out_dir / "scenarios" / f"{scenario.id}.json.gz", payload)
        if scenario.retrain == "none":  # 재생 시작 시점의 모델 (기획서 3.3 models/)
            train, _ = scenario.split(parts)
            name = f"dashboard_t{scenario.product_type}_r{scenario.start_run}.joblib"
            joblib.dump(DashboardModel().fit(train), models_dir / name, compress=3)
        levels = pd.Series([a["level"] for a in payload["alarms"]]).value_counts().to_dict()
        print(
            f"[{scenario.id}] shot {payload['meta']['n_shots']}, 모델 "
            f"{len(payload['meta']['models'])}개, 알람 {levels} ({time.time() - start:.0f}s)"
        )

    # 재생 평가: 일부 시나리오만 다시 만들었어도 저장된 전체 시나리오로 계산한다
    payloads = []
    for scenario in SCENARIOS:
        path = out_dir / "scenarios" / f"{scenario.id}.json.gz"
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as f:
                payloads.append(json.load(f))
    costs, calibration = evaluate_all(payloads)
    costs.round(6).to_csv(out_dir / "replay_eval.csv", index=False)
    calibration.round(6).to_csv(out_dir / "replay_calibration.csv", index=False)
    print(calibration[["scenario", "defect_rate", "mean_p", "roc_auc_raw", "roc_auc_p"]].round(3))


if __name__ == "__main__":
    main()
