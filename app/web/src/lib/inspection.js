// 검사 판정과 누적 비용 (8단계 검사 강도 전환: 경고 뒤 50 shot은 전수검사, 평상시는 위험도 선별).
//
// 검사 기준(임계값)은 8단계와 같은 방식으로 정한다: 로트(50 shot)마다, 재생 중 이미 검사로 결과를 안
// 과거 제품에서 '임계값 이상 검사'의 총비용(검사 수 + 비용 비율 × 놓친 불량)이 가장 작은 값.
// 과거가 짧은 처음(제품 200개·불량 10개 미만)에는 위험도(최근 불량률 기준 확률) ≥ 1/비용 비율을 쓴다(8.7).
// 같은 규칙의 Python 구현: src/diecast_qa/dashboard/evaluate.py (재생 평가 표 replay_eval.csv, e2e로 대조).
// 비용은 검사 비용 1 기준이고 전수검사는 제품당 1이다.

export const SCORE_KEYS = {
  p: "모델 위험도 (최근 불량률 기준 확률)",
  rule: "최근 10 shot 불량률 규칙",
};

/** '점수 ≥ t면 검사'의 총비용이 가장 작은 t. 비용이 같으면 검사가 적은 쪽(큰 t). Infinity = 검사 안 함. */
export function costMinThreshold(scores, labels, ratio) {
  const order = scores.map((s, k) => k).sort((a, b) => scores[a] - scores[b]);
  const sorted = order.map((k) => scores[k]);
  const defectsBelow = [0];
  for (const k of order) defectsBelow.push(defectsBelow.at(-1) + labels[k]);
  const candidates = [...new Set(sorted), Infinity];
  let best = Infinity;
  let bestCost = ratio * defectsBelow.at(-1);
  let below = 0;
  for (const t of candidates) {
    while (below < sorted.length && sorted[below] < t) below += 1;
    const cost = sorted.length - below + ratio * defectsBelow[below];
    if (cost <= bestCost) {
      bestCost = cost;
      best = t;
    }
  }
  return best;
}

export class InspectionLedger {
  /**
   * @param {{ratio: number, scoreKey?: "p" | "rule", shots?: object[], lot?: number,
   *          minParts?: number, minDefects?: number}} options
   */
  constructor({ ratio, scoreKey = "p", shots = [], lot = 50, minParts = 200, minDefects = 10 }) {
    this.ratio = ratio;
    this.scoreKey = scoreKey;
    this.lot = lot;
    this.fallback = 1 / ratio;
    this.thresholds = this.#lotThresholds(shots, minParts, minDefects);
  }

  #lotThresholds(shots, minParts, minDefects) {
    const out = [];
    const scores = [];
    const labels = [];
    for (let start = 0; start < shots.length; start += this.lot) {
      const defects = labels.reduce((a, b) => a + b, 0);
      if (scores.length >= minParts && defects >= minDefects) {
        const t = costMinThreshold(scores, labels, this.ratio);
        // 과거의 모든 제품을 검사하는 기준이 가장 쌌다면 전수검사 모드(기준 0)로 둔다
        out.push(t <= Math.min(...scores) ? 0 : t);
      } else {
        out.push(this.fallback);
      }
      for (const shot of shots.slice(start, start + this.lot)) {
        for (const part of shot.parts) {
          scores.push(this.score(part));
          labels.push(part.y);
        }
      }
    }
    return out;
  }

  score(part) {
    return part[this.scoreKey];
  }

  /** shot 위치 i의 로트에 적용하는 검사 기준. */
  thresholdAt(i) {
    return this.thresholds[Math.floor(i / this.lot)] ?? this.fallback;
  }

  /** 검사 기준이 0 이하면 모든 제품을 검사한다(불량률이 1/비용 비율보다 높은 시기, 8단계). */
  inspectsAll(i) {
    return this.thresholdAt(i) <= 0;
  }

  /** 위험 등급: 상(검사 기준 이상) · 중(기준의 절반 이상) · 하. */
  risk(part, shot) {
    const t = this.thresholdAt(shot.i);
    const score = this.score(part);
    if (score >= t) return "high";
    return score >= t / 2 ? "medium" : "low";
  }

  inspects(part, shot) {
    return shot.tight || this.score(part) >= this.thresholdAt(shot.i);
  }

  /** 0..upto shot의 누적 결과. */
  summarize(shots, upto) {
    let parts = 0;
    let defects = 0;
    let inspected = 0;
    let found = 0;
    for (let i = 0; i <= upto && i < shots.length; i += 1) {
      const shot = shots[i];
      for (const part of shot.parts) {
        const inspect = this.inspects(part, shot);
        parts += 1;
        defects += part.y;
        inspected += inspect ? 1 : 0;
        found += inspect ? part.y : 0;
      }
    }
    const missed = defects - found;
    return {
      parts,
      defects,
      inspected,
      found,
      missed,
      inspectRate: parts ? inspected / parts : null,
      capture: defects ? found / defects : null,
      costPerPart: parts ? (inspected + this.ratio * missed) / parts : null,
      noInspectionCost: parts ? (this.ratio * defects) / parts : null,
    };
  }

  /** step shot마다 누적 포착률·제품당 비용 (차트용). */
  series(shots, upto, step = 10) {
    const out = [];
    let parts = 0;
    let defects = 0;
    let inspected = 0;
    let found = 0;
    for (let i = 0; i <= upto && i < shots.length; i += 1) {
      const shot = shots[i];
      for (const part of shot.parts) {
        const inspect = this.inspects(part, shot);
        parts += 1;
        defects += part.y;
        inspected += inspect ? 1 : 0;
        found += inspect ? part.y : 0;
      }
      if ((i + 1) % step === 0 || i === upto) {
        out.push({
          i,
          capture: defects ? found / defects : null,
          costPerPart: (inspected + this.ratio * (defects - found)) / parts,
          inspectRate: inspected / parts,
        });
      }
    }
    return out;
  }
}
