"use client";

// 차트 색·글꼴을 CSS 변수(토큰)에서 읽어 ECharts 옵션의 공통 부분을 만든다. 테마가 바뀌면 다시 읽는다.
import { useMemo } from "react";

import { useReplay } from "@/components/replay/ReplayProvider";

const VARS = {
  text: "--text-primary",
  secondary: "--text-secondary",
  muted: "--text-muted",
  grid: "--chart-grid",
  baseline: "--chart-baseline",
  band: "--chart-band",
  reference: "--chart-reference",
  zone: "--chart-zone",
  zoneOuter: "--chart-zoneOuter",
  bar: "--chart-bar",
  accent: "--accent-text",
  surface: "--bg-surface",
  raised: "--bg-raised",
  border: "--border-hairline",
  critical: "--status-critical",
  warning: "--status-warning",
  good: "--status-good",
  serious: "--status-serious",
  increase: "--div-6",
  decrease: "--div-2",
  font: "--font-sans",
};

export function useChartColors() {
  const { theme } = useReplay();
  return useMemo(() => {
    if (typeof window === "undefined") return null;
    const style = getComputedStyle(document.documentElement);
    const read = (name) => style.getPropertyValue(name).trim();
    const colors = Object.fromEntries(Object.entries(VARS).map(([k, v]) => [k, read(v)]));
    colors.series = Array.from({ length: 8 }, (_, i) => read(`--series-${i + 1}`));
    colors.theme = theme;
    return colors;
  }, [theme]);
}

/** 가로축이 '구간·shot'인 차트의 축 이름. 오른쪽 끝에 두므로 격자 오른쪽 여백(SHOT_AXIS_RIGHT)이 필요하다. */
export const SHOT_AXIS_RIGHT = 64;
export function shotAxisName(c, name) {
  return { name, nameLocation: "end", nameGap: 8, nameTextStyle: { color: c.muted, fontSize: 11 } };
}

/** 기준선 하나 (관리한계·중심선): 이름은 선 오른쪽 끝 바깥에 둬서 데이터와 겹치지 않게 한다. */
export function refLine(c, value, name, { axis = "yAxis", color = c.reference, type = "solid", width = 1, labelColor = c.muted, bold = false } = {}) {
  return {
    [axis]: value,
    lineStyle: { color, type, width },
    label: { formatter: name, position: "end", color: labelColor, fontSize: 11, fontWeight: bold ? 700 : 400 },
  };
}

/** 모든 차트가 같이 쓰는 축·격자·툴팁 (격자는 값 축에만, 이중 축 없음). */
export function baseOption(c, { grid = {}, percent = false, yMin, yMax } = {}) {
  return {
    animation: false,
    textStyle: { fontFamily: c.font, color: c.secondary },
    grid: { left: 48, right: 16, top: 16, bottom: 28, ...grid },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: c.baseline } },
      backgroundColor: c.raised,
      borderColor: c.border,
      textStyle: { color: c.text, fontFamily: c.font, fontSize: 12 },
      confine: true,
    },
    xAxis: {
      type: "value",
      axisLine: { lineStyle: { color: c.baseline } },
      axisTick: { show: false },
      // 끝 눈금처럼 서로 겹치는 라벨은 숨긴다
      axisLabel: { color: c.muted, fontSize: 11, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: yMin,
      max: yMax,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: c.muted,
        fontSize: 11,
        formatter: percent ? (v) => `${Math.round(v * 100)}%` : undefined,
      },
      splitLine: { lineStyle: { color: c.grid } },
    },
  };
}
