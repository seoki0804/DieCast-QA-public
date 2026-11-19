// 보고서용 대시보드 화면 캡처 → docs/report/images/*.png
// 준비: API(uv run uvicorn app.api.main:app --port 8000)와 화면(npm run dev 또는 npm run build && npm start)을 켠다.
// 실행: npm run shots [-- 이름 ...]   (이름을 주면 그 화면만. CHROME_PATH, WEB_URL 환경 변수로 바꿀 수 있다)
//
// 인쇄 폭(약 15 cm)에서도 글자가 읽히도록 화면 전체가 아니라 폭 1440(두 단 배치가 유지되는 가장 좁은 폭)의
// 위쪽만 2배 해상도로 찍는다. 운영 현황은 공정 변수 칸까지 보이게 더 길게 찍는다.
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "docs", "report", "images");
const BASE = process.env.WEB_URL ?? "http://localhost:3000";
const CHROME = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";

const SHOTS = [
  // 경고가 진행 중인 운영 현황: 상태 띠, 숫자 줄, p-chart·I-MR, 분포와 현재 위치, 알람, 공정 변수 칸
  { name: "dashboard_overview", path: "/?scenario=t1_r2_none&at=820", height: 1340 },
  // 같은 화면의 어두운 테마: 보고서용(공정 변수 칸까지)과 발표용(16:10 첫 화면)
  { name: "dashboard_overview_dark", path: "/?scenario=t1_r2_none&at=820&theme=dark", height: 1340 },
  { name: "dashboard_overview_dark_wide", path: "/?scenario=t1_r2_none&at=820&theme=dark", height: 900 },
  // 알람 센터: 진행 중 경고(목록 맨 위 불량률 CUSUM 경보)를 골라 조치 체크리스트와 원인 진단을 연다
  { name: "dashboard_alarms", path: "/alarms?scenario=t2_r5_alarm&at=400", select: 'tr:has-text("불량률 CUSUM 경보")', height: 1240 },
  { name: "dashboard_alarms_dark_wide", path: "/alarms?scenario=t2_r5_alarm&at=400&theme=dark", select: 'tr:has-text("불량률 CUSUM 경보")', height: 900 },
  // 제품·검사: 위험도 '상' 제품을 골라 판정 근거를 연다
  // (위험도가 최근 불량률 기준이라 at=700 근처에는 '상' 제품이 없다. 630~649 shot에 있다)
  { name: "dashboard_products", path: "/products?scenario=t1_r2_none&at=648", select: "tr.row-hl" },
];

const only = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
try {
  for (const shot of SHOTS.filter((s) => !only.length || only.includes(s.name))) {
    const page = await browser.newPage({ viewport: { width: 1440, height: shot.height ?? 860 }, deviceScaleFactor: 2 });
    // 보고서는 한국어 화면으로 찍는다 (브라우저에 저장된 언어 선택과 관계없이)
    await page.goto(`${BASE}${shot.path}&lang=ko`);
    await page.waitForSelector(".live", { timeout: 60000 });
    // 개발 서버의 Next.js 표시(N 버튼)는 화면 일부가 아니므로 숨긴다
    await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
    if (shot.select) await page.locator(shot.select).first().click();
    await page.waitForTimeout(800); // 차트 그리기
    await page.screenshot({ path: join(OUT, `${shot.name}.png`) });
    await page.close();
    console.log(`${shot.name}.png`);
  }
} finally {
  await browser.close();
}
