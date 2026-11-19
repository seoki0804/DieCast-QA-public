// DieCast-QA 최종 발표 자료(.pptx). 표·차트 숫자는 results/의 CSV에서 읽고, 그림은 분석 그림과 대시보드 캡처를 쓴다.
// 실행: cd report && npm run slides  → docs/presentation/DieCast-QA_최종발표.pptx
// 구성: 테마(색·글꼴) → 레이아웃 2종(어두운 표지, 본문) → 섹션별 슬라이드. 각 슬라이드에 발표자 노트를 단다.
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { num, pct, readCsv } from "./lib/doc.mjs";
import { applyTheme } from "./lib/pptx_theme.mjs";

// pptxgenjs의 ES 모듈 빌드는 Node에서 바로 불러지지 않으므로 CommonJS 빌드를 쓴다
const pptxgen = createRequire(import.meta.url)("pptxgenjs");
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const R = (...p) => join(ROOT, "results", ...p);
const FIG = (name) => join(ROOT, "results", "figures", `${name}.png`);
const SHOT = (name) => join(ROOT, "docs", "report", "images", `${name}.png`);
const OUT = join(ROOT, "docs", "presentation", "DieCast-QA_최종발표.pptx");

// ── 테마: 대시보드와 같은 파랑(데이터)과 쇳물 주황(강조), 경보용 빨강 ─────────────────────────
const THEME = {
  name: "DieCast-QA",
  headFontFace: "Malgun Gothic",
  bodyFontFace: "Malgun Gothic",
  eastAsianFont: "Malgun Gothic",
  colors: {
    dk1: "1B1E23", lt1: "FFFFFF", dk2: "4A5260", lt2: "F2F3F5",
    accent1: "256ABF", accent2: "E0732C", accent3: "9AA3B2", accent4: "D03B3B", accent5: "0C8A0C", accent6: "F2A900",
    hlink: "256ABF", folHlink: "6D4FA8",
  },
};
const HEX = THEME.colors; // 16진수만 받는 옵션(차트 그리드·한 계열 막대 색)용
const GRAY = "9AA3B2";
const LIGHT = "C9CED6";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 × 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "DieCast-QA 팀";
pres.title = "다이캐스팅 공정 데이터를 활용한 불량 예측 모델 개발과 품질관리 방안 — 최종 발표";
const C = pres.SchemeColor;
const W = 13.333;
const X0 = 0.6; // 왼쪽 여백
const CW = W - 2 * X0; // 본문 폭
const Y0 = 1.8; // 본문 시작
const YB = 6.8; // 본문 끝

// ── 레이아웃 ──────────────────────────────────────────────────────────────────────
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: 0.8, y: 1.3, w: 11.7, h: 0.5, fontSize: 16, bold: true, color: C.accent2, margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 1.9, w: 11.7, h: 2.0, fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "subtitle", type: "body", x: 0.8, y: 4.0, w: 11.7, h: 0.6, fontSize: 18, color: C.accent3, margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "eyebrow", type: "body", x: X0, y: 0.4, w: CW, h: 0.4, fontSize: 14, bold: true, color: C.accent2, margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.8, w: CW, h: 0.75, fontSize: 28, bold: true, color: C.text1, valign: "top", align: "left", margin: 0 }, text: "" } },
    { text: { text: "DieCast-QA · 다이캐스팅 불량 예측과 품질관리", options: { x: X0, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: 12.13, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.accent3, align: "right" },
});

// ── 그리기 도우미 ─────────────────────────────────────────────────────────────────
let section = "";
let objectId = 0;
const nameOf = (kind) => `${kind}-${++objectId}`;

function slide(eyebrow, title, notes) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(eyebrow, { placeholder: "eyebrow" });
  s.addText(title, { placeholder: "title" });
  s.addNotes(notes);
  return s;
}

/** 둥근 카드 바탕. tone: "plain"(연회색) | "hl"(주황 강조) | "dark" */
function card(s, x, y, w, h, tone = "plain") {
  const fill = tone === "hl" ? { color: C.accent2, transparency: 85 } : tone === "dark" ? { color: C.text1 } : { color: C.background2 };
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill, line: { type: "none" }, rectRadius: 0.1, objectName: nameOf("card") });
}

function text(s, value, x, y, w, h, opts = {}) {
  s.addText(value, { x, y, w, h, isTextBox: true, margin: 0, fontSize: 16, color: C.text1, valign: "top", objectName: nameOf("text"), ...opts });
}

/** 번호 원 (덱 전체의 반복 모티프) */
function badge(s, label, x, y, d = 0.55, color = C.accent1) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { type: "none" }, objectName: nameOf("badge") });
  text(s, label, x, y, d, d, { fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
}

/** 숫자 강조 카드: 큰 숫자 + 설명 */
function stat(s, value, label, x, y, w, h, { tone = "plain", size = 36, color = C.accent1 } = {}) {
  card(s, x, y, w, h, tone);
  text(s, value, x + 0.25, y + 0.2, w - 0.5, 0.8, { fontSize: size, bold: true, color, valign: "middle" });
  text(s, label, x + 0.25, y + 1.05, w - 0.5, h - 1.2, { fontSize: 14, color: C.text2 });
}

/** 제목 + 설명 카드 */
function note(s, title, body, x, y, w, h, tone = "plain") {
  card(s, x, y, w, h, tone);
  text(s, title, x + 0.25, y + 0.18, w - 0.5, 0.4, { fontSize: 17, bold: true });
  text(s, body, x + 0.25, y + 0.62, w - 0.5, h - 0.75, { fontSize: 15, color: C.text2 });
}

function bullets(s, items, x, y, w, h, fontSize = 16) {
  const runs = items.map((item, k) => ({ text: item, options: { bullet: { indent: 18 }, breakLine: k < items.length - 1, paraSpaceAfter: 10 } }));
  text(s, runs, x, y, w, h, { fontSize, color: C.text1 });
}

/** PNG 크기를 읽어 상자 안에 비율을 지켜 가운데 배치 */
function image(s, path, x, y, w, h, altText) {
  const buf = readFileSync(path);
  const ratio = buf.readUInt32BE(16) / buf.readUInt32BE(20);
  const [iw, ih] = ratio > w / h ? [w, w / ratio] : [h * ratio, h];
  s.addImage({ path, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih, altText, objectName: nameOf("image") });
}

/** 위첨자 2^(4−1) */
const doe = (before, after, opts = {}) => [
  { text: `${before}2`, options: opts },
  { text: "4−1", options: { ...opts, superscript: true } },
  { text: after, options: opts },
];

const CHART_TEXT = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt" };
const chartBase = () => ({
  ...CHART_TEXT,
  catAxisLabelColor: HEX.dk2, valAxisLabelColor: HEX.dk2, catAxisLabelFontSize: 13, valAxisLabelFontSize: 12,
  valGridLine: { color: "E3E5E8", size: 0.5 }, catGridLine: { style: "none" },
  showValue: true, dataLabelFormatCode: "0.000", dataLabelFontSize: 12, dataLabelColor: HEX.dk1,
  valAxisLabelFormatCode: "0.0",
});

function table(s, header, rows, x, y, w, colW, { highlight = () => false, fontSize = 14, rowH = 0.45 } = {}) {
  const head = header.map((h, k) => ({ text: h, options: { bold: true, color: C.background1, fill: { color: C.text1 }, align: k ? "center" : "left" } }));
  const body = rows.map((r, i) => r.map((v, k) => ({ text: String(v), options: { align: k ? "center" : "left", bold: highlight(i) && k === 0, fill: { color: highlight(i) ? "FBE3D5" : i % 2 ? "F7F8F9" : "FFFFFF" } } })));
  s.addTable([head, ...body], { x, y, w, colW, rowH, fontSize, color: HEX.dk1, valign: "middle", margin: [0.04, 0.12, 0.04, 0.12], border: { type: "solid", pt: 0.5, color: "D9DCE1" }, objectName: nameOf("table") });
}

// ── 데이터 ────────────────────────────────────────────────────────────────────────
const by = (rows, key) => Object.fromEntries(rows.map((r) => [key(r), r]));
const s1 = by(readCsv(R("stage1", "metrics_summary.csv")).filter((r) => r.experiment === "main"), (r) => `${r.design}:${r.model}`);
const s1p = by(readCsv(R("stage1", "metrics_pooled.csv")).filter((r) => r.design === "retrain_50"), (r) => r.model);
const e82 = by(readCsv(R("experiments", "e82_alarm_retrain_pooled.csv")).filter((r) => r.model === "et"), (r) => r.design);
const e88t = by(readCsv(R("experiments", "e88_temporal_time_order.csv")), (r) => r.model);
const e88r = by(readCsv(R("experiments", "e88_temporal_retrain.csv")), (r) => `${r.design}:${r.model}`);
const costBest = by(readCsv(R("cost", "cost_best.csv")), (r) => r.ratio);
const ranges = readCsv(R("interpret", "ranges_proposals.csv")).filter((r) => r.verdict === "candidate");
const STRATEGY = { none: "검사 안 함", model: "모델 선별", rule: "규칙 선별", switching: "검사 강도 전환" };

// ══ 1. 문제 정의와 데이터 ═════════════════════════════════════════════════════════
section = "문제 정의와 데이터";
pres.addSection({ title: section });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: section });
  s.addText("AI 기반 생산운영관리 · 팀 프로젝트 최종 발표", { placeholder: "eyebrow" });
  s.addText("다이캐스팅 공정 데이터를 활용한\n불량 예측 모델 개발과 품질관리 방안", { placeholder: "title" });
  s.addText("KAMP 주조 품질보증 AI 데이터셋 · 불량 예측, 공정 안정성, 검사 비용, 이상 대응, 재생 대시보드", { placeholder: "subtitle" });
  const team = [["김민송", "총괄·비용 분석"], ["박준", "데이터·탐색 분석"], ["안형석", "예측 모델"], ["신유민", "품질관리·모델 해석"], ["정화평", "대시보드·발표"]];
  team.forEach(([who, role], k) => {
    text(s, who, 0.8 + k * 2.4, 5.35, 2.2, 0.4, { fontSize: 18, bold: true, color: C.background1 });
    text(s, role, 0.8 + k * 2.4, 5.8, 2.2, 0.35, { fontSize: 14, color: C.accent3 });
  });
  text(s, "2026년 11월", 0.8, 6.6, 4, 0.35, { fontSize: 14, color: C.accent3 });
  s.addNotes("안녕하십니까. 다이캐스팅 공정 데이터로 제품 불량을 예측하고, 그 결과를 검사 운영과 공정 관리에 활용하는 방안을 발표하겠습니다. 데이터 정제부터 예측 모델, 관리도, 검사 비용, 개선 방안과 이상 대응, 그리고 이를 시연하는 재생 시뮬레이션 대시보드까지 순서대로 말씀드리겠습니다.");
}
{
  const s = slide("연구 질문", "예측 모델은 단순 규칙보다 불량을 더 잘 찾는가",
    "같은 데이터를 사용한 기존 분석은 대부분 shot을 무작위로 나누어 모델을 평가했습니다. 하지만 현장에서는 과거 데이터로 학습한 모델이 앞으로 생산될 제품을 예측해야 합니다. 그래서 시간 순서를 지킨 평가를 함께 수행했고, 비교 기준으로 직전 10 shot의 불량률만 보는 단순 규칙을 두었습니다. 연구 질문은 네 가지입니다. 모델이 이 규칙보다 나은지, 그렇지 않다면 원인이 무엇인지, 어떻게 보완할 수 있는지, 그리고 현장에서 어떻게 활용할 수 있는지입니다.");
  text(s, "기존 분석은 대부분 무작위 분할로 평가하였다. 실제 운영처럼 과거 데이터로 학습해 이후 기간을 예측해도 모델이 나은지 확인한다.", X0, Y0, CW, 0.8, { fontSize: 18, color: C.text2 });
  const qs = [
    ["모델이 더 나은가?", "세 가지 검증 방식으로 모델 7종과 규칙 3종을 비교"],
    ["왜 그런가?", "데이터 양의 문제인가, 시간에 따른 분포 변화인가"],
    ["어떻게 보완하나?", "합성 데이터, 재학습, 규칙 결합, 가중치, 시간 정보"],
    ["현장에서는?", "검사 방식과 비용, 관리 범위, 경보와 조치"],
  ];
  const w = (CW - 3 * 0.3) / 4;
  qs.forEach(([q, a], k) => {
    const x = X0 + k * (w + 0.3);
    card(s, x, 2.95, w, 3.6);
    badge(s, String(k + 1), x + 0.3, 3.25);
    text(s, q, x + 0.3, 4.05, w - 0.6, 0.5, { fontSize: 20, bold: true });
    text(s, a, x + 0.3, 4.7, w - 0.6, 1.6, { fontSize: 16, color: C.text2 });
  });
}
{
  const s = slide("데이터와 전처리", "원본 7,535행을 정제해 제품 9,234개를 분석했다",
    "KAMP 공식 배포 파일과 해시값으로 동일함을 확인한 원본을 사용했습니다. 같은 shot이 연속으로 두 번 기록된 행이 38.7%로 많아 제거했는데, 이를 그대로 두고 무작위로 나누면 같은 shot이 학습과 평가에 함께 들어가 ROC-AUC가 0.76에서 0.94로 과대평가됩니다. shot 번호가 다시 1부터 시작하는 지점을 기준으로 7개 생산 구간으로 나누었고, 캐비티 2개를 펼쳐 제품 9,234개, 불량률 12.4%를 분석 단위로 했습니다. 모델은 아래 세 가지 방식으로 검증했습니다. ①은 기존 분석과 같은 무작위 분할, ②는 과거로 학습해 다음 블록을 예측하는 시간 순서 평가, ③은 일정 shot마다 다시 학습하는 운영 방식입니다.");
  const w = (CW - 3 * 0.3) / 4;
  [
    ["2,918", "같은 shot이 두 번 기록된 행(38.7%) 제거. 두면 AUC 0.76 → 0.94로 과대평가"],
    ["7", "생산 구간. shot 번호 재시작 기준 (구간 1~3 제품 유형 1, 4~7 유형 2)"],
    ["9,234", "분석 단위 제품 = shot × 캐비티 2개. 불량 1,144개"],
    ["12.4%", "불량률. 5개 유형: 미성형·박리·기공·변형·기타"],
  ].forEach(([v, l], k) => stat(s, v, l, X0 + k * (w + 0.3), Y0, w, 2.45));
  const w3 = (CW - 2 * 0.3) / 3;
  [
    ["① 같은 기간", "shot 단위 무작위 분할. 기존 분석들과 같은 방식"],
    ["② 시간 순서", "제품 유형별 5개 블록. 앞 블록으로 학습해 다음 블록 평가"],
    ["③ 주기적 재학습", "N shot마다 그 이전 데이터로 다시 학습해 다음 N shot 예측"],
  ].forEach(([t, b], k) => note(s, t, b, X0 + k * (w3 + 0.3), 4.85, w3, 1.85, k === 1 ? "hl" : "plain"));
  text(s, "검증 방식", X0, 4.42, 3, 0.35, { fontSize: 14, bold: true, color: C.text2 });
}

// ══ 2. 탐색 분석과 공정 안정성 ═════════════════════════════════════════════════════
section = "탐색 분석과 공정 안정성";
pres.addSection({ title: section });
{
  const s = slide("탐색 분석", "불량률은 생산 구간마다 크게 달랐다",
    "불량률은 구간마다 0.6%에서 21.9%까지 차이가 컸습니다. 정상 shot과 불량 shot의 공정값을 전체로 비교하면 효과 크기가 최대 0.39였지만, 같은 생산 구간 안에서만 비교하면 0.11로 줄어듭니다. 즉 공정값 차이의 상당 부분은 불량률이 높던 시기와 낮던 시기의 설정 차이를 반영합니다. 캐비티1은 구간을 통제해도 불량 오즈가 2.48배 높았습니다. 이 시기 효과가 뒤에 나오는 모델 결과를 해석하는 출발점입니다.");
  bullets(s, [
    "구간별 불량률 0.6%(구간 3) ~ 21.9%(구간 5)",
    "정상·불량 shot의 공정값 효과 크기: 전체 0.39 → 같은 구간 안 0.11",
    "캐비티1 17.0% vs 캐비티2 7.8% (구간 통제 오즈비 2.48)",
  ], X0, Y0 + 0.1, 4.6, 3.0);
  note(s, "해석", "공정값 차이의 대부분은 불량이 많던 시기와 적던 시기의 설정 차이다", X0, 5.0, 4.6, 1.75, "hl");
  image(s, FIG("eda_defect_rate_by_run"), 5.5, Y0, W - X0 - 5.5, YB - Y0, "생산 구간·캐비티별 불량률 막대그래프. 구간 1과 5가 높고 구간 3·4가 낮으며 캐비티1이 대체로 높다");
}
{
  const s = slide("공정 안정성 (SPC)", "공정은 통계적 관리 상태가 아니었다",
    "50 shot, 즉 제품 100개를 부분군으로 한 p-chart에서 92개 부분군 중 37개가 관리한계를 벗어났습니다. 불량률이 높은 시기와 매우 낮은 시기가 번갈아 나타나기 때문입니다. 공정 변수의 Xbar 관리도는 이탈 비율 중앙값이 93%였는데, 구간마다 설정 수준이 다르고 구간 안에서도 값이 서서히 변해서 독립성 가정이 성립하지 않습니다. 공기압의 공정능력은 Pp 1.63, Ppk 1.55로 여유가 있었고, 군내 표준편차로 구한 Cp는 드리프트를 반영하지 못해 과대평가되므로 Pp로 판단했습니다. 그래서 공정 변수는 원인 진단에 쓰고, 경보와 재학습 신호는 불량률 CUSUM으로 정했습니다.");
  image(s, FIG("spc_p_chart"), X0, Y0, 7.0, YB - Y0, "제품 유형별 불량률 p-chart. 고불량 구간과 저불량 구간이 번갈아 관리한계를 벗어난다");
  bullets(s, [
    "p-chart 92개 부분군 중 37개가 관리한계 이탈",
    "공정 변수 Xbar 이탈 비율 중앙값 93%: 구간마다 수준이 다르고 서서히 변함 (자기상관 0.68)",
    "공기압 Pp 1.63 · Ppk 1.55",
  ], 7.9, Y0 + 0.1, W - X0 - 7.9, 3.1);
  note(s, "운영 결정", "공정 변수는 원인 진단에, 불량률 CUSUM은 경보·재학습 신호로 사용", 7.9, 5.0, W - X0 - 7.9, 1.75, "hl");
}

// ══ 3. 예측 모델과 원인 진단 ══════════════════════════════════════════════════════
section = "예측 모델과 원인 진단";
pres.addSection({ title: section });
{
  const s = slide("불량 여부 예측 (1단계)", "시간 순서 평가에서는 규칙이 모든 모델보다 높았다",
    "1단계 결과입니다. 모델 7종 중 주요 3종과 규칙을 보여 드립니다. 같은 기간 안에서 무작위로 나누면 XGBoost가 0.76으로 규칙 0.73보다 높습니다. 하지만 과거로 학습해 이후 기간을 평가하는 시간 순서 평가에서는 최근 10 shot 불량률 규칙이 0.68로, 가장 높은 Extra Trees 0.60을 포함한 모든 모델보다 높았습니다. 4개 평가 블록 하나하나에서도 같은 결과였고, 시간 순서를 지킨 교차검증으로 하이퍼파라미터를 조정해도 0.63이었습니다. 50 shot마다 다시 학습하면 모델과 규칙이 0.714로 같아집니다.");
  const models = [["rf", "Random Forest"], ["lgbm", "LightGBM"], ["et", "Extra Trees"], ["recent_rate", "규칙: 최근 10 shot"]];
  const labels = models.map(([, l]) => l);
  s.addChart(pres.charts.BAR, [
    { name: "① 같은 기간", labels, values: models.map(([m]) => s1[`same_term:${m}`].roc_auc_mean) },
    { name: "② 시간 순서", labels, values: models.map(([m]) => s1[`time_order:${m}`].roc_auc_mean) },
    { name: "③ 50 shot 재학습", labels, values: models.map(([m]) => s1p[m].roc_auc) },
  ], {
    x: X0, y: Y0, w: 8.2, h: YB - Y0, barDir: "col", barGrouping: "clustered", barGapWidthPct: 60,
    chartColors: [LIGHT, HEX.accent2, HEX.accent1], ...chartBase(), dataLabelFontSize: 11, dataLabelPosition: "outEnd",
    valAxisMinVal: 0.4, valAxisMaxVal: 0.8, valAxisMajorUnit: 0.1,
    showLegend: true, legendPos: "t", legendFontSize: 13, legendColor: HEX.dk1,
    showTitle: true, title: "ROC-AUC (0.5 = 무작위)", titleFontSize: 13, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    objectName: nameOf("chart"),
  });
  const x = 9.1;
  const w = W - X0 - x;
  note(s, "① 같은 기간: 모델 우세", `XGBoost ${num(s1["same_term:xgb"].roc_auc_mean)} vs 규칙 ${num(s1["same_term:recent_rate"].roc_auc_mean)}`, x, Y0, w, 1.45);
  note(s, "② 시간 순서: 규칙 우세", `규칙 ${num(s1["time_order:recent_rate"].roc_auc_mean)} vs 최고 모델 ${num(s1["time_order:et"].roc_auc_mean)}. 4개 평가 블록 모두 같은 결과`, x, Y0 + 1.7, w, 1.75, "hl");
  note(s, "③ 재학습: 같아짐", `Extra Trees ${num(s1p.et.roc_auc, 3)} = 규칙 ${num(s1p.recent_rate.roc_auc, 3)}`, x, Y0 + 3.7, w, 1.3);
}
{
  const s = slide("원인 진단", "평가 기간의 데이터는 학습 기간과 분포가 달랐다",
    "원인을 진단했습니다. 학습 기간과 평가 기간의 데이터를 구별하는 분류기를 만들면, 인접 구간끼리와 시간 순서 평가의 모든 fold에서 AUC가 1.00이었습니다. 공정 변수만 써도 0.94 이상입니다. 두 기간의 분포가 거의 완전히 구별될 만큼 다르다는 뜻입니다. 구간마다 SHAP 주요 변수를 따로 구하면 상위 5개 중 평균 2개만 겹쳐, 불량과 관련된 변수도 시기에 따라 달라졌습니다. 데이터 양의 문제인지 확인하려고 합성 데이터를 추가했더니, 같은 기간 평가에서는 효과가 없고 시간 순서 평가에서는 오히려 낮아졌습니다. 따라서 데이터 양보다 시간에 따른 분포 변화가 주된 원인으로 판단했습니다.");
  const w = (CW - 2 * 0.3) / 3;
  [
    ["1.00", "학습 기간과 평가 기간을 구별하는 분류기의 AUC (공정 변수만 0.94~1.00)"],
    ["2 / 5", "구간별 SHAP 상위 5개 변수 중 공통 변수 수 (평균)"],
    ["0.57 → 0.48", "CTGAN 합성 데이터 추가 시 ② ROC-AUC. SMOTE·Copula·잡음 추가도 개선 없음"],
  ].forEach(([v, l], k) => stat(s, v, l, X0 + k * (w + 0.3), Y0 + 0.1, w, 2.8, { size: 36 }));
  card(s, X0, 5.2, CW, 1.5, "dark");
  text(s, "데이터 양보다 생산 시기에 따른 분포 변화가 성능 저하의 주된 원인 → 최근 데이터를 반영하는 재학습으로 보완", X0 + 0.35, 5.2, CW - 0.7, 1.5, { fontSize: 20, bold: true, color: C.background1, valign: "middle" });
}
{
  const s = slide("보완 · 재학습 시점", "불량률 경보 때 재학습하면 횟수 40%를 줄여도 성능은 같았다",
    "보완책은 재학습입니다. 한 번 학습한 모델을 그대로 쓰면 ROC-AUC가 0.457로 무작위보다도 낮습니다. 자주 다시 학습할수록 높아져 50 shot마다면 0.714입니다. 관리도 경보를 재학습 신호로 쓰면, 불량률 CUSUM 경보 때 44번 재학습해 0.711로 고정 주기 73번과 비슷한 성능을 40% 적은 재학습으로 얻습니다. 공정 변수 CUSUM은 성능이 조금 높지만 약 10 shot마다 경보가 울려 경보로는 쓸 수 없습니다. 규칙과 모델의 결합이나 최근 데이터 가중치는 효과가 없거나 작았습니다.");
  const order = [["never", "재학습 없음"], ["fixed_200", "200 shot마다"], ["fixed_100", "100 shot마다"], ["fixed_50", "50 shot마다"], ["alarm_defect_ewma", "불량률 EWMA 경보"], ["alarm_defect_cusum", "불량률 CUSUM 경보"], ["alarm_process_cusum", "공정 변수 CUSUM 경보"]];
  const colors = { fixed_50: HEX.accent1, alarm_defect_cusum: HEX.accent2, alarm_process_cusum: LIGHT };
  s.addChart(pres.charts.BAR, [{ name: "ROC-AUC", labels: order.map(([k, l]) => `${l} · ${e82[k].retrains ?? 0}회`), values: order.map(([k]) => e82[k].roc_auc) }], {
    x: X0, y: Y0, w: 8.3, h: YB - Y0, barDir: "bar", barGapWidthPct: 45, catAxisOrientation: "maxMin",
    chartColors: order.map(([k]) => colors[k] ?? GRAY), ...chartBase(), dataLabelPosition: "outEnd",
    valAxisMinVal: 0.4, valAxisMaxVal: 0.8, valAxisMajorUnit: 0.1, valAxisHidden: true, showLegend: false,
    showTitle: true, title: "재학습 시점별 Extra Trees ROC-AUC · 재학습 횟수", titleFontSize: 13, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    objectName: nameOf("chart"),
  });
  const x = 9.2;
  const w = W - X0 - x;
  stat(s, "−40%", `불량률 CUSUM 경보 재학습 ${e82.alarm_defect_cusum.retrains}회로 ${num(e82.alarm_defect_cusum.roc_auc, 3)} (50 shot 고정 ${e82.fixed_50.retrains}회 ${num(e82.fixed_50.roc_auc, 3)})`, x, Y0, w, 2.1, { tone: "hl", color: C.accent2 });
  note(s, "효과가 작았던 방법", "합성 데이터, 규칙과 모델 점수 결합, 최근 데이터 가중치", x, Y0 + 2.35, w, 1.25);
  note(s, "공정 변수 CUSUM", "성능은 높지만 약 10 shot마다 경보 → 경보로 부적합", x, Y0 + 3.85, w, 1.15);
}
{
  const s = slide("보완 · 시간 정보 활용", "시간 정보를 입력에 넣어도 규칙을 넘지 못했다",
    "분포 변화를 학습에 직접 반영하는 방법도 비교했습니다. 생산 순서와 구간 번호를 입력에 넣거나, 구간 기준 편차로 바꾸거나, 구간마다 값이 고정된 변수를 빼거나, 최근 데이터와 비슷한 표본에 가중치를 주는 방법입니다. 시간 순서 평가에서 가장 높은 방법도 0.61로 규칙 0.68에 미치지 못했고, 개선 폭 0.01 정도는 fold 간 표준편차보다 작았습니다. 이 데이터에는 날짜와 시각이 없고, 시간 변화가 반복되는 주기가 아니라 구간마다 한 번씩 나타나는 수준 변화이기 때문에, 시간 변수를 입력해도 이후 기간으로 일반화되지 않습니다. 50 shot마다 재학습하면 모든 방법이 규칙과 비슷해집니다.");
  const TEMPORAL = [["et", "기준: 공정·센서 원값"], ["et_time", "+ 생산 순서·구간 번호"], ["et_history", "+ 흔들림·검사 이력"], ["et_relative", "구간 기준 편차만"], ["et_invariant", "시기 표시 변수 제외"], ["et_shift", "공변량 이동 가중치"], ["recent_rate", "규칙: 최근 10 shot"]];
  const models = TEMPORAL.filter(([k]) => k !== "recent_rate").map(([k]) => e88r[`retrain_50:${k}`].roc_auc);
  bullets(s, [
    "시간 변화는 반복 주기가 아니라 구간마다 한 번씩 나타나는 수준 변화",
    "데이터에 날짜·시각이 없어 계절성·교대 주기는 확인 불가",
    `개선 폭(+0.01 내외)은 fold 간 표준편차(${num(e88t.et.roc_auc_std, 3)})보다 작음`,
  ], X0, Y0 + 0.1, 4.4, 3.2);
  note(s, "50 shot 재학습 시", `모든 방법 ${num(Math.min(...models), 3)}~${num(Math.max(...models), 3)}, 규칙 ${num(e88r["retrain_50:recent_rate"].roc_auc, 3)}: 재학습이 차이를 없앤다`, X0, 5.0, 4.4, 1.75, "hl");
  s.addChart(pres.charts.BAR, [{ name: "② ROC-AUC", labels: TEMPORAL.map(([, l]) => l), values: TEMPORAL.map(([k]) => e88t[k].roc_auc_mean) }], {
    x: 5.3, y: Y0, w: W - X0 - 5.3, h: YB - Y0, barDir: "bar", barGapWidthPct: 45, catAxisOrientation: "maxMin",
    chartColors: TEMPORAL.map(([k]) => (k === "recent_rate" ? HEX.accent2 : k === "et" ? HEX.dk2 : GRAY)), ...chartBase(), dataLabelPosition: "outEnd",
    valAxisMinVal: 0.4, valAxisMaxVal: 0.75, valAxisMajorUnit: 0.1, valAxisHidden: true, showLegend: false,
    showTitle: true, title: "② 시간 순서 ROC-AUC (Extra Trees 기준 변형)", titleFontSize: 13, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    objectName: nameOf("chart"),
  });
}
{
  const s = slide("불량 유형 예측 (2단계)", "유형 예측은 시기 변화에 더 약하고 재학습 효과가 컸다",
    "2단계는 불량 제품 1,144개를 5개 유형으로 분류했습니다. 같은 기간 평가에서는 Random Forest가 Macro-F1 0.58로 비교 기준보다 높았지만, 시간 순서 평가에서는 0.34로 기준 0.26과 차이가 작았습니다. 가장 크게 떨어진 유형은 기타인데, 구간 4와 5에서만 나타나 학습 기간에는 없던 유형이기 때문입니다. 반대로 50 shot마다 재학습하면 0.51까지 올라 재학습 효과가 1단계보다 컸습니다. 운영에서는 1단계가 고른 제품에 예상 유형과 점검 항목을 함께 보여 줍니다.");
  const w = (CW - 2 * 0.3) / 3;
  stat(s, "0.58", "① 같은 기간 Macro-F1 (Random Forest). 최다 유형 기준 0.10 · 0.26", X0, Y0, w, 2.4);
  stat(s, "0.34", "② 시간 순서 (Extra Trees). 제품 유형·캐비티별 최다 유형 기준 0.26", X0 + w + 0.3, Y0, w, 2.4);
  stat(s, "0.51", "③ 50 shot마다 재학습. 재학습 효과가 1단계보다 크다", X0 + 2 * (w + 0.3), Y0, w, 2.4, { tone: "hl", color: C.accent2 });
  const w2 = (CW - 0.3) / 2;
  note(s, "'기타' 유형 F1 0.65 → 0.13", "구간 4·5에만 나타나 학습 기간에 없던 유형. 실제 기타의 65%를 기공으로 예측", X0, 4.5, w2, 2.0);
  note(s, "1단계 → 2단계 연결 (시간 순서)", "위험도 상위 20%를 검사하면 불량의 40%를 찾고, 그중 42%의 유형을 맞힌다", X0 + w2 + 0.3, 4.5, w2, 2.0);
}

// ══ 4. 모델 해석과 관리 범위 ══════════════════════════════════════════════════════
section = "모델 해석과 관리 범위";
pres.addSection({ title: section });
{
  const s = slide("모델 해석 (SHAP)", "상위 변수는 대부분 생산 시기를 반영했다",
    "모델이 무엇을 근거로 판단하는지 SHAP으로 해석했습니다. 제품 유형마다 해석용 XGBoost를 학습했는데, 상위 변수가 공장 습도, 캐비티, shot 순번처럼 생산 시기를 반영하는 변수였습니다. 모델이 공정 조건 자체보다 불량이 많던 시기를 식별하고 있다는 뜻이고, 시간 순서 평가에서 성능이 낮은 이유와 일치합니다. 제품 유형별로 모델을 나눈 이유는 유형마다 설정 수준이 크게 다르기 때문입니다. 예를 들어 주조 압력 평균이 유형 1은 1,060, 유형 2는 595입니다. 대시보드에서는 판정 근거를 작업자가 조정할 수 있는 변수와 시기·환경 변수로 나누어 보여 줍니다.");
  image(s, FIG("interp_shap_importance"), X0, Y0, 8.2, YB - Y0, "제품 유형별 SHAP 변수 중요도 막대그래프. 상위에 공장 습도, 캐비티, shot 순번, 고속 사출 속도");
  const x = 9.1;
  bullets(s, [
    "유형 1: 공장 습도 20% · 캐비티 12% · shot 순번 7%",
    "유형 2: 캐비티 18% · 고속 사출 속도 16% · shot 순번 9%",
    "주조 압력은 유형 간 수준 차이(1,060 vs 595)가 커서 유형별로 모델을 분리",
  ], x, Y0 + 0.1, W - X0 - x, 3.2, 15);
  note(s, "대시보드 반영", "판정 근거를 조정 가능 변수와 시기·환경 변수로 구분", x, 5.0, W - X0 - x, 1.75, "hl");
}
{
  const s = slide("관리 범위(안)", "후보 16개 중 5개만 같은 구간 안에서 검증되었다",
    "조정 가능한 변수로 관리 범위 안을 만들었습니다. PDP에서 예측 불량 확률이 평균 이하인 구간을 범위로 잡고, 같은 생산 구간 안에서도 범위 밖 shot의 불량률이 더 높은지 Mantel-Haenszel 오즈비로 검증했습니다. 16개 후보 중 5개가 통과했습니다. 구간을 무시하면 차이가 가장 컸던 냉각수 압력과 고속 사출 속도는 구간마다 값이 거의 고정되어 있어 검증할 수 없었습니다. 또 앞 60% 기간으로 찾은 범위는 뒤 40% 기간에서 재현되지 않았습니다. 그래서 이 범위는 고정 규격이 아니라 주기적으로 다시 확인하는 운영 범위로 제안합니다.");
  table(s, ["유형", "변수", "범위(안)", "범위 안 불량률", "범위 밖 불량률", "구간 내 오즈비"],
    ranges.map((r) => [r.Product_Type, r.label, r.range_label, pct(r.rate_in), pct(r.rate_out), num(r.cmh_or)]),
    X0, Y0, CW, [1.2, 2.9, 2.0, 2.0, 2.0, 2.03], { rowH: 0.46 });
  const w2 = (CW - 0.3) / 2;
  note(s, "찾는 법", "조정 가능 SHAP 상위 8개 변수의 PDP에서 예측 불량 확률이 평균 이하인 구간 → 같은 구간 안 오즈비로 검증", X0, 4.95, w2, 1.8);
  note(s, "고정 규격이 아니다", "앞 60% 기간으로 찾은 범위는 뒤 40%에서 재현되지 않음 → 주기적으로 재검증하는 운영 범위", X0 + w2 + 0.3, 4.95, w2, 1.8, "hl");
}
{
  const s = slide("특성요인도", "데이터 근거를 표시한 불량 특성요인도",
    "설비, 재료, 방법, 환경, 금형의 특성요인도에 데이터 근거를 표시했습니다. 불량 유형마다 같은 생산 구간의 정상 shot과 공정값을 비교해 시기 효과를 제거한 뒤, 차이가 큰 조정 가능 변수 3개를 점검 항목으로 정했습니다. 예를 들어 미성형은 용탕 온도가 낮고 형체력이 높을 때, 기공은 공기압과 스프레이 시간이 높을 때 많았습니다. 별표는 앞에서 본 관리 범위 안입니다. 근거는 설비 쪽에 가장 많았고, 공장 온습도 같은 환경 변수는 같은 구간 안에서는 근거가 없었습니다.");
  image(s, FIG("report_fishbone"), X0, Y0, 7.6, YB - Y0, "설비·재료·방법·환경·금형 특성요인도. 근거 있는 변수 아래에 관리 범위와 유형별 방향 표시");
  bullets(s, [
    "뼈 위 변수 = 데이터 근거 있음, 아래 줄이 근거",
    "★ 관리 범위(안), 유형↑↓ = 같은 구간 정상 대비 높음·낮음",
    "근거는 설비 쪽에 가장 많고, 공장 온습도는 구간 안 근거 없음",
    "캐비티1 금형이 가장 큰 차이",
  ], 8.5, Y0 + 0.1, W - X0 - 8.5, YB - Y0 - 0.1, 15);
}

// ══ 5. 검사 비용·개선·이상 대응 ═══════════════════════════════════════════════════
section = "검사 비용·개선·이상 대응";
pres.addSection({ title: section });
{
  const s = slide("검사 운영과 비용", "미검 비용이 검사 비용의 5배 이상이면 선별검사가 유리하다",
    "검사 방식별 총비용입니다. 검사 비용을 1로 두고 놓친 불량의 비용 배수를 바꿔 가며 비교했고, 50 shot 로트마다 과거 결과만으로 검사 기준을 다시 정했습니다. 불량률이 11.9%이므로 비용 비율이 8.4대1보다 작으면 검사하지 않는 편이 전수검사보다 저렴합니다. 5대1 이상에서는 위험도 기반 선별검사가 전수검사보다 5대1에서 48%, 10대1에서 21%, 20대1에서 7% 저렴했습니다. 모델 선별, 규칙 선별, 검사 강도 전환의 차이는 통계적으로 유의하지 않았고, 같은 검사량에서 샘플링 검사는 불량을 덜 찾았습니다. 선별검사로 바꾸면 검사하지 않은 제품의 결과를 알 수 없게 되는데, 이를 모사하면 규칙의 포착률이 75%에서 58%로 떨어지므로 무작위 감사 검사가 필요합니다.");
  const ratios = [2, 5, 8, 10, 15, 20];
  table(s, ["미검 : 검사", "최소 비용 방식", "검사 비율", "불량 포착", "전수 대비 절감"],
    ratios.map((k) => { const r = costBest[k]; return [`${k} : 1`, STRATEGY[r.best] ?? r.best, pct(r.inspect_rate, 0), pct(r.capture, 0), pct(r.saving_vs_full, 0)]; }),
    X0, Y0, 7.9, [1.5, 2.2, 1.4, 1.4, 1.4], { highlight: (i) => [1, 3, 5].includes(i), rowH: 0.55 });
  text(s, "제품당 비용 기준, 전수검사 = 1. 50 shot 로트마다 과거 결과로 검사 기준 갱신", X0, Y0 + 7 * 0.55 + 0.15, 7.9, 0.4, { fontSize: 12, color: C.text2 });
  const x = 8.8;
  const w = W - X0 - x;
  [
    ["손익분기 8.4 : 1", "불량률 11.9%. 그보다 작으면 무검사가 전수보다 저렴"],
    ["세 방식은 구별 안 됨", "모델·규칙·강도 전환의 차이 구간이 0을 포함"],
    ["샘플링은 덜 찾는다", "AQL 설계: 68% 검사로 79% 포착, 모델·규칙은 87%"],
    ["감사 검사 필요", "미검사 제품 결과가 없으면 규칙 포착 75% → 58%"],
  ].forEach(([t, b], k) => note(s, t, b, x, Y0 + k * 1.27, w, 1.12, k === 3 ? "hl" : "plain"));
}
{
  const s = slide("불량 개선 방안", "개선 여지는 캐비티1 금형이 가장 크다",
    "불량률을 낮출 방안도 데이터로 검토했습니다. 가장 큰 여지는 캐비티1입니다. 캐비티1이 같은 구간의 캐비티2 수준이면 불량이 37% 줄어드는 것으로 추정됩니다. 관리 범위 안을 지키면 불량률이 37~39% 줄어든다는 추정도 나왔지만, 범위 안이 뒤 기간에서 재현되지 않았기 때문에 이 값은 상한으로만 봅니다. 데이터에 조치 기록이 없어 모두 관측 데이터의 연관이므로, 인과를 확인할 2의 4-1승 부분요인실험 8개 조건을 제안했습니다.");
  const w = (CW - 2 * 0.3) / 3;
  const tall = 3.6;
  card(s, X0, Y0, w, tall, "hl");
  text(s, "37%", X0 + 0.3, Y0 + 0.25, w - 0.6, 0.9, { fontSize: 48, bold: true, color: C.accent2 });
  text(s, "캐비티1을 캐비티2 수준으로", X0 + 0.3, Y0 + 1.25, w - 0.6, 0.45, { fontSize: 18, bold: true });
  text(s, "같은 구간의 캐비티2만큼이면 초과 불량 423개(전체 1,143개)가 사라진다. 6개 구간 중 4개에서 캐비티1이 높음", X0 + 0.3, Y0 + 1.8, w - 0.6, 1.7, { fontSize: 15, color: C.text2 });
  const x2 = X0 + w + 0.3;
  card(s, x2, Y0, w, tall);
  text(s, "37~39%", x2 + 0.3, Y0 + 0.25, w - 0.6, 0.9, { fontSize: 48, bold: true, color: C.accent1 });
  text(s, "관리 범위(안) 준수 · 상한", x2 + 0.3, Y0 + 1.25, w - 0.6, 0.45, { fontSize: 18, bold: true });
  text(s, "유형 1 11.7% → 7.1%, 유형 2 13.4% → 8.4%. 범위(안)가 뒤 기간에서 재현되지 않아 상한으로만 해석", x2 + 0.3, Y0 + 1.8, w - 0.6, 1.7, { fontSize: 15, color: C.text2 });
  const x3 = X0 + 2 * (w + 0.3);
  card(s, x3, Y0, w, tall);
  text(s, "8개 조건", x3 + 0.3, Y0 + 0.25, w - 0.6, 0.9, { fontSize: 48, bold: true, color: C.accent1 });
  text(s, doe("확인 실험 ", " 부분요인실험"), x3 + 0.3, Y0 + 1.25, w - 0.6, 0.45, { fontSize: 18, bold: true });
  text(s, "관리 범위와 최우수 구간 조건 4요인. 조건당 143·122 shot이면 30% 감소를 검정력 80%로 확인", x3 + 0.3, Y0 + 1.8, w - 0.6, 1.7, { fontSize: 15, color: C.text2 });
  card(s, X0, 5.65, CW, 1.1, "dark");
  text(s, "조치·정비 기록이 없어 모두 같은 구간 안에서 비교한 관측 데이터의 연관이다. 인과는 실험으로 확인한다", X0 + 0.35, 5.65, CW - 0.7, 1.1, { fontSize: 17, color: C.background1, valign: "middle" });
}
{
  const s = slide("이상 대응 계획 (OCAP)", "경보는 불량률로 울리고, 공정 변수는 원인 진단에 쓴다",
    "경보는 드물게 울리고, 울린 뒤 실제로 불량이 늘어야 쓸모가 있습니다. 비교해 보니 불량률 CUSUM 경보는 100 shot당 0.8번 울리고, 경보 뒤 50 shot의 불량률이 평균의 1.41배였습니다. 반면 공정 변수의 급변이나 관리 범위 이탈 경보 뒤에는 대부분 0.5에서 1.3배로 불량을 예고하지 못했습니다. 그래서 경고, 주의, 정보, 기록의 4등급으로 나누었습니다. 경고가 뜨면 다음 50 shot을 전수검사로 강화하고, 그 시점에 범위 밖인 변수와 늘어난 불량 유형의 점검 항목을 보여 주며 모델을 재학습합니다. 공정 변수 급변은 경보로 쓰지 않고 원인 진단 기록으로 남깁니다.");
  const w2 = (CW - 0.3) / 2;
  card(s, X0, Y0, w2, 1.45, "hl");
  text(s, "1.41배", X0 + 0.3, Y0 + 0.15, 2.4, 1.15, { fontSize: 40, bold: true, color: C.accent2, valign: "middle" });
  text(s, "불량률 CUSUM 경보 후 50 shot 불량률 (평균 대비, 100 shot당 0.8회)", X0 + 2.8, Y0 + 0.15, w2 - 3.1, 1.15, { fontSize: 15, color: C.text2, valign: "middle" });
  const xb = X0 + w2 + 0.3;
  card(s, xb, Y0, w2, 1.45);
  text(s, "0.5~1.3배", xb + 0.3, Y0 + 0.15, 2.8, 1.15, { fontSize: 36, bold: true, color: C.accent3, valign: "middle" });
  text(s, "공정 변수 급변·범위 이탈 경보 후: 불량 증가를 예고하지 못함", xb + 3.2, Y0 + 0.15, w2 - 3.5, 1.15, { fontSize: 15, color: C.text2, valign: "middle" });
  table(s, ["등급", "발생 조건", "즉시 조치", "해제"], [
    ["경고", "불량률 CUSUM 상측 경보", "다음 50 shot 전수검사, 범위 밖 변수·늘어난 유형의 점검 항목 표시, 재학습", "50 shot 동안 새 경보 없음"],
    ["주의", "위험도가 검사 기준 이상인 제품", "해당 제품 검사, 예상 유형과 점검 항목 표시", "검사 후 종료"],
    ["정보", "관리 범위 밖 운전 지속 (최근 20 shot 중 80%)", "설정값 조정 검토, 조정 전후 불량률 기록", "범위 밖 50% 미만"],
    ["기록", "공정 변수 급변 (중앙값 ± 3.5σ)", "경보로 쓰지 않고 원인 진단용으로 기록", "–"],
  ], X0, 3.5, CW, [1.1, 3.4, 5.03, 2.6], { rowH: 0.62, highlight: (i) => i === 0 });
}

// ══ 6. 대시보드와 검증 ═══════════════════════════════════════════════════════════
section = "대시보드와 검증";
pres.addSection({ title: section });
{
  const s = slide("재생 시뮬레이션 대시보드", "과거 데이터를 shot 순서대로 재생해 운영을 시연한다",
    "이 결과를 현장 운영처럼 보여 주는 대시보드입니다. 과거 생산 데이터를 shot 순서대로 재생하면서 관리도, 제품 위험도, 예상 유형, 검사 목록, 경보를 운영 상황처럼 보여 줍니다. 시작 구간 3개와 재학습 방식 3가지를 조합한 9개 시나리오가 있고, 모델은 항상 그 시점 이전 데이터로만 학습합니다. 맨 위 상태 띠가 지금 문제가 있는지 알려 주고, 공정 변수마다 개별값 관리도와 최근 분포 위의 현재 위치를 보여 줍니다. 평소에는 회색이고 이상이 있을 때만 색이 들어가며, 한국어와 영어를 전환할 수 있습니다. 화면의 위험도는 모델 확률을 최근 200 shot 불량률 기준으로 변환한 값입니다.");
  image(s, SHOT("dashboard_overview_dark_wide"), X0, Y0, 8.0, YB - Y0, "대시보드 운영 현황 화면. 경고상태 띠, 숫자 줄, 불량률 관리도, 주조 압력 관리도와 분포 위 현재 위치, 알람 목록");
  bullets(s, [
    "Next.js(ECharts) + FastAPI",
    "시나리오 9개 = 시작 구간 3개 × 재학습 3가지 (없음, 50 shot마다, 경보 시)",
    "상태 띠 → 숫자 줄 → 관리도(I-MR)·분포 위 현재 위치 → 공정 변수 칸",
    "평소엔 회색, 이상 시에만 색. 한/영 전환",
  ], 8.9, Y0 + 0.1, W - X0 - 8.9, YB - Y0 - 0.1, 15);
}
{
  const s = slide("알람 센터", "경고가 뜨면 조치 체크리스트와 원인 진단을 함께 보여 준다",
    "알람 센터 화면입니다. 경고가 뜨면 확인하고, 조치 보기에서 체크리스트를 따라가며 해제합니다. 경보 시점에 관리 범위 밖이던 변수와, 경보 뒤 비중이 늘어난 불량 유형의 점검 항목을 함께 보여 줘 원인을 빨리 좁힐 수 있게 했습니다. 알람 피로를 줄이려고 제품 단위 주의 알림은 10 shot마다 묶고, 전수검사 중에는 띄우지 않습니다.");
  bullets(s, [
    "경고 → 확인 → 조치 보기 → 체크리스트 → 해제",
    "원인 진단: 경보 시점 관리 범위 밖 변수, 늘어난 불량 유형의 점검 항목",
    "주의 알림은 10 shot마다 묶고 전수검사 중에는 생략",
    "공정 변수 급변 기록은 알람 센터에만 (ISA-18.2)",
  ], X0, Y0 + 0.1, 3.9, YB - Y0 - 0.1, 15);
  image(s, SHOT("dashboard_alarms_dark_wide"), W - X0 - 8.0, Y0, 8.0, YB - Y0, "알람 센터 화면. 경보등급별 수, 불량률 CUSUM, 알람 목록과 경보 상세의 조치 체크리스트");
}
{
  const s = slide("현장 적용 구성도", "현장에서는 실시간 수집만 연결하면 된다",
    "현장에 적용한다면 이런 구성입니다. 파란 상자가 이번 프로젝트에서 구현한 부분이고, 점선은 현장 연동 때 추가할 부분입니다. KAMP 데이터 패키지에 포함된 OPC-UA 설정과 AAS 정보 모델을 기준으로 설비 태그를 수집하면, 지금의 재생 시뮬레이션 자리에 실시간 데이터가 들어갑니다. 작업자의 검사 결과가 새 라벨이 되어 재학습으로 돌아오는 고리가 핵심이고, 그래서 무작위 감사 검사가 필요합니다.");
  image(s, FIG("report_architecture"), X0, Y0, 8.3, YB - Y0, "현장 적용 구성도. 설비, 엣지 게이트웨이, 저장·전처리, 예측·감시, 대시보드, 작업자, 재학습");
  bullets(s, [
    "파란 상자 = 이번 구현, 점선 = 현장 연동 시 추가 (KAMP 패키지의 OPC-UA·AAS 설정)",
    "검사 결과가 새 라벨이 되어 재학습으로 돌아온다",
    "감사 검사로 검사하지 않은 제품의 결과도 확보",
  ], 9.2, Y0 + 0.1, W - X0 - 9.2, YB - Y0 - 0.1, 15);
}
{
  const s = slide("검증", "9개 시나리오를 실제 브라우저로 끝까지 재생했다",
    "검증입니다. 실제 Chrome으로 화면을 조작하는 시뮬레이션 테스트에서 9개 시나리오를 처음부터 끝까지 재생했고, 오류가 한 건도 없었으며 경고 배너 수와 경보 수가 일치했습니다. 검사 정책은 Python과 화면 코드에서 각각 계산해 54건 모두 일치함을 확인했고, 모든 분석 스크립트를 처음부터 다시 실행해 결과 파일이 바이트 단위로 같음을 확인했습니다. 재생 결과도 분석과 같은 경향이었습니다. 유형 1과 유형 2 구간 7부터는 모델 선별이 규칙과 같거나 조금 저렴했고, 불량률이 손익분기보다 높은 유형 2 구간 5부터는 전수검사에 가까운 운영이 최적이어서 절감 폭이 작았습니다.");
  const w = (CW - 3 * 0.3) / 4;
  [
    ["0건", "9개 시나리오 전체 재생 중 오류. 경고 배너 수 = 경보 수"],
    ["54 / 54", "검사 정책을 Python과 화면 코드로 각각 계산해 대조"],
    ["123", "자동 테스트: Python 92 · 화면 계산 18 · 브라우저 13"],
    ["동일", "모든 스크립트 재실행 결과 파일이 바이트 단위로 일치"],
  ].forEach(([v, l], k) => stat(s, v, l, X0 + k * (w + 0.3), Y0, w, 2.4));
  const w2 = (CW - 0.3) / 2;
  note(s, "재생 비용 (10 : 1, 전수검사 = 1)", "유형 1 구간 2부터 모델 0.55~0.56 / 규칙 0.56. 유형 2 구간 5부터는 불량률이 손익분기보다 높아 전수검사에 가까운 운영이 최적", X0, 4.5, w2, 2.1);
  note(s, "재생 속 모델 성능 (유형 2 구간 5부터)", "재학습 없음 AUC 0.627, 경보 재학습 0.694 ≈ 최근 불량률 규칙 0.696. 분석과 같은 경향", X0 + w2 + 0.3, 4.5, w2, 2.1);
}

// ══ 7. 결론 ═══════════════════════════════════════════════════════════════════
section = "결론";
pres.addSection({ title: section });
{
  const s = slide("결론", "연구 질문에 대한 답",
    "네 가지 질문에 답하겠습니다. 모델은 같은 기간 안에서는 규칙보다 낫지만, 실제 운영에 해당하는 이후 기간 예측에서는 최근 불량률 규칙이 더 높았습니다. 원인은 데이터 양이 아니라 시간에 따른 분포 변화입니다. 보완책은 재학습이고, 불량률 경보를 재학습 신호로 쓰면 효율적입니다. 현장에서는 미검 비용이 검사 비용의 5배 이상이면 위험도 기반 선별검사에 경보 시 전수검사 강화를 더하는 방식이 전수검사보다 저렴합니다.");
  const rows = [
    ["모델이 더 나은가?", "같은 기간 안에서는 그렇다(0.76 vs 0.73). 이후 기간 예측에서는 최근 불량률 규칙이 모든 모델보다 높았고, 자주 재학습해야 같아진다"],
    ["왜 그런가?", "데이터 양보다 시간에 따른 분포 변화. 불량과 공정값의 관계 대부분이 시기 간 차이이고, 관련 변수도 시기마다 달라졌다"],
    ["어떻게 보완하나?", "재학습. 불량률 CUSUM 경보 때 재학습하면 50 shot 주기와 같은 성능을 40% 적은 재학습으로 얻는다"],
    ["현장에서는?", "미검 비용이 5배 이상이면 선별검사 + 경보 시 전수검사 강화가 전수검사보다 7~48% 저렴. 경보는 불량률, 원인 진단은 공정 변수"],
  ];
  rows.forEach(([q, a], k) => {
    const y = Y0 + k * 1.27;
    card(s, X0, y, CW, 1.1);
    badge(s, String(k + 1), X0 + 0.25, y + 0.27);
    text(s, q, X0 + 1.0, y, 3.0, 1.1, { fontSize: 18, bold: true, valign: "middle" });
    text(s, a, X0 + 4.1, y, CW - 4.4, 1.1, { fontSize: 15, color: C.text2, valign: "middle" });
  });
}
{
  const s = slide("제언", "현장에 제안하는 운영 방식",
    "현장에 네 가지를 제안합니다. 첫째, 전수검사를 위험도 기반 선별검사로 바꾸되 불량률 경보 뒤 50 shot은 전수검사로 강화합니다. 둘째, 모델은 50 shot마다 또는 경보 때 다시 학습하고, 그게 어렵다면 최근 불량률 규칙만 써도 같은 수준의 선별이 가능합니다. 셋째, 선별검사로 바꾸더라도 무작위 감사 검사를 유지해야 합니다. 넷째, 캐비티1 금형 점검과 관리 범위 확인 실험을 우선 개선 과제로 삼습니다.");
  const items = [
    ["선별검사 + 경보 후 50 shot 전수검사", "검사 기준은 50 shot마다 직전 결과에서 총비용이 최소인 값으로 갱신"],
    ["50 shot마다 또는 불량률 경보 때 재학습", "재학습이 어려우면 최근 10 shot 불량률 규칙으로도 같은 수준의 선별 가능"],
    ["무작위 감사 검사 유지", "검사하지 않은 제품의 결과가 없으면 규칙의 불량 포착률이 75% → 58%"],
    ["캐비티1 금형 점검과 확인 실험", "관리 범위(안)는 고정 규격이 아니라 주기적으로 재검증하는 운영 범위"],
  ];
  const w2 = (CW - 0.3) / 2;
  items.forEach(([t, b], k) => {
    const x = X0 + (k % 2) * (w2 + 0.3);
    const y = Y0 + Math.floor(k / 2) * 2.55;
    card(s, x, y, w2, 2.3);
    badge(s, String(k + 1), x + 0.3, y + 0.3, 0.6, C.accent2);
    text(s, t, x + 1.15, y + 0.3, w2 - 1.45, 0.6, { fontSize: 19, bold: true, valign: "middle" });
    text(s, b, x + 1.15, y + 1.05, w2 - 1.45, 1.1, { fontSize: 16, color: C.text2 });
  });
}
{
  const s = slide("한계와 향후 과제", "관측 데이터의 연관이므로, 다음은 실험과 현장 연동이다",
    "한계도 분명합니다. 데이터에 날짜와 시각이 없어 계절성이나 교대 주기를 볼 수 없었고, 구간 간 변화의 원인을 설명하는 변수도 없었습니다. 관리 범위와 개선 효과는 관측 데이터의 연관이라 인과가 아니며, 같은 데이터로 찾고 검증해서 낙관적일 수 있습니다. 비용 단가는 가정값이고 데이터 기간도 짧습니다. 그래서 다음 단계는 shot별 시각, 원자재 로트, 정비 기록을 함께 수집하고, 제안한 실험으로 인과를 확인하며, 실시간 수집과 연결해 감사 검사를 포함한 선별검사를 시범 운영하는 것입니다.");
  const w2 = (CW - 0.3) / 2;
  card(s, X0, Y0, w2, YB - Y0);
  text(s, "한계", X0 + 0.35, Y0 + 0.25, w2 - 0.7, 0.45, { fontSize: 20, bold: true, color: C.accent4 });
  bullets(s, [
    "날짜·시각이 없어 계절성·교대 주기를 식별할 수 없었다",
    "구간 간 변화의 원인(설정·원자재·금형·정비) 변수가 없다",
    "관리 범위·개선 효과는 관측 연관이며 낙관적일 수 있다",
    "비용 단가는 가정값, 약 4,600 shot · 7개 구간으로 짧다",
  ], X0 + 0.35, Y0 + 0.9, w2 - 0.7, YB - Y0 - 1.1, 16);
  const x = X0 + w2 + 0.3;
  card(s, x, Y0, w2, YB - Y0, "hl");
  text(s, "향후 과제", x + 0.35, Y0 + 0.25, w2 - 0.7, 0.45, { fontSize: 20, bold: true, color: C.accent2 });
  text(s, [
    { text: "shot별 시각, 원자재 로트, 금형 온도, 정비 이력 수집", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 10 } },
    { text: "부분요인실험(8개 조건)으로 관리 범위와 최우수 구간 조건의 효과 확인", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 10 } },
    { text: "OPC-UA 실시간 수집 연결, 감사 검사를 포함한 선별검사 시범 운영", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 10 } },
    { text: "구간 효과를 분리하는 모형(혼합효과 랜덤 포레스트 등) 검토", options: { bullet: { indent: 18 }, paraSpaceAfter: 10 } },
  ], x + 0.35, Y0 + 0.9, w2 - 0.7, YB - Y0 - 1.1, { fontSize: 16 });
}
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: section });
  s.addText("DieCast-QA", { placeholder: "eyebrow" });
  s.addText("감사합니다", { placeholder: "title" });
  s.addText("질문을 받겠습니다", { placeholder: "subtitle" });
  text(s, "자세한 수치와 그림은 최종 보고서, 재현 방법은 보고서 부록 B", 0.8, 6.4, 11.7, 0.4, { fontSize: 14, color: C.accent3 });
  s.addNotes("들어 주셔서 감사합니다. 질문 받겠습니다. 자세한 수치와 그림은 최종 보고서에, 재현 방법은 보고서 부록 B에 정리했습니다.");
}

mkdirSync(dirname(OUT), { recursive: true });
await pres.writeFile({ fileName: OUT });
await applyTheme(OUT, THEME);
console.log(`발표 자료: ${OUT} (슬라이드 ${pres.slides.length}장)`);
