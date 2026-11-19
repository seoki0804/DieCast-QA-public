"""11단계 대시보드 데이터: 시나리오 분할, 감시(CUSUM·범위 밖 지속), 모델·위험도, 재생 평가, API,
누수 방지."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from diecast_qa.config import Paths
from diecast_qa.dashboard import SCENARIOS, DashboardModel, Scenario
from diecast_qa.dashboard.api import create_app
from diecast_qa.dashboard.evaluate import ReplayLedger
from diecast_qa.dashboard.models import prior_shift
from diecast_qa.dashboard.monitor import cusum_track, sustained_episodes

DATA_DIR = Paths().results_dir / "dashboard"


@pytest.fixture(scope="module")
def parts(result):
    return result.parts


def test_scenario_split_has_no_future_in_training(parts):
    train, replay = Scenario(2, 5, "none").split(parts)
    assert train["order"].max() < replay["order"].min()
    assert set(replay["Product_Type"]) == {2}
    assert replay["run"].min() == 5


def test_cusum_track_alarms_after_a_jump_and_resets():
    rates = np.r_[np.zeros(300), np.full(60, 0.5)]
    stream = pd.DataFrame({"order": np.arange(360), "run": 1, "defect_rate": rates})
    stream.loc[::10, "defect_rate"] = 0.5  # 기준 기간 불량률 10%
    track = cusum_track(stream, start=250, k=0.25, h=8.0, window=200)
    ups = [a for a in track.alarms if a[1] == "up"]
    assert ups and ups[0][2] >= 300 - 250  # 증가가 시작된 뒤에 경보
    assert ups[0][0] == ups[0][2] + 1  # 다음 shot부터 반영
    assert len(track.upper) == 110
    assert track.upper[ups[0][0]] < 8  # 경보 뒤 기준 재설정, 누적합 다시 시작


def test_sustained_episodes_open_and_close_within_run():
    out = np.r_[np.zeros(20), np.ones(30), np.zeros(30)].astype(bool)
    episodes = sustained_episodes(out, np.ones(80), window=20, enter=0.8, leave=0.5)
    assert episodes == [(35, 60)]  # 20 shot 중 16개(80%)가 넘는 시점에 시작, 50% 미만에서 끝
    assert sustained_episodes(np.ones(30, bool), np.r_[np.ones(25), np.full(5, 2)]) == [(19, 25)]


def test_dashboard_model_outputs(parts):
    train = parts[parts["run"] == 1]
    test = parts[parts["run"] == 2].head(20)
    model = DashboardModel().fit(train)
    pred = model.predict(test)
    assert pred["p_raw"].between(0, 1).all()
    types = pred.filter(like="type_")
    assert np.allclose(types.sum(axis=1), 1)
    rows = model.explain(test.head(3), top=4, n_jobs=1)
    assert len(rows) == 3 and len(rows[0]) == 4
    assert abs(rows[0][0][2]) >= abs(rows[0][-1][2])  # |SHAP| 큰 순서


def test_prior_shift_moves_balanced_probability_to_the_current_rate():
    raw = np.array([0.2, 0.5, 0.8])
    # 균형 가중 모델이 '모르겠다'(0.5)고 하면 위험도는 지금 불량률 그대로다
    assert np.isclose(prior_shift(0.5, 0.12), 0.12)
    shifted = prior_shift(raw, 0.12)
    assert np.all(np.diff(shifted) > 0)  # 순위는 모델 그대로
    # 불량률이 오르면 모든 제품의 위험도가 함께 오른다
    assert np.all(prior_shift(raw, 0.25) > shifted)
    # 0·1 입력도 0·1에 붙지 않는다
    assert 0 < prior_shift(0.0, 0.1) < prior_shift(1.0, 0.1) < 1


def _shot(i, ys, ps, tight=False):
    return {"i": i, "tight": tight, "parts": [{"y": y, "p": p, "rule": p} for y, p in
                                              zip(ys, ps, strict=True)]}  # fmt: skip


def test_replay_ledger_follows_the_screen_rules():
    # 로트 1(shot 0~1): 과거가 없어 1/비용 비율(0.1) 기준. 로트 2: 과거에서 비용 최소 임계값
    shots = [_shot(0, [1, 0], [0.3, 0.05]), _shot(1, [0, 0], [0.2, 0.01]),
             _shot(2, [1, 0], [0.3, 0.05]), _shot(3, [0, 1], [0.01, 0.2], tight=True)]  # fmt: skip
    ledger = ReplayLedger(shots, ratio=10, lot=2, min_parts=4, min_defects=1)
    assert ledger.thresholds[0] == 0.1
    # 과거 4개 중 불량은 점수 0.3 하나: 0.3 이상만 검사하는 것이 가장 싸다
    assert ledger.thresholds[1] == 0.3
    summary = ledger.summarize()
    # 검사: shot0의 0.3·shot1의 0.2(≥0.1), shot2의 0.3, shot3은 경고 뒤라 둘 다
    assert (summary["inspected"], summary["found"]) == (5, 3)
    assert np.isclose(summary["cost_per_part"], 5 / 8)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f)


def test_api_serves_files(tmp_path):
    _write(tmp_path / "meta.json.gz", {"scenarios": [{"id": "s1"}]})
    _write(tmp_path / "summary.json.gz", {"pareto": []})
    shots = [{"i": i} for i in range(5)]
    _write(tmp_path / "scenarios" / "s1.json.gz",
           {"meta": {"id": "s1"}, "limits": {"p": 1}, "shots": shots,
            "alarms": [{"at": 2}]})  # fmt: skip
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/scenarios/s1").json() == {"meta": {"id": "s1"}, "limits": {"p": 1}}
    page = client.get("/api/scenarios/s1/shots", params={"offset": 3, "limit": 10}).json()
    assert page["total"] == 5 and [s["i"] for s in page["shots"]] == [3, 4]
    assert client.get("/api/scenarios/nope").status_code == 404
    assert client.get("/api/scenarios/s1/alarms").json() == [{"at": 2}]


@pytest.mark.skipif(
    not (DATA_DIR / "meta.json.gz").exists(), reason="scripts/11_dashboard_data.py 실행 전"
)
def test_generated_scenarios_train_only_on_the_past():
    for scenario in SCENARIOS:
        with gzip.open(
            DATA_DIR / "scenarios" / f"{scenario.id}.json.gz", "rt", encoding="utf-8"
        ) as f:
            data = json.load(f)
        shots, models = data["shots"], data["meta"]["models"]
        assert len(shots) == data["meta"]["n_shots"]
        for shot in shots:
            model = models[shot["model"]]
            assert model["trained_until"] < shot["order"]  # 예측하는 shot보다 앞선 데이터로만 학습
        for alarm in data["alarms"]:
            assert alarm["at"] >= alarm["detected_at"]  # 경보는 감지한 shot 이후에 반영
        has_shap = all(p["shap"] is not None for s in shots for p in s["parts"])
        assert has_shap == (scenario.retrain == "none")
        # 위험도 = 모델 확률을 그 shot의 기준 불량률(과거 실제 불량률)로 옮긴 값
        for shot in shots[::97]:
            for part in shot["parts"]:
                assert abs(part["p"] - prior_shift(part["raw"], shot["base"])) < 1e-3
