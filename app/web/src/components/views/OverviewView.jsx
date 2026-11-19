"use client";

// ① 운영 현황: 상태 띠(AppShell) → 숫자 줄 → 불량률 관리도·변수 관리도 | 분포·알람 → 공정 변수 칸 →
// 불량 유형·캐비티·위험 제품. 설명은 '?' 도움말로 숨기고, 색은 이상할 때만 쓴다.
import Link from "next/link";
import { useMemo, useState } from "react";

import { Sparkline } from "@/components/charts/Mini";
import { PChartCard } from "@/components/charts/ControlCharts";
import { DistributionCard, ImrCard, VariableTiles } from "@/components/charts/SpcCharts";
import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import { AlarmBadge, BarRow, Card, RiskBadge, Stat, StatStrip } from "@/components/ui/primitives";
import { predictedType } from "@/lib/explain";
import { int, num, pct } from "@/lib/format";
import { pChartUcl, recentWindow } from "@/lib/metrics";
import { mean } from "@/lib/spc";

// 재생 초반에는 최근 불량률의 표본이 작아 한두 개 불량으로도 관리한계를 넘는다 → 이만큼 쌓인 뒤에만 강조
const MIN_KPI_SHOTS = 10;
const MIX_WINDOW = 300;
const TYPE_ORDER = ["short_shot", "exfoliation", "porosity", "deformation", "other"];

/** 최근 window shot의 50 shot 이동 불량률 (숫자 줄의 추세선). */
function rollingRates(shots, position, window = 300, span = 50) {
  const out = [];
  for (let i = Math.max(span - 1, position - window + 1); i <= position; i += 1) out.push(recentWindow(shots, i, span).rate);
  return out;
}

function OverviewStats() {
  const { scenario, position, ledger, ratio } = useReplay();
  const { t } = useI18n();
  const { shots, limits } = scenario;
  const stats = useMemo(() => ledger.summarize(shots, position), [ledger, shots, position]);
  const trend = useMemo(() => rollingRates(shots, position), [shots, position]);
  const recent = recentWindow(shots, position, 50);
  // 관리한계는 실제 표본(제품 수)으로 계산: 50 shot이 다 차기 전에는 더 넓다
  const ucl = pChartUcl(limits.p_chart.center, recent.parts);
  const enough = recent.shots >= MIN_KPI_SHOTS;
  const { h, k } = limits.cusum;
  const cu = Math.max(0, shots[position].cu);
  const from = Math.max(0, position - MIX_WINDOW + 1);
  const window = shots.slice(from, position + 1);
  const cav = [0, 1].map((j) => mean(window.map((s) => s.parts[j]?.y ?? 0)));
  const cycle = mean(shots.slice(Math.max(0, position - 49), position + 1).map((s) => s.x.Cycle_Time));
  const mode = ledger.inspectsAll(position) || shots[position].tight ? t("st.mode.all") : t("st.mode.threshold", { t: pct(ledger.thresholdAt(position)) });
  return (
    <StatStrip className="statstrip-6">
      <Stat
        label={t("st.rate50")}
        help={t("st.rate50.help")}
        value={pct(recent.rate)}
        sub={recent.shots < 50 ? t("st.rate50.small", { n: int(recent.shots), ucl: pct(ucl) }) : t("st.rate50.sub", { ucl: pct(ucl) })}
        alarm={enough && recent.rate > ucl}
      >
        <Sparkline values={trend} height={22} alarm={enough && recent.rate > ucl} />
      </Stat>
      <Stat label={t("st.inspect")} help={t("st.inspect.help")} value={`${pct(stats.inspectRate, 0)} · ${pct(stats.capture, 0)}`} sub={t("st.inspect.sub", { ratio, mode })} />
      <Stat label={t("st.cost")} help={t("st.cost.help")} value={num(stats.costPerPart)} sub={t("st.cost.sub", { none: num(stats.noInspectionCost) })} />
      <Stat label={t("st.cusum")} help={t("st.cusum.help", { h, k })} value={num(cu, 1)} alarm={cu >= h}>
        <span className={`meter${cu >= h ? " meter-hot" : ""}`}>
          <i style={{ width: `${Math.min(100, (cu / h) * 100)}%` }} />
        </span>
        <div className="stat-sub">{t("st.cusum.sub", { h })}</div>
      </Stat>
      <Stat label={t("st.cavity")} help={t("st.cavity.help")} value={pct(cav[0])} unit={`· ${pct(cav[1])}`} sub={t("st.cavity.sub")} />
      <Stat label={t("st.cycle")} help={t("st.cycle.help")} helpAlign="right" value={num(cycle, 2)} unit="s" sub={t("st.cycle.sub")} />
    </StatStrip>
  );
}

/** 알람 피드: 경고·주의·정보만 한 줄씩, 누르면 설명이 펼쳐진다. 기록은 알람 센터로 (ISA-18.2). */
export function AlarmFeed({ limit = 6 }) {
  const { scenario, position, alarmCenter, ledger } = useReplay();
  const { L, t } = useI18n();
  const [open, setOpen] = useState(null);
  const history = alarmCenter.history(position);
  const logs = history.filter((a) => a.level === "log").length;
  const items = useMemo(() => {
    const backend = history.filter((a) => a.level !== "log");
    const warnings = alarmCenter.warnings(scenario.shots, position, ledger);
    return [...backend, ...warnings].sort((a, b) => b.at - a.at || a.level_rank - b.level_rank).slice(0, limit);
  }, [history, alarmCenter, position, scenario, ledger, limit]);
  return (
    <Card
      title={t("feed.title")}
      help={t("feed.help")}
      flush
      actions={
        <Link href="/alarms" className="btn btn-ghost btn-sm">
          {t("feed.link")}
        </Link>
      }
      footer={logs ? <span className="caption">{t("feed.logs", { n: logs })}</span> : null}
    >
      {items.length ? (
        <ul className="feed">
          {items.map((a) => {
            const status = alarmCenter.status(a, position);
            const expanded = open === a.id;
            return (
              <li key={a.id}>
                <button type="button" className="feed-row" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : a.id)}>
                  <AlarmBadge level={status === "resolved" ? "resolved" : a.level} size="sm" />
                  <span className="feed-title">{L.text(a.title)}</span>
                  <span className="feed-shot">
                    {scenario.shots[a.at].run}·{scenario.shots[a.at].shot}
                  </span>
                </button>
                {expanded ? (
                  <div className="feed-detail">
                    <p>{L.text(a.message)}</p>
                    <Link href={`/alarms?id=${a.id}`}>{t("feed.open")}</Link>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="caption pad-x">{t("feed.empty")}</p>
      )}
    </Card>
  );
}

function DefectMix() {
  const { scenario, position, meta } = useReplay();
  const { L, t } = useI18n();
  const counts = useMemo(() => {
    const out = {};
    for (let i = Math.max(0, position - MIX_WINDOW + 1); i <= position; i += 1) {
      for (const part of scenario.shots[i].parts) if (part.y) out[part.type] = (out[part.type] ?? 0) + 1;
    }
    return out;
  }, [scenario, position]);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const rows = TYPE_ORDER.filter((code) => counts[code]).sort((a, b) => counts[b] - counts[a]);
  const max = Math.max(1, ...rows.map((r) => counts[r]));
  return (
    <div className="mini-panel">
      <div className="mini-head">
        <h3>{t("mix.title")}</h3>
        <span className="card-meta">{t("mix.meta")}</span>
      </div>
      {rows.length ? (
        rows.map((code) => (
          <BarRow
            key={code}
            label={L.defectType(code, meta.type_labels[code])}
            value={counts[code]}
            max={max}
            color={`var(--series-${TYPE_ORDER.indexOf(code) + 1})`}
            text={`${counts[code]} · ${pct(counts[code] / total, 0)}`}
          />
        ))
      ) : (
        <p className="caption">{t("mix.none")}</p>
      )}
    </div>
  );
}

function CavityRates() {
  const { scenario, position } = useReplay();
  const { t } = useI18n();
  const window = scenario.shots.slice(Math.max(0, position - MIX_WINDOW + 1), position + 1);
  const rows = [0, 1].map((j) => {
    const ys = window.map((s) => s.parts[j]?.y ?? 0);
    return { cav: j + 1, rate: mean(ys), n: ys.reduce((a, b) => a + b, 0) };
  });
  const max = Math.max(...rows.map((r) => r.rate), 0.001);
  return (
    <div className="mini-panel">
      <div className="mini-head">
        <h3>{t("cav.title")}</h3>
        <span className="card-meta">{t("mix.meta")}</span>
      </div>
      {rows.map((r) => (
        <BarRow key={r.cav} label={t("cav.label", { c: r.cav })} value={r.rate} max={max} color="var(--text-secondary)" text={`${pct(r.rate)} · ${r.n}`} />
      ))}
    </div>
  );
}

function TopRisk() {
  const { scenario, position, ledger, meta, setSelected } = useReplay();
  const { L, t } = useI18n();
  const rows = useMemo(() => {
    const out = [];
    for (let i = Math.max(0, position - 49); i <= position; i += 1) {
      const shot = scenario.shots[i];
      shot.parts.forEach((part) => out.push({ i, shot, part }));
    }
    return out.sort((a, b) => ledger.score(b.part) - ledger.score(a.part)).slice(0, 5);
  }, [scenario, position, ledger]);
  return (
    <div className="mini-panel">
      <div className="mini-head">
        <h3>{t("toprisk.title")}</h3>
        <Link href="/products" className="card-meta">
          {t("toprisk.link")} →
        </Link>
      </div>
      <table className="table table-compact">
        <thead>
          <tr>
            <th>{t("col.shot")}</th>
            <th>{t("col.cavity")}</th>
            <th className="num">{t("col.risk")}</th>
            <th>{t("col.grade")}</th>
            <th title={t("type.hint")}>{t("col.type")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ i, shot, part }) => {
            const risk = ledger.risk(part, shot);
            const type = predictedType(part, meta.defect_types);
            return (
              <tr key={`${i}-${part.cav}`} className={risk === "high" ? "row-hl" : undefined} onClick={() => setSelected({ i, cav: part.cav })}>
                <td>
                  <Link href="/products" onClick={() => setSelected({ i, cav: part.cav })}>
                    {shot.run}·{shot.shot}
                  </Link>
                </td>
                <td>{part.cav}</td>
                <td className="num">{pct(ledger.score(part))}</td>
                <td>
                  <RiskBadge risk={risk} />
                </td>
                <td>{L.defectType(type.code, type.label)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function OverviewView() {
  const { scenario } = useReplay();
  const { t } = useI18n();
  const [variable, setVariable] = useState("Casting_Pressure");
  if (!scenario) return null;
  return (
    <div className="stack">
      <h1 className="page-title">{t("ov.title")}</h1>
      <OverviewStats />
      <div className="grid-main">
        <div className="stack">
          <PChartCard />
          <ImrCard variable={variable} />
        </div>
        <div className="stack">
          <DistributionCard variable={variable} />
          <AlarmFeed />
        </div>
      </div>
      <Card title={t("vp.title")} help={t("vp.help")} meta={t("vp.meta")} flush>
        <VariableTiles selected={variable} onSelect={setVariable} />
      </Card>
      <Card flush className="card-row">
        <div className="mini-grid">
          <DefectMix />
          <CavityRates />
          <TopRisk />
        </div>
      </Card>
    </div>
  );
}
