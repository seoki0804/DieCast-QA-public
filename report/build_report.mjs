// DieCast-QA 최종 보고서(.docx). 표 숫자는 results/의 CSV에서 읽고, 본문 수치는 docs/ROADMAP.md의
// 검증된 기록(전체 재실행·수치 대조 완료)을 쓴다. 실행: cd report && npm run all (빌드 → PDF → 목차 쪽 번호 → 다시 빌드)
// 문체: 학술 보고서체(~하였다, ~로 나타났다). 주장은 수치와 함께 쓰고, 해석은 '~로 해석된다'로 구분한다.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { AlignmentType, Document, Packer, Paragraph, TableOfContents, TextRun } from "docx";

import { COLORS, FONT, NUMBERING, ReportBuilder, STYLES, num, pageFooter, pct, readCsv } from "./lib/doc.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const R = (...p) => join(ROOT, "results", ...p);
const FIG = (name) => join(ROOT, "results", "figures", `${name}.png`);
const SHOT = (name) => join(ROOT, "docs", "report", "images", `${name}.png`);
const OUT = join(ROOT, "docs", "report", "DieCast-QA_최종보고서.docx");
// 목차 쪽 번호: npm run pdf가 렌더링한 PDF에서 읽어 둔 값(없으면 빈칸, Word가 열 때 채운다)
const TOC_PAGES = join(dirname(fileURLToPath(import.meta.url)), "toc_pages.json");

const MODEL = { logreg: "Logistic Regression", tree: "Decision Tree", rf: "Random Forest", et: "Extra Trees", xgb: "XGBoost", lgbm: "LightGBM", mlp: "MLP", recent_rate: "규칙: 최근 10 shot 불량률", cavity_rate: "규칙: 캐비티별 불량률", random: "규칙: 무작위", type_mode: "기준: 가장 흔한 유형", type_group_mode: "기준: 제품 유형·캐비티별 최다" };
const STRATEGY = { full: "전수검사", none: "검사 안 함", model: "모델 선별", rule: "규칙 선별", switching: "검사 강도 전환", sampling: "샘플링(비용 최소)", sampling_classical: "샘플링(AQL 설계)", cavity: "캐비티 규칙", rule_censored: "규칙(검사한 제품만)", random_matched: "무작위(같은 검사량)", perfect: "완벽한 예측" };

const doc = new ReportBuilder();
const by = (rows, key) => Object.fromEntries(rows.map((r) => [key(r), r]));

// ── 참고문헌: 데이터·선행 연구 + 본문에서 쓴 방법의 원 문헌. 본문은 cite("키")로 [번호]를 단다 ─────────────
const REFERENCES = [
  ["kamp", "KAMP(한국 인공지능 제조 플랫폼), 「주조 품질보증 AI 데이터셋」 및 분석실습 가이드북. kamp-ai.kr"],
  ["joshua", "JoshuaKim757, Defect-Prediction-Die-Casting, GitHub 저장소 (같은 데이터를 쓴 팀 프로젝트)."],
  ["kangmunju", "Kangmunju, diecasting-defect-prediction, GitHub 저장소 (같은 데이터, 7개 클래스 유형 분류)."],
  ["hansung", "한성대학교 학위논문, 「불균형 데이터셋에서의 다이캐스팅 공정의 불량예측 성능 연구: SMOTE와 랜덤포레스트의 활용」."],
  ["inha", "홍지수 외, 「XAI 알고리즘 기반 사출 공정 수율 개선 방법론」, 인하대학교 (KAMP 사출성형 데이터)."],
  ["ijmc", "International Journal of Metalcasting (2025), 마그네슘 고압 다이캐스팅 결함 예측 머신러닝 비교. doi:10.1007/s40962-025-01592-w"],
  ["schmalzer", "Schmalzer, S., Holom, R., Michno, T., Falkner, D., Repanšek, U., Košir, N., & Šifrer, P. (2026). Time series classification in high-pressure die casting manufacturing using dynamic time warping. Procedia Computer Science, 277, 1631–1640. doi:10.1016/j.procs.2026.02.201"],
  ["stevenson", "Stevenson, W. J. 『생산운영관리』 — 품질경영·품질관리."],
  ["montgomery", "Montgomery, D. C. (2019). Introduction to Statistical Quality Control (8th ed.). Wiley."],
  ["page", "Page, E. S. (1954). Continuous inspection schemes. Biometrika, 41(1/2), 100–115."],
  ["roberts", "Roberts, S. W. (1959). Control chart tests based on geometric moving averages. Technometrics, 1(3), 239–250."],
  ["breiman", "Breiman, L. (2001). Random forests. Machine Learning, 45(1), 5–32."],
  ["geurts", "Geurts, P., Ernst, D., & Wehenkel, L. (2006). Extremely randomized trees. Machine Learning, 63(1), 3–42."],
  ["xgboost", "Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. Proceedings of KDD 2016, 785–794."],
  ["lightgbm", "Ke, G. et al. (2017). LightGBM: A highly efficient gradient boosting decision tree. Advances in Neural Information Processing Systems 30."],
  ["grinsztajn", "Grinsztajn, L. et al. (2022). Why do tree-based models still outperform deep learning on typical tabular data? NeurIPS 2022."],
  ["optuna", "Akiba, T. et al. (2019). Optuna: A next-generation hyperparameter optimization framework. Proceedings of KDD 2019."],
  ["smote", "Chawla, N. V. et al. (2002). SMOTE: Synthetic minority over-sampling technique. Journal of Artificial Intelligence Research, 16, 321–357."],
  ["ctgan", "Xu, L. et al. (2019). Modeling tabular data using conditional GAN. NeurIPS 2019."],
  ["gama", "Gama, J. et al. (2014). A survey on concept drift adaptation. ACM Computing Surveys, 46(4), Article 44."],
  ["lu", "Lu, J., Liu, A., Dong, F., Gu, F., Gama, J., & Zhang, G. (2019). Learning under concept drift: A review. IEEE Transactions on Knowledge and Data Engineering, 31(12), 2346–2363."],
  ["jourdan", "Jourdan, N., Sen, S., Husom, E. J., Garcia-Ceja, E., Biegel, T., & Metternich, J. (2021). On the reliability of machine learning applications in manufacturing environments. NeurIPS 2021 Workshop on Distribution Shifts. arXiv:2112.06986"],
  ["kadlec", "Kadlec, P., Grbić, R., & Gabrys, B. (2011). Review of adaptation mechanisms for data-driven soft sensors. Computers & Chemical Engineering, 35(1), 1–24."],
  ["morenotorres", "Moreno-Torres, J. G., Raeder, T., Alaiz-Rodríguez, R., Chawla, N. V., & Herrera, F. (2012). A unifying view on dataset shift in classification. Pattern Recognition, 45(1), 521–530."],
  ["shimodaira", "Shimodaira, H. (2000). Improving predictive inference under covariate shift by weighting the log-likelihood function. Journal of Statistical Planning and Inference, 90(2), 227–244."],
  ["arjovsky", "Arjovsky, M., Bottou, L., Gulrajani, I., & Lopez-Paz, D. (2019). Invariant risk minimization. arXiv:1907.02893"],
  ["hajjem", "Hajjem, A., Bellavance, F., & Larocque, D. (2014). Mixed-effects random forest for clustered data. Journal of Statistical Computation and Simulation, 84(6), 1313–1328."],
  ["shap", "Lundberg, S. M., & Lee, S.-I. (2017). A unified approach to interpreting model predictions. Advances in Neural Information Processing Systems 30."],
  ["friedman", "Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. Annals of Statistics, 29(5), 1189–1232."],
  ["ice", "Goldstein, A., Kapelner, A., Bleich, J., & Pitkin, E. (2015). Peeking inside the black box: Visualizing statistical learning with plots of individual conditional expectation. Journal of Computational and Graphical Statistics, 24(1), 44–65."],
  ["mh", "Mantel, N., & Haenszel, W. (1959). Statistical aspects of the analysis of data from retrospective studies of disease. Journal of the National Cancer Institute, 22(4), 719–748."],
  ["platt", "Platt, J. (1999). Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods. In Advances in Large Margin Classifiers. MIT Press."],
  ["zadrozny", "Zadrozny, B., & Elkan, C. (2002). Transforming classifier scores into accurate multiclass probability estimates. Proceedings of KDD 2002."],
  ["niculescu", "Niculescu-Mizil, A., & Caruana, R. (2005). Predicting good probabilities with supervised learning. Proceedings of ICML 2005."],
  ["saerens", "Saerens, M., Latinne, P., & Decaestecker, C. (2002). Adjusting the outputs of a classifier to new a priori probabilities: A simple procedure. Neural Computation, 14(1), 21–41."],
  ["doe", "Montgomery, D. C. (2017). Design and Analysis of Experiments (9th ed.). Wiley."],
];
const REF_TEXT = Object.fromEntries(REFERENCES);
const cited = []; // 처음 인용된 순서 = 참고문헌 번호
/** cite("a", "b") → "[3, 4]". 번호는 본문에서 처음 인용된 순서로 매긴다. 없는 키는 빌드를 멈춘다(오타 방지). */
const cite = (...keys) => {
  const numbers = keys.map((key) => {
    if (!REF_TEXT[key]) throw new Error(`참고문헌 키 없음: ${key}`);
    if (!cited.includes(key)) cited.push(key);
    return cited.indexOf(key) + 1;
  });
  return `[${numbers.join(", ")}]`;
};

// ── 표지 ────────────────────────────────────────────────────────────────────────────
const cover = [
  new Paragraph({ spacing: { before: 2600 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.LEFT, children: [new TextRun({ text: "AI 기반 생산운영관리 · 팀 프로젝트 최종 보고서", font: FONT, size: 24, color: COLORS.accent, bold: true })] }),
  new Paragraph({ spacing: { before: 200, after: 120 }, children: [new TextRun({ text: "다이캐스팅 공정 데이터를 활용한", font: FONT, size: 44, bold: true })] }),
  new Paragraph({ spacing: { after: 400 }, children: [new TextRun({ text: "불량 예측 모델 개발과 품질관리 방안", font: FONT, size: 44, bold: true })] }),
  new Paragraph({ border: { top: { style: "single", size: 8, color: COLORS.rule, space: 12 } }, spacing: { after: 120 }, children: [new TextRun({ text: "KAMP 「주조 품질보증 AI 데이터셋」을 이용한 불량 여부·유형 예측, 공정 안정성 평가, 검사 비용 분석, 불량 개선 방안과 이상 대응 계획, 재생 시뮬레이션 대시보드", font: FONT, size: 22, color: COLORS.secondary })] }),
  new Paragraph({ spacing: { before: 1800 }, children: [new TextRun({ text: "팀원", font: FONT, size: 20, bold: true, color: COLORS.secondary })] }),
  ...[
    ["김민송", "총괄·비용 분석"],
    ["박준", "데이터·탐색 분석"],
    ["안형석", "예측 모델"],
    ["신유민", "품질관리·모델 해석"],
    ["정화평", "대시보드·발표"],
  ].map(([name, role]) => new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: `${name}  `, font: FONT, size: 20, bold: true }), new TextRun({ text: role, font: FONT, size: 20, color: COLORS.secondary })] })),
  new Paragraph({ spacing: { before: 400 }, children: [new TextRun({ text: "2026년 11월", font: FONT, size: 20, color: COLORS.secondary })] }),
  new Paragraph({ pageBreakBefore: true, children: [new TextRun({ text: "목차", font: FONT, size: 32, bold: true })] }),
];

// ── 6.6절 시간 정보 실험 결과 (요약에서도 쓰므로 먼저 읽는다) ─────────────────────────────────
const TEMPORAL = {
  et: "기준 (공정·센서 원값)",
  et_time: "+ 생산 순서·구간 번호",
  et_history: "+ 흔들림·검사 이력 변수",
  et_relative: "구간 기준 편차만",
  et_invariant: "시기 표시 변수 제외",
  et_shift: "공변량 이동 가중치",
  recent_rate: "규칙: 최근 10 shot 불량률",
};
const e88t = by(readCsv(R("experiments", "e88_temporal_time_order.csv")), (r) => r.model);
const e88r = by(readCsv(R("experiments", "e88_temporal_retrain.csv")), (r) => `${r.design}:${r.model}`);
const e88s = readCsv(R("experiments", "e88_temporal_invariant_shares.csv"));
const modelKeys = Object.keys(TEMPORAL).filter((k) => k !== "recent_rate");
const bestTime = modelKeys.reduce((a, b) => (e88t[b].roc_auc_mean > e88t[a].roc_auc_mean ? b : a));

// ── 8장 검사 비용 요약 (요약·8.4절·결론에서 쓰므로 먼저 계산한다) ─────────────────────────────
const costBest = readCsv(R("cost", "cost_best.csv"));
const costSummary = readCsv(R("cost", "cost_summary.csv"));
const costOf = (ratio, strategy) => costSummary.find((r) => r.ratio === ratio && r.strategy === strategy).cost_per_part;
const screened = costBest.filter((r) => r.ratio >= 5); // 선별검사가 두 단순 방식보다 싸지는 비율
const percentSpan = (values) => `${Math.round(Math.min(...values) * 100)}~${Math.round(Math.max(...values) * 100)}%`;
// 무검사·전수검사 중 더 싼 쪽 대비 절감 (5:1에서 '전수 대비 48%'는 대부분 검사를 안 해서 생기는 절감이다)
const simpleSaving = percentSpan(screened.map((r) => r.saving_vs_simple));
// 규칙 선별 − 모델 기반 방식(모델 선별·검사 강도 전환 중 싼 쪽): 양수면 모델 기반이 그만큼 싸다
const ruleGap = screened.map((r) => ({ ratio: r.ratio, gap: costOf(r.ratio, "rule") - Math.min(costOf(r.ratio, "model"), costOf(r.ratio, "switching")) }));
const maxRuleGap = Math.max(...ruleGap.map((g) => g.gap));
const ruleCheaper = ruleGap.filter((g) => g.gap < 0).map((g) => `${g.ratio}:1`);
// 본문은 '규칙 선별과 최소 비용 방식의 차이 구간이 모두 0을 포함'이라고 쓴다. 결과가 바뀌면 빌드를 멈춘다
const ruleCi = readCsv(R("cost", "cost_uncertainty.csv")).filter((r) => r.strategy === "rule" && r.ratio >= 5);
if (ruleCi.some((r) => r.diff_low > 0 || r.diff_high < 0)) throw new Error("규칙 선별과 최소 비용 방식의 차이 구간이 0을 포함하지 않는 비율이 있음: 8.4절 문장 확인");
// 목표 불량 포착률을 달성하는 최소 검사 비율 (③ 50 shot 재학습 예측 전체, 위험도 순)
const curves = readCsv(R("cost", "sampling_curves.csv"));
const needInspect = (column, target) => Math.min(...curves.filter((r) => r[column] >= target).map((r) => r.inspect_rate));
const evalRate = costSummary[0].defects / costSummary[0].parts; // 평가 기간 불량률 (11.9%)

// ── 요약 ────────────────────────────────────────────────────────────────────────────
doc.pageBreak();
doc.h1("요약");
doc.p("본 연구는 KAMP 「주조 품질보증 AI 데이터셋」의 shot 단위 공정·센서 데이터를 이용하여 다이캐스팅 제품의 불량 여부와 불량 유형을 예측하고, 예측 결과를 검사 운영과 공정 관리에 적용하는 방안을 검토하였다. 같은 데이터를 사용한 기존 분석은 대부분 shot을 무작위로 나누어 모델을 평가하였으나, 실제 운영에서는 과거 데이터로 학습한 모델이 이후에 생산되는 제품을 예측해야 한다. 따라서 무작위 분할 외에 시간 순서를 지킨 평가를 함께 수행하고, 다음 네 가지 연구 질문을 검토하였다. (1) 예측 모델이 최근 검사 결과만 사용하는 단순 규칙(직전 10 shot의 불량률)보다 불량을 더 잘 찾는가, (2) 그렇지 않다면 원인은 무엇인가, (3) 이를 어떻게 보완할 수 있는가, (4) 현장 운영에 어떻게 적용할 수 있는가.");
doc.p("분석은 전처리(중복 기록 제거, 생산 구간 식별), 층별 비교와 관리도 분석, 모델 7종과 규칙 3종의 세 가지 검증 방식(같은 기간, 시간 순서, 주기적 재학습) 비교, 원인 진단과 보완 실험, 모델 해석, 검사 비용 분석, 개선 방안과 이상 대응 계획 수립, 재생 시뮬레이션 대시보드 구현의 순서로 수행하였다.");
doc.callout("주요 결과", [
  "1. 정상·불량 shot의 공정값 차이는 대부분 생산 구간 간 차이에서 비롯되었다. 같은 구간 안에서 비교하면 효과 크기의 최댓값이 0.39에서 0.11로 감소하였고, 인접한 두 구간의 데이터는 공정 변수만으로도 거의 완전히 구별되었다(구별 분류기 AUC 0.94~1.00). SHAP 상위 변수에도 공장 습도·shot 순번 등 생산 시기를 반영하는 변수가 다수 포함되었다.",
  `2. 과거 데이터로 학습하여 이후 기간을 예측하는 시간 순서 평가에서 최근 10 shot 불량률 규칙(ROC-AUC 0.68)이 모델 7종(최고 0.60, 하이퍼파라미터 조정 후 0.63)보다 높았으며, 4개 평가 블록 모두에서 같은 결과였다. 50 shot마다 재학습하면 모델과 규칙이 같은 수준(0.714)이 되었고, 불량률 CUSUM 경보 시점에 재학습하면 재학습 횟수를 40% 줄이면서 비슷한 수준(0.711)을 유지하였다. 합성 데이터, 규칙과 모델의 결합, 시간 가중치의 효과는 없거나 작았으며, 시간 정보를 입력에 넣거나 학습 방식에 반영한 여섯 가지 방법도 시간 순서 평가에서 규칙(${num(e88t.recent_rate.roc_auc_mean, 3)})에 미치지 못하였다(최고 ${num(e88t[bestTime].roc_auc_mean, 3)}).`,
  `3. 불량률 11.9%에서 무검사와 전수검사의 손익분기 비용 비율(미검:검사)은 약 8.4:1이었다. 위험도(예측 불량 확률)가 높은 제품만 검사하는 선별검사와 검사 강도 전환은 5:1 이상에서 두 단순 방식 중 더 저렴한 쪽보다 비용이 ${simpleSaving} 낮았다. 모델 선별, 규칙 선별, 검사 강도 전환 간 차이는 통계적으로 유의하지 않아 규칙 대비 모델의 추가 가치는 확인되지 않았다. 불량 포착률 95%를 보장하려면 모델을 사용해도 제품의 ${pct(needInspect("et", 0.95), 0)}를 검사해야 했다.`,
  "4. 캐비티1의 불량률을 같은 구간의 캐비티2 수준으로 낮추면 불량이 37% 감소하는 것으로 추정되었다. 관리 범위(안) 준수 시의 감소 추정치 37~39%는 범위(안)가 이후 기간에서 재현되지 않았으므로 상한으로 해석하였으며, 인과 효과 확인을 위한 2^{4−1} 부분요인실험을 설계하였다.",
  "5. 공정 변수의 급변·범위 이탈 경보는 이후 불량 증가와 관련이 약했던 반면, 불량률 CUSUM 경보 후 50 shot의 불량률은 평균의 1.41배였다. 이에 따라 경고·주의·정보·기록의 4등급 경보와 이상 대응 계획(OCAP)을 수립하고 재생 시뮬레이션 대시보드에 구현하였다.",
]);
doc.h2("현장 적용 제언");
doc.numbered([
  "전수검사를 위험도 기반 선별검사로 전환하되, 불량률 CUSUM 경보 후 50 shot은 전수검사로 강화한다(검사 강도 전환). 검사 기준은 50 shot마다 직전 결과에서 총비용이 최소가 되는 값으로 갱신한다.",
  "선별의 위험도는 최근 10 shot 불량률 규칙으로 시작한다(모델과의 비용 차이가 유의하지 않음, 8.4절). 모델을 사용하는 경우 50 shot 주기 또는 불량률 경보 시점에 재학습한다.",
  "선별검사로 운영하더라도 무작위 감사 검사를 유지한다. 검사하지 않은 제품의 결과가 누락되면 규칙의 불량 포착률이 75%에서 58%로 낮아진다.",
  "캐비티1 금형 점검과 관리 범위(안)의 확인 실험을 우선 개선 과제로 한다. 관리 범위는 고정 규격이 아니라 주기적으로 재검증하는 운영 범위로 사용한다.",
]);
doc.p("모든 결과는 스크립트로 다시 생성할 수 있으며, 재실행 시 결과 파일이 바이트 단위로 일치함을 확인하였다(부록 B).");

// ── 1. 서론 ─────────────────────────────────────────────────────────────────────────
doc.pageBreak();
doc.h1("1. 서론");
doc.h2("1.1 배경과 목적");
doc.p("다이캐스팅은 용탕을 고압으로 금형에 주입하여 한 번의 주입(shot)으로 여러 제품을 생산하는 공정이다. 미성형·박리·기공·변형 등의 불량은 대부분 검사 단계에서 발견되므로, 공정 데이터로 불량을 사전에 예측할 수 있으면 검사 자원을 위험도가 높은 제품에 집중하고 공정 조건을 조기에 수정할 수 있다. 본 연구의 목적은 다음과 같다.");
doc.bullets([
  "공정·센서 데이터로 제품의 불량 여부(1단계)와 불량 유형(2단계)을 예측하고, 단순 규칙과 비교하여 실용성을 평가한다.",
  "관리도와 공정능력 분석으로 공정 안정성을 평가하고, 모델 해석 기법으로 불량과 관련된 공정 변수와 관리 범위(안)를 도출한다.",
  "검사 방식별 총비용을 비교하여 운영 방안을 정하고, 불량 개선 방안과 이상 발생 시 대응 계획을 수립한다.",
  "위 결과를 과거 데이터 재생 방식으로 시연하는 대시보드를 구현한다.",
]);
doc.h2("1.2 관련 연구");
doc.p(`다이캐스팅 결함 예측에 관한 선행 연구는 주로 shot 단위 공정 변수나 사출 속도·압력 파형을 입력으로 하는 분류 모델을 다룬다. 마그네슘 고압 다이캐스팅에서는 약 8,000 사이클의 공정 데이터로 SVM, Random Forest, AutoML을 비교하였고${cite("ijmc")}, 사출 속도·압력 파형에 동적 시간 워핑(DTW)을 적용한 시계열 분류도 보고되었다${cite("schmalzer")}. 본 연구와 같은 KAMP 데이터${cite("kamp")}를 사용한 분석도 있으나${cite("joshua", "kangmunju", "hansung")}, 대부분 무작위 분할로 성능을 평가하였다.`);
doc.p(`제조 데이터는 설비 마모, 원자재와 제품 구성의 변경, 작업자 차이 등으로 시간에 따라 분포가 달라지며, 이러한 개념 변화(concept drift)는 학습된 모델의 성능을 저하시킨다${cite("gama", "lu")}. 36개월간 수집한 산업 데이터에서도 분포 변화가 커질수록 모든 알고리즘의 정확도가 낮아지는 것으로 보고되었다${cite("jourdan")}. 공정 산업의 소프트 센서 연구에서는 이를 이동 창(moving window), 재귀적 갱신, 앙상블, 적시 학습(just-in-time learning) 등의 적응 기법으로 다루어 왔다${cite("kadlec")}. 학습 분포와 평가 분포의 차이는 공변량 이동, 사전확률 이동, 개념 변화로 구분되며${cite("morenotorres")}, 각각에 대해 중요도 가중치를 이용한 공변량 이동 보정${cite("shimodaira")}, 사전확률 보정${cite("saerens")}, 여러 환경에서 유지되는 관계만 학습하는 불변 학습${cite("arjovsky")}, 군집(구간) 효과를 무작위 효과로 분리하는 혼합효과 랜덤 포레스트${cite("hajjem")} 등이 제안되었다. 본 연구는 이 가운데 재학습 주기, 경보 기반 재학습, 공변량 이동 가중치, 불변 변수 선택, 사전확률 보정을 실험하였다(6장, 10장).`);
doc.h2("1.3 연구 질문");
doc.numbered([
  "예측 모델이 최근 검사 결과만 사용하는 단순 규칙보다 불량을 더 잘 찾는가?",
  "그렇지 않다면 원인은 무엇인가? (데이터 양, 시간에 따른 분포 변화)",
  "어떻게 보완할 수 있는가? (합성 데이터, 재학습, 규칙 결합, 최근 데이터 가중치, 시간 정보 활용)",
  "현장에서 어떻게 활용할 수 있는가? (검사 방식과 비용, 관리 범위, 경보와 조치)",
]);
doc.h2("1.4 분석 원칙");
doc.bullets([
  "**데이터 누수 방지:** 결측 대체, 표준화, 불균형 처리, 임계값 선택은 학습 데이터 안에서만 수행하였고, 같은 shot의 중복 기록은 제거하였다. 시간 순서 평가에서는 항상 과거 데이터로만 학습하였다.",
  "**세 가지 검증 방식:** ① 같은 기간(shot 단위 무작위 분할), ② 시간 순서(제품 유형별 5개 블록 중 앞 블록으로 학습하여 다음 블록 평가), ③ 주기적 재학습(평가 구간을 N shot 단위로 나누고 매번 그 이전 데이터로 다시 학습).",
  "**효과 크기 중심의 해석:** 생산 순서에 따른 자기상관으로 p-value가 과소 추정될 수 있으므로, 같은 구간 내 비교, 효과 크기, 구간별 방향 일치를 함께 검토하였다.",
  "**재현성:** 난수 시드를 42로 고정하고 모든 단계를 스크립트로 실행하였으며, 결과 파일을 저장소에 함께 보관하였다.",
]);
doc.p("본문에 사용한 지표, 관리도, 해석 기법의 정의는 부록 C에 정리하였다.");

// ── 2. 데이터 ───────────────────────────────────────────────────────────────────────
// 장마다 쪽을 넘기면 짧은 장 뒤에 빈 쪽이 많이 생겨(38쪽 중 6쪽이 절반 이상 빔), 요약·본문 시작·참고문헌·부록에서만 넘긴다
doc.h1("2. 데이터와 전처리");
doc.p(`KAMP(한국 인공지능 제조 플랫폼)의 「주조 품질보증 AI 데이터셋」${cite("kamp")} 원본(7,535행 × 57열)을 사용하였으며, 공식 배포 파일과 바이트 단위로 일치함(SHA-256)을 확인하였다. 각 행은 shot 하나에 해당하고, 공정 조건 14개, 센서 측정값 6개, 캐비티 2개 각각의 13개 불량 유형 수가 기록되어 있다.`);
doc.h2("2.1 정제");
doc.bullets([
  "**중복 기록 제거:** 같은 shot이 연속으로 두 번 기록된 행 2,918개(38.7%)를 제거하여 4,617 shot을 얻었다. 중복을 유지한 채 무작위로 분할하면 같은 shot이 학습과 평가에 함께 포함되어 성능이 과대평가된다(Random Forest ROC-AUC 0.76 → 0.94).",
  "**생산 구간:** shot 번호가 감소하는 지점을 재시작으로 보아 7개 구간으로 나누었다. 구간 1~3은 제품 유형 1, 구간 4~7은 제품 유형 2이다.",
  "**비정상 shot:** 고속 사출 속도·비스킷 두께·증압 상승 시간이 0이거나 사이클 타임이 중앙값의 2배를 넘는 shot 8개는 삭제하지 않고 표시만 하였다. 이들을 제외한 경우의 모델 성능 차이는 미미하였다(4장).",
  "**제품 단위 변환:** shot × 캐비티로 펼쳐 제품 9,234개(불량 1,144개, 12.4%)를 분석 단위로 하였다.",
  "**파생·이력 변수:** 주요 공정 변수 8개의 직전 대비 변화, 최근 10 shot 표준편차, 직전까지의 구간 내 중앙값 대비 편차와, 직전 1·10·50 shot 불량률을 모두 과거 정보만으로 계산하였다.",
]);
const runs = readCsv(R("eda", "strata_rates.csv")).filter((r) => r.factor === "run");
doc.table("생산 구간별 규모와 불량률", [
  { label: "구간", width: 2 }, { label: "제품 유형", width: 2.5, align: "center" }, { label: "shot 수", width: 3, align: "right" }, { label: "제품 수", width: 3, align: "right" }, { label: "불량 제품", width: 3, align: "right" }, { label: "불량률", width: 3, align: "right" },
], runs.map((r) => [r.level, Number(r.level) <= 3 ? "1" : "2", (r.n / 2).toLocaleString(), r.n.toLocaleString(), r.defects.toLocaleString(), pct(r.rate)]));
doc.p("구간별 불량률은 0.6%(구간 3)에서 21.9%(구간 5)까지 분포하였다. 구간 6은 4 shot으로 구성되어 해석에서 제외하였다.");
doc.h2("2.2 불량 유형 정의 (2단계 분류 대상)");
doc.p("13개 원래 유형을 5개 클래스로 통합하였다: 미성형(391), 박리(209), 기공(기포 포함, 253), 변형(171), 기타(얼룩·오염·찍힘 등 8종, 120). 한 제품에 여러 유형이 기록된 경우(24개)에는 건수가 많은 유형을, 건수가 같으면 미성형 → 박리 → 기공 → 변형 → 기타 순으로 지정하였다. 발생 건수가 적은 8개 유형은 유형별 학습 표본을 확보하기 위해 '기타'로 묶었다.");

// ── 3. 탐색 분석과 공정 안정성 ────────────────────────────────────────────────────────
doc.h1("3. 탐색 분석과 공정 안정성");
doc.h2("3.1 불량 유형과 층별 비교");
doc.figure(FIG("eda_pareto"), "불량 유형 파레토 (상위 4개 유형이 전체의 82.3%)");
doc.bullets([
  "**캐비티 간 차이:** 캐비티1의 불량률은 17.0%, 캐비티2는 7.8%였다. 구간을 통제한 Mantel-Haenszel 오즈비는 2.48(95% CI 2.17~2.84)이었으나 구간 간 이질성이 유의하였고(p<0.001), 구간 3·4에서는 차이가 없었다. 얼룩 106건은 모두 캐비티1에서 발생하였다.",
  "**유형 구성의 변화:** 불량 유형 구성은 제품 유형(Cramér's V 0.69)과 생산 구간(0.47)에 따라 크게 달랐다. 변형은 구간 1에서만, 기타는 구간 4·5에 집중되어 발생하였다.",
]);
doc.figure(FIG("eda_defect_rate_by_run"), "생산 구간·캐비티별 불량률");
doc.h2("3.2 정상·불량 shot의 공정값 차이");
doc.p("정상 shot과 불량 shot의 공정·센서 값을 전체 데이터에서 비교하면 효과 크기(rank-biserial)가 최대 0.39였으나, 같은 생산 구간 안에서 비교하면 최대 0.11로 감소하였다. 이는 공정값 차이의 상당 부분이 불량률이 높았던 시기와 낮았던 시기의 설정 차이를 반영함을 의미한다. 이 결과는 이후 시간 순서 평가에서 나타난 모델 성능 저하를 해석하는 근거가 된다. 다만 구간 간 설정 변화가 실제 원인일 가능성은 관측 데이터만으로 배제할 수 없다.");
doc.figure(FIG("eda_process_effects"), "정상 대비 불량 shot의 효과 크기: 전체 비교(파랑)와 같은 구간 내 비교(주황)");
doc.h2("3.3 관리도와 공정능력");
doc.bullets([
  `**p-chart(50 shot = 제품 100개 부분군)${cite("montgomery")}:** 제품 유형 1은 53개 부분군 중 22개, 유형 2는 39개 중 15개가 관리한계를 벗어났다. 불량률이 높은 시기(구간 1·5)와 매우 낮은 시기(구간 3·4)가 교대로 나타나 공정이 통계적 관리 상태에 있지 않은 것으로 판단된다.`,
  "**공정 변수 Xbar-R 관리도:** 관리한계 이탈 비율의 중앙값은 93%였다. 구간마다 수준이 달랐고(예: 주조 압력 1,050 → 1,150), 구간 안에서도 값이 서서히 변하였다(lag-1 자기상관 중앙값 0.68). Shewhart 관리도의 독립성 가정이 성립하지 않으므로 공정 변수 경보에는 다른 기준이 필요하다(9장).",
  "**공정능력:** 공기압의 Pp는 1.63, Ppk는 1.55로 규격(3~9) 대비 여유가 있었다. 군내 표준편차로 계산한 Cp는 28.8로, 부분군 사이의 드리프트를 반영하지 못해 능력을 과대평가하므로 전체 표준편차 기준의 Pp·Ppk를 기준으로 판단하였다.",
  `**불량률 CUSUM:** 작은 불량률 변화를 탐지하는 CUSUM${cite("page")}(k=0.25, h=8, 경보 후 재설정)은 고불량·저불량 구간에서 경보가 밀집하여 재학습 시점의 후보가 되었다(6.3절에서 EWMA${cite("roberts")}와 비교).`,
]);
doc.figure(FIG("spc_p_chart"), "제품 유형별 p-chart (50 shot 부분군)");
doc.figure(FIG("spc_cusum_defect"), "불량률 CUSUM 관리도");

// ── 4. 1단계 모델 ───────────────────────────────────────────────────────────────────
doc.h1("4. 불량 여부 예측 (1단계)");
doc.p(`입력 변수는 공정 조건 14개, 센서 측정값 6개, 제품 유형, 캐비티, shot 번호이다. 표 형식 데이터에서 성능이 높은 트리 계열${cite("grinsztajn")}을 중심으로 모델 7종(Logistic Regression, Decision Tree, Random Forest${cite("breiman")}, Extra Trees${cite("geurts")}, XGBoost${cite("xgboost")}, LightGBM${cite("lightgbm")}, MLP)과 비교 기준 규칙 3종(무작위, 캐비티별 불량률, 최근 10 shot 같은 캐비티 불량률)을 세 가지 검증 방식으로 비교하였다. 불균형은 Class Weight로 처리하였다. 모델이 출력한 제품별 불량 확률을 위험도라 하고, 평가 지표로는 위험도 순위의 ROC-AUC와 위험도 상위 20%를 검사할 때 전체 불량 중 발견되는 비율(불량 포착률)을 사용하였다. 규칙은 같은 캐비티의 직전 10 shot 불량률을 위험도로 사용한다.`);
const s1 = readCsv(R("stage1", "metrics_summary.csv")).filter((r) => r.experiment === "main");
const s1p = readCsv(R("stage1", "metrics_pooled.csv")).filter((r) => r.design === "retrain_50");
const m1 = by(s1, (r) => `${r.design}:${r.model}`);
const m3 = by(s1p, (r) => r.model);
const cellOf = (r) => (r ? `${num(r.roc_auc_mean ?? r.roc_auc, 3)} / ${pct(r.capture_20_mean ?? r.capture_20, 0)}` : "–");
doc.table("1단계 성능 비교 (ROC-AUC / 상위 20% 불량 포착률, ①② fold 평균, ③ 평가 구간 합산)", [
  { label: "방법", width: 5.2 }, { label: "① 같은 기간", width: 3.6, align: "right" }, { label: "② 시간 순서", width: 3.6, align: "right" }, { label: "③ 50 shot 재학습", width: 3.8, align: "right" },
], ["logreg", "tree", "rf", "et", "xgb", "lgbm", "mlp", "recent_rate", "cavity_rate", "random"].map((m) => [MODEL[m], cellOf(m1[`same_term:${m}`]), cellOf(m1[`time_order:${m}`]), cellOf(m3[m])]));
doc.bullets([
  "① 같은 기간 평가에서는 XGBoost(0.76 / 52%)가 최근 불량률 규칙(0.73 / 48%)보다 높았다.",
  `② 시간 순서 평가에서는 최근 불량률 규칙(0.68 / 40%)이 가장 높은 모델인 Extra Trees(0.60 / 33%)를 포함한 모든 모델보다 높았다. 4개 평가 블록 각각에서도 규칙이 모든 모델보다 높았으며, 가장 높은 모델과의 차이는 0.01~0.10이었다(모델의 fold 간 표준편차 0.03~0.08). 시간 순서를 지킨 교차검증으로 하이퍼파라미터를 조정한 경우(Optuna${cite("optuna")})에도 0.63 / 38%였다.`,
  "③ 50 shot마다 재학습한 경우 Extra Trees(0.714)와 규칙(0.714)이 같은 수준이었고, 재학습 간격이 500 shot이면 0.60으로 낮아졌다.",
  "Random Forest에 흔들림 파생 변수나 검사 이력 변수(2.1절)를 추가하거나 비정상 shot·결측을 제외해도 ② 시간 순서 평가의 ROC-AUC 변화는 0.01 이하였다.",
]);
doc.figure(FIG("stage1_design_gap"), "검증 방식별 1단계 성능 (같은 기간 대비 시간 순서)");
doc.figure(FIG("stage1_retrain"), "재학습 주기에 따른 1단계 성능");

// ── 5. 2단계 모델 ───────────────────────────────────────────────────────────────────
doc.h1("5. 불량 유형 예측 (2단계)");
doc.p("불량 제품 1,144개를 대상으로 5개 유형을 분류하였다. 1단계와 같은 분할을 사용하고 학습 데이터만 불량 제품으로 한정하였다. 운영 단계에서는 1단계에서 선별된 제품에 예상 유형과 점검 항목을 함께 제시한다.");
const s2 = by(readCsv(R("stage2", "metrics_summary.csv")), (r) => `${r.design}:${r.model}`);
const s2p = by(readCsv(R("stage2", "metrics_pooled.csv")).filter((r) => r.design === "retrain_50"), (r) => r.model);
doc.table("2단계 Macro-F1 (①② fold 평균, ③ 평가 구간 합산)", [
  { label: "방법", width: 6 }, { label: "① 같은 기간", width: 3.4, align: "right" }, { label: "② 시간 순서", width: 3.4, align: "right" }, { label: "③ 50 shot 재학습", width: 3.6, align: "right" },
], ["rf", "et", "xgb", "logreg", "type_group_mode", "type_mode"].map((m) => [MODEL[m], num(s2[`same_term:${m}`]?.macro_f1_mean), num(s2[`time_order:${m}`]?.macro_f1_mean), num(s2p[m]?.macro_f1)]));
doc.bullets([
  "① 같은 기간 평가에서 Random Forest(0.58)는 비교 기준(0.10, 0.26)보다 높았다. ② 시간 순서 평가에서는 가장 높은 Extra Trees도 0.34로, 제품 유형·캐비티별 최다 유형 기준(0.26)과의 차이가 작았다.",
  "② 시간 순서 평가에서 성능 저하가 가장 큰 유형은 기타(F1 0.65 → 0.13)였다. 기타는 구간 4·5에서만 발생하여 학습 기간에 관측되지 않은 유형이며, 실제 기타의 65%가 기공으로 예측되었다.",
  "50 shot마다 재학습하면 Macro-F1이 0.51로 높아져, 재학습의 효과가 1단계보다 컸다.",
  "시간 순서 평가에서 위험도 상위 20%를 검사할 때 1단계 규칙과 2단계 Random Forest를 연결하면 전체 불량의 40%를 찾고, 그중 42%의 유형을 맞혔다(전체 불량 대비 17%).",
]);
doc.figure(FIG("stage2_class_f1"), "검증 방식별 유형별 F1");

// ── 6. 추가 실험 ───────────────────────────────────────────────────────────────────
doc.h1("6. 원인 진단과 보완 실험");
doc.p("4·5장의 결과를 설명하고 보완하기 위하여 다음 순서로 실험하였다: 데이터 양의 영향(6.1), 기간별 분포 변화(6.2), 재학습 시점(6.3), 규칙과 모델의 결합(6.4), 최근 데이터 가중치(6.5), 시간 정보의 활용(6.6).");
doc.h2("6.1 합성 데이터 생성 비교");
doc.bullets([
  `① 같은 기간 평가에서 불균형 처리·합성 기법(SMOTE 계열${cite("smote")}, 무작위 복제, 잡음 추가, Gaussian Copula, CTGAN${cite("ctgan")})은 순위 성능을 개선하지 못하였다(최대 +0.002). Recall의 상승은 판정 기준의 이동에 따른 것이었다.`,
  "② 시간 순서 평가에서는 새로운 값을 생성하는 기법의 성능이 증강하지 않은 경우(0.57)보다 낮았다: Copula 0.43, CTGAN 0.48, 잡음 추가 0.49.",
  "잡음을 shot 번호에만 추가하면 성능 변화가 없었고(0.57), 공정 변수에 추가하면 낮아졌다(0.475). 합성 값을 실제 관측값으로 대체해도 개선되지 않았다. 따라서 성능 저하의 원인은 비현실적인 합성 값이 아니라, 과거 불량 패턴을 주변 공정 조건으로 확장한 것이 이후 기간의 패턴과 맞지 않은 데 있는 것으로 해석된다.",
]);
doc.figure(FIG("e81_synthetic_stage1"), "불균형 처리·합성 데이터 기법별 1단계 성능");
doc.h2("6.2 기간별 분포 변화 진단");
doc.bullets([
  `두 기간의 데이터를 구별하도록 분류기를 학습하는 방법(adversarial validation, 부록 C)으로 분포 차이를 측정하였다. 인접 구간 4쌍과 ② 시간 순서 평가의 모든 fold에서 학습 기간과 평가 기간을 구별하는 AUC가 1.00이었다(공정 변수만 사용 시 0.94~1.00). 즉 두 기간의 데이터가 거의 완전히 구별될 만큼 분포가 달랐으며, 이는 시간에 따라 데이터 분포가 달라지는 개념 변화${cite("gama")}에 해당한다.`,
  "분포 변화가 가장 큰 변수는 냉각수 압력(PSI 11.7~17.8)과 공장 온습도였다.",
  "구간별로 산출한 SHAP 중요도 순위의 상관계수 중앙값은 0.68이었고, 상위 5개 변수 중 공통 변수는 평균 2개였다. 즉 불량과 관련된 변수 자체도 시기에 따라 달라졌다.",
]);
doc.figure(FIG("e84_drift_psi"), "인접 구간 간 변수별 분포 변화(PSI)");
doc.h2("6.3 관리도 경보 기반 재학습");
const e82 = by(readCsv(R("experiments", "e82_alarm_retrain_pooled.csv")).filter((r) => r.model === "et"), (r) => r.design);
const e82Labels = { never: "재학습 없음", fixed_200: "200 shot마다", fixed_100: "100 shot마다", fixed_50: "50 shot마다", alarm_defect_ewma: "경보: 불량률 EWMA", alarm_defect_cusum: "경보: 불량률 CUSUM", alarm_process_cusum: "경보: 공정 변수 CUSUM" };
doc.table("재학습 시점별 성능 (Extra Trees, 평가 구간 합산)", [
  { label: "재학습 시점", width: 5.5 }, { label: "ROC-AUC", width: 3, align: "right" }, { label: "상위 20% 포착", width: 3.5, align: "right" }, { label: "재학습 횟수", width: 3, align: "right" },
], Object.entries(e82Labels).map(([k, label]) => [label, num(e82[k]?.roc_auc, 3), pct(e82[k]?.capture_20, 0), e82[k]?.retrains ?? "–"]));
doc.bullets([
  "재학습하지 않은 경우 ROC-AUC는 0.457로 무작위 수준보다 낮았으며, 재학습 빈도가 높을수록 성능이 높아졌다.",
  "불량률 CUSUM 경보 시점에 재학습하면 44회의 재학습으로 0.711을 기록하여, 50 shot 고정 주기(73회, 0.714)와 비슷한 성능을 40% 적은 재학습으로 달성하였다.",
  "공정 변수 CUSUM 경보는 성능이 가장 높았으나(0.725) 약 10 shot마다 경보가 발생하여(343회) 경보로서의 실용성이 낮았다. 이는 공정값의 자기상관에 기인한다.",
]);
doc.figure(FIG("e82_alarm_retrain_compare"), "재학습 시점별 성능: 고정 주기와 관리도 경보");
doc.h2("6.4 규칙과 모델 점수의 결합");
doc.p("규칙과 모델 점수의 결합(순위 평균, Stacking)은 ② 시간 순서 평가에서 모델 단독보다 높았으나(0.674, 0.662 vs 0.603) 규칙(0.683)보다는 낮았고, ③ 재학습 평가에서는 두 방법 모두보다 낮았다. 최근 불량률을 모델의 입력 변수로 추가한 경우에도 효과가 없었다.");
doc.h2("6.5 최근 데이터 가중치");
doc.p("100 shot마다 재학습할 때 최근 500 shot만 학습에 사용하면 ROC-AUC가 소폭 상승하였으나(+0.014), 시간 가중치(반감기 200·500 shot)의 효과는 없었다. 500 shot마다 재학습하는 경우에는 학습 데이터 구성과 관계없이 0.60 내외였다. 따라서 학습 데이터의 선택 방식보다 재학습 빈도가 성능에 더 큰 영향을 미치는 것으로 나타났다.");
doc.h2("6.6 시간 정보를 활용한 학습");
doc.p(`6.2절의 분포 변화를 학습에 직접 반영하는 방법을 비교하였다. 기준 모델(Extra Trees, 4장과 같은 설정)에 대해 다음 다섯 가지를 바꾸었다: (1) 생산 순서와 구간 번호를 입력에 추가, (2) 흔들림 파생 변수와 검사 이력 변수 추가, (3) 공정·센서 원값 대신 구간 시작부터 직전 shot까지의 중앙값 대비 편차만 사용(구간 간 수준 차이 제거), (4) 학습 데이터에서 구간 간 분산 비율(η²)이 0.5를 넘는 변수를 제외(불변 학습${cite("arjovsky")}의 단순화된 형태), (5) 학습 데이터의 최근 20%와 유사한 표본에 큰 가중치를 부여(공변량 이동 보정${cite("shimodaira")}). 변수 선택과 가중치는 fold마다 학습 데이터 안에서만 계산하였다.`);
const e88cell = (key) => {
  const t = e88t[key];
  const r200 = e88r[`retrain_200:${key}`];
  const r50 = e88r[`retrain_50:${key}`];
  return [TEMPORAL[key], `${num(t.roc_auc_mean, 3)} / ${pct(t.capture_20_mean, 0)}`, `${num(r200.roc_auc, 3)} / ${pct(r200.capture_20, 0)}`, `${num(r50.roc_auc, 3)} / ${pct(r50.capture_20, 0)}`];
};
doc.table("시간 정보를 활용한 학습 방법별 성능 (ROC-AUC / 상위 20% 포착률, ② fold 평균, ③ 평가 구간 합산)", [
  { label: "방법", width: 5.4 }, { label: "② 시간 순서", width: 3.6, align: "right" }, { label: "③ 200 shot 재학습", width: 3.8, align: "right" }, { label: "③ 50 shot 재학습", width: 3.8, align: "right" },
], Object.keys(TEMPORAL).map(e88cell));
const dropped = e88s.filter((r) => r.dropped === "True" || r.dropped === true).map((r) => r.label);
const d = (key, design = "time") => (design === "time" ? e88t[key].roc_auc_mean - e88t.et.roc_auc_mean : e88r[`${design}:${key}`].roc_auc - e88r[`${design}:et`].roc_auc);
const signed = (v) => `${v >= 0 ? "+" : "−"}${num(Math.abs(v), 3)}`;
const spanOf = (design) => {
  const v = modelKeys.map((k) => e88r[`${design}:${k}`].roc_auc);
  return `${num(Math.min(...v), 3)}~${num(Math.max(...v), 3)}`;
};
doc.bullets([
  `② 시간 순서 평가에서 기준 모델 대비 변화는 생산 순서·구간 번호 추가 ${signed(d("et_time"))}, 흔들림·이력 변수 추가 ${signed(d("et_history"))}, 구간 기준 편차 ${signed(d("et_relative"))}, 시기 표시 변수 제외 ${signed(d("et_invariant"))}, 공변량 이동 가중치 ${signed(d("et_shift"))}였다. 가장 높은 방법(${TEMPORAL[bestTime]}, ${num(e88t[bestTime].roc_auc_mean, 3)})도 규칙(${num(e88t.recent_rate.roc_auc_mean, 3)})보다 낮았다.`,
  `전체 데이터 기준으로 구간 간 분산 비율이 0.5를 넘은 변수는 ${dropped.join(", ")}였다. 이 변수들은 구간마다 값이 거의 고정되어 있어 생산 시기를 식별하는 역할을 한다.`,
  `③ 재학습 평가에서도 같은 경향이었다. 50 shot마다 재학습하면 모든 방법이 ${spanOf("retrain_50")}로 규칙(${num(e88r["retrain_50:recent_rate"].roc_auc, 3)})과 비슷해졌고, 200 shot마다 재학습하면 ${spanOf("retrain_200")}로 규칙(${num(e88r["retrain_200:recent_rate"].roc_auc, 3)})보다 낮았다. 생산 순서 추가와 공변량 이동 가중치에 따른 변화(+0.01 내외)는 기준 모델의 fold 간 표준편차(${num(e88t.et.roc_auc_std, 3)})보다 작았다.`,
  `구간 기준 편차만 사용한 경우가 모든 평가에서 가장 낮았다. 이는 구간 간 수준 차이가 가까운 이후 기간의 불량률에 관한 정보를 포함하며, 구간 안의 변동만으로는 불량을 설명하기 어렵다는 3.2절의 결과와 일치한다. 이 데이터의 시간 정보는 반복되는 주기가 아니라 구간마다 한 번씩 나타나는 수준 변화이므로, 시간 변수를 입력에 추가하는 방식으로는 이후 기간으로 일반화되지 않으며, 최근 결과를 반영하는 재학습이나 규칙이 더 효과적인 것으로 판단된다.`,
]);
doc.figure(FIG("e88_temporal_compare"), "시간 정보를 활용한 학습 방법별 성능");
doc.h2("6.7 소결");
doc.p("이 데이터에서 시간 순서 평가의 성능 저하는 데이터 양의 부족보다 생산 구간 간 분포 변화에서 비롯된 것으로 판단된다. 합성 데이터, 규칙과 모델의 결합, 시간 정보의 입력은 이 문제를 해소하지 못하였으며, 재학습 빈도가 성능에 가장 큰 영향을 주었다. 불량률 관리도 경보를 재학습 신호로 사용하면 재학습 횟수를 줄이면서 같은 수준의 성능을 유지할 수 있었다.");

// ── 7. 해석과 관리 범위 ─────────────────────────────────────────────────────────────
doc.h1("7. 모델 해석과 관리 범위");
doc.h2("7.1 SHAP 변수 중요도");
doc.p(`제품 유형별로 해석용 XGBoost(5-fold ROC-AUC 0.75 / 0.76)를 학습하여 SHAP${cite("shap")} 값을 계산하였다. 상위 변수에는 생산 시기를 반영하는 변수가 다수 포함되었다. 유형 1은 공장 습도(20%), 캐비티(12%), shot 순번(7%), 유형 2는 캐비티(18%), 고속 사출 속도(16%), shot 순번(9%)의 순이었다. 제품 유형별로 모델을 나눈 것은 유형에 따라 설정 수준이 크게 다르기 때문이다. 예를 들어 주조 압력의 평균은 유형 1이 1,060, 유형 2가 595로, 두 유형을 하나의 모델로 학습하면 불량과의 관계보다 유형의 차이가 중요도에 반영된다. 유형별 모델에서 주조 압력은 13위와 16위였다. 이러한 결과에 따라 대시보드의 판정 근거는 조정 가능 변수와 시기·환경 변수로 구분하여 제시하였다.`);
doc.figure(FIG("interp_shap_importance"), "제품 유형별 SHAP 변수 중요도 (색 = 특성요인 분류)");
doc.h2("7.2 관리 범위(안)와 검증");
doc.p(`조정 가능한 변수 중 SHAP 상위 8개에 대해 PDP(부분 의존도)${cite("friedman")}와 ICE${cite("ice")}에서 예측 불량 확률이 평균 이하인 가장 넓은 구간을 범위(안)로 정하고(사출성형 XAI 연구${cite("inha")}의 방식), 같은 생산 구간 안에서도 범위 밖 shot의 불량률이 높은지를 Mantel-Haenszel 오즈비${cite("mh")}로 검증하였다. 16개 후보 중 5개가 검증을 통과하였다.`);
const ranges = readCsv(R("interpret", "ranges_proposals.csv")).filter((r) => r.verdict === "candidate");
doc.table("관리 범위(안): 구간 내 검증 통과 변수", [
  { label: "제품 유형", width: 2 }, { label: "변수", width: 3.2 }, { label: "범위(안)", width: 2.6 }, { label: "범위 안 불량률", width: 2.6, align: "right" }, { label: "범위 밖", width: 2, align: "right" }, { label: "구간 내 오즈비 (95% CI)", width: 3.4, align: "right" }, { label: "같은 방향 구간", width: 2.2, align: "center" },
], ranges.map((r) => [r.Product_Type, r.label, r.range_label, pct(r.rate_in), pct(r.rate_out), `${num(r.cmh_or)} (${num(r.cmh_low)}~${num(r.cmh_high)})`, `${r.runs_agree}/${r.runs_tested}`]));
doc.bullets([
  "구간을 고려하지 않은 비교에서 차이가 가장 컸던 변수(유형 1 냉각수 압력, 유형 2 고속 사출 속도)는 구간마다 값이 거의 고정되어 있어(구간 간 분산 비율 89%, 97%) 구간 내 검증이 불가능하였다. 모델은 이러한 변수를 통해 불량률이 높았던 시기를 식별하는 것으로 해석된다.",
  "앞 60% 기간으로 도출한 범위는 뒤 40% 기간에서 재현되지 않았다. 따라서 관리 범위는 고정 규격이 아니라 주기적으로 재검증하는 운영 범위로 사용하는 것이 적절하다.",
]);
doc.figure(FIG("interp_pdp_ice_type2"), "제품 유형 2의 PDP·ICE와 관리 범위(안)");
doc.figure(FIG("interp_range_check"), "관리 범위(안) 검증: 구간 무시 비교와 같은 구간 내 비교");
doc.h2("7.3 불량 유형별 점검 항목과 특성요인도");
doc.p("유형별로 같은 생산 구간의 정상 shot과 공정값을 비교하여 시기 효과를 제거하고, 조정 가능 변수 중 차이가 큰 3개를 점검 항목으로 선정하였다.");
const checks = readCsv(R("interpret", "checklist_items.csv"));
doc.table("불량 유형별 점검 항목 (같은 구간 정상 대비)", [
  { label: "유형", width: 1.8 }, { label: "변수", width: 3 }, { label: "정상 대비", width: 1.8, align: "center" }, { label: "효과 크기", width: 2, align: "right" }, { label: "같은 방향 구간", width: 2.3, align: "center" }, { label: "현장 점검 항목", width: 5.7 },
], checks.map((r) => [r.type_label, r.label, r.direction, num(r.effect), `${r.runs_agree}/${r.runs}`, r.check_point]));
doc.p("변형은 구간 1에서만 발생하여 근거가 제한적이다. 위 결과와 관리 범위(안)를 특성요인도(설비·재료·방법·환경·금형)에 표시하면 다음과 같다.");
doc.figure(FIG("report_fishbone"), "데이터 근거를 표시한 불량 특성요인도");

// ── 8. 검사 운영과 비용 ─────────────────────────────────────────────────────────────
doc.h1("8. 검사 운영과 비용");
doc.p(`총비용은 검사 수 × 검사 비용 + 놓친 불량 수 × 미검 비용으로 정의하였다${cite("stevenson")}. 단가는 가정값이므로 검사 비용을 1로 두고 미검 비용의 배수(비용 비율)를 1:1에서 20:1까지 변화시켰다. 평가는 ③ 50 shot 재학습 예측을 50 shot 로트로 나누고, 로트마다 과거 로트의 결과만으로 임계값, 샘플링 계획, 보정을 다시 정하는 방식으로 수행하였다(평가 제품 6,986개, 불량률 11.9%). 비교한 검사 방식은 전수검사, 무검사, 위험도 상위 제품을 검사하는 모델 선별과 규칙 선별, 평상시에는 모델로 선별하고 불량률 경보 후 50 shot은 전수검사하는 검사 강도 전환, 과거 불량률이 손익분기를 넘는 캐비티만 전수검사하는 캐비티 규칙, 샘플링 검사(8.1절)이다.`);
doc.table("비용 비율별 최소 비용 검사 방식 (제품당 비용, 전수검사 = 1. 단순 방식은 무검사·전수검사 중 저렴한 쪽)", [
  { label: "미검:검사", width: 2.0, align: "center" }, { label: "최소 비용 방식", width: 3.6 }, { label: "제품당 비용", width: 2.2, align: "right" }, { label: "검사 비율", width: 2.0, align: "right" }, { label: "불량 포착", width: 2.0, align: "right" }, { label: "전수 대비 절감", width: 2.5, align: "right" }, { label: "단순 방식 대비 절감", width: 2.7, align: "right" },
], costBest.map((r) => [`${r.ratio}:1`, STRATEGY[r.best] ?? r.best, num(r.cost_per_part, 3), pct(r.inspect_rate, 0), pct(r.capture, 0), pct(r.saving_vs_full, 0), pct(r.saving_vs_simple, 0)]));
doc.bullets([
  "불량률이 11.9%이므로 비용 비율이 8.4:1(= 1/0.119) 미만이면 무검사의 총비용이 전수검사보다 낮았다. 따라서 선별검사의 효과는 전수검사가 아니라 두 단순 방식 중 더 저렴한 쪽과 비교해야 한다. 예를 들어 5:1에서 전수검사 대비 절감 48% 중 대부분은 검사를 하지 않는 것만으로 얻을 수 있으며, 무검사 대비 절감은 12%였다. 3:1 이하에서는 선별 방식도 대부분의 제품을 검사하지 않는 기준을 선택하였다.",
  "5:1 이상에서는 모델 선별과 규칙 선별의 비용이 가장 낮았고, 두 방식 간 차이는 유의하지 않았다(로트 bootstrap 차이 구간이 0을 포함). 8~10:1에서는 검사 강도 전환이, 15~20:1에서는 비용 최소 샘플링 검사가 같은 수준에 포함되었다. 표의 최소 비용 방식은 점추정 기준이며, 규칙 선별은 5:1 이상의 모든 비율에서 최소 비용 방식과 통계적으로 구별되지 않았다.",
  "미검 비용이 클수록 검사 비율이 80~90%로 증가하여 전수검사에 가까워졌으며, 20:1에서도 전수검사 대비 절감(7%)은 통계적으로 유의하였다.",
]);
doc.figure(FIG("cost_by_ratio"), "검사 방식별 제품당 비용과 검사 비율 (비용 비율 민감도)");
doc.figure(FIG("cost_uncertainty"), "제품당 비용의 불확실성 (로트 bootstrap 95% 구간)");
doc.h2("8.1 샘플링 검사 비교");
doc.p(`로트(제품 100개)에서 n개를 추출하여 불량이 c개 이하이면 합격, 초과하면 로트 전체를 검사하는 선별형 단일 샘플링을 비교하였다. 이 공정의 불량률에서는 일반적인 AQL(1~2.5%)로 설계하면 대부분의 로트가 불합격되므로, AQL 10%·LTPD 25%(α 5%, β 10%)로 설계하였다(n=55, c=9). 같은 검사량에서 샘플링 검사의 불량 포착률은 모델·규칙보다 낮았다. 계획 35개 중 모델보다 많은 불량을 찾은 계획은 3개였고, AQL 설계 계획은 68%를 검사하여 79%를 찾은 반면 모델·규칙은 87%를 찾았다. 샘플링 계획의 설계와 OC 곡선은 Montgomery${cite("montgomery")}를 따랐다.`);
doc.figure(FIG("sampling_capture"), "같은 검사량에서의 불량 포착률: 모델·규칙·검사 강도 전환과 샘플링 계획");
doc.h2("8.2 확률 보정");
doc.p(`보정된 확률 p에서는 p ≥ 1/비용 비율일 때 검사하는 것이 최적이다. Extra Trees의 평균 예측 확률은 13.6%로 실제 불량률(11.9%)에 가까웠고, Random Forest는 23.0%로 과대 추정되었다. Platt${cite("platt")}과 Isotonic${cite("zadrozny", "niculescu")} 보정은 모두 Brier score와 ECE를 낮추었으나(RF ECE 0.112 → 0.022), 비용 판정에 큰 영향을 준 경우는 확률이 과대 추정된 Random Forest였다(5:1 비용 0.683 → 0.538). 과거 비용 최소 임계값은 Isotonic 보정 후 1/비용 비율을 적용한 결과와 거의 같았다.`);
doc.figure(FIG("calibration_reliability"), "신뢰도 그림: 보정 전후 예측 확률과 실제 불량률");
doc.h2("8.3 미검사 제품의 결과 누락");
doc.p("분석 데이터는 전수검사 결과이므로 모든 제품의 불량 여부가 알려져 있다. 선별검사로 전환하면 검사하지 않은 제품의 결과를 알 수 없으므로 규칙의 입력(최근 불량률)도 검사한 제품만으로 계산해야 한다. 이를 모사한 결과, 10:1에서 규칙 선별의 불량 포착률은 75%에서 58%로 낮아졌고, 20:1에서는 비용이 전수검사보다 높아졌다(1.136). 따라서 선별검사 운영 시에는 무작위 감사 검사로 결과를 지속적으로 확보할 필요가 있다.");
doc.h2("8.4 도입 판단과 품질 기준");
doc.p(`예측 모델 기반 검사 시스템을 도입하면 설비 연동, 재학습, 감시 등의 구축·운영 비용이 추가된다. 그 효과는 전수검사가 아니라 추가 투자 없이 적용할 수 있는 최근 불량률 규칙과 비교하여 판단해야 한다. 5:1 이상의 비용 비율에서 모델 기반 방식(모델 선별과 검사 강도 전환 중 저렴한 쪽)의 제품당 비용은 규칙 선별보다 최대 ${num(maxRuleGap, 3)}(전수검사 비용의 ${pct(maxRuleGap, 1)}) 낮았고${ruleCheaper.length ? `, ${ruleCheaper.join("·")}에서는 오히려 높았다` : ""}. 이 차이에는 모델이 아닌 불량률 CUSUM 경보에 의한 검사 강화의 효과도 포함되며, 규칙 선별과 최소 비용 방식의 차이 구간은 모든 비율에서 0을 포함하였다.`);
doc.p("따라서 모델 기반 시스템은 연간 전수검사 비용 × 규칙 대비 제품당 비용 차이가 시스템의 연간 운영비와 구축비 상각액보다 클 때 타당하나, 본 데이터에서는 이 차이가 0과 구별되지 않았다. 실제 검사 단가, 생산량(데이터에 시각 정보가 없어 연간 환산이 불가능), 현재 검사 방식의 비용, 시스템 구축비 자료가 없으므로 금액 기준의 투자 회수 기간은 산출하지 않았다. 현장 적용은 규칙 선별, 불량률 CUSUM, 감사 검사로 시작하고, 추가 데이터가 축적된 후 규칙 대비 모델의 효과를 다시 평가하는 것이 적절하다.");
doc.p("비용 비율 대신 품질 기준(목표 불량 포착률)을 먼저 정하는 경우, 이를 달성하는 데 필요한 검사 비율은 다음과 같다.");
doc.table("목표 불량 포착률별 필요한 검사 비율 (③ 50 shot 재학습 예측 전체를 위험도 순으로 검사)", [
  { label: "목표 포착률", width: 3, align: "center" }, { label: "모델 (Extra Trees)", width: 3.4, align: "right" }, { label: "규칙: 최근 10 shot", width: 3.4, align: "right" }, { label: "무작위", width: 2.6, align: "right" }, { label: "출하 불량률", width: 4.2, align: "right" },
], [0.8, 0.9, 0.95].map((q) => [pct(q, 0), pct(needInspect("et", q), 0), pct(needInspect("recent_rate", q), 0), pct(needInspect("random", q), 0), pct(evalRate * (1 - q), 1)]));
doc.bullets([
  `포착률 95%를 보장하려면 모델을 사용해도 제품의 ${pct(needInspect("et", 0.95), 0)}를 검사해야 했다(규칙 ${pct(needInspect("recent_rate", 0.95), 0)}, 무작위 ${pct(needInspect("random", 0.95), 0)}). 높은 품질 기준에서는 선별검사로 줄일 수 있는 검사량이 작다.`,
  `포착률 95%에서도 출하 불량률(검사에서 발견한 불량은 제거된다고 가정)은 약 ${pct(evalRate * 0.05, 1)}이다. 고객 요구가 ppm 단위라면 검사 방식의 최적화만으로는 부족하며, 불량률 자체를 낮추는 개선(9장)이 우선되어야 한다.`,
  "이 표는 평가 기간 전체에 하나의 기준을 적용한 결과이며, 로트마다 기준을 다시 정하는 8장 본문의 방식과는 다르다. 품질 기준을 제약조건으로 두고 그 안에서 비용을 최소화하는 로트별 정책 설계는 향후 과제로 남긴다.",
]);

// ── 9. 불량 개선과 이상 대응 ────────────────────────────────────────────────────────
doc.h1("9. 불량 개선 방안과 이상 대응");
doc.p("데이터에 조치·정비 기록이 없으므로 본 장의 결과는 모두 같은 생산 구간 안에서 비교한 관측 데이터의 연관이며, 인과 효과는 실험 계획(9.2절)으로 확인해야 한다.");
doc.h2("9.1 개선 여지");
const lev = readCsv(R("improve", "levers_ranges.csv"));
const cav = readCsv(R("improve", "levers_cavity.csv"));
const cavExcess = cav.reduce((a, r) => a + r.excess, 0);
const cavDefects = cav.reduce((a, r) => a + r.defects, 0);
doc.table("개선 수단별 불량 감소 추정", [
  { label: "개선 수단", width: 6 }, { label: "추정 감소", width: 3, align: "right" }, { label: "근거", width: 7.6 },
], [
  ["캐비티1 금형을 캐비티2 수준으로", pct(cavExcess / cavDefects, 0), `초과 불량 ${Math.round(cavExcess)}개/${cavDefects}개, 구간 6을 제외한 6개 구간 중 4개에서 캐비티1이 높음`],
  ...lev.map((r) => [`관리 범위(안) 준수 · 유형 ${r.Product_Type}`, pct(r.reduction, 0), `불량률 ${pct(r.actual_rate)} → ${pct(r.in_range_rate)} (95% 구간 ${pct(r.reduction_low, 0)}~${pct(r.reduction_high, 0)})`]),
  ["재가동·기록 중단 직후 shot 관리", "효과 없음", "오즈비 0.91 (0.66~1.25)"],
]);
doc.figure(FIG("improve_golden"), "불량률이 가장 낮은 구간과 가장 높은 구간의 운전 조건 비교 (가설)");
doc.h2("9.2 확인 실험 계획");
const doe = readCsv(R("improve", "doe_factors.csv"));
doc.p(`관측 데이터로는 운전 조건의 효과와 시기의 효과를 분리할 수 없으므로, 관리 범위(안)와 최우수 구간 조건을 요인으로 하는 2^{4−1} 부분요인실험${cite("doe")}(8개 조건, 해상도 IV)을 제안한다. 조건당 143 shot(유형 1), 122 shot(유형 2)이면 불량률 30% 감소를 검정력 80%로 확인할 수 있다.`);
doc.table("실험 요인과 수준", [
  { label: "유형", width: 1.5, align: "center" }, { label: "요인", width: 1.3, align: "center" }, { label: "변수", width: 3.2 }, { label: "현재", width: 2.2, align: "right" }, { label: "개선안", width: 2.2, align: "right" }, { label: "근거", width: 6.2 },
], doe.map((r) => [r.Product_Type, r.factor, r.label, Number(r.current.toPrecision(4)), Number(r.improved.toPrecision(4)), r.source]));
doc.h2("9.3 경보 규칙과 이상 대응 계획(OCAP)");
doc.p(`경보는 발생 빈도가 낮고 발생 후 실제로 불량이 증가해야 유용하다. 비교 결과 공정 변수 급변·관리 범위 이탈 경보 후의 불량 배수는 같은 구간 평균 대비 대부분 0.5~1.3배로, 불량 증가를 예고하지 못하였다. 반면 불량률 CUSUM 경보는 100 shot당 0.8회 발생하였고, 경보 후 50 shot의 불량률은 전체 평균의 1.41배였으며 불량 shot의 26%를 포함하였다(유형 2). 경보 후에는 기공(유형 2) 또는 미성형(유형 1)의 비중이 증가하여, 해당 유형의 점검 항목을 우선 제시하는 근거가 되었다. 등급별 조치는 관리도 이상 시 대응 계획(OCAP)${cite("montgomery")}의 형식으로 정리하였다.`);
doc.figure(FIG("improve_alarm_rules"), "경보 규칙 비교: 100 shot당 경보 수와 경보 후 불량 배수");
const ocap = readCsv(R("improve", "alarms_ocap.csv"));
doc.table("경보 등급과 조치 (OCAP)", [
  { label: "등급", width: 1.6, align: "center" }, { label: "발생 조건", width: 4.6 }, { label: "즉시 조치", width: 6 }, { label: "해제", width: 4.4 },
], ocap.map((r) => [r.level, r.trigger, r.action, r.release]));

// ── 10. 대시보드 ───────────────────────────────────────────────────────────────────
doc.h1("10. 재생 시뮬레이션 대시보드");
doc.p("과거 생산 데이터를 shot 순서대로 재생하면서 관리도, 제품 위험도, 예상 불량 유형, 검사 목록, 경보를 운영 상황과 같이 표시하는 대시보드를 구현하였다. 화면은 Next.js(JavaScript, ECharts)로, 데이터 제공은 FastAPI로 구현하였다. 색·글꼴·간격 토큰과 밝은·어두운 테마로 구성된 디자인 시스템을 먼저 정의하고, 분석 그림과 같은 토큰을 사용하였다.");
doc.figure(FIG("report_architecture"), "현장 적용 구성도: 본 연구의 구현 범위와 현장 연동 시 추가할 부분");
doc.h2("10.1 구성");
doc.bullets([
  "**재생 시나리오:** 시작 구간 3개(유형 1 구간 2, 유형 2 구간 5·7)와 재학습 방식 3가지(없음, 50 shot마다, 불량률 경보 시)를 조합한 9개 시나리오이다. 모델은 항상 해당 시점 이전에 생산된 데이터로만 학습한다.",
  "**화면:** 운영 현황(상태 띠, 숫자 줄, p-chart, 공정 변수 I-MR 관리도, 분포와 현재 위치, 공정 변수 10개 칸, 경보 피드), 제품·검사(비용 비율에 따른 검사 목록, 판정 근거, 예상 유형과 점검 항목), 알람 센터(CUSUM, 조치 체크리스트, 원인 진단, 해제), 분석 요약, 설정의 5개 화면으로 구성하였다. 예상 유형은 시간 순서 정확도가 낮으므로(5장) '참고'로 표시하였다.",
  "**경보 체계:** 경고(불량률 CUSUM, 이후 50 shot 전수검사), 주의(위험도 상위 제품, 10 shot 단위로 묶음), 정보(관리 범위 밖 운전 지속), 기록(공정 변수 급변)의 4등급이다. 불량률이 손익분기보다 높은 시기에는 '전수검사 모드'로 표시하고 제품별 주의 알림을 생략한다.",
  `**화면 설계:** 품질 관리 화면의 관례에 따라 공정 변수는 개별값 관리도(I-MR, ±1σ·±2σ 구역, 관리한계 이탈과 한쪽 9개 연속 표시)${cite("montgomery")}와 최근 200 shot 히스토그램·정규곡선 위의 현재 shot 위치로 표시하였다. 평상시에는 회색조로 표시하고 경고와 범위 이탈에만 색을 사용하였다(고성능 HMI 원칙). 설명 문장은 '?' 도움말로 제공하고, 화면 문구는 한국어와 영어로 전환할 수 있다(재생 데이터의 모든 한국어 문구가 영어로 변환되는지 테스트로 확인). 공정 변수의 단위는 KAMP 자료에 없어 값 범위로 추정하였으며 화면에 '추정'으로 표기하였다.`,
  `**위험도:** 모델은 균형 가중(Class Weight)으로 학습하였으므로 예측 확률은 불량률 50%를 기준으로 한다. 화면의 위험도는 이 확률의 승산에 직전 200 shot 실제 불량률의 승산을 곱하여 50 shot마다 해당 시점의 불량률 기준으로 변환한 값이다(사전확률 보정${cite("saerens")}). 모델 확률이 50%이면 위험도는 최근 불량률과 같고, 제품 간 순위는 모델과 같다.`,
  "**검사 기준:** 50 shot마다 직전 결과에서 총비용이 최소가 되는 위험도 임계값을 사용하였다(8장과 같은 방식). 과거 결과가 부족한 초기에는 위험도 ≥ 1/비용 비율을 적용하였다.",
  "**구현 과정의 변경:** 초기 구현에서는 재생 시작(재학습) 시점에 학습 데이터의 뒤 20%로 맞춘 Isotonic 보정을 그대로 사용하였다. 그러나 시기가 바뀌면 확률이 한쪽으로 치우쳤고(실제 26% 구간에서 9%), 계단형 함수이므로 위험도가 몇 개 값(0%·100% 포함)에 집중되어 순위 정보가 손실되었다. 이에 검사 기준을 과거 로트의 비용 최소값으로, 위험도를 최근 불량률 기준으로 변경하였다(비교는 10.2절).",
]);
doc.figure(SHOT("dashboard_overview_dark"), "대시보드 운영 현황 화면 (경고 발생 중):상태 띠·숫자 줄, 불량률·공정 변수 관리도, 분포와 현재 위치, 공정 변수 칸", 15.5);
doc.figure(SHOT("dashboard_alarms"), "알람 센터: 조치 체크리스트, 원인 진단, 증가한 유형의 점검 항목", 15.5);
doc.figure(SHOT("dashboard_products"), "제품·검사 화면: 비용 비율별 검사 기준과 판정 근거(조정 가능 / 시기·환경 변수)", 15.5);
doc.h2("10.2 시뮬레이션 결과와 검증");
// 재생 평가: scripts/11_dashboard_data.py가 화면과 같은 검사 규칙(evaluate.py)으로 계산한 표
const replayEval = readCsv(R("dashboard", "replay_eval.csv"));
const replayCal = by(readCsv(R("dashboard", "replay_calibration.csv")), (r) => r.scenario);
const ev = (id, score, ratio = 10) => replayEval.find((r) => r.scenario === id && r.score === score && r.ratio === ratio);
const RETRAIN = { none: "재학습 없음", every_50: "50 shot마다", alarm: "경보 시" };
const replayIds = [...new Set(replayEval.map((r) => r.scenario))];
const span = (ids, score, key = "cost_per_part") => {
  const v = ids.map((id) => ev(id, score)[key]);
  const [lo, hi] = [Math.min(...v), Math.max(...v)].map((x) => num(x, 3));
  return lo === hi ? lo : `${lo}~${hi}`;
};
const group = (pt, run) => replayIds.filter((id) => id.startsWith(`t${pt}_r${run}_`));
doc.table("재생 결과 (재생 구간 전체, 비용 비율 10:1. 위험도 AUC는 화면 위험도, 모델 AUC는 보정 전 모델 확률의 순위 성능)", [
  { label: "시작 · 재학습", width: 3.8 }, { label: "불량률", width: 1.7, align: "right" }, { label: "평균 위험도", width: 2, align: "right" },
  { label: "AUC 모델 / 위험도 / 규칙", width: 4, align: "right" }, { label: "제품당 비용 모델 / 규칙", width: 3.4, align: "right" }, { label: "검사 비율 모델", width: 2.2, align: "right" },
], replayIds.map((id) => {
  const c = replayCal[id];
  const m = ev(id, "p");
  return [`유형 ${m.product_type} 구간 ${m.start_run} · ${RETRAIN[m.retrain]}`, pct(c.defect_rate), pct(c.mean_p),
    `${num(c.roc_auc_raw, 3)} / ${num(c.roc_auc_p, 3)} / ${num(ev(id, "rule").roc_auc, 3)}`,
    `${num(m.cost_per_part, 3)} / ${num(ev(id, "rule").cost_per_part, 3)}`, pct(m.inspect_rate, 0)];
}));
const stale = replayCal.t2_r5_none;
const meanOf = (rows, key) => rows.reduce((a, r) => a + r[key], 0) / rows.length;
const calRows = Object.values(replayCal);
const at10 = (score) => meanOf(replayEval.filter((r) => r.score === score && r.ratio === 10), "cost_per_part");
doc.bullets([
  `위험도의 평균은 대부분의 시나리오에서 실제 불량률과 근접하였다. 예외는 재학습 없이 구간 5에 진입한 유형 2(평균 위험도 ${pct(stale.mean_p)}, 실제 ${pct(stale.defect_rate)})로, 이전 기간에 학습한 모델이 시기 변화를 반영하지 못한 결과이다. 경보 시 재학습한 경우에는 ${pct(replayCal.t2_r5_alarm.mean_p)}였다.`,
  `10:1에서 제품당 비용(모델 위험도 / 규칙)은 유형 1 구간 2 시작이 ${span(group(1, 2), "p")} / ${span(group(1, 2), "rule")}, 유형 2 구간 7 시작이 ${span(group(2, 7), "p")} / ${span(group(2, 7), "rule")}로 모델이 규칙과 같거나 약간 낮았다. 불량률이 손익분기(1/10)보다 높은 유형 2 구간 5 시작은 ${span(group(2, 5), "p")} / ${span(group(2, 5), "rule")}로 규칙이 낮았으며, 전수검사에 가까운 운영이 최적이어서 절감 폭이 작았다.`,
  `모델 자체의 순위 성능은 분석 결과와 같은 경향을 보였다. 재학습하지 않은 경우가 가장 낮았고(유형 2 구간 5 시작, AUC ${num(stale.roc_auc_raw, 3)}), 경보 시 재학습(${num(replayCal.t2_r5_alarm.roc_auc_raw, 3)})과 최근 불량률 규칙(${num(ev("t2_r5_alarm", "rule").roc_auc, 3)})이 비슷하였다.`,
  `초기 구현(Isotonic 보정)과 비교하면 9개 시나리오 평균 위험도 AUC는 0.541에서 ${num(meanOf(calRows, "roc_auc_p"), 3)}로, Brier score는 0.229에서 ${num(meanOf(calRows, "brier"), 3)}로, 10:1 제품당 비용은 0.858에서 ${num(at10("p"), 3)}(규칙 ${num(at10("rule"), 3)})로 개선되었다. 초기 구현에서는 위험도의 31%가 0% 또는 100%에 집중되었다. 초기 구현의 수치는 이전 커밋(86323ea)의 재생 데이터를 같은 평가 코드로 계산한 값이다.`,
  "실제 Chrome 브라우저로 화면을 조작하는 시뮬레이션 테스트 13개를 통과하였다. 시험 항목은 재생 속도와 정지, 키보드 조작, 시나리오 전환, 한/영 전환과 유지, '?' 도움말, 공정 변수 칸 선택, 경고 → 확인 → 조치 보기 → 체크리스트, 표시값과 독립 계산의 일치, 화면의 검사 계산과 Python 재생 평가의 일치(54건), 9개 시나리오 전체 재생(오류 0건, 경고 배너 수와 경보 수 일치, 메모리 누수 없음)이다.",
]);

// ── 11. 결론 ───────────────────────────────────────────────────────────────────────
doc.h1("11. 결론과 제언");
doc.h2("11.1 연구 질문에 대한 답");
doc.numbered([
  "**예측 모델이 단순 규칙보다 우수한가?** 같은 기간 평가에서는 모델이 우수하였다(0.76 vs 0.73). 그러나 과거 데이터로 이후 기간을 예측하는 시간 순서 평가에서는 최근 불량률 규칙이 모든 모델보다 우수하였으며, 재학습 빈도를 높여야 같은 수준에 도달하였다.",
  "**원인은 무엇인가?** 데이터 양보다 시간에 따른 분포 변화가 주된 원인으로 판단된다. 불량과 공정값의 관계는 대부분 생산 구간 간 차이를 반영하였고, 평가 기간의 데이터는 학습 기간과 구별될 만큼 분포가 달랐으며, 불량과 관련된 변수도 구간에 따라 달라졌다.",
  "**어떻게 보완할 수 있는가?** 재학습이 가장 효과적이었다. 불량률 CUSUM 경보 시점에 재학습하면 50 shot 고정 주기와 비슷한 성능을 40% 적은 재학습으로 얻었다. 합성 데이터, 규칙 결합, 시간 가중치, 시간 정보 입력의 효과는 없거나 작았다.",
  `**현장에서 어떻게 활용할 수 있는가?** 미검 비용이 검사 비용의 5배 이상이면 위험도 기반 선별검사와 경보 시 전수검사 강화를 결합한 운영이 무검사·전수검사 중 더 저렴한 방식보다 ${simpleSaving} 비용이 낮았다. 다만 규칙 선별과의 차이는 유의하지 않아, 투자가 필요한 모델 기반 시스템보다 규칙·관리도·감사 검사로 시작하는 것이 적절하다. 경보는 불량률로 발생시키고 공정 변수는 원인 진단에 사용하는 것이 적절하며, 캐비티1 금형 점검과 관리 범위(안)의 확인 실험이 우선 개선 과제이다.`,
]);
doc.h2("11.2 한계");
doc.bullets([
  "본 연구의 결론은 이 데이터의 시간 구조에 크게 의존한다. 데이터에는 날짜·시각이 없어 계절성이나 주·교대 단위의 주기를 식별할 수 없었고, 관측된 시간 변화는 반복되는 주기가 아니라 7개 생산 구간 사이의 수준 변화였다. 한 번씩만 관측된 구간 수준은 학습으로 일반화하기 어렵다. 생산 순서나 구간 번호를 입력으로 넣어도 평가 기간의 값은 학습 범위 밖에 있으며, 트리 모델은 학습 범위 밖으로 외삽하지 못한다(6.6절).",
  "구간 간 변화의 원인(설정 변경, 원자재 로트, 금형 상태, 정비 등)을 설명하는 변수가 데이터에 없어, 분포 변화를 사전에 예측하거나 원인별로 보정할 수 없었다.",
  "관리 범위와 개선 효과는 관측 데이터의 연관 분석 결과로 인과 관계가 아니며, 같은 데이터로 범위를 도출하고 검증하였으므로 추정치가 낙관적일 수 있다(이후 기간에서는 재현되지 않음).",
  "비용 단가는 가정값이며, 분석은 모든 제품의 검사 결과를 알고 있다고 가정하였다. 검사 단가·생산량·시스템 구축비 자료가 없어 금액 기준의 경제성은 산출하지 않았다(8.4절).",
  "선별검사 시 검사하지 않은 제품의 결과 누락은 규칙에 대해서만 모사하였으며(8.3절), 검사한 제품만으로 재학습할 때 모델이 받는 영향은 평가하지 않았다.",
  "데이터는 약 4,600 shot, 7개 생산 구간으로 기간이 짧아 결과의 일반화에 한계가 있다.",
  "재생 시뮬레이션은 저장된 데이터로 실시간 수집을 대체하였다.",
]);
doc.h2("11.3 향후 과제");
doc.p("11.2절의 한계를 고려할 때, 시간에 따른 변화에 대응하기 위해서는 모델 개선과 함께 변화를 설명하는 데이터의 확보가 필요하다.");
doc.bullets([
  "**데이터 수집:** shot별 시각, 원자재 로트, 금형 온도, 정비·조치 이력을 함께 수집하면 구간 간 변화를 설명 변수로 다룰 수 있다. 여러 주기에 걸친 데이터가 축적되면 계절성·교대 효과도 검토할 수 있다.",
  `**공정 파형 활용:** shot 단위 요약값 대신 사출 속도·압력의 고주파 파형을 확보하면 동적 시간 워핑 기반 시계열 분류${cite("schmalzer")} 등 공정 파형 자체의 형상을 이용하는 방법을 적용할 수 있다.`,
  `**구간 효과를 분리하는 모형:** 생산 구간을 무작위 효과로 두는 혼합효과 랜덤 포레스트${cite("hajjem")}, 여러 구간에서 유지되는 관계만 학습하는 불변 학습${cite("arjovsky")}은 구간 수가 충분할 때 효과를 기대할 수 있다. 본 연구의 단순화된 불변 변수 선택은 구간이 7개뿐인 조건에서 시험하였다.`,
  `**적응형 학습 체계:** 소프트 센서 분야의 적시 학습·이동 창 기법${cite("kadlec")}과 개념 변화 탐지${cite("lu")}를 결합하여, 현재 관리도 경보 기반 재학습을 자동화된 운영 절차로 발전시킬 수 있다.`,
  "**인과 확인과 현장 적용:** 제안한 2^{4−1} 실험으로 관리 범위(안)와 최우수 구간 조건의 인과 효과를 확인하고, 설비 OPC-UA(KAMP 패키지의 AAS 정보 모델) 실시간 수집과 대시보드를 연결하여 무작위 감사 검사를 포함한 선별검사를 시범 운영한다.",
]);

// ── 참고문헌 ─────────────────────────────────────────────────────────────────────────
doc.h1("참고문헌");
const uncited = REFERENCES.map(([key]) => key).filter((key) => !cited.includes(key));
if (uncited.length) throw new Error(`본문에서 인용하지 않은 참고문헌: ${uncited.join(", ")}`);
cited.forEach((key, k) => doc.reference(k + 1, REF_TEXT[key]));

// ── 부록 ───────────────────────────────────────────────────────────────────────────
doc.pageBreak();
doc.h1("부록 A. 주요 분석 결정");
doc.table("분석 과정의 주요 결정과 근거", [
  { label: "항목", width: 3.6 }, { label: "결정", width: 7 }, { label: "근거", width: 6 },
], [
  ["중복 기록", "같은 shot이 연속으로 두 번 기록된 2,918행 제거", "중복을 유지하면 같은 shot이 학습과 평가에 함께 포함되어 성능이 과대평가됨(ROC-AUC 0.76 → 0.94, 2.1절)"],
  ["비정상 shot", "속도·두께·상승 시간 0 또는 사이클 타임 2배 초과인 8 shot을 표시만 함", "제외 여부에 따른 모델 성능 차이가 미미함(4장)"],
  ["불량 유형 통합", "13개 유형을 5개 클래스로 통합. 여러 유형이 기록된 제품은 건수가 많은 유형(기공 = 기공+기포 합산)으로 지정", "발생 건수가 적은 유형의 학습 표본 확보(2.2절)"],
  ["검증 방식", "무작위 분할 외에 시간 순서 평가와 주기적 재학습 평가를 함께 수행", "운영 시에는 과거 데이터로 이후 기간을 예측해야 함(1.4절)"],
  ["공정능력", "Cp·Cpk(군내 σ)와 Pp·Ppk(전체 σ)를 함께 계산하고 Pp·Ppk로 판단", "부분군 사이 드리프트로 군내 σ가 과소 추정됨(Cp 28.8, 3.3절)"],
  ["공정 변수 경보", "경보 대신 원인 진단에 사용, 경보는 불량률 CUSUM", "자기상관으로 Xbar 이탈 93%, 급변·이탈 경보가 불량 증가를 예고하지 못함(9장)"],
  ["검사 기준", "로트마다 과거 결과의 비용 최소 임계값", "시기 변화로 고정 보정이 치우침(8.2절, 10장)"],
  ["대시보드 위험도", "모델 확률을 로트마다 최근 200 shot 불량률 기준으로 변환(사전확률 보정)", "시작 시점 Isotonic 보정은 계단형이어서 시기가 바뀌면 0%·100%에 집중되고 순위 정보가 손실됨(10.2절)"],
]);
doc.h1("부록 B. 재현 방법");
doc.p("저장소 루트에서 다음 명령으로 모든 결과를 다시 생성할 수 있다(uv, Node.js 20 필요). 모든 스크립트를 처음부터 다시 실행하여 결과 파일이 바이트 단위로 일치함을 확인하였다.");
doc.bullets([
  "uv sync → uv run python scripts/01_clean.py … 09_improve.py, 11_dashboard_data.py, 12_report_figures.py",
  "대시보드: uv run uvicorn app.api.main:app --port 8000, cd app/web && npm install && npm run dev",
  "테스트: uv run pytest (Python 92개), npm test (화면 계산·SPC·한영 문구 18개), npm run e2e (재생 시뮬레이션 13개, 전체 재생은 E2E_FULL=1)",
  "보고서 화면 캡처: API와 화면을 실행한 뒤 cd app/web && npm run shots",
  "보고서: cd report && npm install && npm run all (.docx와 PDF, LibreOffice 필요)",
]);
doc.h1("부록 C. 주요 용어");
doc.table("본문에 사용한 지표·기법", [{ label: "용어", width: 4.2 }, { label: "정의", width: 12.4 }], [
  ["shot · 캐비티", "shot은 금형에 한 번 주입하는 단위, 캐비티는 금형 안의 제품 자리이다. 이 데이터는 shot마다 캐비티 2개(제품 2개)이다"],
  ["생산 구간", "shot 번호가 다시 1부터 시작하는 지점으로 나눈 7개의 연속 생산 기간"],
  ["① ② ③ 검증 방식", "① 같은 기간: shot 단위 무작위 분할. ② 시간 순서: 제품 유형별로 5개 블록으로 나누어 앞 블록으로 학습하고 다음 블록을 평가. ③ 주기적 재학습: N shot마다 그 이전의 모든 데이터로 다시 학습"],
  ["위험도", "모델이 출력한 제품별 불량 확률(규칙은 같은 캐비티의 직전 10 shot 불량률). 검사 순위와 검사 여부 판정에 사용"],
  ["데이터 누수", "평가 데이터의 정보가 학습에 포함되어 성능이 과대평가되는 현상(예: 같은 shot의 중복 기록이 학습과 평가에 함께 포함)"],
  ["ROC-AUC", "불량 제품에 정상 제품보다 높은 점수를 줄 확률. 0.5는 무작위, 1은 완전한 순위"],
  ["상위 20% 포착률", "위험도 상위 20% 제품만 검사할 때 전체 불량 중 발견되는 비율"],
  ["Macro-F1", "유형별 F1(정밀도와 재현율의 조화평균)의 단순 평균. 빈도가 낮은 유형도 같은 가중치로 반영"],
  ["p-chart", "부분군 불량률의 관리도. 관리한계 = 중심선 ± 3 × 이항 표준편차"],
  ["CUSUM · EWMA", "기준과의 차이를 누적하거나(CUSUM, k = 허용 폭, h = 경보 기준) 최근 값에 큰 가중치를 주어(EWMA) 작은 변화를 탐지하는 관리도"],
  ["Cp·Cpk / Pp·Ppk", "규격 폭 대비 공정 산포. Cp·Cpk는 군내 표준편차, Pp·Ppk는 전체 표준편차 기준"],
  ["PSI", "두 기간의 변수 분포 차이를 나타내는 지표. 0.1 미만은 안정, 0.25 초과는 큰 변화"],
  ["Adversarial validation", "두 기간의 데이터를 구별하는 분류기를 학습하고, 그 AUC로 분포 변화의 크기를 측정하는 방법"],
  ["개념 변화 (concept drift)", "시간에 따라 입력 분포나 입력과 결과의 관계가 달라지는 현상"],
  ["공변량 이동 가중치", "학습 표본 중 평가 시기와 유사한 표본에 큰 가중치를 주어 입력 분포의 차이를 보정하는 방법"],
  ["구간 간 분산 비율 (η²)", "변수의 전체 분산 중 생산 구간 평균의 차이가 설명하는 비율. 1에 가까우면 구간마다 값이 거의 고정"],
  ["SHAP", "개별 예측을 변수별 기여(+는 위험 증가)로 분해한 값"],
  ["PDP · ICE", "한 변수만 변화시킬 때 예측의 평균적 변화(PDP)와 제품별 변화(ICE)를 나타낸 그림"],
  ["rank-biserial", "두 집단의 순위 차이에 기반한 효과 크기(−1~1). 0이면 차이 없음"],
  ["Mantel-Haenszel 오즈비", "구간별 2×2 표를 결합하여 구한 오즈비. 구간(시기)의 영향을 제거한 연관"],
  ["확률 보정", "모델 점수를 실제 불량률에 맞는 확률로 변환하는 것(Platt: 로지스틱 함수, Isotonic: 단조 계단 함수)"],
  ["사전확률 보정", "불량률(사전확률)이 바뀌었을 때 모델 확률의 승산에 새 불량률의 승산비를 곱해 확률을 조정하는 방법. 대시보드 위험도에 사용"],
  ["비용 비율", "놓친 불량 1개의 비용 ÷ 제품 1개의 검사 비용. 손익분기 임계값은 1/비용 비율"],
  ["OCAP", "Out-of-Control Action Plan. 관리도 경보 시 확인·조치 사항과 담당을 정한 계획"],
  ["출하 불량률", "검사 후 출하되는 제품 중 불량의 비율. 검사에서 발견한 불량을 모두 제거한다고 가정하면 불량률 × (1 − 불량 포착률)"],
  ["2^{4−1} 부분요인실험", "요인 4개의 효과를 16개 대신 8개 조건으로 추정하는 실험 계획(해상도 IV: 주효과가 2요인 교호작용과 교락되지 않음)"],
]);

// ── 저장 ───────────────────────────────────────────────────────────────────────────
/** 목차: 제목 1·2단계, 쪽 번호는 toc_pages.json에 있는 것만. */
function tableOfContents(headings) {
  const pages = existsSync(TOC_PAGES) ? (JSON.parse(readFileSync(TOC_PAGES, "utf8")).pages ?? {}) : {};
  const entries = headings.filter((h) => h.level <= 2).map((h) => ({ title: h.title, level: h.level, page: pages[h.title] }));
  return new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-2", cachedEntries: entries });
}

const document = new Document({
  creator: "DieCast-QA 팀",
  title: "다이캐스팅 공정 데이터를 활용한 불량 예측 모델 개발과 품질관리 방안 — 최종 보고서",
  features: { updateFields: true },
  styles: STYLES,
  numbering: NUMBERING,
  sections: [
    {
      properties: { page: { margin: { top: 1300, bottom: 1200, left: 1250, right: 1250 } } },
      footers: { default: pageFooter() },
      children: [...cover, tableOfContents(doc.headings), ...doc.children],
    },
  ],
});
mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, await Packer.toBuffer(document));
// 다음 npm run pdf가 쪽 번호를 찾을 제목 목록 (기존 쪽 번호는 유지)
const saved = existsSync(TOC_PAGES) ? JSON.parse(readFileSync(TOC_PAGES, "utf8")) : {};
writeFileSync(TOC_PAGES, JSON.stringify({ headings: doc.headings.filter((h) => h.level <= 2).map((h) => h.title), pages: saved.pages ?? {} }, null, 1));
console.log(`보고서: ${OUT} (그림 ${doc.figures}개, 표 ${doc.tables}개)`);
