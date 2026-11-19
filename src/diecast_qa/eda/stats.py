"""여러 분석에서 함께 쓰는 검정·효과 크기 계산."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats.contingency import expected_freq

from diecast_qa.config import SEED


def chi_square_test(observed: pd.DataFrame, n_resamples: int = 9999) -> dict:
    """분할표 독립성 검정과 Cramér's V.

    기대도수 5 미만 칸이 20%를 넘으면 근사 분포 대신 Monte Carlo p-value를 쓴다 (Cochran 기준).
    """
    table = observed.to_numpy()
    low_expected = float((expected_freq(table) < 5).mean())
    method = None
    if low_expected > 0.2:
        method = stats.MonteCarloMethod(n_resamples=n_resamples, rng=np.random.default_rng(SEED))
    # Yates 연속성 보정은 근사 분포용이라 Monte Carlo와 함께 쓰지 않는다
    res = stats.chi2_contingency(table, correction=method is None, method=method)
    n = table.sum()
    return {
        "n": int(n),
        "chi2": res.statistic,
        "dof": (table.shape[0] - 1) * (table.shape[1] - 1),
        "p_value": res.pvalue,
        "cramers_v": float(np.sqrt(res.statistic / (n * (min(table.shape) - 1)))),
        "low_expected_share": low_expected,
        "method": "monte_carlo" if method else "asymptotic",
    }


def hedges_g(x: np.ndarray, y: np.ndarray) -> float:
    """x 평균 - y 평균을 합동 표준편차로 나누고 소표본 보정한 효과 크기."""
    n1, n2 = len(x), len(y)
    pooled = np.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / (n1 + n2 - 2))
    if pooled == 0:
        return np.nan
    return (x.mean() - y.mean()) / pooled * (1 - 3 / (4 * (n1 + n2) - 9))


def rank_biserial(u_statistic: float, n1: int, n2: int) -> float:
    """Mann-Whitney U의 효과 크기. 양수면 첫 번째 집단의 값이 더 큰 경향 (-1~1)."""
    return 2 * u_statistic / (n1 * n2) - 1


def rank_biserial_by_group(
    values: pd.Series, case: pd.Series, groups: pd.Series, min_group: int = 10
) -> pd.DataFrame:
    """그룹(생산 구간 등)마다 case=True 집단과 나머지의 rank-biserial.

    결측은 빼고, 어느 한쪽이 min_group 미만인 그룹은 뺀다.
    반환: 행 = 그룹, 열 = effect, weight(비교 쌍 수 n_case × n_rest). 가중 평균이 구간 내 효과다.
    """
    rows = {}
    frame = pd.DataFrame({"value": values, "case": case.astype(bool), "group": groups}).dropna()
    for group, g in frame.groupby("group"):
        a = g.loc[g["case"], "value"].to_numpy(float)
        b = g.loc[~g["case"], "value"].to_numpy(float)
        if min(len(a), len(b)) < min_group:
            continue
        u = stats.mannwhitneyu(a, b).statistic
        rows[group] = {"effect": rank_biserial(u, len(a), len(b)), "weight": len(a) * len(b)}
    return pd.DataFrame(rows, index=["effect", "weight"]).T


def weighted_effect(by_group: pd.DataFrame) -> float:
    """rank_biserial_by_group 결과의 비교 쌍 수 가중 평균 (그룹이 없으면 NaN)."""
    if by_group.empty:
        return np.nan
    return float(np.average(by_group["effect"], weights=by_group["weight"]))


def format_p(p: float) -> str:
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"
