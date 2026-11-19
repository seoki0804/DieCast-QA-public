// 화면과 분리된 계산 로직의 단위 테스트: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { AlarmCenter } from "./alarms.js";
import { groupContributions, predictedType } from "./explain.js";
import { costMinThreshold, InspectionLedger } from "./inspection.js";
import { pChart, pChartUcl, recentDefectRate, recentWindow } from "./metrics.js";

const part = (y, p, rule = 0) => ({ y, p, rule, tp: [0.1, 0.6, 0.1, 0.1, 0.1] });
const shot = (ys, ps, tight = false, i = 0) => ({ parts: ys.map((y, k) => part(y, ps[k])), tight, model: 0, shot: 1, i });

test("recentDefectRate counts parts in the last window shots", () => {
  const shots = [shot([1, 1], [0, 0]), shot([0, 0], [0, 0]), shot([1, 0], [0, 0])];
  assert.equal(recentDefectRate(shots, 2, 2), 0.25);
  assert.equal(recentDefectRate(shots, 0, 50), 1);
});

test("recentWindow reports the sample size so early replay is not over-read", () => {
  const shots = [shot([1, 0], [0, 0]), shot([0, 0], [0, 0])];
  assert.deepEqual(recentWindow(shots, 1, 50), { rate: 0.25, shots: 2, parts: 4 });
  // 표본이 작을수록 관리한계가 넓다: 제품 100개 기준(9.6%)보다 제품 4개 기준이 훨씬 높다
  assert.ok(Math.abs(pChartUcl(0.039, 100) - 0.0971) < 1e-3);
  assert.ok(pChartUcl(0.039, 4) > 0.3);
});

test("pChart uses only full subgroups and flags points above UCL", () => {
  const shots = Array.from({ length: 120 }, (_, i) => shot(i < 50 ? [0, 0] : [1, 1], [0, 0]));
  const { points } = pChart(shots, 119, { p_chart: { center: 0.1, subgroup_shots: 50 } });
  assert.equal(points.length, 2);
  assert.equal(points[0].p, 0);
  assert.ok(points[1].above);
});

test("costMinThreshold matches brute force and prefers fewer inspections on ties", () => {
  const scores = [0.1, 0.1, 0.3, 0.5, 0.5, 0.9];
  const labels = [0, 1, 0, 1, 0, 1];
  for (const ratio of [1, 3, 10]) {
    const cost = (t) => scores.filter((s) => s >= t).length + ratio * labels.filter((y, k) => y && scores[k] < t).length;
    const t = costMinThreshold(scores, labels, ratio);
    const best = Math.min(...[...new Set(scores), Infinity].map(cost));
    assert.equal(cost(t), best);
  }
  assert.equal(costMinThreshold([0.2, 0.4], [0, 0], 10), Infinity); // 불량이 없으면 검사 안 함
});

test("InspectionLedger: warm-up uses 1/ratio, later lots use past cost-min threshold, tightened shots inspect all", () => {
  const shots = Array.from({ length: 6 }, (_, i) => ({ ...shot([1, 0], [0.6, 0.05], i === 5), i }));
  const ledger = new InspectionLedger({ ratio: 10, shots, lot: 2, minParts: 4, minDefects: 1 });
  assert.equal(ledger.thresholdAt(0), 0.1); // 과거 부족 → 1/비용 비율
  assert.equal(ledger.thresholdAt(2), 0.6); // 과거에서 불량(0.6)만 고르는 기준
  const s = ledger.summarize(shots, 5);
  assert.equal(s.parts, 12);
  assert.equal(s.found, 6);
  assert.equal(s.inspected, 7); // 불량 6개 + 강화 구간의 정상 1개
  assert.equal(s.costPerPart, 7 / 12);
  assert.equal(ledger.risk(shots[3].parts[1], shots[3]), "low");
  assert.equal(ledger.risk(shots[3].parts[0], shots[3]), "high");
});

test("AlarmCenter tracks release and groups warnings", () => {
  const alarms = [
    { id: "a", level: "critical", level_rank: 0, at: 2, release_at: 5 },
    { id: "b", level: "log", level_rank: 3, at: 3, release_at: null },
  ];
  const center = new AlarmCenter(alarms, { warningWindow: 2 });
  assert.equal(center.history(1).length, 0);
  assert.equal(center.active(4).length, 1);
  assert.equal(center.status(alarms[0], 5), "resolved");
  assert.equal(center.countByLevel(3).log, 1);
  const shots = [shot([0, 0], [0.5, 0], false, 0), shot([0, 0], [0.5, 0.5], false, 1), shot([0, 0], [0, 0], false, 2)];
  const ledger = new InspectionLedger({ ratio: 10, shots });
  const warnings = center.warnings(shots, 2, ledger);
  assert.equal(warnings.length, 1);
  assert.equal(warnings[0].parts.length, 3);
});

test("no per-part warnings while every part is inspected anyway", () => {
  const shots = Array.from({ length: 4 }, (_, i) => ({ ...shot([1, 1], [0.5, 0.5], i === 0), i }));
  const ledger = new InspectionLedger({ ratio: 10, shots, lot: 2, minParts: 2, minDefects: 1 });
  assert.ok(ledger.inspectsAll(2)); // 과거 불량률 100% → 기준 0
  assert.equal(new AlarmCenter([]).warnings(shots, 3, ledger).length, 1); // shot 1만 (0은 강화, 2·3은 전수 모드)
});

test("groupContributions splits controllable and context variables", () => {
  const variables = { Air_Pressure: { label: "공기압", group: "controllable" }, Cavity: { label: "캐비티", group: "context" } };
  const groups = groupContributions([["Cavity", 1, 0.03], ["Air_Pressure", 5.7, -0.04]], variables);
  assert.equal(groups.controllable[0].label, "공기압");
  assert.equal(groups.context[0].shap, 0.03);
  const type = predictedType(part(0, 0), [{ label: "미성형" }, { label: "박리" }]);
  assert.equal(type.label, "박리");
});
