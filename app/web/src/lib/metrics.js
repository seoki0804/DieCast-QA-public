// 관리도·KPI 계산. 모두 재생 위치(upto, 포함)까지의 shot만 쓴다.

/** 최근 window shot의 제품 불량률. */
export function recentDefectRate(shots, upto, window = 50) {
  return recentWindow(shots, upto, window).rate;
}

/** 최근 window shot의 불량률과 표본 크기(shot 수·제품 수). 재생 초반에는 window보다 적다. */
export function recentWindow(shots, upto, window = 50) {
  const from = Math.max(0, upto - window + 1);
  let defects = 0;
  let parts = 0;
  for (let i = from; i <= upto; i += 1) {
    for (const part of shots[i].parts) {
      defects += part.y;
      parts += 1;
    }
  }
  return { rate: parts ? defects / parts : null, shots: upto - from + 1, parts };
}

/** 불량률 p-chart 상한: 기준 불량률 center, 제품 parts개 (표본이 작을수록 넓다). */
export function pChartUcl(center, parts) {
  return parts ? center + 3 * Math.sqrt((center * (1 - center)) / parts) : null;
}

/**
 * p-chart: subgroupShots shot(제품 subgroupShots × 2개)씩 묶은 불량률과 관리한계.
 * 중심선은 재생 시작 이전 기준 기간(limits.p_chart.center)이고, 다 찬 부분군만 그린다.
 */
export function pChart(shots, upto, limits) {
  const { center, subgroup_shots: size } = limits.p_chart;
  const points = [];
  for (let start = 0; start + size - 1 <= upto; start += size) {
    let defects = 0;
    let parts = 0;
    for (let i = start; i < start + size; i += 1) {
      for (const part of shots[i].parts) {
        defects += part.y;
        parts += 1;
      }
    }
    const sigma = Math.sqrt((center * (1 - center)) / parts);
    const ucl = center + 3 * sigma;
    const lcl = Math.max(0, center - 3 * sigma);
    const p = defects / parts;
    points.push({ start, end: start + size - 1, p, ucl, lcl, out: p > ucl || p < lcl, above: p > ucl });
  }
  return { center, points };
}

/** 지금까지 재생한 shot 수와 진행률. */
export function progress(shots, upto) {
  return { done: upto + 1, total: shots.length, ratio: shots.length ? (upto + 1) / shots.length : 0 };
}
