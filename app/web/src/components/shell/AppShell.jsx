"use client";

// 화면 틀: 상단 바(시나리오·재생 상태·shot·경과 시각·알람 수·언어·테마), 재생 바, 왼쪽 탐색,
// 상태 띠(정상 운전 / 경고와 조치), 주의 토스트.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "@/components/i18n/I18nProvider";
import { SPEEDS, useReplay } from "@/components/replay/ReplayProvider";
import HelpTip from "@/components/ui/HelpTip";
import Icon from "@/components/ui/Icon";
import { AlarmBadge, Button, EmptyState, Segmented } from "@/components/ui/primitives";
import { int } from "@/lib/format";
import { clock } from "@/lib/spc";

const NAV = [
  { href: "/", key: "nav.overview", icon: "gauge" },
  { href: "/products", key: "nav.products", icon: "box" },
  { href: "/alarms", key: "nav.alarms", icon: "bell" },
  { href: "/summary", key: "nav.summary", icon: "chart" },
  { href: "/settings", key: "nav.settings", icon: "settings" },
];

function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <Segmented
      size="sm"
      label={t("lang.label")}
      value={lang}
      onChange={setLang}
      options={[
        { value: "ko", label: "한국어" },
        { value: "en", label: "EN" },
      ]}
    />
  );
}

function TopBar() {
  const { meta, scenarioId, setScenarioId, scenario, position, playing, alarmCenter, ledger, theme, setTheme, elapsed } = useReplay();
  const { L, t } = useI18n();
  const warnings = scenario ? alarmCenter.warnings(scenario.shots, position, ledger) : [];
  const active = scenario ? alarmCenter.active(position) : [];
  const critical = active.filter((a) => a.level === "critical").length;
  const info = active.filter((a) => a.level === "info").length;
  const shot = scenario?.shots[position];
  return (
    <header className="topbar">
      <span className="brand">DieCast-QA</span>
      <label className="scenario-picker">
        <span className="sr-only">{t("top.scenario")}</span>
        <select value={scenarioId ?? ""} onChange={(e) => setScenarioId(e.target.value)} disabled={!meta}>
          {(meta?.scenarios ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {L.scenarioLabel(s)}
            </option>
          ))}
        </select>
      </label>
      <span className="spacer" />
      {shot ? (
        <div className="readouts">
          <span className={`live ${playing ? "live-on" : ""}`}>
            {playing ? t("live.playing") : t("live.paused")} · {int(position + 1)}/{int(scenario.shots.length)}
          </span>
          <span className="readout">
            <small>shot</small>
            <b>
              {shot.run}·{shot.shot}
            </b>
          </span>
          <span className="readout">
            <small>
              {t("top.elapsed")}
              <HelpTip text={t("top.elapsed.help")} align="right" />
            </small>
            <b>{clock(elapsed[position] ?? 0)}</b>
          </span>
        </div>
      ) : null}
      <Link href="/alarms" className="alarm-counts" aria-label={t("top.alarms")}>
        <AlarmBadge level="critical" size="sm">
          {critical}
        </AlarmBadge>
        <AlarmBadge level="warning" size="sm">
          {warnings.length}
        </AlarmBadge>
        <AlarmBadge level="info" size="sm">
          {info}
        </AlarmBadge>
      </Link>
      <LanguageSwitch />
      <Button
        variant="ghost"
        icon={theme === "dark" ? "sun" : "moon"}
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        aria-label={theme === "dark" ? t("theme.toLight") : t("theme.toDark")}
      />
    </header>
  );
}

function ReplayBar() {
  const { scenario, position, seek, step, playing, setPlaying, speed, setSpeed, alarmCenter } = useReplay();
  const { t } = useI18n();
  if (!scenario) return null;
  const n = scenario.shots.length;
  const marks = alarmCenter.alarms.filter((a) => a.level === "critical");
  return (
    <div className="replaybar">
      <Button variant="primary" icon={playing ? "pause" : "play"} onClick={() => setPlaying(!playing)} aria-label={playing ? t("rb.pause") : t("rb.play")} />
      <Button icon="rewind" onClick={() => seek(0)} aria-label={t("rb.start")} />
      <Button icon="back" onClick={() => step(-1)} aria-label={t("rb.back")} />
      <Button icon="forward" onClick={() => step(1)} aria-label={t("rb.forward")} />
      <Segmented label={t("rb.speed")} value={speed} onChange={setSpeed} options={SPEEDS.map((s) => ({ value: s, label: `${s}`, title: t("rb.speedTitle", { n: s }) }))} />
      <div className="track">
        <input type="range" min={0} max={n - 1} value={position} onChange={(e) => seek(Number(e.target.value))} aria-label={t("rb.position")} />
        <div className="track-marks" aria-hidden>
          {marks.map((a) => (
            <i key={a.id} style={{ left: `${(a.at / (n - 1)) * 100}%` }} />
          ))}
        </div>
      </div>
      <span className="caption">{Math.round(((position + 1) / n) * 100)}%</span>
    </div>
  );
}

/** 상태 띠: 평소에는 '정상 운전'(회색조), 경고가 진행 중이면 빨간 띠에 조치·확인 (ISA-101: 색은 이상할 때만). */
function StatusBand() {
  const { scenario, position, alarmCenter, acknowledged, acknowledge } = useReplay();
  const { L, t } = useI18n();
  if (!scenario) return null;
  const active = alarmCenter.active(position);
  const critical = active.filter((a) => a.level === "critical");
  if (!critical.length) {
    const info = active.filter((a) => a.level === "info").length;
    return (
      <div className="band band-ok" role="status">
        <span className="lamp" aria-hidden />
        <b>{t("band.ok")}</b>
        <span className="caption">{info ? t("band.info", { n: info }) : t("band.okDetail")}</span>
      </div>
    );
  }
  const alarm = critical[0];
  const remaining = alarm.release_at != null ? alarm.release_at - position : null;
  const acked = acknowledged.has(alarm.id);
  return (
    <div className={`band banner${acked ? " banner-ack" : ""}`} role="alert">
      <AlarmBadge level="critical" />
      <div className="banner-msg">
        <b>{L.text(alarm.title)}</b> · shot {int(scenario.shots[alarm.detected_at].shot)} · {t("band.inspecting")}
        {remaining != null ? ` · ${t("band.left", { n: remaining })}` : ""}
        {critical.length > 1 ? ` · ${t("band.more", { n: critical.length })}` : ""}
      </div>
      <Link className="btn btn-primary btn-sm" href={`/alarms?id=${alarm.id}`}>
        {t("band.actions")}
      </Link>
      {!acked ? (
        <Button className="btn-sm" onClick={() => acknowledge(alarm.id)}>
          {t("band.ack")}
        </Button>
      ) : (
        <span className="caption">{t("band.acked")}</span>
      )}
    </div>
  );
}

/** 주의(위험도 상 제품) 알림: 10 shot 묶음마다 한 번만, 6초 뒤 닫힘. */
function WarningToast() {
  const { scenario, position, alarmCenter, ledger, playing } = useReplay();
  const { L, t } = useI18n();
  const [toast, setToast] = useState(null);
  const lastId = useRef(null);
  const warnings = useMemo(() => (scenario ? alarmCenter.warnings(scenario.shots, position, ledger) : []), [scenario, position, alarmCenter, ledger]);
  useEffect(() => {
    const latest = warnings[0];
    if (!playing || !latest || latest.id === lastId.current) return undefined;
    lastId.current = latest.id;
    setToast(latest);
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [warnings, playing]);
  if (!toast) return null;
  return (
    <div className="toast" role="status">
      <AlarmBadge level="warning" />
      <div>
        <b>{L.text(toast.title)}</b>
        <div className="caption">{L.text(toast.message)}</div>
      </div>
      <Button variant="ghost" icon="close" onClick={() => setToast(null)} aria-label={t("toast.close")} />
    </div>
  );
}

function SideNav() {
  const pathname = usePathname();
  const { t } = useI18n();
  return (
    <nav className="sidenav" aria-label={t("nav.label")}>
      {NAV.map((item) => (
        <Link key={item.href} href={item.href} className={pathname === item.href ? "nav-on" : undefined} aria-current={pathname === item.href ? "page" : undefined}>
          <Icon name={item.icon} size={20} />
          <span>{t(item.key)}</span>
        </Link>
      ))}
    </nav>
  );
}

export default function AppShell({ children }) {
  const { error, loading, scenario } = useReplay();
  const { t } = useI18n();
  let content = children;
  if (error) {
    content = (
      <EmptyState title={t("err.title")}>
        <p>{error}</p>
        <p className="caption">{t("err.help", { api: "uv run uvicorn app.api.main:app --port 8000", data: "uv run python scripts/11_dashboard_data.py" })}</p>
      </EmptyState>
    );
  } else if (loading && !scenario) {
    content = <EmptyState title={t("loading")} />;
  }
  return (
    <div className="shell">
      <TopBar />
      <ReplayBar />
      <div className="shell-body">
        <SideNav />
        <main className="content">
          <StatusBand />
          {content}
        </main>
      </div>
      <WarningToast />
    </div>
  );
}
