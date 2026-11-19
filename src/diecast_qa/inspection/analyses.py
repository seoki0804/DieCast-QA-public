"""검사 운영·비용 분석 (10장), 샘플링 검사 비교 (8.6), 확률 보정 (8.7).

세 분석 모두 4단계의 ③ 50 shot 재학습 예측을 같은 평가 절차(ChunkedEvaluation)로 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import SEED
from diecast_qa.inspection.calibration import (
    CALIBRATORS,
    brier_score,
    expected_calibration_error,
    reliability,
)
from diecast_qa.inspection.costs import COST_RATIOS, Outcome
from diecast_qa.inspection.evaluation import (
    SCORER_LABELS,
    SCORERS,
    AlarmSwitch,
    ChunkedEvaluation,
    evaluation_stream,
    summarize,
)
from diecast_qa.inspection.sampling import AQL, CLASSICAL_PLAN, LTPD, PLAN_GRID
from diecast_qa.inspection.strategies import (
    CalibratedThreshold,
    CavityScreening,
    CensoredRecentRate,
    CostMinThreshold,
    FullInspection,
    InspectionStrategy,
    NoInspection,
    PerfectInspection,
    SamplingInspection,
    ScoreScreening,
    SwitchingInspection,
    cost_min_threshold,
)
from diecast_qa.modeling.metrics import capture_rate


def _model() -> ScoreScreening:
    return ScoreScreening("et", CostMinThreshold(), "모델 선별 (Extra Trees)")


# 10장 검사 방식. (라벨, 만드는 함수)
STRATEGIES: dict[str, tuple[str, Callable[[], InspectionStrategy]]] = {
    "full": ("전수검사", FullInspection),
    "none": ("검사 안 함", NoInspection),
    "sampling_classical": (f"샘플링 검사 (AQL {AQL:.0%}·LTPD {LTPD:.0%} 설계)",
                           lambda: SamplingInspection((CLASSICAL_PLAN,))),
    "sampling": ("샘플링 검사 (비용 최소 계획)", SamplingInspection),
    "cavity": ("캐비티 규칙", CavityScreening),
    "rule": ("규칙 선별 (최근 불량률)",
             lambda: ScoreScreening("recent_rate", CostMinThreshold(), "규칙 선별")),
    "rule_censored": ("규칙 선별 (검사한 제품 결과만)", CensoredRecentRate),
    "model": ("모델 선별 (Extra Trees)", _model),
    "switching": ("검사 강도 전환 (경보 시 전수 + 모델)",
                  lambda: SwitchingInspection(_model(), "검사 강도 전환")),
    "perfect": ("완벽한 예측 (하한)", PerfectInspection),
}  # fmt: skip
RANDOM_MATCHED = "random_matched"
STRATEGY_LABELS = {k: v[0] for k, v in STRATEGIES.items()} | {
    RANDOM_MATCHED: "무작위 검사 (모델 선별과 같은 검사량)"}  # fmt: skip
# 비용 비교의 기준에서 뺀다: 도달할 수 없는 하한, 결과를 모두 안다는 가정이 성립하지 않는 비교용
NOT_COMPARABLE = ("perfect", "rule_censored")


class _InspectionAnalysis(Analysis):
    def __init__(self, predictions: pd.DataFrame, ratios: tuple[float, ...] = COST_RATIOS,
                 evaluation: ChunkedEvaluation | None = None,
                 switch: AlarmSwitch | None = None) -> None:  # fmt: skip
        self.predictions = predictions
        self.ratios = ratios
        self.evaluation = evaluation or ChunkedEvaluation()
        self.switch = switch or AlarmSwitch()

    def stream(self, parts: pd.DataFrame) -> pd.DataFrame:
        return evaluation_stream(self.predictions, parts, switch=self.switch)


class InspectionCostAnalysis(_InspectionAnalysis):
    """검사 방식별 총비용을 비용 비율(미검:검사) 1:1~20:1에서 비교한다 (10장)."""

    name = "cost"

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        stream = self.stream(parts)
        chunks = self.evaluation.run(stream, {k: f for k, (_, f) in STRATEGIES.items()},
                                     self.ratios)  # fmt: skip
        summary = self._with_random(summarize(chunks, ["ratio", "strategy"]))
        summary["saving_vs_full"] = 1 - summary["cost_per_part"]
        tables = {
            "summary": summary.set_index(["ratio", "strategy"]),
            "best": self._best(summary),
            "by_type": summarize(chunks, ["ratio", "strategy", "Product_Type"]).set_index(
                ["ratio", "strategy", "Product_Type"]
            ),  # fmt: skip
            "settings": self._params(chunks),
            "uncertainty": self._uncertainty(chunks),
            "switching": self._switching(stream, parts),
            "chunks": chunks,
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    @staticmethod
    def _with_random(summary: pd.DataFrame) -> pd.DataFrame:
        """무작위 검사는 모델 선별과 같은 검사 비율 q로: 기대 검사 qN, 놓친 불량 (1-q)D."""
        model = summary[summary["strategy"] == "model"]
        rows = []
        for r in model.itertuples():
            q = r.inspect_rate
            out = Outcome(r.parts, r.defects, q * r.parts, (1 - q) * r.defects)
            rows.append({"ratio": r.ratio, "strategy": RANDOM_MATCHED, **vars(out),
                         "inspect_rate": q, "capture": out.capture,
                         "cost_per_part": out.cost_per_part(r.ratio)})  # fmt: skip
        return pd.concat([summary, pd.DataFrame(rows)], ignore_index=True)

    @staticmethod
    def _best(summary: pd.DataFrame) -> pd.DataFrame:
        """비용 비율마다 가장 싼 방식 (하한·비교용 제외)과 전수검사·검사 안 함 대비."""
        rows = []
        for ratio, g in summary.groupby("ratio"):
            g = g[~g["strategy"].isin(NOT_COMPARABLE)].set_index("strategy")
            best = g["cost_per_part"].idxmin()
            baseline = min(g.loc["full", "cost_per_part"], g.loc["none", "cost_per_part"])
            b = g.loc[best]
            rows.append({"ratio": ratio, "best": best, "cost_per_part": b["cost_per_part"],
                         "inspect_rate": b["inspect_rate"], "capture": b["capture"],
                         "saving_vs_full": 1 - b["cost_per_part"],
                         "saving_vs_simple": 1 - b["cost_per_part"] / baseline})  # fmt: skip
        return pd.DataFrame(rows).set_index("ratio")

    @staticmethod
    def _params(chunks: pd.DataFrame) -> pd.DataFrame:
        """로트마다 다시 정한 조정값의 요약: 임계값 중앙값, 가장 자주 고른 계획·캐비티."""
        rows = []
        for (ratio, strategy), g in chunks.groupby(["ratio", "strategy"]):
            row = {"ratio": ratio, "strategy": strategy}
            if g.get("threshold") is not None and g["threshold"].notna().any():
                t = g["threshold"].replace(np.inf, np.nan)
                row |= {"threshold_median": t.median(), "never_inspect_share":
                        g["threshold"].eq(np.inf).mean()}  # fmt: skip
            for col in ("plan", "cavities"):
                if col in g and g[col].notna().any():
                    row[f"{col}_mode"] = g[col].mode().iloc[0]
            rows.append(row)
        return pd.DataFrame(rows).set_index(["ratio", "strategy"]).dropna(how="all")

    @staticmethod
    def _uncertainty(chunks: pd.DataFrame, n_boot: int = 2000) -> pd.DataFrame:
        """로트를 복원 추출(2,000회)한 제품당 비용의 95% 구간과, 그 비율의 최저 방식과의 차이 구간.

        차이 구간이 0을 포함하면 최저 방식과 구별되지 않는다. 로트 사이 자기상관은 반영하지 않는다.
        """
        rng = np.random.default_rng(SEED)
        rows = []
        for ratio, g in chunks.groupby("ratio"):
            lots = g.assign(cost=g["inspected"] + ratio * g["missed"]).pivot_table(
                index=["Product_Type", "chunk"], columns="strategy", values=["cost", "parts"]
            )
            order = [s for s in STRATEGIES if s in lots["cost"].columns]  # 동점이면 앞의 방식
            cost, parts = lots["cost"][order], lots["parts"].iloc[:, 0].to_numpy()
            point = cost.sum() / parts.sum()
            best = point.drop(list(NOT_COMPARABLE), errors="ignore").idxmin()
            idx = rng.integers(0, len(cost), (n_boot, len(cost)))
            boot = cost.to_numpy()[idx].sum(axis=1) / parts[idx].sum(axis=1)[:, None]
            diff = boot - boot[:, [cost.columns.get_loc(best)]]
            for j, strategy in enumerate(cost.columns):
                rows.append({"ratio": ratio, "strategy": strategy, "cost_per_part": point[strategy],
                             "ci_low": np.quantile(boot[:, j], 0.025),
                             "ci_high": np.quantile(boot[:, j], 0.975), "best": best,
                             "diff_low": np.quantile(diff[:, j], 0.025),
                             "diff_high": np.quantile(diff[:, j], 0.975)})  # fmt: skip
        return pd.DataFrame(rows).set_index(["ratio", "strategy"])

    def _switching(self, stream: pd.DataFrame, parts: pd.DataFrame) -> pd.DataFrame:
        """제품 유형별 평가 구간 안 경보 수, 검사 강화 구간 비율과 그 구간의 불량률."""
        evaluated = self.evaluation.evaluated(stream)
        alarms = self.switch.alarms(parts)
        rows = []
        for ptype, g in evaluated.groupby("Product_Type"):
            t = g["tightened"]
            inside = [o for o in alarms.get(ptype, []) if o in set(g["order"])]
            rows.append({"Product_Type": ptype, "alarms": len(inside),
                         "shots": g["order"].nunique(), "tightened_share": t.mean(),
                         "rate_tightened": g.loc[t, "y"].mean(),
                         "rate_normal": g.loc[~t, "y"].mean()})  # fmt: skip
        return pd.DataFrame(rows).set_index("Product_Type")

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        s = tables["summary"]
        full = s.xs("full", level="strategy").iloc[0]
        rate = full["defects"] / full["parts"]
        notes = [f"평가: 제품 {full['parts']:.0f}개(불량률 {rate:.1%}). 비용 비율이 "
                 f"{1 / rate:.1f}:1보다 작으면 검사 안 함이 전수검사보다 싸다"]  # fmt: skip
        for ratio, b in tables["best"].iterrows():
            g = s.xs(ratio, level="ratio")["cost_per_part"]
            notes.append(
                f"{ratio}:1 → 최저 {STRATEGY_LABELS[b['best']]} {b['cost_per_part']:.3f} "
                f"(전수검사 대비 {b['saving_vs_full']:.0%} 절감, 검사 {b['inspect_rate']:.0%}, "
                f"포착 {b['capture']:.0%}) | 모델 {g['model']:.3f}, 규칙 {g['rule']:.3f}, 전환 "
                f"{g['switching']:.3f}, 샘플링 {g['sampling']:.3f}, 캐비티 {g['cavity']:.3f}, "
                f"검사 안 함 {g['none']:.3f}"
            )  # fmt: skip
        for ratio in (10, 20):
            if ratio in s.index.get_level_values("ratio"):
                full_info, censored = s.loc[(ratio, "rule")], s.loc[(ratio, "rule_censored")]
                notes.append(f"검사한 제품 결과만 아는 규칙 ({ratio}:1): 비용 "
                             f"{full_info['cost_per_part']:.3f} → {censored['cost_per_part']:.3f}, "
                             f"포착 {full_info['capture']:.0%} → "
                             f"{censored['capture']:.0%}")  # fmt: skip
        unc = tables["uncertainty"]
        for ratio, g in unc.groupby(level="ratio"):
            g = g.droplevel("ratio").drop(list(NOT_COMPARABLE), errors="ignore")
            tied = g[(g["diff_low"] <= 0) & (g["diff_high"] >= 0)].index
            notes.append(f"{ratio}:1 최저와 구별되지 않는 방식(최저 포함, 차이 95% 구간이 0 포함): "
                         + ", ".join(STRATEGY_LABELS[t] for t in tied))  # fmt: skip
        sw = tables["switching"]
        notes.append("검사 강도 전환(평가 구간): " + ", ".join(
            f"유형 {p} 경보 {r.alarms:.0f}회, 강화 구간 {r.tightened_share:.0%}"
            + (f" (불량률 {r.rate_tightened:.1%} vs 평상시 {r.rate_normal:.1%})"
               if r.tightened_share > 0 else "")
            for p, r in sw.iterrows()))  # fmt: skip
        notes.append("비용은 제품 1개당(검사 비용 1 기준). 전수검사 = 1")
        return tuple(notes)


class SamplingComparison(_InspectionAnalysis):
    """같은 검사량에서 샘플링 검사·규칙·모델·검사 강도 전환의 불량 포착률, OC curve (8.6)."""

    name = "sampling"
    LOT_SIZE = 100

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        stream = self.stream(parts)
        data = self.evaluation.evaluated(stream)
        tables = {
            "plans": self._plans(data),
            "curves": self._curves(data),
            "switching_curve": self._switching_curve(data),
            "points": self._points(data),
            "oc": self._oc(stream),
            "lots": data.groupby("chunk").agg(Product_Type=("Product_Type", "first"),
                                              parts=("y", "size"), rate=("y", "mean")),
        }  # fmt: skip
        return AnalysisResult(self.name, tables, self.notes(tables))

    def _plans(self, data: pd.DataFrame) -> pd.DataFrame:
        """계획마다 평가 로트 전체의 기대 검사 비율·포착률.

        capture_et·capture_recent_rate: 같은 검사 비율에서 모델·규칙의 포착률.
        """
        lots = [g["y"].to_numpy() for _, g in data.groupby("chunk")]
        y = data["y"].to_numpy()
        rows = []
        for plan in (*PLAN_GRID, CLASSICAL_PLAN):
            total = sum((plan.outcome(lot) for lot in lots), Outcome())
            rate = total.inspect_rate
            rows.append({"plan": plan.label, "n": plan.n, "c": plan.c,
                         "classical": plan == CLASSICAL_PLAN, "inspect_rate": rate,
                         "capture": total.capture,
                         **{f"capture_{s}": capture_rate(y, data[s].to_numpy(), rate)
                            for s in ("et", "recent_rate")}})  # fmt: skip
        return pd.DataFrame(rows).set_index("plan")

    @staticmethod
    def _curves(data: pd.DataFrame) -> pd.DataFrame:
        y = data["y"].to_numpy()
        fracs = np.round(np.arange(0.01, 1.0001, 0.01), 2)
        curves = {s: [capture_rate(y, data[s].to_numpy(), f) for f in fracs]
                  for s in ("et", "recent_rate")}  # fmt: skip
        return pd.DataFrame({"inspect_rate": fracs, "random": fracs, **curves}).set_index(
            "inspect_rate")  # fmt: skip

    @staticmethod
    def _switching_curve(data: pd.DataFrame) -> pd.DataFrame:
        """경보 구간은 전수, 그 밖은 모델 점수 ≥ t. t를 바꿔 가며 (검사 비율, 포착률)."""
        y, score, tight = data["y"].to_numpy(), data["et"].to_numpy(), data["tightened"].to_numpy()
        rows = []
        for t in [np.inf, *np.quantile(score, np.linspace(1, 0, 41))]:
            out = Outcome.from_inspection(y, (score >= t) | tight)
            rows.append({"threshold": t, "inspect_rate": out.inspect_rate, "capture": out.capture})
        return pd.DataFrame(rows)

    @staticmethod
    def _points(data: pd.DataFrame) -> pd.DataFrame:
        """한 점으로 나오는 방식: 캐비티1만 검사, 경보 구간만 검사."""
        y = data["y"].to_numpy()
        masks = {"cavity_1": data["Cavity"].eq(1), "tightened_only": data["tightened"]}
        return pd.DataFrame([{"point": k, "inspect_rate": (o := Outcome.from_inspection(
            y, m.to_numpy())).inspect_rate, "capture": o.capture}
            for k, m in masks.items()]).set_index("point")  # fmt: skip

    def _oc(self, stream: pd.DataFrame) -> pd.DataFrame:
        """고전적 설계 계획과, 비용 최소 계획으로 가장 자주 고른 계획(10:1, 20:1)의 OC curve."""
        chosen = self.evaluation.run(stream, {"sampling": SamplingInspection}, (10, 20))
        plans = {CLASSICAL_PLAN.label: CLASSICAL_PLAN}
        grid = {p.label: p for p in PLAN_GRID}
        for _, g in chosen.groupby("ratio"):
            label = g["plan"].mode().iloc[0]
            plans.setdefault(label, grid[label])
        p = np.round(np.arange(0, 0.501, 0.01), 2)
        return pd.DataFrame({label: plan.oc(p, self.LOT_SIZE) for label, plan in plans.items()},
                            index=pd.Index(p, name="lot_rate"))  # fmt: skip

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        plans = tables["plans"]
        grid = plans[~plans["classical"]]
        better = (grid["capture"] > grid["capture_et"]).sum()
        better_rule = (grid["capture"] > grid["capture_recent_rate"]).sum()
        c = plans[plans["classical"]].iloc[0]
        notes = [
            f"고전적 설계 계획 {plans.index[plans['classical']][0]} (AQL {AQL:.0%}, "
            f"LTPD {LTPD:.0%}, α 5%·β 10%): 검사 {c['inspect_rate']:.0%}, "
            f"포착 {c['capture']:.0%} | 같은 검사량에서 "
            f"모델 {c['capture_et']:.0%}, 규칙 {c['capture_recent_rate']:.0%}",
            f"샘플링 계획 {len(grid)}개 중 같은 검사량에서 모델보다 많이 찾는 계획 {better}개, "
            f"규칙보다 많이 찾는 계획 {better_rule}개",
        ]  # fmt: skip
        curves = tables["curves"]
        for f in (0.2, 0.5):
            notes.append(f"검사 {f:.0%}일 때 포착률: 모델 {curves.loc[f, 'et']:.0%}, 규칙 "
                         f"{curves.loc[f, 'recent_rate']:.0%}, 무작위 {f:.0%}")  # fmt: skip
        pts = tables["points"]
        notes.append(f"캐비티1만 검사: 검사 {pts.loc['cavity_1', 'inspect_rate']:.0%}, 포착 "
                     f"{pts.loc['cavity_1', 'capture']:.0%}. 경보 구간만 검사: 검사 "
                     f"{pts.loc['tightened_only', 'inspect_rate']:.0%}, 포착 "
                     f"{pts.loc['tightened_only', 'capture']:.0%}")  # fmt: skip
        return tuple(notes)


class CalibrationAnalysis(_InspectionAnalysis):
    """점수 보정(Platt, Isotonic)의 신뢰도·Brier score와, 보정이 비용 판정을 바꾸는지 (8.7).

    보정기는 임계값과 같이 로트마다 과거 로트의 예측으로 다시 학습한다.
    """

    name = "calibration"
    POLICIES = {**{m: c.label + " + 1/비용 비율" for m, c in CALIBRATORS.items()},
                "cost_min": "과거 비용 최소 임계값",
                "hindsight": "사후 최적 임계값 (참고)"}  # fmt: skip

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        stream = self.stream(parts)
        probs = self._calibrated(stream)
        groups = probs.groupby(["scorer", "method"], sort=False)
        tables = {
            "scores": groups.apply(
                lambda g: pd.Series(
                    {
                        "brier": brier_score(g["prob"], g["y"]),
                        "ece": expected_calibration_error(g["prob"], g["y"]),
                        "mean_prob": g["prob"].mean(),
                        "observed": g["y"].mean(),
                    }
                ),
                include_groups=False,
            ),  # fmt: skip
            "reliability": groups.apply(
                lambda g: reliability(g["prob"].to_numpy(), g["y"].to_numpy()), include_groups=False
            ),  # fmt: skip
            "cost": self._cost(stream),
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    def _calibrated(self, stream: pd.DataFrame) -> pd.DataFrame:
        frames = []
        for _, past, current, ready in self.evaluation.steps(stream):
            if not ready:
                continue
            for scorer in SCORERS:
                for method, make in CALIBRATORS.items():
                    cal = make().fit(past[scorer].to_numpy(), past["y"].to_numpy())
                    frames.append(pd.DataFrame({"scorer": scorer, "method": method,
                                                "prob": cal.transform(current[scorer].to_numpy()),
                                                "y": current["y"].to_numpy()}))  # fmt: skip
        return pd.concat(frames, ignore_index=True)

    def _cost(self, stream: pd.DataFrame) -> pd.DataFrame:
        strategies = {}
        for scorer in SCORERS:
            for method, make in CALIBRATORS.items():
                strategies[f"{scorer}:{method}"] = lambda s=scorer, m=make: ScoreScreening(
                    s, CalibratedThreshold(m), ""
                )
            strategies[f"{scorer}:cost_min"] = lambda s=scorer: ScoreScreening(
                s, CostMinThreshold(), ""
            )
        chunks = self.evaluation.run(stream, strategies, self.ratios)
        table = summarize(chunks, ["ratio", "strategy"])
        data = self.evaluation.evaluated(stream)
        hindsight = []
        for ratio in self.ratios:
            for scorer in SCORERS:
                t = cost_min_threshold(data[scorer].to_numpy(), data["y"].to_numpy(float), ratio)
                out = Outcome.from_inspection(data["y"], data[scorer].to_numpy() >= t)
                hindsight.append({"ratio": ratio, "strategy": f"{scorer}:hindsight", **vars(out),
                                  "inspect_rate": out.inspect_rate, "capture": out.capture,
                                  "cost_per_part": out.cost_per_part(ratio)})  # fmt: skip
        table = pd.concat([table, pd.DataFrame(hindsight)], ignore_index=True)
        table[["scorer", "policy"]] = table["strategy"].str.split(":", expand=True)
        return table.drop(columns="strategy").set_index(["ratio", "scorer", "policy"]).sort_index()

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        notes = []
        scores = tables["scores"]
        for scorer in SCORERS:
            s = scores.loc[scorer]
            notes.append(
                f"{SCORER_LABELS[scorer]}: 평균 예측 {s.loc['raw', 'mean_prob']:.1%} vs 실제 "
                f"{s.loc['raw', 'observed']:.1%}. Brier 보정 없음 {s.loc['raw', 'brier']:.4f} → "
                f"Platt {s.loc['platt', 'brier']:.4f}, Isotonic {s.loc['isotonic', 'brier']:.4f}"
                f" (ECE {s.loc['raw', 'ece']:.3f} → {s.loc['platt', 'ece']:.3f}, "
                f"{s.loc['isotonic', 'ece']:.3f})"
            )  # fmt: skip
        cost = tables["cost"]["cost_per_part"]
        for ratio in (5, 10, 20):
            if ratio not in cost.index.get_level_values("ratio"):
                continue
            for scorer in SCORERS:
                c = cost.loc[(ratio, scorer)]
                notes.append(f"{ratio}:1 {SCORER_LABELS[scorer]} 비용: " + ", ".join(
                    f"{self.POLICIES[p]} {c[p]:.3f}" for p in self.POLICIES))  # fmt: skip
        return tuple(notes)
