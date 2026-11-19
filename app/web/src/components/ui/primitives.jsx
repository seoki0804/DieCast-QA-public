"use client";

// 기본 요소: 버튼, 분할 버튼, 배지, 패널(카드), 숫자 줄(Stat), 표, 빈 상태. 색은 토큰(CSS 변수)만 쓰고,
// 설명 문장은 펼쳐 두지 않고 '?' 도움말(HelpTip)로 숨긴다.
import { useState } from "react";

import { useI18n } from "@/components/i18n/I18nProvider";

import HelpTip from "./HelpTip";
import Icon from "./Icon";

export const ALARM_ICONS = { critical: "critical", warning: "warning", info: "info", log: "log", resolved: "resolved" };
export const RISK_ICONS = { high: "arrowUp", medium: "minus", low: "arrowDown" };

export function Button({ variant = "secondary", icon, children, className = "", ...props }) {
  return (
    <button type="button" className={`btn btn-${variant} ${className}`} {...props}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}

export function Segmented({ options, value, onChange, label, size }) {
  return (
    <div className={`seg${size === "sm" ? " seg-sm" : ""}`} role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)} title={o.title}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function AlarmBadge({ level, children, size = "md" }) {
  const { L } = useI18n();
  const zero = children === 0;
  return (
    <span className={`badge ${zero ? "badge-log" : `badge-${level}`} badge-${size}`} title={L.level(level)}>
      <Icon name={ALARM_ICONS[level]} size={size === "sm" ? 12 : 14} />
      {children ?? L.level(level)}
    </span>
  );
}

export function RiskBadge({ risk }) {
  const { t } = useI18n();
  return (
    <span className={`badge risk-${risk}`} title={t(`risk.hint.${risk}`)}>
      {t("risk.badge", { level: t(`risk.${risk}`) })}
    </span>
  );
}

/** 패널: 제목 옆 '?' 도움말, 오른쪽에 짧은 메타(기간·단위)와 동작 버튼. */
export function Card({ title, help, meta, actions, children, className = "", footer, flush = false }) {
  return (
    <section className={`card ${flush ? "card-flush " : ""}${className}`}>
      {title || actions || meta ? (
        <header className="card-head">
          <div className="card-titles">
            {title ? <h2 className="card-title">{title}</h2> : null}
            <HelpTip text={help} />
          </div>
          {meta ? <span className="card-meta">{meta}</span> : null}
          {actions ? <div className="card-actions">{actions}</div> : null}
        </header>
      ) : null}
      {children}
      {footer ? <footer className="card-foot">{footer}</footer> : null}
    </section>
  );
}

/** 차트 패널: 범례와 '표로 보기' 전환 (DESIGN_SYSTEM 3.4). */
export function ChartCard({ title, help, meta, legend, table, children, className = "" }) {
  const { t } = useI18n();
  const [asTable, setAsTable] = useState(false);
  return (
    <Card
      title={title}
      help={help}
      meta={meta}
      className={className}
      actions={
        table ? (
          <Button variant="ghost" className="btn-sm" onClick={() => setAsTable((v) => !v)}>
            {asTable ? t("table.hide") : t("table.show")}
          </Button>
        ) : null
      }
    >
      {legend && !asTable ? <div className="legend">{legend}</div> : null}
      {asTable && table ? <DataTable {...table} /> : children}
    </Card>
  );
}

export function LegendItem({ color, label, line = false, dashed = false, area = false }) {
  return (
    <span className="legend-item">
      <i
        className={area ? "legend-area" : line ? "legend-line" : "legend-dot"}
        style={{ background: dashed ? "transparent" : color, borderColor: color, borderStyle: dashed ? "dashed" : "solid" }}
      />
      {label}
    </span>
  );
}

export function DataTable({ columns, rows, maxRows = 200 }) {
  const { t } = useI18n();
  const shown = rows.slice(-maxRows);
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.numeric ? "num" : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? "num" : undefined}>
                  {c.format ? c.format(row[c.key], row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > maxRows ? <p className="caption">{t("table.lastRows", { n: maxRows })}</p> : null}
    </div>
  );
}

/** 숫자 줄: 같은 높이의 칸을 얇은 선으로 나눈다 (큰 KPI 카드 대신). */
export function StatStrip({ children, className = "" }) {
  return <div className={`statstrip ${className}`}>{children}</div>;
}

export function Stat({ label, help, value, unit, sub, alarm = false, children, helpAlign }) {
  return (
    <div className={`stat${alarm ? " stat-alarm" : ""}`}>
      <div className="stat-label">
        <span>{label}</span>
        <HelpTip text={help} align={helpAlign} />
      </div>
      <div className="stat-value">
        {value}
        {unit ? <small>{unit}</small> : null}
      </div>
      {children}
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}

/** 수평 막대 한 줄 (불량 유형·캐비티 비교): 이름 · 막대 · 값. */
export function BarRow({ label, value, max, color, text, title }) {
  return (
    <div className="bar-row" title={title}>
      <span className="bar-label">{label}</span>
      <span className="bar-track">
        <i style={{ width: `${max ? (value / max) * 100 : 0}%`, background: color }} />
      </span>
      <span className="bar-text">{text}</span>
    </div>
  );
}

export function EmptyState({ title, children }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}
