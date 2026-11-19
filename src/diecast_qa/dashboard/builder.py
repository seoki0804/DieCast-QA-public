"""시나리오 하나의 재생 데이터: shot별 예측·판정 근거·감시값, 관리한계, 알람, 재학습 기록.

대시보드는 이 결과를 읽기만 한다(실시간 학습 없음). 같은 시나리오는 항상 같은 결과다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from diecast_qa.config import CONTROL_VARS, KEY_VARS, SENSOR_COLS, TYPE5_LABELS, VARIABLE_LABELS
from diecast_qa.dashboard.models import DashboardModel, prior_shift
from diecast_qa.dashboard.monitor import cusum_track, shift_events, sustained_episodes
from diecast_qa.dashboard.scenarios import Scenario
from diecast_qa.improvement.levers import candidate_ranges
from diecast_qa.modeling.type_models import TYPE_CLASSES
from diecast_qa.spc.monitoring import monitored_shots

PROCESS_VARS = tuple(dict.fromkeys([*CONTROL_VARS, *SENSOR_COLS]))


@dataclass(frozen=True)
class MonitorSettings:
    """9단계 OCAP 규칙의 파라미터."""

    cusum_k: float = 0.25
    cusum_h: float = 8.0
    cusum_window: int = 200
    tighten_shots: int = 50  # 경고 뒤 전수검사 shot 수
    sustained_window: int = 20
    retrain_every: int = 50
    retrain_min_gap: int = 10
    shift_cooldown: int = 20  # 같은 변수 급변 기록을 묶는 간격
    reference_shots: int = 1000  # p-chart 기준 기간 (시작 직전 같은 제품 유형 shot)
    lot_shots: int = 50  # 검사 기준·위험도 기준 불량률을 다시 정하는 간격 (화면의 로트와 같다)
    base_rate_shots: int = 200  # 위험도의 기준 불량률: 로트 시작 직전 이만큼의 실제 불량률


class ScenarioBuilder:
    def __init__(self, parts: pd.DataFrame, proposals: pd.DataFrame, checklist: pd.DataFrame,
                 ocap: pd.DataFrame, settings: MonitorSettings | None = None) -> None:  # fmt: skip
        self.parts = parts
        self.ranges = candidate_ranges(proposals)
        self.checklist = checklist
        self.ocap = ocap.set_index("level") if "level" in ocap.columns else ocap
        self.settings = settings or MonitorSettings()

    # 전체 흐름 -------------------------------------------------------------------------
    def build(self, scenario: Scenario) -> dict:
        s = self.settings
        _, replay = scenario.split(self.parts)
        stream = monitored_shots(self.parts, exclude_abnormal=False)
        stream = stream[stream["Product_Type"] == scenario.product_type].reset_index(drop=True)
        start = int(np.searchsorted(stream["order"].to_numpy(), replay["order"].min()))
        shots = stream.iloc[start:].reset_index(drop=True)
        track = cusum_track(stream, start, s.cusum_k, s.cusum_h, s.cusum_window)
        tightened = self._tightened(track, len(shots))
        base = self._base_rates(stream, start, len(shots))

        retrains = self._retrain_positions(scenario.retrain, track, len(shots))
        predictions, explanations, models = self._predict(scenario, shots, replay, retrains)
        return {
            "meta": self._meta(scenario, shots, retrains, models),
            "limits": self._limits(stream, start, track),
            "shots": self._shots(
                shots, replay, predictions, explanations, track, tightened, retrains, base
            ),  # fmt: skip
            "alarms": self._alarms(scenario, shots, replay, track),
        }

    # 재학습과 예측 ----------------------------------------------------------------------
    def _retrain_positions(self, option: str, track, n: int) -> list[int]:
        if option == "none":
            return [0]
        if option == "every_50":
            return list(range(0, n, self.settings.retrain_every))
        positions = [0]
        for at, _, _ in track.alarms:  # 8.2: 불량률 CUSUM 경보(상·하측) 때마다
            if at < n and at - positions[-1] >= self.settings.retrain_min_gap:
                positions.append(at)
        return positions

    def _predict(self, scenario: Scenario, shots: pd.DataFrame, replay: pd.DataFrame,
                 retrains: list[int]) -> tuple[pd.DataFrame, dict, list[dict]]:  # fmt: skip
        """재학습 구간마다 그 시작 shot 이전의 모든 제품으로 학습해 구간의 제품을 예측한다."""
        bounds = [*retrains, len(shots)]
        frames, explanations, models = [], {}, []
        for lo, hi in zip(bounds[:-1], bounds[1:], strict=True):
            first, last = shots["order"].iloc[lo], shots["order"].iloc[hi - 1]
            model = DashboardModel().fit(self.parts[self.parts["order"] < first])
            segment = replay[(replay["order"] >= first) & (replay["order"] <= last)]
            frames.append(model.predict(segment))
            if scenario.retrain == "none":
                explanations.update(zip(segment.index, model.explain(segment), strict=True))
            importance = model.importance().head(10)
            models.append({"position": lo, "order": int(first), "n_train": model.n_train_,
                           "prior": model.prior_, "trained_until": model.trained_until_,
                           "importance": [[v, float(w)]
                                          for v, w in importance.items()]})  # fmt: skip
        return pd.concat(frames), explanations, models

    def _base_rates(self, stream: pd.DataFrame, start: int, n: int) -> np.ndarray:
        """shot마다 위험도의 기준 불량률: 그 shot이 속한 로트가 시작하기 직전 base_rate_shots shot의
        실제 불량률(재생 이전 생산 기록 포함, 과거만). 0·1을 피하려고 (불량 + 0.5) / (제품 + 1)."""
        s = self.settings
        defects = stream["defect_rate"].to_numpy() * 2  # shot당 불량 제품 수 (캐비티 2개)
        rates = np.empty(n)
        for i in range(n):
            pos = start + (i // s.lot_shots) * s.lot_shots
            lo = max(0, pos - s.base_rate_shots)
            rates[i] = (defects[lo:pos].sum() + 0.5) / (2 * (pos - lo) + 1)
        return rates

    # 감시 -----------------------------------------------------------------------------
    def _tightened(self, track, n: int) -> np.ndarray:
        """상측 경보가 반영된 shot부터 tighten_shots shot 동안 검사 강화(전수검사)."""
        flag = np.zeros(n, bool)
        for at, direction, _ in track.alarms:
            if direction == "up" and at < n:
                flag[at : at + self.settings.tighten_shots] = True
        return flag

    def _limits(self, stream: pd.DataFrame, start: int, track) -> dict:
        s = self.settings
        reference = stream.iloc[max(0, start - s.reference_shots) : start]
        return {
            "p_chart": {"center": float(reference["defect_rate"].mean()), "subgroup_shots": 50,
                        "parts_per_shot": 2, "reference_shots": len(reference)},
            "cusum": {"k": s.cusum_k, "h": s.cusum_h, "window": s.cusum_window,
                      "segments": [{"position": p, "center": c, "sigma": sd}
                                   for p, c, sd in track.centers]},
        }  # fmt: skip

    # shot 데이터 ----------------------------------------------------------------------
    def _shots(self, shots, replay, predictions, explanations, track, tightened, retrains, base):
        parts = replay.join(predictions)
        model_of = np.searchsorted(retrains, np.arange(len(shots)), side="right") - 1
        rule_prior = float(self.parts.loc[self.parts["order"] < shots["order"].iloc[0],
                                          "defect"].mean())  # fmt: skip
        by_order = {o: g for o, g in parts.groupby("order")}
        rows = []
        for i, shot in shots.iterrows():
            g = by_order[shot["order"]]
            rows.append({
                "i": i, "order": int(shot["order"]), "run": int(shot["run"]),
                "shot": int(shot["Shot"]), "abnormal": bool(shot["is_abnormal"]),
                "rate": float(shot["defect_rate"]), "cu": round(float(track.upper[i]), 4),
                "cl": round(float(track.lower[i]), 4), "tight": bool(tightened[i]),
                "model": int(model_of[i]), "base": round(float(base[i]), 4),
                "x": {v: _round(shot[v]) for v in PROCESS_VARS},
                "parts": [self._part(p, explanations.get(idx), rule_prior, base[i])
                          for idx, p in g.sort_values("Cavity").iterrows()],
            })  # fmt: skip
        return rows

    @staticmethod
    def _part(p: pd.Series, shap_rows, rule_prior: float, base: float) -> dict:
        """p: 위험도(모델 확률을 shot의 기준 불량률로 옮긴 값), raw: 모델 확률(불량 50% 기준)."""
        rule = p["hist_cav_rate_10"]
        return {
            "cav": int(p["Cavity"]), "p": round(float(prior_shift(p["p_raw"], base)), 4),
            "raw": round(float(p["p_raw"]), 4),
            "rule": round(float(rule if pd.notna(rule) else rule_prior), 4), "y": int(p["defect"]),
            "type": p["type5"], "tp": [round(float(p[f"type_{c}"]), 3) for c in TYPE_CLASSES],
            "shap": [[v, _round(x), round(s, 4)] for v, x, s in shap_rows] if shap_rows else None,
        }  # fmt: skip

    # 알람 -----------------------------------------------------------------------------
    def _alarms(self, scenario: Scenario, shots: pd.DataFrame, replay: pd.DataFrame,
                track) -> list[dict]:  # fmt: skip
        alarms = [*self._cusum_alarms(scenario, shots, replay, track),
                  *self._range_alarms(scenario, shots), *self._shift_alarms(shots)]  # fmt: skip
        alarms.sort(key=lambda a: (a["at"], a["level_rank"]))
        for k, alarm in enumerate(alarms):
            alarm["id"] = f"{scenario.id}-{k}"
        return alarms

    def _ocap(self, level: str) -> dict:
        row = self.ocap.loc[level]
        return {"evidence": row["evidence"],
                "actions": [a for a in (row["action"], row["follow_up"]) if a and a != "-"],
                "release": row["release"]}  # fmt: skip

    def _cusum_alarms(self, scenario, shots, replay, track) -> list[dict]:
        s, n = self.settings, len(shots)
        ups = [at for at, d, _ in track.alarms if d == "up"]
        alarms = []
        for at, direction, raw_at in track.alarms:
            if at >= n:
                continue
            if direction == "up":
                later = [u for u in ups if at < u < at + s.tighten_shots]
                release = (later[-1] if later else at) + s.tighten_shots
                alarms.append(_alarm(
                    "critical", "defect_cusum_up", at, raw_at, "불량률 CUSUM 경보",
                    f"불량률 상측 누적합이 h={s.cusum_h:g}를 넘었다. 다음 {s.tighten_shots} shot "
                    "전수검사로 전환", release if release < n else None,
                    self._ocap("경고"),
                    self._diagnosis(scenario, shots, replay, raw_at)))  # fmt: skip
            else:
                alarms.append(_alarm(
                    "info", "defect_cusum_down", at, raw_at, "불량률 감소 감지",
                    f"불량률 하측 누적합이 h={s.cusum_h:g}를 넘었다(불량률이 기준보다 낮아짐)",
                    None, {"evidence": "보고서 6.3절: 경보 재학습 신호(상·하측)", "release": "-",
                           "actions": ["재학습 옵션이 '경보 시'면 모델을 다시 학습"]},
                    None))  # fmt: skip
        return alarms

    def _diagnosis(self, scenario, shots, replay, at: int) -> dict:
        """경보 shot 기준: 관리 범위 밖 비율(최근 20 shot), 최근 50 shot 불량 유형 구성 변화,
        늘어난 유형의 점검 항목(7단계)."""
        s = self.settings
        recent = shots.iloc[max(0, at - s.sustained_window + 1) : at + 1]
        out_of_range = [{"variable": r.variable, "label": VARIABLE_LABELS[r.variable],
                         "range": r.label(),
                         "share": float((~r.contains(recent[r.variable])).mean())}
                        for r in self.ranges.get(scenario.product_type, [])]  # fmt: skip
        window = shots["order"].iloc[max(0, at - s.tighten_shots + 1) : at + 1]
        now = replay[replay["order"].isin(window) & (replay["defect"] == 1)]["type5"]
        before = self.parts[(self.parts["order"] < shots["order"].iloc[0])
                            & (self.parts["Product_Type"] == scenario.product_type)
                            & (self.parts["defect"] == 1)]["type5"]  # fmt: skip
        mix = []
        for code in TYPE_CLASSES:
            mix.append({"type": code, "label": TYPE5_LABELS[code],
                        "now": float((now == code).mean()) if len(now) else 0.0,
                        "before": float((before == code).mean())
                        if len(before) else 0.0})  # fmt: skip
        rising = sorted(mix, key=lambda m: m["now"] - m["before"], reverse=True)[:2]
        checks = []
        for m in rising:
            if m["now"] == 0:
                continue
            items = self.checklist[self.checklist["type5"] == m["type"]]
            checks.append({"type": m["type"], "label": m["label"],
                           "items": [{"check_point": r.check_point, "variable": r.variable,
                                      "label": r.label, "direction": r.direction,
                                      "evidence": f"구간 {r.runs_agree:.0f}/{r.runs:.0f}"}
                                     for r in items.itertuples()]})  # fmt: skip
        return {"out_of_range": out_of_range, "type_mix": mix, "defects_recent": int(len(now)),
                "checks": checks}  # fmt: skip

    def _range_alarms(self, scenario, shots) -> list[dict]:
        s, alarms = self.settings, []
        runs = shots["run"].to_numpy()
        for r in self.ranges.get(scenario.product_type, []):
            out = (~r.contains(shots[r.variable])).to_numpy()
            for begin, end in sustained_episodes(out, runs, s.sustained_window):
                share = out[max(0, begin - s.sustained_window + 1) : begin + 1].mean()
                alarms.append(_alarm(
                    "info", f"range_{r.variable}", begin, begin,
                    f"{VARIABLE_LABELS[r.variable]} 관리 범위(안) 밖 운전 지속",
                    f"최근 {s.sustained_window} shot 중 {share:.0%}가 범위 {r.label()} 밖",
                    end, self._ocap("정보"), None, variable=r.variable))  # fmt: skip
        return alarms

    def _shift_alarms(self, shots) -> list[dict]:
        s, alarms = self.settings, []
        runs = shots["run"].to_numpy()
        for v in KEY_VARS:
            last = -s.shift_cooldown
            for at in shift_events(shots[v].to_numpy(), runs):
                if at - last < s.shift_cooldown:
                    continue
                last = at
                alarms.append(_alarm(
                    "log", f"shift_{v}", int(at), int(at), f"{VARIABLE_LABELS[v]} 급변",
                    f"값 {_round(shots[v].iloc[at])} (직전 50 shot 중앙값에서 3.5σ 넘게 벗어남)",
                    None, self._ocap("기록만"), None, variable=v))  # fmt: skip
        return alarms

    # 메타 -----------------------------------------------------------------------------
    def _meta(self, scenario: Scenario, shots: pd.DataFrame, retrains, models) -> dict:
        return {
            "id": scenario.id, "label": scenario.label, "product_type": scenario.product_type,
            "start_run": scenario.start_run, "retrain": scenario.retrain, "n_shots": len(shots),
            "first_order": int(shots["order"].iloc[0]), "last_order": int(shots["order"].iloc[-1]),
            "runs": sorted(int(r) for r in shots["run"].unique()),
            "has_shap": scenario.retrain == "none", "models": models,
            "ranges": [{"variable": r.variable, "label": VARIABLE_LABELS[r.variable],
                        "low": None if r.open_low else r.low,
                        "high": None if r.open_high else r.high, "text": r.label()}
                       for r in self.ranges.get(scenario.product_type, [])],
            "settings": vars(self.settings),
        }  # fmt: skip


LEVEL_RANK = {"critical": 0, "warning": 1, "info": 2, "log": 3}


def _alarm(level, rule, at, raw_at, title, message, release_at, ocap, diagnosis, variable=None):
    return {"level": level, "level_rank": LEVEL_RANK[level], "rule": rule, "at": int(at),
            "detected_at": int(raw_at), "title": title, "message": message,
            "release_at": None if release_at is None else int(release_at), "variable": variable,
            "evidence": ocap["evidence"], "actions": ocap["actions"], "release": ocap["release"],
            "diagnosis": diagnosis}  # fmt: skip


def _round(value) -> float | None:
    """유효숫자 5자리 (JSON 크기 절약)."""
    if value is None or pd.isna(value):
        return None
    return float(f"{float(value):.5g}")
