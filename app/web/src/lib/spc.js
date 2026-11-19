// SPC 계산: 분포(히스토그램·정규곡선), 개별값 관리도(I-MR)와 규칙 위반, 최근 기준 대비 현재 위치.
// 화면과 분리해 단위 테스트한다 (npm test).

// 이동범위(n = 2) 관리도 상수: σ = MR̄ / d2, MR 관리 상한 = D4 × MR̄
export const D2 = 1.128;
export const D4 = 3.267;

export function mean(values) {
  return values.length ? values.reduce((s, x) => s + x, 0) / values.length : null;
}

/** 표본 표준편차 (n − 1). */
export function stdev(values) {
  if (values.length < 2) return 0;
  const m = mean(values);
  return Math.sqrt(values.reduce((s, x) => s + (x - m) ** 2, 0) / (values.length - 1));
}

export function quantile(values, q) {
  const sorted = [...values].sort((a, b) => a - b);
  const p = (sorted.length - 1) * q;
  const lo = Math.floor(p);
  return sorted[lo] + (sorted[Math.ceil(p)] - sorted[lo]) * (p - lo);
}

export function normalPdf(x, m, s) {
  return Math.exp(-0.5 * ((x - m) / s) ** 2) / (s * Math.sqrt(2 * Math.PI));
}

/**
 * 히스토그램. 값의 종류가 적으면(설비가 정해진 눈금으로 기록하는 변수) 값마다 막대 하나,
 * 많으면 Freedman–Diaconis 폭(8~30개 구간). step은 정규곡선을 개수 단위로 맞출 때 쓰는 구간 폭이다.
 */
export function histogram(values, maxDistinct = 30) {
  const distinct = [...new Set(values)].sort((a, b) => a - b);
  if (distinct.length <= maxDistinct) {
    let step = Infinity;
    for (let k = 1; k < distinct.length; k += 1) step = Math.min(step, distinct[k] - distinct[k - 1]);
    if (!Number.isFinite(step)) step = Math.abs(distinct[0]) * 0.02 || 1;
    const counts = new Map();
    values.forEach((v) => counts.set(v, (counts.get(v) ?? 0) + 1));
    return { step, bins: distinct.map((v) => ({ from: v - step / 2, to: v + step / 2, center: v, count: counts.get(v) })) };
  }
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const iqr = quantile(values, 0.75) - quantile(values, 0.25);
  const fd = 2 * iqr * values.length ** (-1 / 3);
  const n = Math.min(30, Math.max(8, Math.ceil((hi - lo) / (fd || (hi - lo) / 8))));
  const step = (hi - lo) / n;
  const bins = Array.from({ length: n }, (_, k) => ({ from: lo + k * step, to: lo + (k + 1) * step, center: lo + (k + 0.5) * step, count: 0 }));
  values.forEach((v) => {
    bins[Math.min(n - 1, Math.floor((v - lo) / step))].count += 1;
  });
  return { step, bins };
}

/**
 * 개별값 관리도(I-MR). 중심선 = 평균, σ = MR̄/d2, 관리한계 = 중심 ± 3σ.
 * 규칙 위반: beyond = 관리한계 밖(규칙 1), run = 중심선 한쪽에 9개 연속(Nelson 규칙 2)의 9번째부터.
 */
export function imr(values) {
  const center = mean(values);
  const mr = values.map((x, k) => (k ? Math.abs(x - values[k - 1]) : null));
  const mrBar = mean(mr.slice(1)) ?? 0;
  const sigma = mrBar / D2 || stdev(values);
  const ucl = center + 3 * sigma;
  const lcl = center - 3 * sigma;
  const beyond = [];
  const run = [];
  let length = 0;
  let side = 0;
  values.forEach((x, k) => {
    if (x > ucl || x < lcl) beyond.push(k);
    const s = Math.sign(x - center);
    length = s !== 0 && s === side ? length + 1 : s !== 0 ? 1 : 0;
    side = s;
    if (length >= 9) run.push(k);
  });
  return { center, sigma, ucl, lcl, mr, mrBar, mrUcl: D4 * mrBar, beyond, run };
}

/**
 * 현재 값의 위치: 직전 window개(현재 제외)의 평균·표준편차로 z를 구하고, 관리 범위(안)가 있으면
 * 기준 기간 중 범위 밖 비율과 현재 값이 범위 밖인지도 낸다. range = { low, high } (한쪽만 있어도 된다).
 */
export function locate(history, current, range = null) {
  const m = mean(history);
  const s = stdev(history);
  const inRange = (x) => !range || ((range.low == null || x >= range.low) && (range.high == null || x <= range.high));
  return {
    n: history.length,
    mean: m,
    sd: s,
    z: s > 0 ? (current - m) / s : 0,
    outShare: range ? history.filter((x) => !inRange(x)).length / history.length : null,
    currentOut: range ? !inRange(current) : false,
  };
}

/** 누적합 (재생 시계: shot별 사이클 타임을 더한 경과 시간). */
export function cumulativeSum(values) {
  let total = 0;
  return values.map((v) => (total += v ?? 0));
}

/** 경과 초 → 'hh:mm:ss'. */
export function clock(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const pad = (v) => String(v).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}
