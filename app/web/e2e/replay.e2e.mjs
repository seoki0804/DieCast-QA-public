// 재생 시뮬레이션 종단 테스트: 실제 Chrome으로 화면을 조작하고, 표시된 값을 같은 데이터로 따로
// 계산한 값과 비교한다.
//
// 준비: API(uv run uvicorn app.api.main:app --port 8000)와 화면(npm run build && npm start)을 켠다.
// 실행: npm run e2e   (CHROME_PATH, WEB_URL 환경 변수로 바꿀 수 있다)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

import { AlarmCenter } from "../src/lib/alarms.js";
import { InspectionLedger } from "../src/lib/inspection.js";

const BASE = process.env.WEB_URL ?? "http://127.0.0.1:3000";
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PAGES = ["/", "/products", "/alarms", "/summary", "/settings"];
const EVAL_CSV = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "results", "dashboard", "replay_eval.csv");

let browser;
const cache = new Map();

async function scenario(id) {
  if (!cache.has(id)) {
    const res = await fetch(`${BASE}/api/scenarios/${id}/shots?offset=0&limit=2000`);
    const alarms = await (await fetch(`${BASE}/api/scenarios/${id}/alarms`)).json();
    cache.set(id, { shots: (await res.json()).shots, alarms });
  }
  return cache.get(id);
}

/** 콘솔 오류·페이지 오류·실패한 요청을 모은다. */
async function openPage(path) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.errors = [];
  page.on("console", (m) => m.type() === "error" && !m.text().startsWith("Failed to load resource") && page.errors.push(m.text()));
  page.on("pageerror", (e) => page.errors.push(e.message));
  page.on("requestfailed", (r) => page.errors.push(`요청 실패 ${r.url()}`));
  page.on("response", (r) => r.status() >= 400 && page.errors.push(`${r.status()} ${r.url()}`));
  await page.goto(`${BASE}${path}`);
  await page.waitForSelector(".live", { timeout: 20000 });
  return page;
}

/** 상단 바 '… · 381/1,364'에서 재생 위치(0부터)와 전체 shot 수. */
async function position(page) {
  const text = await page.locator(".live").innerText();
  const [, done, total] = text.match(/([\d,]+)\/([\d,]+)/);
  return { index: Number(done.replace(/,/g, "")) - 1, total: Number(total.replace(/,/g, "")), playing: text.startsWith("재생 중") };
}

const fmt2 = (v) => new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);

before(async () => {
  // --expose-gc: 메모리 검사에서 정리(GC) 뒤 남은 양만 잰다
  browser = await chromium.launch({ executablePath: CHROME, headless: true, args: ["--js-flags=--expose-gc"] });
});

after(async () => {
  await browser?.close();
});

describe("재생", () => {
  test("선택한 속도로 진행하고 끝에서 멈춘다", async () => {
    const page = await openPage("/?scenario=t2_r7_none&at=0");
    await page.locator('.replaybar .seg button:text-is("10")').click();
    await page.keyboard.press("Space");
    const start = await position(page);
    const t0 = Date.now();
    await page.waitForTimeout(4000);
    const now = await position(page);
    const rate = (now.index - start.index) / ((Date.now() - t0) / 1000);
    assert.ok(now.playing, "재생 중이어야 한다");
    assert.ok(rate > 7 && rate < 11.5, `초당 10 shot 근처여야 한다 (${rate.toFixed(1)})`);
    await page.keyboard.press("Space");
    assert.equal((await position(page)).playing, false);

    await page.goto(`${BASE}/?scenario=t2_r7_none&at=625`);
    await page.waitForSelector(".live");
    await page.locator('.replaybar .seg button:text-is("10")').click();
    await page.keyboard.press("Space");
    await page.waitForTimeout(2500);
    const end = await position(page);
    assert.equal(end.index, end.total - 1, "마지막 shot에서 멈춰야 한다");
    assert.equal(end.playing, false);
    assert.deepEqual(page.errors, []);
    await page.close();
  });

  test("키보드로 이동하고, 시나리오를 바꾸면 처음부터 다시 연다", async () => {
    const page = await openPage("/?scenario=t1_r2_none&at=100");
    await page.locator(".page-title").click();
    await page.keyboard.press("ArrowRight");
    assert.equal((await position(page)).index, 101);
    await page.keyboard.press("Shift+ArrowRight");
    assert.equal((await position(page)).index, 151);
    await page.keyboard.press("ArrowLeft");
    assert.equal((await position(page)).index, 150);
    await page.locator(".scenario-picker select").selectOption("t2_r7_every_50");
    await page.waitForFunction(() => document.querySelector(".live")?.textContent.includes("/635"));
    assert.equal((await position(page)).index, 0);
    assert.deepEqual(page.errors, []);
    await page.close();
  });
});

describe("알람", () => {
  test("경고가 울리면 배너 → 확인 → 조치 보기 → 체크리스트, 화면을 옮겨도 재생 위치 유지", async () => {
    const { alarms } = await scenario("t2_r5_alarm");
    const first = alarms.find((a) => a.level === "critical");
    const page = await openPage(`/?scenario=t2_r5_alarm&at=${first.at - 2}`);
    assert.equal(await page.locator(".banner").count(), 0, "경보 전에는 배너가 없어야 한다");
    await page.locator(".page-title").click();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await page.waitForSelector(".banner");
    assert.match(await page.locator(".banner").innerText(), /불량률 CUSUM 경보/);
    await page.locator(".banner button:text-is('확인')").click();
    await page.waitForSelector(".banner-ack");
    await page.locator(".banner a:text-is('조치 보기')").click();
    await page.waitForURL(/\/alarms\?id=/);
    await page.waitForSelector(".action-list input");
    assert.equal((await position(page)).index, first.at, "화면을 옮겨도 재생 위치가 같아야 한다");
    const box = page.locator(".action-list input").first();
    await box.check();
    assert.ok(await box.isChecked());
    assert.match(await page.locator(".card-title").filter({ hasText: "불량률 CUSUM 경보" }).first().innerText(), /경보/);
    assert.deepEqual(page.errors, []);
    await page.close();
  });

  test("위험도 상 제품이 나오면 재생 중 주의 토스트를 띄운다", async () => {
    const { shots, alarms } = await scenario("t1_r2_none");
    const ledger = new InspectionLedger({ ratio: 10, shots });
    const warnings = new AlarmCenter(alarms).warnings(shots, shots.length - 1, ledger).reverse();
    const target = warnings.find((w) => w.at > 20);
    const page = await openPage(`/?scenario=t1_r2_none&at=${target.at - 3}`);
    await page.locator('.replaybar .seg button:text-is("5")').click();
    await page.keyboard.press("Space");
    await page.waitForSelector(".toast", { timeout: 8000 });
    assert.match(await page.locator(".toast").innerText(), /위험도 상 제품/);
    await page.keyboard.press("Space");
    assert.deepEqual(page.errors, []);
    await page.close();
  });
});

describe("표시 값", () => {
  test("검사 기준·비용이 비용 비율·점수 변경에 맞춰 바뀌고 따로 계산한 값과 같다", async () => {
    const { shots } = await scenario("t1_r2_none");
    const at = 700;
    const page = await openPage(`/products?scenario=t1_r2_none&at=${at}`);
    for (const [ratio, scoreKey, label] of [[10, "p", "모델"], [20, "p", "모델"], [5, "rule", "규칙"]]) {
      await page.locator(`.seg[aria-label="비용 비율"] button:text-is("${ratio}:1")`).click();
      await page.locator(`.seg[aria-label="위험 점수"] button:text-is("${label}")`).click();
      const s = new InspectionLedger({ ratio, scoreKey, shots }).summarize(shots, at);
      const cost = await page.locator(".statstrip-inline .stat").nth(3).locator(".stat-value").innerText();
      assert.ok(cost.startsWith(fmt2(s.costPerPart)), `${ratio}:1 ${scoreKey}: 화면 ${cost} vs 계산 ${fmt2(s.costPerPart)}`);
    }
    assert.deepEqual(page.errors, []);
    await page.close();
  });

  test("화면의 검사 계산이 Python 재생 평가(replay_eval.csv)와 같다", async () => {
    // 9개 시나리오 × 점수 2개(모델·규칙) × 비용 비율 3개 = 54건
    const lines = readFileSync(EVAL_CSV, "utf8").trim().split(/\r?\n/);
    const header = lines[0].split(",");
    const col = (name) => header.indexOf(name);
    let checked = 0;
    for (const line of lines.slice(1)) {
      const row = line.split(",");
      const { shots } = await scenario(row[col("scenario")]);
      const ratio = Number(row[col("ratio")]);
      const scoreKey = row[col("score")];
      const s = new InspectionLedger({ ratio, scoreKey, shots }).summarize(shots, shots.length - 1);
      const label = `${row[col("scenario")]} ${scoreKey} ${ratio}:1`;
      assert.equal(s.inspected, Number(row[col("inspected")]), `${label} 검사 수`);
      assert.equal(s.found, Number(row[col("found")]), `${label} 찾은 불량`);
      assert.ok(Math.abs(s.costPerPart - Number(row[col("cost_per_part")])) < 1e-5, `${label} 비용`);
      checked += 1;
    }
    assert.equal(checked, 54);
  });

  test("재생 끝의 제품당 비용(숫자 줄)이 따로 계산한 값과 같다", async () => {
    const { shots } = await scenario("t2_r7_none");
    const last = shots.length - 1;
    const page = await openPage(`/?scenario=t2_r7_none&at=${last}`);
    const s = new InspectionLedger({ ratio: 10, shots }).summarize(shots, last);
    const kpi = page.locator(".statstrip-6 .stat").filter({ hasText: "제품당 비용" }).locator(".stat-value");
    assert.equal(await kpi.innerText(), fmt2(s.costPerPart));
    assert.deepEqual(page.errors, []);
    await page.close();
  });

  test("테마 전환이 새로고침 뒤에도 유지된다", async () => {
    const page = await openPage("/settings");
    await page.locator('.seg[aria-label="테마"] button:text-is("어두운 테마")').click();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark");
    await page.reload();
    await page.waitForSelector(".live");
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "dark");
    await page.locator('.seg[aria-label="테마"] button:text-is("밝은 테마")').click();
    await page.close();
  });
});

describe("화면 v2", () => {
  test("영어로 바꾸면 화면 문구가 바뀌고 새로고침 뒤에도 유지된다", async () => {
    const page = await openPage("/?scenario=t2_r5_alarm&at=400");
    await page.locator('.topbar .seg button:text-is("EN")').click();
    await page.waitForFunction(() => document.querySelector(".page-title")?.textContent === "Overview");
    assert.equal(await page.evaluate(() => document.documentElement.lang), "en");
    assert.match(await page.locator(".banner").innerText(), /Defect-rate CUSUM alarm/);
    await page.reload();
    await page.waitForFunction(() => document.querySelector(".page-title")?.textContent === "Overview");
    // 알람 센터의 서버 문구(제목·조치)도 영어로 옮겨져 한글이 남지 않는다
    await page.goto(`${BASE}/alarms?scenario=t2_r5_alarm&at=400`);
    await page.waitForSelector(".action-list input");
    const detail = await page.locator(".grid-main > .card").nth(1).innerText();
    assert.doesNotMatch(detail, /[가-힣]/, detail.slice(0, 200));
    await page.locator('.topbar .seg button:text-is("한국어")').click();
    await page.waitForFunction(() => document.querySelector(".page-title")?.textContent === "알람 센터");
    assert.deepEqual(page.errors, []);
    await page.close();
  });

  test("? 도움말은 초점을 받으면 열리고 Esc로 닫힌다", async () => {
    const page = await openPage("/?scenario=t1_r2_none&at=820");
    const help = page.locator(".card").filter({ hasText: "불량률 관리도" }).locator(".help-btn").first();
    await help.focus();
    await page.waitForSelector(".help-tip");
    assert.match(await page.locator(".help-tip").innerText(), /50 shot/);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator(".help-tip").count(), 0);
    assert.deepEqual(page.errors, []);
    await page.close();
  });

  test("공정 변수 칸을 누르면 관리도·분포가 그 변수로 바뀐다", async () => {
    const page = await openPage("/?scenario=t1_r2_none&at=820");
    await page.locator(".tile").filter({ hasText: "비스킷 두께" }).click();
    await page.waitForFunction(() => [...document.querySelectorAll(".card-title")].some((h) => h.textContent === "비스킷 두께 관리도"));
    assert.ok(await page.locator(".card-title", { hasText: "비스킷 두께 분포와 현재 위치" }).count());
    assert.equal(await page.locator(".tile[aria-pressed=true]").innerText().then((t) => t.includes("비스킷 두께")), true);
    assert.deepEqual(page.errors, []);
    await page.close();
  });
});

describe("전체 시나리오", () => {
  test("모든 시나리오 × 화면을 재생 중간 지점에서 오류 없이 연다", async () => {
    const meta = await (await fetch(`${BASE}/api/meta`)).json();
    for (const { id } of meta.scenarios) {
      const { shots } = await scenario(id);
      for (const path of PAGES) {
        const page = await openPage(`${path}?scenario=${id}&at=${Math.floor(shots.length / 2)}`);
        await page.waitForSelector(".page-title");
        assert.deepEqual(page.errors, [], `${id} ${path}`);
        await page.close();
      }
    }
  });
});

// 9개 시나리오를 처음부터 끝까지 초당 10 shot으로 재생한다(약 10분). E2E_FULL=1 npm run e2e
describe("전체 재생 (E2E_FULL=1)", { skip: !process.env.E2E_FULL }, () => {
  test("모든 시나리오가 오류 없이 끝까지 재생되고, 경고 배너가 경보 수만큼 뜨며, 메모리가 계속 늘지 않는다", { timeout: 40 * 60 * 1000 }, async () => {
    const meta = await (await fetch(`${BASE}/api/meta`)).json();
    const ids = meta.scenarios.map((s) => s.id);
    const results = [];
    for (let k = 0; k < ids.length; k += 3) {
      results.push(...(await Promise.all(ids.slice(k, k + 3).map(playThrough))));
    }
    for (const r of results) console.log(JSON.stringify(r));
    for (const r of results) {
      assert.deepEqual(r.errors, [], r.id);
      assert.equal(r.end, r.total - 1, `${r.id} 끝까지 재생`);
      assert.equal(r.bannersSeen, r.criticalAlarms, `${r.id} 경고 배너 수`);
      // 차트에 쌓이는 데이터만큼만 늘어야 한다 (정리 뒤 1,500 shot 재생에 약 10MB)
      assert.ok(r.heapEndMb < r.heapStartMb + 30, `${r.id} 메모리 ${r.heapStartMb} → ${r.heapEndMb} MB`);
    }
  });
});

/** 한 시나리오를 끝까지 재생하며 새로 뜬 경고 배너 수, 걸린 시간, JS 메모리를 잰다. */
async function playThrough(id) {
  const { alarms, shots } = await scenario(id);
  const page = await openPage(`/?scenario=${id}&at=0`);
  const heap = () =>
    page.evaluate(async () => {
      window.gc?.();
      await new Promise((r) => setTimeout(r, 300));
      window.gc?.();
      return Math.round((performance.memory?.usedJSHeapSize ?? 0) / 1e6);
    });
  const heapStartMb = await heap();
  await page.locator('.replaybar .seg button:text-is("10")').click();
  await page.locator(".page-title").click();
  // 배너에 처음 뜬 경고 shot을 기록한다 (재생 중 화면에서 관찰)
  await page.evaluate(() => {
    window.__banners = new Set();
    new MutationObserver(() => {
      const text = document.querySelector(".banner .banner-msg")?.textContent;
      if (text) window.__banners.add(text.match(/shot ([\d,]+)/)?.[1]);
    }).observe(document.querySelector(".content"), { childList: true, subtree: true, characterData: true });
  });
  const t0 = Date.now();
  await page.keyboard.press("Space");
  await page.waitForFunction(() => document.querySelector(".live")?.textContent.startsWith("재생 중"));
  await page.waitForFunction(() => document.querySelector(".live")?.textContent.startsWith("정지"), null, { timeout: 30 * 60 * 1000, polling: 1000 });
  const seconds = (Date.now() - t0) / 1000;
  const end = (await position(page)).index;
  const bannersSeen = await page.evaluate(() => window.__banners.size);
  const heapEndMb = await heap();
  // 같은 shot에서 감지한 경고는 배너 하나로 보이므로 감지 shot 기준으로 센다
  const criticalAlarms = new Set(alarms.filter((a) => a.level === "critical").map((a) => shots[a.detected_at].shot)).size;
  const result = { id, total: shots.length, end, seconds: Math.round(seconds), rate: +(end / seconds).toFixed(1), bannersSeen, criticalAlarms, heapStartMb, heapEndMb, errors: page.errors };
  await page.close();
  return result;
}
