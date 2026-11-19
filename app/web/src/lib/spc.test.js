// SPC 계산 단위 테스트: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { clock, cumulativeSum, D2, histogram, imr, locate, mean, normalPdf, stdev } from "./spc.js";

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} ≠ ${b}`);

test("mean and sample stdev", () => {
  close(mean([1, 2, 3, 4]), 2.5);
  close(stdev([2, 4, 4, 4, 5, 5, 7, 9]), Math.sqrt(32 / 7));
  assert.equal(stdev([5]), 0);
});

test("histogram keeps one bar per value for coarsely recorded variables and conserves counts", () => {
  const coarse = [10, 10, 11, 12, 12, 12, 14];
  const h = histogram(coarse);
  assert.equal(h.step, 1);
  assert.deepEqual(h.bins.map((b) => [b.center, b.count]), [[10, 2], [11, 1], [12, 3], [14, 1]]);
  const fine = Array.from({ length: 200 }, (_, k) => Math.sin(k) * 10 + k / 50);
  const g = histogram(fine);
  assert.ok(g.bins.length >= 8 && g.bins.length <= 30);
  assert.equal(g.bins.reduce((s, b) => s + b.count, 0), 200);
});

test("normal curve scaled by n × step has about the same area as the histogram", () => {
  const values = Array.from({ length: 400 }, (_, k) => 50 + 5 * Math.sin(k * 1.7) + 3 * Math.cos(k * 0.31));
  const { step, bins } = histogram(values);
  const m = mean(values);
  const s = stdev(values);
  const curveArea = bins.reduce((sum, b) => sum + normalPdf(b.center, m, s) * values.length * step, 0);
  assert.ok(Math.abs(curveArea - values.length) / values.length < 0.1, `${curveArea}`);
});

test("imr limits come from the average moving range and flag rule 1 and rule 2", () => {
  const base = [10, 11, 10, 11, 10, 11, 10, 11, 10, 11];
  const r = imr(base);
  close(r.center, 10.5);
  close(r.mrBar, 1);
  close(r.sigma, 1 / D2);
  close(r.ucl, 10.5 + 3 / D2);
  assert.deepEqual(r.beyond, []);
  assert.deepEqual(imr([...base, 20]).beyond, [10]);
  // 중심선 한쪽에 9개 연속이면 9번째 점부터 규칙 2 (아래쪽 0 열 개, 위쪽 1 열 개)
  const run = imr([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]);
  assert.deepEqual(run.run, [8, 9, 18, 19]);
});

test("locate reports z against the history and the share outside a one-sided range", () => {
  const history = [10, 12, 14, 16, 18];
  const p = locate(history, 20, { low: 13, high: null });
  close(p.mean, 14);
  close(p.z, (20 - 14) / stdev(history));
  close(p.outShare, 0.4);
  assert.equal(p.currentOut, false);
  assert.equal(locate(history, 12, { low: 13 }).currentOut, true);
  assert.equal(locate([5, 5, 5], 7).z, 0);
});

test("replay clock adds cycle times", () => {
  assert.deepEqual(cumulativeSum([20.5, 21, null, 20]), [20.5, 41.5, 41.5, 61.5]);
  assert.equal(clock(17231.4), "04:47:11");
  assert.equal(clock(0), "00:00:00");
});
