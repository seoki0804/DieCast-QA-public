"use client";

// ③ 알람 센터: 등급별 수 → 불량률 CUSUM → 목록 | 상세(발생 조건·근거, 조치 체크리스트, 원인 진단, 해제 조건).
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { CusumCard, ProcessTrend } from "@/components/charts/ControlCharts";
import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import HelpTip from "@/components/ui/HelpTip";
import { AlarmBadge, Button, Card, RiskBadge, Segmented, Stat, StatStrip } from "@/components/ui/primitives";
import { predictedType } from "@/lib/explain";
import { int, num, pct } from "@/lib/format";

const LEVELS = ["critical", "warning", "info", "log"];

function useAllAlarms() {
  const { scenario, position, alarmCenter, ledger } = useReplay();
  return useMemo(() => {
    if (!scenario) return [];
    const warnings = alarmCenter.warnings(scenario.shots, position, ledger);
    return [...alarmCenter.history(position), ...warnings].sort((a, b) => b.at - a.at || a.level_rank - b.level_rank);
  }, [scenario, position, alarmCenter, ledger]);
}

function TypeMix({ mix, recent }) {
  const { L, t } = useI18n();
  return (
    <div>
      <h3 className="mini-title">
        {t("ad.mix", { n: recent })} <HelpTip text={t("ad.mix.help")} />
      </h3>
      {mix.map((m, k) => (
        <div key={m.type} className="mix-row">
          <span>{L.defectType(m.type, m.label)}</span>
          <span className="mix-bars">
            <i className="mix-before" style={{ width: `${m.before * 100}%` }} title={t("ad.mix.before", { v: pct(m.before, 0) })} />
            <i className="mix-now" style={{ width: `${m.now * 100}%`, background: `var(--series-${k + 1})` }} title={t("ad.mix.now", { v: pct(m.now, 0) })} />
          </span>
          <span className="num">
            {pct(m.before, 0)} → <b>{pct(m.now, 0)}</b>
          </span>
        </div>
      ))}
    </div>
  );
}

function AlarmDetail({ alarm }) {
  const { scenario, position, alarmCenter, acknowledged, acknowledge, actionChecks, toggleAction, meta, ledger } = useReplay();
  const { L, t } = useI18n();
  if (!alarm) {
    return (
      <Card title={t("ad.title")}>
        <p className="caption">{t("ad.empty")}</p>
      </Card>
    );
  }
  const shot = scenario.shots[alarm.detected_at];
  const status = alarmCenter.status(alarm, position);
  const checks = actionChecks[alarm.id] ?? [];
  const plan = alarm.level === "warning" ? meta.ocap.find((o) => o.level === "주의") : null;
  const actionList = alarm.actions ?? (plan ? [plan.action, plan.follow_up] : []);
  const range = alarm.variable ? scenario.meta.ranges.find((r) => r.variable === alarm.variable) : null;
  const evidence = alarm.evidence ?? plan?.evidence;
  return (
    <Card
      title={L.text(alarm.title)}
      meta={t("ad.meta", { shot: int(shot.shot), run: shot.run, status: t(`status.${status}`) })}
      actions={
        <>
          <AlarmBadge level={status === "resolved" ? "resolved" : alarm.level} />
          {alarm.level !== "log" && !acknowledged.has(alarm.id) ? (
            <Button variant="primary" className="btn-sm" onClick={() => acknowledge(alarm.id)}>
              {t("ad.ack")}
            </Button>
          ) : null}
        </>
      }
    >
      <div className="stack-sm">
        <p className="lead">
          {L.text(alarm.message)}
          {evidence ? <HelpTip text={`${t("ad.evidence")}: ${L.text(evidence)}`} /> : null}
        </p>
        {actionList.length ? (
          <div>
            <h3 className="mini-title">
              {t("ad.actions")} <HelpTip text={t("ad.actions.help")} />
            </h3>
            <ul className="action-list">
              {actionList.map((text, k) => (
                <li key={k}>
                  <label>
                    <input type="checkbox" checked={!!checks[k]} onChange={() => toggleAction(alarm.id, k)} />
                    <span>{L.text(text)}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {alarm.diagnosis ? (
          <>
            <div>
              <h3 className="mini-title">{t("ad.oor")}</h3>
              {alarm.diagnosis.out_of_range.map((o) => (
                <div key={o.variable} className="mix-row">
                  <span>
                    {L.variable(o.variable, o.label)} <span className="caption">{o.range}</span>
                  </span>
                  <span className="mix-bars">
                    <i className="mix-now" style={{ width: `${o.share * 100}%`, background: o.share >= 0.8 ? "var(--status-serious)" : "var(--text-muted)" }} />
                  </span>
                  <span className="num">{pct(o.share, 0)}</span>
                </div>
              ))}
            </div>
            <TypeMix mix={alarm.diagnosis.type_mix} recent={alarm.diagnosis.defects_recent} />
            {alarm.diagnosis.checks.map((group) => (
              <div key={group.type}>
                <h3 className="mini-title">{t("ad.grown", { type: L.defectType(group.type, group.label) })}</h3>
                <ul className="checks">
                  {group.items.map((item) => (
                    <li key={item.variable}>
                      <b>{L.text(item.check_point)}</b> — {t("ex.checkLine", { label: L.variable(item.variable, item.label), dir: L.text(item.direction) })}{" "}
                      <span className="caption">· {L.text(item.evidence)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </>
        ) : null}
        {alarm.level === "warning" ? (
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
              {alarm.parts.map(({ shot: s, part }) => {
                const type = predictedType(part, meta.defect_types);
                return (
                  <tr key={`${s.i}-${part.cav}`}>
                    <td>
                      {s.run}·{s.shot}
                    </td>
                    <td>{part.cav}</td>
                    <td className="num">{pct(ledger.score(part))}</td>
                    <td>
                      <RiskBadge risk="high" />
                    </td>
                    <td>{L.defectType(type.code, type.label)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}
        {alarm.variable ? <ProcessTrend variable={alarm.variable} range={range} height={140} /> : null}
        <p className="caption">
          <b>{t("ad.release")}:</b> {L.text(alarm.release ?? plan?.release ?? "-")}
          {alarm.release_at != null ? t("ad.releaseShot", { shot: int(scenario.shots[Math.min(alarm.release_at, scenario.shots.length - 1)].shot) }) : ""}
        </p>
      </div>
    </Card>
  );
}

function AlarmsContent() {
  const { scenario, position, alarmCenter, acknowledged } = useReplay();
  const { L, t } = useI18n();
  const params = useSearchParams();
  const [level, setLevel] = useState("all");
  const [selectedId, setSelectedId] = useState(params.get("id"));
  const alarms = useAllAlarms();
  if (!scenario) return null;
  const shown = alarms.filter((a) => level === "all" || a.level === level);
  // 고른 알람이 없으면 진행 중인 경고 → 가장 최근 알람 순으로 보여 준다 (상세가 빈 채로 열리지 않게)
  const selected =
    alarms.find((a) => a.id === selectedId) ??
    alarms.find((a) => a.level === "critical" && alarmCenter.status(a, position) === "active") ??
    alarms.find((a) => a.level !== "log") ??
    null;
  const counts = { critical: 0, warning: 0, info: 0, log: 0 };
  alarms.forEach((a) => (counts[a.level] += 1));
  return (
    <div className="stack">
      <h1 className="page-title">{t("al.title")}</h1>
      <StatStrip className="statstrip-4">
        {LEVELS.map((l) => (
          <Stat
            key={l}
            label={<AlarmBadge level={l} size="sm" />}
            value={int(counts[l])}
            sub={l === "warning" ? t("al.groups") : t("al.rate", { r: num((counts[l] / (position + 1)) * 100, 1) })}
          />
        ))}
      </StatStrip>
      <CusumCard />
      <div className="grid-main">
        <Card
          title={`${t("al.list")} (${shown.length})`}
          help={t("al.list.help")}
          flush
          actions={<Segmented size="sm" label={t("al.filter")} value={level} onChange={setLevel} options={[{ value: "all", label: t("al.all") }, ...LEVELS.map((l) => ({ value: l, label: L.level(l) }))]} />}
        >
          <div className="table-wrap tall">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("col.shot")}</th>
                  <th>{t("col.level")}</th>
                  <th>{t("col.content")}</th>
                  <th>{t("col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((a) => {
                  const status = alarmCenter.status(a, position);
                  return (
                    <tr
                      key={a.id}
                      className={a.id === selected?.id ? "row-selected" : undefined}
                      onClick={() => setSelectedId(a.id)}
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && setSelectedId(a.id)}
                    >
                      <td>
                        {scenario.shots[a.at].run}·{scenario.shots[a.at].shot}
                      </td>
                      <td>
                        <AlarmBadge level={a.level} size="sm" />
                      </td>
                      <td>
                        <b>{L.text(a.title)}</b>
                        {a.id === selected?.id ? <div className="caption">{L.text(a.message)}</div> : null}
                      </td>
                      <td>
                        {status === "resolved" ? <AlarmBadge level="resolved" size="sm" /> : t(`status.${status}`)}
                        {acknowledged.has(a.id) ? <span className="caption">{t("al.acked")}</span> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
        <AlarmDetail alarm={selected} />
      </div>
    </div>
  );
}

export default AlarmsContent;
