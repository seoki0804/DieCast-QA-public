"use client";

// ② 제품·검사: 검사 기준(비용 비율·점수) → 위험도 표 → 선택한 제품의 판정 근거·점검 항목.
import { useMemo } from "react";

import { InspectionTrend } from "@/components/charts/ControlCharts";
import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import HelpTip from "@/components/ui/HelpTip";
import { BarRow, Card, RiskBadge, Segmented, Stat, StatStrip } from "@/components/ui/primitives";
import { groupContributions, predictedType } from "@/lib/explain";
import { int, num, pct, sig, signed } from "@/lib/format";
import { SCORE_KEYS } from "@/lib/inspection";

const RATIOS = [3, 5, 8, 10, 15, 20];

function InspectionControls() {
  const { scenario, position, ledger, ratio, setRatio, scoreKey, setScoreKey } = useReplay();
  const { t } = useI18n();
  const s = useMemo(() => ledger.summarize(scenario.shots, position), [ledger, scenario, position]);
  const threshold = ledger.inspectsAll(position) ? t("ic.allMode") : Number.isFinite(ledger.thresholdAt(position)) ? pct(ledger.thresholdAt(position)) : t("ic.none");
  return (
    <Card title={t("ic.title")} help={t("ic.help")} flush>
      <div className="controls">
        <div className="control">
          <div className="control-label">{t("ic.ratio")}</div>
          <Segmented label={t("ic.ratioAria")} value={ratio} onChange={setRatio} options={RATIOS.map((r) => ({ value: r, label: `${r}:1` }))} />
        </div>
        <div className="control">
          <div className="control-label">{t("ic.score")}</div>
          <Segmented
            label={t("ic.score")}
            value={scoreKey}
            onChange={setScoreKey}
            options={Object.keys(SCORE_KEYS).map((value) => ({ value, label: value === "p" ? t("ic.model") : t("ic.rule"), title: t(`score.${value}`) }))}
          />
        </div>
      </div>
      <StatStrip className="statstrip-inline">
        <Stat label={t("ic.threshold")} value={threshold} />
        <Stat label={t("ic.rate")} value={pct(s.inspectRate, 0)} />
        <Stat label={t("ic.capture")} value={pct(s.capture, 0)} unit={`${int(s.found)}/${int(s.defects)}`} />
        <Stat label={t("ic.cost")} value={num(s.costPerPart)} sub={t("ic.cost.sub", { none: num(s.noInspectionCost) })} />
      </StatStrip>
    </Card>
  );
}

function RiskTable() {
  const { scenario, position, ledger, meta, selected, setSelected, variables } = useReplay();
  const { L, t } = useI18n();
  const rows = useMemo(() => {
    const out = [];
    for (let i = position; i >= Math.max(0, position - 49); i -= 1) {
      const shot = scenario.shots[i];
      shot.parts.forEach((part) => out.push({ i, shot, part }));
    }
    return out;
  }, [scenario, position]);
  return (
    <Card title={t("rt.title")} help={t("rt.help")} meta={t("rt.meta")} flush>
      <div className="table-wrap tall">
        <table className="table">
          <thead>
            <tr>
              <th>{t("col.shot")}</th>
              <th>{t("col.cavity")}</th>
              <th className="num">{t("col.risk")}</th>
              <th>{t("col.grade")}</th>
              <th title={t("type.hint")}>{t("col.type")}</th>
              <th>{t("col.reason")}</th>
              <th>{t("col.inspect")}</th>
              <th>{t("col.actual")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ i, shot, part }) => {
              const risk = ledger.risk(part, shot);
              const type = predictedType(part, meta.defect_types);
              const groups = groupContributions(part.shap, variables);
              const isSelected = selected?.i === i && selected?.cav === part.cav;
              return (
                <tr
                  key={`${i}-${part.cav}`}
                  className={`${risk === "high" ? "row-hl" : ""} ${isSelected ? "row-selected" : ""}`}
                  onClick={() => setSelected({ i, cav: part.cav })}
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && setSelected({ i, cav: part.cav })}
                >
                  <td>
                    {shot.run}·{shot.shot}
                  </td>
                  <td>{part.cav}</td>
                  <td className="num">{pct(ledger.score(part))}</td>
                  <td>
                    <RiskBadge risk={risk} />
                  </td>
                  <td>
                    {L.defectType(type.code, type.label)} <span className="caption">{pct(type.probability, 0)}</span>
                  </td>
                  <td>
                    {groups.controllable.slice(0, 2).map((g) => (
                      <span key={g.name} className="chip">
                        {L.variable(g.name, g.label)} {g.shap > 0 ? "↑" : "↓"}
                      </span>
                    ))}
                    {!part.shap ? <span className="caption">{t("rt.retrained")}</span> : null}
                  </td>
                  <td>{ledger.inspects(part, shot) ? (shot.tight ? t("rt.tight") : t("rt.check")) : <span className="caption">{t("rt.pass")}</span>}</td>
                  <td className={part.y ? "text-defect" : "caption"}>{part.y ? L.defectType(part.type, meta.type_labels[part.type]) : t("rt.normal")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ContributionBars({ title, items }) {
  const { L } = useI18n();
  if (!items.length) return null;
  const max = Math.max(...items.map((g) => Math.abs(g.shap)), 0.01);
  return (
    <div className="contrib">
      <h3 className="mini-title">{title}</h3>
      {items.map((g) => (
        <div key={g.name} className="contrib-row">
          <span>
            {L.variable(g.name, g.label)} = {sig(g.value)}
          </span>
          <span className="contrib-neg">{g.shap < 0 ? <i style={{ width: `${(-g.shap / max) * 100}%` }} /> : null}</span>
          <span className="contrib-pos">{g.shap > 0 ? <i style={{ width: `${(g.shap / max) * 100}%` }} /> : null}</span>
          <span className="num">{signed(g.shap * 100, 1)}%p</span>
        </div>
      ))}
    </div>
  );
}

function ExplanationPanel() {
  const { scenario, position, ledger, meta, summary, selected, variables } = useReplay();
  const { L, t } = useI18n();
  const target = useMemo(() => {
    if (selected && selected.i <= position) {
      const shot = scenario.shots[selected.i];
      return { i: selected.i, shot, part: shot.parts.find((p) => p.cav === selected.cav) };
    }
    for (let i = position; i >= 0; i -= 1) {
      const shot = scenario.shots[i];
      const part = shot.parts.find((p) => ledger.risk(p, shot) === "high");
      if (part) return { i, shot, part };
    }
    const shot = scenario.shots[position];
    return { i: position, shot, part: shot.parts[0] };
  }, [selected, position, scenario, ledger]);
  const { shot, part } = target;
  const type = predictedType(part, meta.defect_types);
  const typeName = L.defectType(type.code, type.label);
  const groups = groupContributions(part.shap, variables);
  const model = scenario.meta.models[shot.model];
  const checks = (summary?.checklist ?? []).filter((c) => c.type5 === type.code);
  return (
    <Card
      title={t("ex.title", { shot: `${shot.run}·${shot.shot}`, cav: part.cav })}
      help={t("ex.help", { p: pct(part.p), raw: pct(part.raw), base: pct(shot.base), prior: pct(model.prior) })}
      meta={t("ex.meta", { p: pct(part.p) })}
    >
      <div className="stack-sm">
        <div>
          <h3 className="mini-title">
            {t("ex.type")} <HelpTip text={t("type.hint")} />
          </h3>
          {meta.defect_types.map((d, k) => (
            <BarRow
              key={d.code}
              label={
                <>
                  <i className="dot" style={{ background: `var(--series-${k + 1})` }} /> {L.defectType(d.code, d.label)}
                </>
              }
              value={part.tp[k]}
              max={1}
              color={`var(--series-${k + 1})`}
              text={pct(part.tp[k], 0)}
            />
          ))}
        </div>
        {part.shap ? (
          <>
            <p className="caption">{t("ex.shapNote")}</p>
            <ContributionBars title={t("ex.adjustable")} items={groups.controllable} />
            <ContributionBars title={t("ex.context")} items={groups.context} />
          </>
        ) : (
          <div>
            <h3 className="mini-title">{t("ex.importance")}</h3>
            {model.importance.slice(0, 6).map(([name, w]) => (
              <BarRow key={name} label={L.variable(name, variables[name]?.label)} value={w} max={model.importance[0][1]} color="var(--series-1)" text={pct(w, 0)} />
            ))}
          </div>
        )}
        <div>
          <h3 className="mini-title">
            {t("ex.checks", { type: typeName })} <HelpTip text={t("ex.checks.help")} />
          </h3>
          {checks.length ? (
            <ul className="checks">
              {checks.map((c) => (
                <li key={c.variable}>
                  <b>{L.text(c.check_point)}</b> — {t("ex.checkLine", { label: L.variable(c.variable, c.label), dir: L.text(c.direction) })}
                  <span className="caption"> · {t("ex.runsAgree", { a: c.runs_agree, n: c.runs })}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="caption">{t("ex.noChecks")}</p>
          )}
        </div>
      </div>
    </Card>
  );
}

export default function ProductsView() {
  const { scenario } = useReplay();
  const { t } = useI18n();
  if (!scenario) return null;
  return (
    <div className="stack">
      <h1 className="page-title">{t("pr.title")}</h1>
      <InspectionControls />
      <div className="grid-main">
        <RiskTable />
        <div className="stack">
          <ExplanationPanel />
          <InspectionTrend />
        </div>
      </div>
    </div>
  );
}
