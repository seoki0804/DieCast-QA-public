"use client";

// 공정 변수 SPC: 개별값 관리도(I-MR), 분포와 현재 위치(히스토그램 + 정규곡선), 공정 변수 칸.
// 품질 현장에서 쓰는 형식(Minitab Capability Sixpack의 I-MR·히스토그램, 회색 바탕에 이상만 색)을 따른다.
import { useMemo } from "react";

import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import { ChartCard, LegendItem } from "@/components/ui/primitives";
import { num, pct } from "@/lib/format";
import { histogram, imr, locate, normalPdf } from "@/lib/spc";
import { digitsOf, PANEL_VARIABLES, unitOf } from "@/lib/variables";

import { shotLabel } from "./ControlCharts";
import EChart from "./EChart";
import { Sparkline, SigmaBar } from "./Mini";
import { baseOption, refLine, useChartColors } from "./theme";

const IMR_WINDOW = 100;
const DIST_WINDOW = 200;
const TREND_WINDOW = 50;

/** 변수 값 포맷 (변수마다 소수 자리가 다르다). */
function useValueFormat(variable, sample) {
  const digits = digitsOf(variable, sample ?? 0);
  return { digits, f: (v) => num(v, digits) };
}

/** 축 눈금 자릿수: 값 범위가 좁으면 반올림한 눈금이 겹치지 않게 자릿수를 늘린다. */
function axisFormat(digits, lo, hi, ticks = 5) {
  const step = (hi - lo) / ticks;
  const need = step > 0 ? Math.ceil(-Math.log10(step)) : 0;
  const d = Math.min(4, Math.max(digits, need));
  return (v) => num(v, d);
}

export function ImrCard({ variable }) {
  const { scenario, position } = useReplay();
  const { L, t } = useI18n();
  const c = useChartColors();
  const shots = scenario.shots;
  const from = Math.max(0, position - IMR_WINDOW + 1);
  const values = useMemo(() => shots.slice(from, position + 1).map((s) => s.x[variable]), [shots, from, position, variable]);
  const r = useMemo(() => (values.length >= 5 ? imr(values) : null), [values]);
  const { digits, f } = useValueFormat(variable, values[0]);
  const name = L.variable(variable);
  const option = useMemo(() => {
    if (!c || !r) return {};
    const cats = values.map((_, k) => shotLabel(shots[from + k]));
    const lo = Math.min(r.lcl, ...values);
    const hi = Math.max(r.ucl, ...values);
    const pad = (hi - lo) * 0.06 || 1;
    const base = baseOption(c);
    const tickI = axisFormat(digits, lo - pad, hi + pad);
    const tickMr = axisFormat(digits, 0, Math.max(r.mrUcl, ...r.mr.slice(1)), 2);
    const axisX = (gridIndex, showLabels) => ({ ...base.xAxis, type: "category", data: cats, gridIndex, axisLabel: { ...base.xAxis.axisLabel, show: showLabels } });
    const axisY = (gridIndex, tick, extra) => ({ ...base.yAxis, gridIndex, axisLabel: { ...base.yAxis.axisLabel, formatter: tick }, ...extra });
    const zones = [
      [{ yAxis: r.center - r.sigma, itemStyle: { color: c.zone } }, { yAxis: r.center + r.sigma }],
      [{ yAxis: r.center + r.sigma, itemStyle: { color: c.zoneOuter } }, { yAxis: r.center + 2 * r.sigma }],
      [{ yAxis: r.center - 2 * r.sigma, itemStyle: { color: c.zoneOuter } }, { yAxis: r.center - r.sigma }],
    ];
    return {
      ...base,
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      tooltip: { ...base.tooltip, valueFormatter: (v) => (v == null ? "–" : f(v)) },
      grid: [
        { left: 56, right: 78, top: 12, height: "60%" },
        { left: 56, right: 78, top: "77%", bottom: 22 },
      ],
      xAxis: [axisX(0, false), axisX(1, true)],
      yAxis: [axisY(0, tickI, { min: lo - pad, max: hi + pad }), axisY(1, tickMr, { min: 0, splitNumber: 2 })],
      series: [
        {
          name: t("imr.value"),
          type: "line",
          data: values,
          xAxisIndex: 0,
          yAxisIndex: 0,
          symbol: "none",
          lineStyle: { color: c.secondary, width: 1.3 },
          markArea: { silent: true, data: zones },
          markLine: {
            silent: true,
            symbol: "none",
            data: [refLine(c, r.ucl, `UCL ${tickI(r.ucl)}`), refLine(c, r.center, `x̄ ${tickI(r.center)}`, { type: "dashed" }), refLine(c, r.lcl, `LCL ${tickI(r.lcl)}`)],
          },
        },
        { type: "scatter", data: r.run.map((k) => [k, values[k]]), xAxisIndex: 0, yAxisIndex: 0, symbolSize: 6, itemStyle: { color: c.warning }, tooltip: { show: false }, z: 4 },
        {
          type: "scatter",
          data: r.beyond.map((k) => [k, values[k]]),
          xAxisIndex: 0,
          yAxisIndex: 0,
          symbol: "diamond",
          symbolSize: 10,
          itemStyle: { color: c.critical, borderColor: c.surface, borderWidth: 1.5 },
          tooltip: { show: false },
          z: 5,
        },
        {
          name: t("imr.mr"),
          type: "line",
          data: r.mr,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: "none",
          lineStyle: { color: c.muted, width: 1 },
          markLine: { silent: true, symbol: "none", data: [refLine(c, r.mrUcl, `UCL ${tickMr(r.mrUcl)}`)] },
        },
      ],
    };
  }, [c, r, values, shots, from, f, digits, t]);
  return (
    <ChartCard
      title={t("imr.title", { v: name })}
      help={t("imr.help")}
      meta={t("imr.meta", { n: values.length })}
      legend={
        <>
          <LegendItem color={c?.zone} label={t("imr.zone")} area />
          <LegendItem color={c?.critical} label={t("imr.beyond")} />
          <LegendItem color={c?.warning} label={t("imr.run")} />
        </>
      }
      table={{
        columns: [
          { key: "shot", label: t("col.shot") },
          { key: "value", label: `${t("imr.value")} (${unitOf(variable)})`, numeric: true, format: (v) => f(v) },
          { key: "mr", label: t("imr.mr"), numeric: true, format: (v) => (v == null ? "–" : f(v)) },
        ],
        rows: values.map((v, k) => ({ shot: shotLabel(shots[from + k]), value: v, mr: r?.mr[k] })),
      }}
    >
      {r ? <EChart option={option} height={262} label={t("imr.title", { v: name })} /> : <p className="caption pad">…</p>}
    </ChartCard>
  );
}

export function DistributionCard({ variable }) {
  const { scenario, position } = useReplay();
  const { L, t } = useI18n();
  const c = useChartColors();
  const shots = scenario.shots;
  const range = scenario.meta.ranges.find((r) => r.variable === variable) ?? null;
  const history = useMemo(() => shots.slice(Math.max(0, position - DIST_WINDOW), position).map((s) => s.x[variable]), [shots, position, variable]);
  const current = shots[position].x[variable];
  const p = useMemo(() => (history.length >= 20 ? locate(history, current, range) : null), [history, current, range]);
  const hist = useMemo(() => (history.length >= 20 ? histogram(history) : null), [history]);
  const { digits, f } = useValueFormat(variable, current);
  const unit = unitOf(variable);
  const name = L.variable(variable);
  const option = useMemo(() => {
    if (!c || !p || !hist) return {};
    const s = p.sd || hist.step;
    const lo = Math.min(p.mean - 3.6 * s, ...history, current) - hist.step;
    const hi = Math.max(p.mean + 3.6 * s, ...history, current) + hist.step;
    const curve = [];
    for (let k = 0; k <= 160; k += 1) {
      const x = lo + ((hi - lo) * k) / 160;
      curve.push([x, p.sd > 0 ? normalPdf(x, p.mean, p.sd) * history.length * hist.step : 0]);
    }
    const band = range ? [[{ xAxis: range.low ?? lo, itemStyle: { color: c.band } }, { xAxis: range.high ?? hi }]] : [];
    const base = baseOption(c, { grid: { left: 40, right: 18, top: 28, bottom: 26 } });
    return {
      ...base,
      tooltip: {
        ...base.tooltip,
        trigger: "item",
        formatter: (q) => (q.seriesIndex === 0 ? `${f(q.value[3])} ${unit}<br/>${t("dist.tt.count")} <b>${q.value[2]}</b>` : ""),
      },
      xAxis: { ...base.xAxis, min: lo, max: hi, axisLabel: { ...base.xAxis.axisLabel, formatter: axisFormat(digits, lo, hi, 6), showMinLabel: false, showMaxLabel: false } },
      yAxis: { ...base.yAxis, min: 0, splitNumber: 3 },
      series: [
        {
          type: "custom",
          data: hist.bins.map((b) => [b.from + hist.step * 0.08, b.to - hist.step * 0.08, b.count, b.center]),
          encode: { x: [0, 1], y: 2 },
          renderItem: (_, api) => {
            const a = api.coord([api.value(0), 0]);
            const b = api.coord([api.value(1), api.value(2)]);
            return { type: "rect", shape: { x: a[0], y: b[1], width: Math.max(1.5, b[0] - a[0]), height: a[1] - b[1], r: [2, 2, 0, 0] }, style: { fill: c.bar } };
          },
        },
        {
          type: "line",
          data: curve,
          symbol: "none",
          smooth: true,
          silent: true,
          tooltip: { show: false },
          lineStyle: { color: c.text, width: 1.5 },
          markArea: { silent: true, data: band },
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              // 평균선은 범례로 설명하고 라벨은 생략한다 (이번 shot 값 라벨과 겹치지 않게)
              { ...refLine(c, p.mean, "", { axis: "xAxis", color: c.muted }), label: { show: false } },
              ...(p.sd > 0 ? [-3, 3].map((k) => refLine(c, p.mean + k * p.sd, `${k > 0 ? "+" : "−"}3σ`, { axis: "xAxis", color: c.baseline })) : []),
              refLine(c, current, f(current), { axis: "xAxis", color: c.accent, width: 2.2, labelColor: c.accent, bold: true }),
            ],
          },
        },
      ],
    };
  }, [c, p, hist, history, current, range, f, digits, unit, t]);
  const z = p && p.sd > 0 ? `${p.z >= 0 ? "+" : "−"}${num(Math.abs(p.z), 2)}` : "–";
  return (
    <ChartCard
      title={t("dist.title", { v: name })}
      help={t("dist.help")}
      meta={t("dist.meta", { n: history.length })}
      legend={
        <>
          <LegendItem color={c?.accent} label={t("dist.now")} line />
          <LegendItem color={c?.text} label={t("dist.mean")} line />
          {range ? <LegendItem color={c?.band} label={t("dist.band")} area /> : null}
        </>
      }
      table={hist ? { columns: [{ key: "center", label: `${name} (${unit})`, numeric: true, format: (v) => f(v) }, { key: "count", label: t("dist.tt.count"), numeric: true }], rows: hist.bins } : null}
    >
      {p ? (
        <>
          <EChart option={option} height={214} label={t("dist.title", { v: name })} />
          <dl className="kv">
            <div>
              <dt>{t("dist.kv.now")}</dt>
              <dd className={p.currentOut ? "kv-out" : undefined}>
                {f(current)} <small>{unit}</small>
              </dd>
            </div>
            <div>
              <dt>{t("dist.kv.mean")}</dt>
              <dd>{f(p.mean)}</dd>
            </div>
            <div>
              <dt>{t("dist.kv.sd")}</dt>
              <dd>{num(p.sd, digits + 1)}</dd>
            </div>
            <div>
              <dt>{t("dist.kv.z")}</dt>
              <dd>{z}</dd>
            </div>
            <div>
              <dt>{t("dist.kv.out")}</dt>
              <dd>{p.outShare == null ? "–" : pct(p.outShare, 0)}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="caption pad">…</p>
      )}
    </ChartCard>
  );
}

/** 공정 변수 칸: 값·추정 단위·z, 최근 50 shot 추세, σ 위치 막대. 누르면 위 관리도·분포가 그 변수로 바뀐다. */
export function VariableTiles({ selected, onSelect }) {
  const { scenario, position } = useReplay();
  const { L, t } = useI18n();
  const shots = scenario.shots;
  const tiles = useMemo(
    () =>
      PANEL_VARIABLES.map((v) => {
        const history = shots.slice(Math.max(0, position - DIST_WINDOW), position).map((s) => s.x[v]);
        const current = shots[position].x[v];
        const range = scenario.meta.ranges.find((r) => r.variable === v) ?? null;
        const p = history.length >= 20 ? locate(history, current, range) : null;
        const edges = p && p.sd > 0 && range ? [range.low, range.high].filter((e) => e != null).map((e) => (e - p.mean) / p.sd) : [];
        const trend = shots.slice(Math.max(0, position - TREND_WINDOW + 1), position + 1).map((s) => s.x[v]);
        return { v, current, p, edges, trend };
      }),
    [shots, position, scenario],
  );
  return (
    <div className="tiles">
      {tiles.map(({ v, current, p, edges, trend }) => {
        const beyond = p ? Math.abs(p.z) > 3 : false;
        const digits = digitsOf(v, current);
        return (
          <button key={v} type="button" className="tile" aria-pressed={selected === v} onClick={() => onSelect(v)}>
            <span className="tile-name">
              <span>{L.variable(v)}</span>
              <span className="tile-unit">{unitOf(v)}</span>
            </span>
            <span className="tile-value">
              <b>{num(current, digits)}</b>
              {p ? <em>{`${p.z >= 0 ? "+" : "−"}${num(Math.abs(p.z), 1)}σ`}</em> : null}
              {p?.currentOut ? <span className="tile-chip">{t("vp.out")}</span> : beyond ? <span className="tile-chip tile-chip-alarm">{t("vp.sigma")}</span> : null}
            </span>
            <Sparkline values={trend} alarm={beyond} />
            {p ? <SigmaBar z={p.z} edges={edges} beyond={beyond} /> : null}
          </button>
        );
      })}
    </div>
  );
}
