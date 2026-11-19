# DieCast-QA

다이캐스팅 공정 데이터를 활용한 불량 예측 모델 개발과 품질관리 방안 — AI 기반 생산운영관리 팀 프로젝트

- 최종 보고서: [docs/report/DieCast-QA_최종보고서.pdf](docs/report/DieCast-QA_최종보고서.pdf)
- 발표 자료: [docs/presentation/DieCast-QA_최종발표.pptx](docs/presentation/DieCast-QA_최종발표.pptx)
- 진행 상황과 결정 기록: [docs/ROADMAP.md](docs/ROADMAP.md)

## 개발 환경

[uv](https://docs.astral.sh/uv/)로 Python 3.12 환경을 고정한다.

```bash
uv sync                # .venv 생성 및 의존성 설치
uv run pytest          # 테스트
uv run ruff check .    # 린트
```

## 실행

```bash
uv run python scripts/01_clean.py    # 원본 CSV → data/processed/parts.csv
uv run python scripts/02_eda.py      # 탐색 분석·검정 → results/eda/, results/figures/eda_*.png
uv run python scripts/03_spc.py      # 관리도·공정능력 → results/spc/, results/control_limits.csv
uv run python scripts/04_stage1.py   # 1단계 모델(약 15분) → results/stage1/, results/predictions.csv.gz
uv run python scripts/05_stage2.py   # 2단계 유형 분류·연결 평가 → results/stage2/, results/predictions_stage2.csv.gz
uv run python scripts/06_experiments.py [실험 이름 …]   # 8장 추가 실험(전체 약 25분) → results/experiments/
uv run python scripts/07_interpret.py   # SHAP·PDP·ICE, 관리 범위, 유형별 점검 항목 → results/interpret/, results/shap_values.csv
uv run python scripts/08_cost.py        # 검사 방식·비용, 샘플링 검사(8.6), 확률 보정(8.7) → results/cost/, results/cost_params.csv
uv run python scripts/09_improve.py     # 불량 개선 여지, 실험 계획, 경보 규칙·대응 계획(OCAP) → results/improve/
uv run python scripts/11_dashboard_data.py   # 대시보드 재생 데이터(약 7분) → results/dashboard/, models/
uv run python scripts/12_report_figures.py   # 보고서 그림(특성요인도, 현장 적용 구성도) → results/figures/report_*.png
```

그림은 대시보드와 같은 디자인 토큰(`docs/design/tokens.json`)과 저장소의 Pretendard 글꼴(`assets/fonts/`, OFL)로 그린다.

## 최종 보고서

`docs/report/DieCast-QA_최종보고서.docx`(와 같은 내용의 PDF)는 결과 CSV·그림을 읽어 스크립트로 만든다.

```bash
cd report && npm install && npm run all   # .docx → PDF(LibreOffice) → 목차 쪽 번호 → 다시 빌드
cd report && npm run build                # .docx만 (목차 쪽 번호는 직전 PDF 기준, Word가 열 때 갱신)
```

보고서 화면 캡처는 `docs/report/images/`에 있고, API와 화면을 켠 뒤 `cd app/web && npm run shots`로 다시 찍는다
(`npm run shots -- dashboard_overview_dark`처럼 이름을 주면 그 화면만).

## 발표 자료

`docs/presentation/DieCast-QA_최종발표.pptx`(24장, 발표자 노트 포함)는 `cd report && npm run slides`로 만든다.
표·차트 숫자는 결과 CSV에서 읽고, 차트는 PowerPoint에서 바로 고칠 수 있는 차트 객체다.

프로젝트 제안서 보완본(연구 시작 전 기준, 교수님 피드백 반영)은 `cd report && npm run proposal`로 `docs/proposal/`에 만든다.

## 대시보드 (재생 시뮬레이션)

과거 생산 데이터를 shot 단위로 재생하면서 관리도·제품 위험도·예상 불량 유형·검사 목록·알람을 보여 준다.
디자인 기준은 [docs/design/DESIGN_SYSTEM.md](docs/design/DESIGN_SYSTEM.md), 토큰은
[docs/design/tokens.json](docs/design/tokens.json). Node.js 20 이상이 필요하다.

```bash
uv run uvicorn app.api.main:app --port 8000      # 터미널 1: API (results/dashboard/를 읽음)
cd app/web && npm install && npm run dev          # 터미널 2: 화면 → http://localhost:3000
cd app/web && npm test                            # 화면 계산 로직 테스트
```

- 재생 데이터(`results/dashboard/`)는 저장소에 들어 있어 API만 켜면 된다. 분석 결과를 바꿨으면
  `scripts/11_dashboard_data.py`로 다시 만든다.
- 화면: 운영 현황 · 제품·검사 · 알람 센터 · 분석 요약 · 설정.
- 시나리오: 시작 구간(유형 1 구간 2, 유형 2 구간 5·7) × 재학습(없음, 50 shot마다, 관리도 경보 시).
- 키보드: Space 재생/정지, ←/→ 한 shot, Shift+←/→ 50 shot, 1·2·5·0 속도.
- 특정 장면으로 바로 열기: `http://localhost:3000/alarms?scenario=t2_r5_alarm&at=400&theme=dark&lang=en`
  (`at` = 재생 위치, `theme` = light·dark, `lang` = ko·en). 화면 문구는 한국어·영어로 바꿀 수 있고, 설명은 제목 옆 '?'에 있다.
- 공정 변수 단위는 KAMP 자료에 없어 값 범위로 추정했다(`app/web/src/lib/variables.js`).

`shap_values.csv` (9,234행): `order`, `Cavity`, `Product_Type`, `model`(`xgb_interp`), `defect`, `p_defect`,
`base_value`, `shap_<변수>` 22개. 제품 유형별 해석용 XGBoost의 log-odds 단위 SHAP으로,
`base_value + SHAP 합 = logit(p_defect)`.

`parts.csv` (9,234행 × 70열, 제품 = shot × 캐비티 단위)

| 열 묶음 | 내용 |
|---|---|
| 식별 | `id`, `order`(생산 순서), `run`(생산 구간 1~7), `Product_Type`, `Shot`, `Cavity`, `is_abnormal` |
| 기본 입력 | 공정 조건 14개, 센서 측정값 6개 |
| 파생 (`drift`) | 주요 8개 변수 × `__diff1`(직전 대비 변화), `__std10`(최근 10 shot 표준편차), `__dev_med`(직전까지 중앙값 대비 편차) |
| 검사 이력 (`history`) | `hist_rate_1·10·50`(직전 N shot 불량률), `hist_cav_rate_10`(같은 캐비티 최근 10 shot) |
| 목표 | `defect`(0/1), `type5`(2단계 유형), 13개 불량 유형 원값 |

변수 묶음 목록은 `results/preprocess_report.json`의 `feature_sets`에 있다.

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `data/raw/` | 원본 CSV (수정 금지) |
| `data/processed/` | 정제 데이터 (`parts.csv`) |
| `src/diecast_qa/` | 분석 패키지 (정제·변수·모델·관리도·비용) |
| `scripts/` | 단계별 실행 스크립트 (`01_clean.py` …) |
| `tests/` | 기획서 수치 재현·누수 방지 테스트 |
| `models/` | 대시보드 재생 시작 시점의 모델 (`.joblib`, git 제외, `scripts/11_dashboard_data.py`가 만듦) |
| `results/` | 예측값, SHAP 값, 관리한계, 성능표, 그림 |
| `app/api/` | 대시보드 API 진입점 (FastAPI, 코드는 `src/diecast_qa/dashboard/`) |
| `app/web/` | 대시보드 화면 (Next.js, JavaScript, ECharts) |
| `report/` | 최종 보고서 생성기 (Node.js, docx) |
| `docs/report/` | 최종 보고서 .docx·PDF와 화면 캡처 |
| `assets/fonts/` | 그림용 Pretendard 글꼴 (OFL) |

## 데이터

KAMP 「주조 품질보증 AI 데이터셋」 `DieCasting_Quality_Raw_Data.csv` (7,535행 × 57열, 헤더 2줄).
**이 공개 저장소에는 원본 데이터(`data/raw/`), 정제 데이터(`data/processed/`), KAMP 가이드북을 넣지 않았다.**
KAMP(kamp-ai.kr)에서 데이터셋을 내려받아 `data/raw/DieCasting_Quality_Raw_Data.csv`로 두고 `scripts/01_clean.py`부터 실행한다.
분석 결과(`results/`), 보고서, 발표 자료는 포함되어 있으므로 데이터 없이도 결과를 보고 대시보드를 실행할 수 있다
(대시보드 모델은 `scripts/11_dashboard_data.py`가 만들며, 원본 데이터가 필요한 일부 테스트·스크립트는 데이터를 둔 뒤 실행한다).

출처 확인: KAMP에서 받은 공식 데이터셋 ZIP(`Dataset_주조 품질보증 AI 데이터셋.zip`)의
`data/DieCasting_Quality_Raw_Data.csv`와 바이트 단위로 같다 (SHA-256
`165bba739f68cae771fecb2ad53b722e4223a8f2c6674cff1cb0c7f3c8e12319`). 같은 데이터를 쓴 공개 GitHub
저장소에 올라온 파일도 같은 파일이다. KAMP 공식 가이드북의
사양(7,535행 × 57열, 1.43MB)과 기술통계표도 모두 일치한다. 공식 파일로 1~4단계를 처음부터 다시
실행해 모든 결과 파일이 그대로 재현되는 것을 확인했다 (2026-11-15).

`data/raw/kamp_package/`(이 저장소에는 없음): KAMP 데이터셋에 함께 들어 있는 설비 연동 설명 파일(공정·불량 데이터 없음).
현장 적용 구성도(11.3)에 참고한다. 받은 상태에서는 파일 이름이 서로 뒤바뀌어 있어 내용에 맞게 고쳤다.

| 파일 | 내용 |
|---|---|
| `engineering.csv` | 설비 태그 목록 (OPC-UA 노드 ID, 샘플링 주기) |
| `nodeset.xml` | OPC-UA 정보 모델 (UANodeSet) |
| `Die_Casting_Machine_AAS_Final.aasx` / `.xml` | 자산관리셸(AAS) 패키지와 그 안의 XML |
| `syscfg.json` | 엣지 게이트웨이 설정 (OPC-UA 서버 주소, 샘플링 100ms) |
