// 한/영 문구 테스트: npm test. 재생 데이터(results/dashboard)의 모든 한국어 문구가 영어로 옮겨지는지 확인한다.
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

import { Localizer } from "./i18n.js";

const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..", "results", "dashboard");
const HANGUL = /[가-힣]/;
const read = (path) => JSON.parse(gunzipSync(readFileSync(path)).toString("utf8"));

/** 객체 안의 한국어 문자열 전부 (재생 shot 값은 숫자라 건너뛴다). */
function koreanStrings(node, out = new Set()) {
  if (typeof node === "string") {
    if (HANGUL.test(node)) out.add(node);
  } else if (Array.isArray(node)) {
    node.forEach((v) => koreanStrings(v, out));
  } else if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) if (key !== "shots") koreanStrings(value, out);
  }
  return out;
}

test("UI keys exist in both languages", () => {
  const ko = new Localizer("ko");
  const en = new Localizer("en");
  const missing = Object.keys(ko.dict).filter((k) => !(k in en.dict));
  assert.deepEqual(missing, []);
  assert.deepEqual(Object.keys(en.dict).filter((k) => !(k in ko.dict)), []);
  assert.equal(en.t("band.left", { n: 4 }), "4 shots left");
  assert.equal(ko.t("band.left", { n: 4 }), "남은 4 shot");
});

test("Korean screens keep server text as is", () => {
  const ko = new Localizer("ko");
  assert.equal(ko.text("비스킷 두께 급변"), "비스킷 두께 급변");
  assert.equal(ko.variable("Casting_Pressure"), "주조 압력");
});

test("server phrases translate by rule", () => {
  const en = new Localizer("en");
  assert.equal(en.text("비스킷 두께 급변"), "Biscuit thickness sudden change");
  assert.equal(en.text("3단 사출 속도 관리 범위(안) 밖 운전 지속"), "Velocity 3 outside the draft range");
  assert.equal(en.text("최근 20 shot 중 95%가 범위 ≥ 12 밖"), "95% of the last 20 shots outside ≥ 12");
  assert.equal(en.text("값 1037.0 (직전 50 shot 중앙값에서 3.5σ 넘게 벗어남)"), "Value 1037.0 (more than 3.5σ from the median of the previous 50 shots)");
  assert.equal(en.text("유형 2 · 구간 5부터 · 관리도 경보 시 재학습"), "Type 2 · from run 5 · retrain on control-chart alarm");
  assert.equal(en.text("스프레이 1 시간"), "Spray 1 time");
  assert.equal(en.text("위험도 상 제품 3건"), "3 high-risk parts");
});

test("every Korean string in the replay data has an English version", () => {
  const en = new Localizer("en");
  const strings = new Set();
  koreanStrings(read(join(DATA, "meta.json.gz")), strings);
  koreanStrings(read(join(DATA, "summary.json.gz")), strings);
  for (const file of readdirSync(join(DATA, "scenarios"))) koreanStrings(read(join(DATA, "scenarios", file)), strings);
  assert.ok(strings.size > 100, `문구 ${strings.size}개`);
  const untranslated = [...strings].filter((s) => HANGUL.test(en.text(s)));
  assert.deepEqual(untranslated, []);
});
