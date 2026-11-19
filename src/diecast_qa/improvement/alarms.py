"""경보 규칙 비교와 이탈 시 대응 계획 (OCAP, Out-of-Control Action Plan) (추가 연구).

경보가 쓸모 있으려면 (1) 너무 자주 울리지 않고 (2) 울린 뒤 실제로 불량이 늘어야 한다.
규칙마다 100 shot당 경보 수, 경보 뒤 horizon shot의 불량 배수, 그 구간에 든 불량 shot 비율을 본다.
불량 배수는 두 가지다. 전체 평균 대비는 운영자가 겪는 위험이고, 같은 구간 평균 대비는 '불량이
많은 시기'라는 정보를 빼고도 경보가 위험을 알려 주는지다(공정 변수 경보의 판단 기준).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import KEY_VARS, TYPE5_LABELS, VARIABLE_LABELS
from diecast_qa.data import shot_view
from diecast_qa.improvement.levers import candidate_ranges
from diecast_qa.inspection.evaluation import AlarmSwitch


def consecutive_alarm(out: np.ndarray, runs: np.ndarray, m: int) -> np.ndarray:
    """같은 구간에서 범위 밖이 m shot 연속된 시점(m번째 shot)에 경보."""
    count = np.zeros(len(out), int)
    for i in range(len(out)):
        same = i > 0 and runs[i] == runs[i - 1]
        count[i] = (count[i - 1] + 1 if same else 1) if out[i] else 0
    return count == m


def sustained_alarm(out: np.ndarray, runs: np.ndarray, window: int = 20,
                    share: float = 0.8) -> np.ndarray:  # fmt: skip
    """같은 구간의 최근 window shot 중 범위 밖 비율이 share 이상이 되는 순간(진입 시점)에 경보."""
    frame = pd.DataFrame({"out": out.astype(float), "run": runs})
    rolling = frame.groupby("run")["out"].transform(
        lambda s: s.rolling(window, min_periods=window).mean())  # fmt: skip
    state = (rolling >= share).to_numpy()
    previous = pd.Series(state).groupby(runs).shift(1, fill_value=False).to_numpy()
    return state & ~previous


def sudden_shift_alarm(values: np.ndarray, runs: np.ndarray, k: float = 3.5, window: int = 50,
                       min_periods: int = 20) -> np.ndarray:  # fmt: skip
    """직전 window shot의 중앙값에서 k × 강건 표준편차(1.4826·MAD) 넘게 벗어나면 경보.
    공정값의 자기상관 때문에 고정 관리한계 대신 같은 구간의 최근 값을 기준으로 쓴다(3단계)."""
    s = pd.Series(values, dtype=float)
    grouped = s.groupby(runs)
    med = grouped.transform(lambda x: x.shift(1).rolling(window, min_periods=min_periods).median())
    mad = (s - med).abs().groupby(runs).transform(
        lambda x: x.shift(1).rolling(window, min_periods=min_periods).median())  # fmt: skip
    z = (s - med) / (1.4826 * mad).replace(0, np.nan)
    return (z.abs() > k).fillna(False).to_numpy()


def alarm_windows(alarm: np.ndarray, runs: np.ndarray, horizon: int) -> np.ndarray:
    """경보 다음 shot부터 horizon shot (같은 구간 안)."""
    window = np.zeros(len(alarm), bool)
    for i in np.flatnonzero(alarm):
        j = i + 1
        while j < len(alarm) and j <= i + horizon and runs[j] == runs[i]:
            window[j] = True
            j += 1
    return window


def evaluate_alarm(alarm: np.ndarray, y: np.ndarray, runs: np.ndarray, horizon: int) -> dict:
    """100 shot당 경보 수, 경보 뒤 불량 배수(전체 평균·같은 구간 평균 대비), 불량 shot 포착 비율."""
    window = alarm_windows(alarm, runs, horizon)
    run_mean = pd.Series(y, dtype=float).groupby(runs).transform("mean").to_numpy()
    hit = y[window].sum()
    return {"horizon": horizon, "alarms": int(alarm.sum()), "alarms_per_100": alarm.mean() * 100,
            "window_share": window.mean(),
            "lift": hit / (y.mean() * window.sum()) if window.any() else np.nan,
            "lift_within_run": hit / run_mean[window].sum() if window.any() else np.nan,
            "coverage": hit / y.sum()}  # fmt: skip


class AlarmDesign(Analysis):
    """제품 유형별로 경보 규칙을 비교하고, 불량률 경보 시점의 원인 진단 정보와 OCAP 표를 만든다."""

    name = "alarms"
    RANGE_RULES = {"range_out_1": "관리 범위 밖 1 shot", "range_out_3": "관리 범위 밖 3 shot 연속",
                   "sustained_20": "최근 20 shot 중 80% 이상 범위 밖"}  # fmt: skip

    def __init__(self, proposals: pd.DataFrame, horizon: int = 10,
                 switch: AlarmSwitch | None = None) -> None:  # fmt: skip
        self.ranges = candidate_ranges(proposals)
        self.horizon = horizon  # 공정 변수 경보. 불량률 경보는 조치 기간(switch.window)으로 본다
        self.switch = switch or AlarmSwitch()

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        clean = parts[~parts["is_abnormal"]]
        shots = shot_view(clean).reset_index().sort_values("order", ignore_index=True)
        cusum = self.switch.alarms(parts)
        tables = {"rules": self._rules(shots, cusum), "diagnosis": self._diagnosis(clean, cusum)}
        tables["ocap"] = self._ocap(tables)
        return AnalysisResult(self.name, tables, self.notes(tables))

    def _rules(self, shots: pd.DataFrame, cusum: dict[int, list[int]]) -> pd.DataFrame:
        rows = []
        for ptype, s in shots.groupby("Product_Type"):
            y, runs = s["shot_defect"].to_numpy(), s["run"].to_numpy()

            def add(variable, rule, label, alarm, horizon=self.horizon, ptype=ptype, y=y,
                    runs=runs):  # fmt: skip
                rows.append(
                    {
                        "Product_Type": ptype,
                        "variable": variable,
                        "rule": rule,
                        "label": label,
                        **evaluate_alarm(alarm, y, runs, horizon),
                    }
                )

            for r in self.ranges.get(ptype, []):
                out = (~r.contains(s[r.variable])).to_numpy()
                add(r.variable, "range_out_1", self.RANGE_RULES["range_out_1"],
                    consecutive_alarm(out, runs, 1))  # fmt: skip
                add(r.variable, "range_out_3", self.RANGE_RULES["range_out_3"],
                    consecutive_alarm(out, runs, 3))  # fmt: skip
                add(r.variable, "sustained_20", self.RANGE_RULES["sustained_20"],
                    sustained_alarm(out, runs))  # fmt: skip
            for v in KEY_VARS:
                add(v, "sudden_shift", "급변 (최근 50 shot 중앙값 ± 3.5σ)",
                    sudden_shift_alarm(s[v].to_numpy(), runs))  # fmt: skip
            add(
                "defect_rate",
                "defect_cusum",
                "불량률 CUSUM 상측 경보",
                s["order"].isin(cusum.get(ptype, [])).to_numpy(),
                self.switch.window,
            )
        table = pd.DataFrame(rows)
        table.insert(2, "variable_label", table["variable"].map(VARIABLE_LABELS).fillna("불량률"))
        return table.set_index(["Product_Type", "variable", "rule"])

    def _diagnosis(self, parts: pd.DataFrame, cusum: dict[int, list[int]]) -> pd.DataFrame:
        """불량률 경보 뒤 50 shot(검사 강화 구간) vs 같은 구간의 나머지: 범위 밖 비율, 유형 구성."""
        flags = self.switch.tightened(parts)
        rows = []
        for ptype, g in parts.groupby("Product_Type"):
            alarmed_runs = g.loc[g["order"].map(flags).fillna(False).astype(bool), "run"].unique()
            g = g[g["run"].isin(alarmed_runs)]
            if g.empty:
                continue
            tight = g["order"].map(flags).fillna(False).astype(bool)
            for r in self.ranges.get(ptype, []):
                out = ~r.contains(g[r.variable])
                rows.append({"Product_Type": ptype,
                             "item": f"범위 밖: {VARIABLE_LABELS[r.variable]}",
                             "alarm_window": out[tight].mean(),
                             "other": out[~tight].mean()})  # fmt: skip
            bad = g[g["defect"] == 1]
            bad_tight = tight[bad.index]
            for code in TYPE5_LABELS:
                if code == "normal":
                    continue
                share = bad["type5"].eq(code)
                rows.append({"Product_Type": ptype, "item": f"불량 유형: {TYPE5_LABELS[code]}",
                             "alarm_window": share[bad_tight].mean(),
                             "other": share[~bad_tight].mean()})  # fmt: skip
            rows.append({"Product_Type": ptype, "item": "제품 불량률",
                         "alarm_window": g.loc[tight, "defect"].mean(),
                         "other": g.loc[~tight, "defect"].mean()})  # fmt: skip
        return pd.DataFrame(rows).set_index(["Product_Type", "item"])

    def _ocap(self, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """대시보드 알람 시스템의 등급·발생 조건·조치. 근거 열은 위 규칙 비교에서 가져온다."""
        rules = tables["rules"]

        def evidence(rule: str) -> str:
            r = rules.xs(rule, level="rule")
            return ", ".join(
                f"유형 {p} {x.variable_label}: 100 shot당 {x.alarms_per_100:.1f}회, 뒤 "
                f"{x.horizon} shot 불량 {x.lift:.2f}배(구간 평균 대비 {x.lift_within_run:.2f}배)"
                for (p, _), x in r.iterrows() if np.isfinite(x.lift))  # fmt: skip

        rows = [
            ("경고", "불량률 CUSUM 상측 경보 (k=0.25, h=8, 직전 200 shot 기준)",
             evidence("defect_cusum"),
             "다음 50 shot 전수검사로 전환(검사 강도 전환, 보고서 8장). 그 시점에 관리 범위 밖인 "
             "변수와 최근 불량 유형의 점검 항목(보고서 7.3절)을 표시하고 설비 점검",
             "모델 재학습(경보 재학습: 50 shot 고정 주기와 같은 성능을 재학습 40% 적게, "
             "보고서 6.3절)",
             "50 shot 경과 후 새 경보가 없으면 평상시 선별검사로 복귀"),
            ("주의", "모델 위험도가 검사 기준(비용 최소 임계값, 보고서 8장) 이상인 제품",
             "보고서 8장: 같은 검사량에서 무작위의 약 2배 불량 포착",
             "해당 제품 검사, 예상 불량 유형과 점검 항목 표시(보고서 5장·7.3절)",
             "검사 결과를 최근 불량률·관리도에 반영", "제품 단위(검사 후 종료)"),
            ("정보", "관리 범위(안) 밖 운전 지속: 최근 20 shot 중 80% 이상",
             evidence("sustained_20"),
             "설정값을 관리 범위(안) 쪽으로 조정할지 검토. 조정 전후 불량률을 기록",
             "실험 계획(2^(4-1))의 요인으로 효과 확인", "최근 20 shot 중 범위 밖 50% 미만"),
            ("기록만", "공정 변수 급변 (최근 50 shot 중앙값 ± 3.5σ)", evidence("sudden_shift"),
             "경보로 쓰지 않음(불량 증가를 예고하지 못함). 원인 진단용 기록으로 남김", "-", "-"),
        ]  # fmt: skip
        return pd.DataFrame(rows, columns=["level", "trigger", "evidence", "action", "follow_up",
                                           "release"]).set_index("level")  # fmt: skip

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        rules = tables["rules"]
        notes = []
        for (ptype, _), g in rules.groupby(level=["Product_Type", "rule"], sort=False):
            g = g.droplevel(["Product_Type", "rule"])
            label, horizon = g["label"].iloc[0], g["horizon"].iloc[0]
            text = ", ".join(f"{r.variable_label} {r.alarms_per_100:.1f}회/{r.lift:.2f}배"
                             f"({r.lift_within_run:.2f}배)/{r.coverage:.0%}"
                             for r in g.itertuples() if r.alarms)  # fmt: skip
            notes.append(f"유형 {ptype} {label} [100 shot당 경보 / 뒤 {horizon} shot 불량 배수"
                         f"(구간 평균 대비) / 불량 shot 포착]: {text or '경보 없음'}")  # fmt: skip
        diag = tables["diagnosis"]
        for ptype, g in diag.groupby(level="Product_Type"):
            g = g.droplevel("Product_Type")
            gap = (g["alarm_window"] - g["other"]).drop("제품 불량률").sort_values()
            notes.append(f"유형 {ptype} 불량률 경보 뒤 50 shot: 불량률 "
                         f"{g.loc['제품 불량률', 'alarm_window']:.1%} vs 나머지 "
                         f"{g.loc['제품 불량률', 'other']:.1%}. 가장 많이 늘어난 항목: "
                         + ", ".join(f"{i} {g.loc[i, 'other']:.0%}→{g.loc[i, 'alarm_window']:.0%}"
                                     for i in gap.index[::-1][:3]))  # fmt: skip
        return tuple(notes)
