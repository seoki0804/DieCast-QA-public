"""재생 구간의 감시: 불량률 CUSUM(경보·재학습 신호), 관리 범위 밖 지속, 공정 변수 급변.

모두 그 shot까지 알 수 있는 정보만 쓴다. 불량률은 검사 뒤에 알므로 경보는 다음 shot부터 반영(lag 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from diecast_qa.improvement.alarms import sudden_shift_alarm
from diecast_qa.spc.charts import CUSUMChart


@dataclass
class CusumTrack:
    """재생 구간 shot마다 상·하측 누적합(σ 단위)과 경보. 경보 뒤에는 직전 window shot으로 기준을
    다시 잡는다(8.2와 같은 방식). alarms: (경보가 반영되는 위치, "up"|"down", 경보 shot 위치)."""

    upper: np.ndarray
    lower: np.ndarray
    centers: list[tuple[int, float, float]] = field(default_factory=list)  # (시작 위치, 중심, σ)
    alarms: list[tuple[int, str, int]] = field(default_factory=list)


def cusum_track(stream: pd.DataFrame, start: int, k: float = 0.25, h: float = 8.0,
                window: int = 200, lag: int = 1) -> CusumTrack:  # fmt: skip
    """stream: 한 제품 유형의 shot(생산 순서, defect_rate 열). start 이후를 감시한다.

    반환 배열의 i번째는 stream의 start + i번째 shot이다."""
    n = len(stream) - start
    track = CusumTrack(np.zeros(n), np.zeros(n))
    current = start
    while current < len(stream):
        chart = CUSUMChart("defect_rate", k=k, h=h, sigma_method="binomial").fit(
            stream.iloc[max(0, current - window) : current])  # fmt: skip
        track.centers.append((current - start, chart.center_, chart.sigma_))
        points = chart.evaluate(stream.iloc[current:])
        upper = points[points["statistic"] == "cusum_upper"]
        lower = points[points["statistic"] == "cusum_lower"]
        signal = upper["signal"].to_numpy() | lower["signal"].to_numpy()
        stop = int(np.argmax(signal)) if signal.any() else len(signal) - 1
        span = slice(current - start, current - start + stop + 1)
        track.upper[span] = upper["value"].to_numpy()[: stop + 1]
        track.lower[span] = lower["value"].to_numpy()[: stop + 1]
        if not signal.any():
            break
        direction = "up" if upper["signal"].to_numpy()[stop] else "down"
        alarm_at = current + stop
        track.alarms.append((alarm_at + lag - start, direction, alarm_at - start))
        current = alarm_at + lag
    return track


def sustained_episodes(out: np.ndarray, runs: np.ndarray, window: int = 20, enter: float = 0.8,
                       leave: float = 0.5) -> list[tuple[int, int | None]]:  # fmt: skip
    """최근 window shot 중 범위 밖 비율이 enter 이상이면 시작, leave 미만이면 끝 (같은 구간 안).
    (시작 위치, 끝 위치 또는 None)."""
    share = pd.Series(out.astype(float)).groupby(runs).transform(
        lambda s: s.rolling(window, min_periods=window).mean()).to_numpy()  # fmt: skip
    episodes, open_at = [], None
    for i, value in enumerate(share):
        new_run = i > 0 and runs[i] != runs[i - 1]
        if open_at is not None and (new_run or (np.isfinite(value) and value < leave)):
            episodes.append((open_at, i))
            open_at = None
        if open_at is None and np.isfinite(value) and value >= enter:
            open_at = i
    if open_at is not None:
        episodes.append((open_at, None))
    return episodes


def shift_events(values: np.ndarray, runs: np.ndarray) -> np.ndarray:
    """공정 변수 급변 위치 (9단계 sudden_shift_alarm: 직전 50 shot 중앙값 ± 3.5 강건 σ)."""
    return np.flatnonzero(sudden_shift_alarm(values, runs))
