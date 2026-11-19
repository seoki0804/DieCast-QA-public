"""불량 개선 여지 (추가 연구, 사용자 요청): 어디를 고치면 불량이 얼마나 줄 수 있나.

데이터에 조치·정비 기록이 없으므로 모두 관측 데이터의 연관에 근거한 추정이다. 시기 효과를 빼려고
같은 생산 구간 안에서 비교하고, 인과 확인은 실험 계획(doe.py)으로 넘긴다.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.contingency_tables import StratifiedTable

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import CONTROL_VARS, SEED, TYPE5_LABELS, VARIABLE_LABELS
from diecast_qa.data import shot_view
from diecast_qa.interpret.ranges import OperatingRange


def candidate_ranges(proposals: pd.DataFrame) -> dict[int, list[OperatingRange]]:
    """7단계 관리 범위 후보(구간 내 검증 통과)를 제품 유형별 OperatingRange로."""
    table = proposals.reset_index()
    ranges: dict[int, list[OperatingRange]] = {}
    for r in table[table["verdict"] == "candidate"].itertuples():
        ranges.setdefault(int(r.Product_Type), []).append(OperatingRange(
            r.variable, r.range_low if pd.notna(r.range_low) else -np.inf,
            r.range_high if pd.notna(r.range_high) else np.inf,
            open_low=pd.isna(r.range_low), open_high=pd.isna(r.range_high)))  # fmt: skip
    return ranges


def golden_runs(shots: pd.DataFrame, min_shots: int = 100) -> dict[int, tuple[int, int]]:
    """제품 유형별 (불량률이 가장 낮은 구간, 가장 높은 구간). shot이 적은 구간은 뺀다."""
    out = {}
    for ptype, g in shots.groupby("Product_Type"):
        rate = g.groupby("run")["shot_defect"].agg(["size", "mean"])
        rate = rate[rate["size"] >= min_shots]["mean"]
        out[int(ptype)] = (int(rate.idxmin()), int(rate.idxmax()))
    return out


class ImprovementLevers(Analysis):
    """개선 수단별 불량 감소 여지: 캐비티 격차, 관리 범위 준수, 재가동 직후, 최우수 구간 조건."""

    name = "levers"

    def __init__(self, proposals: pd.DataFrame, n_boot: int = 200, block: int = 50,
                 restart_window: int = 10) -> None:  # fmt: skip
        self.ranges = candidate_ranges(proposals)
        self.n_boot = n_boot
        self.block = block  # 관리 범위 효과 bootstrap의 블록 크기(shot). 자기상관을 블록으로 보존
        self.restart_window = restart_window

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        clean = parts[~parts["is_abnormal"]]
        shots = shot_view(clean).reset_index()
        tables = {
            "cavity": self._cavity(clean),
            "cavity_types": self._cavity_types(clean),
            "ranges": self._range_compliance(clean),
            "restart": self._restart(shots),
            "golden": self._golden(shots),
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    # 캐비티 격차 -------------------------------------------------------------------------
    @staticmethod
    def _cavity(parts: pd.DataFrame) -> pd.DataFrame:
        """구간마다 캐비티1이 캐비티2와 같은 불량률이었다면 줄었을 불량 수(excess, 음수 가능)."""
        rows = []
        for run, g in parts.groupby("run"):
            r1, r2 = (g.loc[g["Cavity"] == c, "defect"].mean() for c in (1, 2))
            n1 = (g["Cavity"] == 1).sum()
            rows.append({"run": run, "rate_cavity1": r1, "rate_cavity2": r2, "parts_cavity1": n1,
                         "defects": g["defect"].sum(), "excess": (r1 - r2) * n1})  # fmt: skip
        return pd.DataFrame(rows).set_index("run")

    @staticmethod
    def _cavity_types(parts: pd.DataFrame) -> pd.DataFrame:
        bad = parts[parts["defect"] == 1]
        table = pd.crosstab(bad["type5"], bad["Cavity"])
        return table.assign(cavity1_share=table[1] / table.sum(axis=1)).rename_axis("type5")

    # 관리 범위 준수 ----------------------------------------------------------------------
    def _range_compliance(self, parts: pd.DataFrame) -> pd.DataFrame:
        """구간·캐비티를 고정한 로지스틱 회귀에 '범위 밖' 지표를 넣고, 모든 shot이 범위 안일 때의
        평균 예측 불량률을 계산한다(g-computation). 구간은 시기 효과를 흡수한다.
        신뢰구간은 50 shot 블록 bootstrap."""
        rows = []
        rng = np.random.default_rng(SEED)
        for ptype, ranges in self.ranges.items():
            data = self._indicators(parts[parts["Product_Type"] == ptype], ranges)
            terms = [f"out_{r.variable}" for r in ranges]
            point, coefs = self._g_computation(data, terms)
            blocks = data.groupby("order").ngroup() // self.block
            ids = blocks.unique()
            boot = []
            for _ in range(self.n_boot):
                pick = rng.choice(ids, len(ids))
                sample = pd.concat([data[blocks == b] for b in pick], ignore_index=True)
                try:
                    boot.append(self._g_computation(sample, terms)[0]["reduction"])
                except np.linalg.LinAlgError:
                    continue
            low, high = np.quantile(boot, [0.025, 0.975])
            rows.append({"Product_Type": ptype, **point, "reduction_low": low,
                         "reduction_high": high,
                         "ranges": "; ".join(f"{VARIABLE_LABELS[r.variable]} {r.label()}"
                                             for r in ranges),
                         **{f"or_{t[4:]}": np.exp(c) for t, c in coefs.items()},
                         **{f"out_share_{t[4:]}": data[t].mean() for t in terms}})  # fmt: skip
        return pd.DataFrame(rows).set_index("Product_Type")

    @staticmethod
    def _indicators(parts: pd.DataFrame, ranges: list[OperatingRange]) -> pd.DataFrame:
        data = parts[["order", "run", "Cavity", "defect"]].copy()
        for r in ranges:
            data[f"out_{r.variable}"] = (~r.contains(parts[r.variable])).astype(int)
        return data

    @staticmethod
    def _g_computation(data: pd.DataFrame, terms: list[str]) -> tuple[dict, pd.Series]:
        with warnings.catch_warnings():  # bootstrap 표본에서 드물게 생기는 수렴 경고
            warnings.simplefilter("ignore")
            model = smf.logit(f"defect ~ {' + '.join(terms)} + C(run) + C(Cavity)", data).fit(
                disp=0)  # fmt: skip
        inside = data.assign(**dict.fromkeys(terms, 0))
        actual, target = data["defect"].mean(), model.predict(inside).mean()
        return ({"actual_rate": actual, "in_range_rate": target,
                 "reduction": 1 - target / actual}, model.params[terms])  # fmt: skip

    # 재가동 직후 -------------------------------------------------------------------------
    def _restart(self, shots: pd.DataFrame) -> pd.DataFrame:
        """구간 시작·shot 번호가 건너뛴 뒤(기록 중단) restart_window shot과 나머지의 불량률."""
        s = shots.sort_values("order")
        gap = s.groupby("run")["Shot"].diff().fillna(2) > 1  # 구간 첫 shot도 재시작
        since = s.groupby(["run", gap.cumsum()]).cumcount()
        early = since < self.restart_window
        tables, rows = [], []
        for run, g in s.groupby("run"):
            e, y = early[g.index].to_numpy(), g["shot_defect"].to_numpy()
            rows.append({"run": run, "restarts": int(gap[g.index].sum()), "early_shots": e.sum(),
                         "rate_early": y[e].mean() if e.any() else np.nan,
                         "rate_rest": y[~e].mean() if (~e).any() else np.nan})  # fmt: skip
            if e.any() and (~e).any():
                tables.append(np.array([[y[e].sum(), (1 - y[e]).sum()],
                                        [y[~e].sum(), (1 - y[~e]).sum()]]))  # fmt: skip
        pooled = StratifiedTable(tables)
        low, high = pooled.oddsratio_pooled_confint()
        table = pd.DataFrame(rows).set_index("run")
        return table.assign(pooled_or=pooled.oddsratio_pooled, or_low=low, or_high=high)

    # 최우수 구간 조건 --------------------------------------------------------------------
    @staticmethod
    def _golden(shots: pd.DataFrame) -> pd.DataFrame:
        """제품 유형마다 불량률이 가장 낮은/높은 구간의 조정 가능 변수 중앙값과 표준화 차이
        (구간 내 표준편차의 합동값으로 나눔). 차이가 큰 변수가 '좋았던 시기의 조건' 후보다."""
        rows = []
        for ptype, (best, worst) in golden_runs(shots).items():
            g = shots[shots["Product_Type"] == ptype]
            within = g.groupby("run")[list(CONTROL_VARS)].std().pow(2).mean().pow(0.5)
            for v in CONTROL_VARS:
                b, w = (g.loc[g["run"] == r, v].median() for r in (best, worst))
                rows.append({"Product_Type": ptype, "variable": v, "label": VARIABLE_LABELS[v],
                             "best_run": best, "worst_run": worst, "best": b, "worst": w,
                             "std_diff": (b - w) / within[v] if within[v] > 0
                             else np.nan})  # fmt: skip
        table = pd.DataFrame(rows)
        table["abs_diff"] = table["std_diff"].abs()
        return table.sort_values(["Product_Type", "abs_diff"], ascending=[True, False]).set_index(
            ["Product_Type", "variable"])  # fmt: skip

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        cav = tables["cavity"]
        excess, defects = cav["excess"].sum(), cav["defects"].sum()
        worse = (cav["rate_cavity1"] > cav["rate_cavity2"]).sum()
        types = tables["cavity_types"]["cavity1_share"].sort_values(ascending=False)
        notes = [f"캐비티: 캐비티1이 같은 구간의 캐비티2 수준이면 불량 {excess:.0f}개 감소(전체 "
                 f"{defects:.0f}개의 {excess / defects:.0%}). 캐비티1이 나쁜 구간 "
                 f"{worse}/{len(cav)}. "
                 "유형별 캐비티1 비중: " + ", ".join(f"{TYPE5_LABELS[t]} {s:.0%}"
                                                  for t, s in types.items())]  # fmt: skip
        for ptype, r in tables["ranges"].iterrows():
            notes.append(f"관리 범위 준수 (유형 {ptype}: {r['ranges']}): 불량률 "
                         f"{r['actual_rate']:.1%} → {r['in_range_rate']:.1%} (감소 "
                         f"{r['reduction']:.0%}, 블록 bootstrap 95% 구간 "
                         f"{r['reduction_low']:.0%}~{r['reduction_high']:.0%})")  # fmt: skip
        rs = tables["restart"]
        notes.append(f"재가동·기록 중단 직후 {self.restart_window} shot: 불량 오즈비 "
                     f"{rs['pooled_or'].iloc[0]:.2f} ({rs['or_low'].iloc[0]:.2f}~"
                     f"{rs['or_high'].iloc[0]:.2f}), 재시작 {rs['restarts'].sum()}회")  # fmt: skip
        golden = tables["golden"]
        for ptype, g in golden.groupby(level="Product_Type"):
            g = g.droplevel("Product_Type")
            first = g.iloc[0]
            diffs = ", ".join(f"{r.label} {r.worst:.4g}→{r.best:.4g}"
                              for r in g.head(5).itertuples())  # fmt: skip
            notes.append(
                f"최우수 구간 {first['best_run']} vs 최악 구간 {first['worst_run']} "
                f"(유형 {ptype}) 차이 큰 변수: {diffs}"
            )
        return tuple(notes)
