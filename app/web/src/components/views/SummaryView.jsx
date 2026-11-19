"use client";

// ④ 분석 요약 (정적): 보고서 3~9장 결과 중 운영 판단에 필요한 것만. 설명은 '?'로.
import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import { BarRow, Card, DataTable, EmptyState } from "@/components/ui/primitives";
import { num, pct } from "@/lib/format";

const TYPE_ORDER = ["short_shot", "exfoliation", "porosity", "deformation", "other"];
const MODEL_NAMES = { et: "Extra Trees", xgb: "XGBoost" };

export default function SummaryView() {
  const { summary } = useReplay();
  const { L, t } = useI18n();
  if (!summary) return <EmptyState title={t("su.loading")} />;
  const model = (m) => MODEL_NAMES[m] ?? t(`model.${m}`);
  const perf = summary.performance.map((p) => ({ ...p, design: t(`design.${p.design}`), model: model(p.model) }));
  const checklist = TYPE_ORDER.map((code) => ({ code, items: summary.checklist.filter((c) => c.type5 === code) }));
  const totalParts = summary.pareto.reduce((a, r) => a + r.parts, 0);
  const maxShare = Math.max(...summary.pareto.map((r) => r.share));
  return (
    <div className="stack">
      <h1 className="page-title">{t("su.title")}</h1>
      <div className="grid-2">
        <Card title={t("su.pareto")} help={t("su.pareto.help", { n: totalParts.toLocaleString("en-US") })} meta={t("ref", { n: 3 })}>
          {summary.pareto.map((r) => (
            <BarRow
              key={r.type5}
              label={L.defectType(r.type5, r.label)}
              value={r.share}
              max={maxShare}
              color={`var(--series-${TYPE_ORDER.indexOf(r.type5) + 1})`}
              text={t("su.parts", { n: r.parts, p: pct(r.share, 0) })}
            />
          ))}
        </Card>
        <Card title={t("su.models")} help={t("su.models.help")} meta={t("ref", { n: 4 })} flush>
          <DataTable
            columns={[
              { key: "design", label: t("col.design") },
              { key: "model", label: t("col.method") },
              { key: "roc_auc", label: "ROC-AUC", numeric: true, format: (v) => num(v, 3) },
              { key: "capture_20", label: t("col.top20"), numeric: true, format: (v) => pct(v, 0) },
            ]}
            rows={perf}
          />
        </Card>
      </div>
      <Card title={t("su.ranges")} help={t("su.ranges.help")} meta={t("ref", { n: 7 })} flush>
        <DataTable
          columns={[
            { key: "Product_Type", label: t("col.productType") },
            { key: "label", label: t("col.variable"), format: (v, r) => L.variable(r.variable, v) },
            { key: "range_label", label: t("col.range"), format: (v) => v ?? "–" },
            { key: "rate_in", label: t("col.rateIn"), numeric: true, format: (v) => pct(v) },
            { key: "rate_out", label: t("col.rateOut"), numeric: true, format: (v) => pct(v) },
            { key: "cmh_or", label: t("col.or"), numeric: true, format: (v) => num(v) },
            { key: "verdict", label: t("col.verdict"), format: (v) => t(`verdict.${v}`) },
          ]}
          rows={summary.ranges}
        />
      </Card>
      <Card title={t("su.checks")} help={t("su.checks.help")} meta={t("ref", { n: 7 })}>
        <div className="grid-3">
          {checklist.map(({ code, items }) => (
            <div key={code} className="check-card">
              <h3 className="mini-title">
                <i className="dot" style={{ background: `var(--series-${TYPE_ORDER.indexOf(code) + 1})` }} /> {L.defectType(code, items[0]?.type_label)}
              </h3>
              <ul className="checks">
                {items.map((c) => (
                  <li key={c.variable}>
                    {L.text(c.check_point)} — {L.variable(c.variable, c.label)} {L.text(c.direction)} <span className="caption">({c.runs_agree}/{c.runs})</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Card>
      <div className="grid-2">
        <Card title={t("su.cost")} help={t("su.cost.help")} meta={t("ref", { n: 8 })} flush>
          <DataTable
            columns={[
              { key: "ratio", label: t("col.ratio"), format: (v) => `${v}:1` },
              { key: "label", label: t("col.cheapest"), format: (v) => L.text(v) },
              { key: "cost_per_part", label: t("col.cost"), numeric: true, format: (v) => num(v, 3) },
              { key: "inspect_rate", label: t("col.inspectRate"), numeric: true, format: (v) => pct(v, 0) },
              { key: "saving_vs_full", label: t("col.saving"), numeric: true, format: (v) => pct(v, 0) },
            ]}
            rows={summary.cost_best}
          />
        </Card>
        <Card title={t("su.improve")} help={t("su.improve.help")} meta={t("ref", { n: 9 })}>
          <ul className="checks">
            <li>
              <b>{t("su.cavityLever")}:</b> {t("su.cavityLever.text", { p: pct(summary.levers.cavity_reduction, 0) })}
            </li>
            {summary.levers.ranges.map((r) => (
              <li key={r.Product_Type}>
                <b>{t("su.rangeLever", { t: r.Product_Type })}:</b>{" "}
                {t("su.rangeLever.text", {
                  a: pct(r.actual_rate),
                  b: pct(r.in_range_rate),
                  lo: pct(r.reduction_low, 0),
                  hi: pct(r.reduction_high, 0),
                  ranges: L.text(r.ranges),
                })}
              </li>
            ))}
            <li>{t("su.restart")}</li>
          </ul>
          <h3 className="mini-title">{t("su.doe")}</h3>
          <DataTable
            columns={[
              { key: "Product_Type", label: t("col.type2") },
              { key: "label", label: t("col.factor"), format: (v, r) => L.variable(r.variable, v) },
              { key: "current", label: t("col.current"), numeric: true, format: (v) => num(v, 3) },
              { key: "improved", label: t("col.improved"), numeric: true, format: (v) => num(v, 3) },
              { key: "source", label: t("col.basis"), format: (v) => L.text(v) },
            ]}
            rows={summary.doe}
          />
        </Card>
      </div>
    </div>
  );
}
