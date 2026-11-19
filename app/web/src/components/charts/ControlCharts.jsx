"use client";

// 공정 현황 차트: p-chart, 불량률 CUSUM, 공정 변수 추이(관리 범위 띠), 누적 포착률·비용.
import { useMemo } from "react";

import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import { ChartCard, LegendItem } from "@/components/ui/primitives";
import { num, pct, sig } from "@/lib/format";
import { pChart } from "@/lib/metrics";

import EChart from "./EChart";
import { baseOption, refLine, SHOT_AXIS_RIGHT, shotAxisName, useChartColors } from "./theme";

/** shot 번호는 구간마다 다시 시작하므로 축에는 '구간·shot'으로 쓴다. */
export const shotLabel = (s) => `${s.run}·${s.shot}`;

const diamond = (c, color = c.critical) => ({ symbol: "diamond", symbolSize: 10, itemStyle: { color, borderColor: c.surface, borderWidth: 2 } });

export function PChartCard() {
  const { scenario, position } = useReplay();
  const { t } = useI18n();
  const c = useChartColors();
  const data = useMemo(() => pChart(scenario.shots, position, scenario.limits), [scenario, position]);
  const shots = scenario.shots;
  const option = useMemo(() => {
    if (!c) return {};
    const xs = data.points.map((p) => shotLabel(shots[p.end]));
    const ucl = data.points[0]?.ucl ?? data.center;
    const lcl = data.points[0]?.lcl ?? 0;
    const top = Math.max(ucl, ...data.points.map((p) => p.p)) * 1.12;
    const base = baseOption(c, { percent: true, yMin: 0, yMax: Number(top.toFixed(3)), grid: { right: SHOT_AXIS_RIGHT } });
    return {
      ...base,
      xAxis: { ...base.xAxis, ...shotAxisName(c, t("shotAxis")), type: "category", data: xs, axisLabel: { ...base.xAxis.axisLabel, formatter: (v) => v } },
      tooltip: {
        ...base.tooltip,
        formatter: (items) => {
          const p = data.points[items[0].dataIndex];
          const flag = p.above ? `<br/><b style="color:${c.critical}">${t("p.tt.above")}</b>` : p.out ? `<br/><b style="color:${c.good}">${t("p.tt.below")}</b>` : "";
          return `${t("p.tt.range", { run: shots[p.end].run, from: shots[p.start].shot, to: shots[p.end].shot })}<br/>${t("p.tt.rate")} <b>${pct(p.p)}</b><br/>${t("p.tt.limits")} ${pct(p.lcl)} ~ ${pct(p.ucl)}${flag}`;
        },
      },
      series: [
        {
          type: "line",
          data: data.points.map((p) => p.p),
          lineStyle: { color: c.text, width: 1.6 },
          itemStyle: { color: c.text, borderColor: c.surface, borderWidth: 1.5 },
          symbolSize: 6,
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              refLine(c, ucl, `UCL ${pct(ucl)}`),
              refLine(c, data.center, `${t("p.center")} ${pct(data.center)}`, { type: "dashed" }),
              ...(lcl > 0 ? [refLine(c, lcl, `LCL ${pct(lcl)}`)] : []),
            ],
          },
        },
        { type: "scatter", data: data.points.map((p, i) => (p.above ? [i, p.p] : null)).filter(Boolean), ...diamond(c), z: 5 },
        { type: "scatter", data: data.points.map((p, i) => (p.out && !p.above ? [i, p.p] : null)).filter(Boolean), ...diamond(c, c.good), z: 5 },
      ],
    };
  }, [c, data, shots, t]);
  return (
    <ChartCard
      title={t("p.title")}
      help={t("p.help")}
      meta={t("p.meta")}
      legend={
        <>
          <LegendItem color={c?.text} label={t("p.lg.rate")} line />
          <LegendItem color={c?.reference} label={t("p.lg.limits")} line />
          <LegendItem color={c?.critical} label={t("p.lg.up")} />
          <LegendItem color={c?.good} label={t("p.lg.down")} />
        </>
      }
      table={{
        columns: [
          { key: "range", label: t("col.shot") },
          { key: "p", label: t("col.rate"), numeric: true, format: (v) => pct(v) },
          { key: "ucl", label: "UCL", numeric: true, format: (v) => pct(v) },
          { key: "out", label: t("col.verdict"), format: (v, r) => (r.above ? t("p.tt.above") : v ? t("p.tt.below") : t("p.v.in")) },
        ],
        rows: data.points.map((p) => ({ ...p, range: `${shots[p.start].shot}~${shots[p.end].shot}` })),
      }}
    >
      {data.points.length ? <EChart option={option} height={196} label={t("p.title")} /> : <p className="caption pad">{t("p.empty")}</p>}
    </ChartCard>
  );
}

export function CusumCard() {
  const { scenario, position, alarmCenter } = useReplay();
  const { t } = useI18n();
  const c = useChartColors();
  const { h, k, window: resetWindow } = scenario.limits.cusum;
  const shots = scenario.shots;
  const option = useMemo(() => {
    if (!c) return {};
    const visible = shots.slice(0, position + 1);
    const alarms = alarmCenter.history(position).filter((a) => a.rule.startsWith("defect_cusum"));
    const base = baseOption(c, { yMin: -h * 1.25, yMax: h * 1.25, grid: { right: SHOT_AXIS_RIGHT } });
    return {
      ...base,
      // 음수 값이 있어도 축(과 축 이름)은 아래에 둔다
      xAxis: {
        ...base.xAxis,
        ...shotAxisName(c, t("shotAxis")),
        axisLine: { ...base.xAxis.axisLine, onZero: false },
        min: 0,
        max: shots.length - 1,
        axisLabel: { ...base.xAxis.axisLabel, formatter: (v) => (shots[v] ? shotLabel(shots[v]) : "") },
      },
      tooltip: {
        ...base.tooltip,
        formatter: (items) => {
          const s = shots[items[0].dataIndex];
          return t("cu.tt", { run: s.run, shot: s.shot, up: num(s.cu), down: num(s.cl) });
        },
      },
      series: [
        {
          type: "line",
          showSymbol: false,
          data: visible.map((s, i) => [i, s.cu]),
          lineStyle: { color: c.series[0], width: 1.6 },
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              refLine(c, h, `+h ${h}`),
              refLine(c, -h, "−h"),
              ...alarms.map((a) => ({ xAxis: a.detected_at, lineStyle: { color: a.level === "critical" ? c.critical : c.muted, type: "dashed" }, label: { show: false } })),
            ],
          },
        },
        { type: "line", showSymbol: false, data: visible.map((s, i) => [i, s.cl]), lineStyle: { color: c.series[1], width: 1.6 } },
      ],
    };
  }, [c, shots, position, alarmCenter, h, t]);
  const ups = alarmCenter.history(position).filter((a) => a.rule === "defect_cusum_up").length;
  return (
    <ChartCard
      title={t("cu.title")}
      help={t("cu.help", { k, h, w: resetWindow, n: ups })}
      meta={t("cu.meta")}
      legend={
        <>
          <LegendItem color={c?.series[0]} label={t("cu.up")} line />
          <LegendItem color={c?.series[1]} label={t("cu.down")} line />
          <LegendItem color={c?.critical} label={t("cu.alarm")} line dashed />
        </>
      }
      table={{
        columns: [
          { key: "shot", label: t("col.shot") },
          { key: "cu", label: t("col.upper"), numeric: true, format: (v) => num(v) },
          { key: "cl", label: t("col.lower"), numeric: true, format: (v) => num(v) },
          { key: "tight", label: t("col.tight"), format: (v) => (v ? t("cu.tightAll") : "") },
        ],
        rows: shots.slice(0, position + 1),
      }}
    >
      <EChart option={option} height={160} label={t("cu.title")} />
    </ChartCard>
  );
}

/** 공정 변수 하나: 값 추이 + 관리 범위(안) 띠. */
export function ProcessTrend({ variable, range, height = 110 }) {
  const { scenario, position } = useReplay();
  const { L, t } = useI18n();
  const c = useChartColors();
  const shots = scenario.shots;
  const label = L.variable(variable);
  const option = useMemo(() => {
    if (!c) return {};
    const values = shots.slice(0, position + 1).map((s, i) => [i, s.x[variable]]);
    const all = shots.map((s) => s.x[variable]).filter((v) => v != null);
    const sorted = [...all].sort((a, b) => a - b);
    const lo = sorted[Math.floor(sorted.length * 0.01)];
    const hi = sorted[Math.floor(sorted.length * 0.99)];
    const pad = (hi - lo) * 0.15 || 1;
    const base = baseOption(c, { grid: { left: 44, top: 8, bottom: 20 }, yMin: +(lo - pad).toPrecision(4), yMax: +(hi + pad).toPrecision(4) });
    const band = range ? [[{ yAxis: range.low ?? lo - pad * 2, itemStyle: { color: c.band } }, { yAxis: range.high ?? hi + pad * 2 }]] : [];
    return {
      ...base,
      xAxis: { ...base.xAxis, min: 0, max: shots.length - 1, axisLabel: { show: false } },
      yAxis: { ...base.yAxis, splitNumber: 2, axisLabel: { ...base.yAxis.axisLabel, formatter: (v) => sig(v) } },
      tooltip: { ...base.tooltip, formatter: (items) => `shot ${shots[items[0].dataIndex].shot}<br/>${label} <b>${sig(items[0].value[1])}</b>` },
      series: [{ type: "line", showSymbol: false, data: values, lineStyle: { color: c.text, width: 1.4 }, markArea: { silent: true, data: band } }],
    };
  }, [c, shots, position, variable, range, label]);
  const current = shots[position]?.x[variable];
  const outside = range && current != null && ((range.low != null && current < range.low) || (range.high != null && current > range.high));
  return (
    <div className="trend">
      <div className="trend-head">
        <b>{label}</b>
        <span className={outside ? "trend-out" : "caption"}>
          {sig(current)} · {range ? `${t("tr.range", { text: range.text })}${outside ? t("tr.out") : ""}` : t("tr.noRange")}
        </span>
      </div>
      <EChart option={option} height={height} label={t("tr.aria", { v: label })} />
    </div>
  );
}

/** 누적 포착률과 제품당 비용: 단위가 달라 위아래 두 차트로 나눈다 (이중 축 금지). */
function trendOption(c, shots, series, key, label, percent, axisName, reference) {
  const base = baseOption(c, { percent, yMin: 0, grid: { top: 12, bottom: 22, right: SHOT_AXIS_RIGHT } });
  return {
    ...base,
    xAxis: {
      ...base.xAxis,
      ...shotAxisName(c, axisName),
      min: 0,
      max: shots.length - 1,
      axisLabel: { ...base.xAxis.axisLabel, formatter: (v) => (shots[v] ? shotLabel(shots[v]) : "") },
    },
    tooltip: { ...base.tooltip, formatter: (items) => `shot ${shots[items[0].value[0]].shot}<br/>${label} <b>${percent ? pct(items[0].value[1]) : num(items[0].value[1])}</b>` },
    series: [
      {
        type: "line",
        showSymbol: false,
        data: series.map((p) => [p.i, p[key]]),
        lineStyle: { color: c.series[0], width: 1.6 },
        markLine: reference ? { silent: true, symbol: "none", data: [refLine(c, reference.value, reference.name)] } : undefined,
      },
    ],
  };
}

export function InspectionTrend() {
  const { scenario, position, ledger } = useReplay();
  const { t } = useI18n();
  const c = useChartColors();
  const shots = scenario.shots;
  const series = useMemo(() => ledger.series(shots, position, 10), [ledger, shots, position]);
  const capture = useMemo(() => (c ? trendOption(c, shots, series, "capture", t("it.capture"), true, t("shotAxis")) : {}), [c, shots, series, t]);
  const cost = useMemo(
    () => (c ? trendOption(c, shots, series, "costPerPart", t("ic.cost"), false, t("shotAxis"), { name: t("it.costRef"), value: 1 }) : {}),
    [c, shots, series, t],
  );
  return (
    <ChartCard title={t("it.title")} help={t("it.help")}>
      <h3 className="mini-title">{t("it.capture")}</h3>
      <EChart option={capture} height={130} label={t("it.capture")} />
      <h3 className="mini-title">{t("it.cost")}</h3>
      <EChart option={cost} height={130} label={t("it.cost")} />
    </ChartCard>
  );
}
