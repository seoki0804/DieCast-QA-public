"""재생 결과 평가: 대시보드 화면과 같은 규칙으로 검사 판정·누적 비용·순위 성능을 계산한다.

`ReplayLedger`는 app/web/src/lib/inspection.js의 InspectionLedger와 같은 규칙이다. 로트(50 shot)마다
재생 중 이미 결과를 안 과거 제품으로 '점수 ≥ t면 검사'의 총비용이 가장 작은 t를 정하고(8장), 과거가
짧은 처음(제품 200개·불량 10개 미만)에는 보정 확률 ≥ 1/비용 비율을 쓴다. 경고 뒤 50 shot(tight)은
전수검사다. 보고서 10.2절의 재생 비용·AUC는 이 모듈이 만든 표에서 읽는다.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from diecast_qa.inspection.strategies import cost_min_threshold

SCORE_KEYS = ("p", "rule")


class ReplayLedger:
    """재생 시나리오 하나의 검사 판정 (화면의 InspectionLedger와 같은 규칙)."""

    def __init__(self, shots: Sequence[dict], ratio: float, score_key: str = "p", lot: int = 50,
                 min_parts: int = 200, min_defects: int = 10) -> None:  # fmt: skip
        self.shots, self.ratio, self.score_key, self.lot = shots, ratio, score_key, lot
        self.fallback = 1 / ratio
        self.thresholds = self._lot_thresholds(min_parts, min_defects)

    def _lot_thresholds(self, min_parts: int, min_defects: int) -> list[float]:
        out, scores, labels = [], [], []
        for start in range(0, len(self.shots), self.lot):
            if len(scores) >= min_parts and sum(labels) >= min_defects:
                t = cost_min_threshold(np.asarray(scores), np.asarray(labels, float), self.ratio)
                # 과거 제품을 전부 검사하는 기준이 가장 쌌으면 전수검사 모드(기준 0)
                out.append(0.0 if t <= min(scores) else t)
            else:
                out.append(self.fallback)
            for shot in self.shots[start : start + self.lot]:
                for part in shot["parts"]:
                    scores.append(part[self.score_key])
                    labels.append(part["y"])
        return out

    def threshold_at(self, i: int) -> float:
        k = i // self.lot
        return self.thresholds[k] if k < len(self.thresholds) else self.fallback

    def inspects(self, part: dict, shot: dict) -> bool:
        return bool(shot["tight"]) or part[self.score_key] >= self.threshold_at(shot["i"])

    def summarize(self) -> dict:
        parts = defects = inspected = found = 0
        for shot in self.shots:
            for part in shot["parts"]:
                inspect = self.inspects(part, shot)
                parts += 1
                defects += part["y"]
                inspected += inspect
                found += part["y"] if inspect else 0
        missed = defects - found
        return {"parts": parts, "defects": defects, "inspected": inspected, "found": found,
                "inspect_rate": inspected / parts,
                "capture": found / defects if defects else np.nan,
                "cost_per_part": (inspected + self.ratio * missed) / parts}  # fmt: skip


def part_frame(payload: dict) -> pd.DataFrame:
    """시나리오의 제품 행: 위치(i), 모델 번호, 점수(p·raw·rule), 실제 불량(y)."""
    return pd.DataFrame([{"i": s["i"], "model": s["model"], "tight": s["tight"], **part}
                         for s in payload["shots"] for part in s["parts"]])  # fmt: skip


def evaluate_scenario(payload: dict, ratios: Sequence[float] = (5, 10, 20)) -> pd.DataFrame:
    """점수별 순위 성능(ROC-AUC)과 비용 비율별 누적 비용·검사 비율·포착률."""
    meta, shots = payload["meta"], payload["shots"]
    parts = part_frame(payload)
    rows = []
    for key in SCORE_KEYS:
        auc = roc_auc_score(parts["y"], parts[key])
        for ratio in ratios:
            result = ReplayLedger(shots, ratio, key).summarize()
            rows.append({"scenario": meta["id"], "product_type": meta["product_type"],
                         "start_run": meta["start_run"], "retrain": meta["retrain"],
                         "defect_rate": parts["y"].mean(), "score": key, "roc_auc": auc,
                         "ratio": ratio, **result})  # fmt: skip
    return pd.DataFrame(rows)


def calibration_summary(payload: dict) -> dict:
    """화면에 보이는 위험도(p)가 실제 불량률과 맞는지: 평균 위험도, 서로 다른 값의 수, 0·1에 붙은
    비율, Brier score, 그리고 모델 확률(raw)과 위험도의 순위 성능."""
    parts = part_frame(payload)
    p, y = parts["p"], parts["y"]
    return {"scenario": payload["meta"]["id"], "defect_rate": y.mean(), "mean_p": p.mean(),
            "distinct_p": int(p.round(3).nunique()),
            "share_p_0_or_1": float(((p <= 0.001) | (p >= 0.999)).mean()),
            "brier": float(((p - y) ** 2).mean()), "roc_auc_raw": roc_auc_score(y, parts["raw"]),
            "roc_auc_p": roc_auc_score(y, p)}  # fmt: skip


def evaluate_all(payloads: Sequence[dict], ratios: Sequence[float] = (5, 10, 20)) -> tuple[
        pd.DataFrame, pd.DataFrame]:  # fmt: skip
    """(시나리오 × 점수 × 비용 비율 표, 시나리오별 위험도 보정 상태 표)."""
    costs = pd.concat([evaluate_scenario(p, ratios) for p in payloads], ignore_index=True)
    return costs, pd.DataFrame([calibration_summary(p) for p in payloads])
