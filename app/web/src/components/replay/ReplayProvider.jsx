"use client";

// 재생 상태(시나리오, 위치, 속도)와 사용자 설정(비용 비율, 테마, 소리, 알람 확인)을 모든 화면이 공유한다.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { AlarmCenter } from "@/lib/alarms";
import { ApiClient } from "@/lib/api";
import { InspectionLedger } from "@/lib/inspection";
import { cumulativeSum } from "@/lib/spc";

const ReplayContext = createContext(null);
export const SPEEDS = [1, 2, 5, 10];

function readSetting(key, fallback) {
  try {
    const value = window.localStorage.getItem(`diecast.${key}`);
    return value == null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

function writeSetting(key, value) {
  try {
    window.localStorage.setItem(`diecast.${key}`, JSON.stringify(value));
  } catch {
    // 저장소를 쓸 수 없어도 화면은 동작한다
  }
}

/** 경고가 새로 울릴 때 짧은 소리 (설정에서 켰을 때만). */
function beep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch {
    // 브라우저가 소리를 막으면 무시
  }
}

export function ReplayProvider({ children }) {
  const api = useMemo(() => new ApiClient(), []);
  const [meta, setMeta] = useState(null);
  const [summary, setSummary] = useState(null);
  const [scenarioId, setScenarioId] = useState(null);
  const [scenario, setScenario] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const [ratio, setRatio] = useState(10);
  const [scoreKey, setScoreKey] = useState("p");
  const [theme, setThemeState] = useState("light");
  const [sound, setSoundState] = useState(false);
  const [acknowledged, setAcknowledged] = useState(() => new Set());
  const [actionChecks, setActionChecks] = useState({});
  const [selected, setSelected] = useState(null);
  // 주소의 ?scenario=…&at=… 로 특정 장면부터 연다 (발표·공유용)
  const deepLink = useRef(null);

  // 설정 복원 (브라우저 저장소, 없으면 기본값)
  useEffect(() => {
    const linked = new URLSearchParams(window.location.search).get("theme");
    setThemeState(["light", "dark"].includes(linked) ? linked : readSetting("theme", "light"));
    setSoundState(readSetting("sound", false));
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setTheme = useCallback((value) => {
    setThemeState(value);
    writeSetting("theme", value);
  }, []);
  const setSound = useCallback((value) => {
    setSoundState(value);
    writeSetting("sound", value);
  }, []);

  // 메타 → 기본 시나리오
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    deepLink.current = { scenario: params.get("scenario"), at: Number(params.get("at") ?? 0) };
    api
      .meta()
      .then((m) => {
        setMeta(m);
        api.summary().then(setSummary).catch(() => setSummary(null));
        setRatio(m.default_ratio);
        const linked = m.scenarios.find((s) => s.id === deepLink.current?.scenario)?.id;
        setScenarioId((id) => id ?? linked ?? m.scenarios.find((s) => s.id === "t2_r5_alarm")?.id ?? m.scenarios[0].id);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [api]);

  useEffect(() => {
    if (!scenarioId) return;
    let cancelled = false;
    setLoading(true);
    setPlaying(false);
    api
      .scenario(scenarioId)
      .then((data) => {
        if (cancelled) return;
        setScenario(data);
        const at = deepLink.current?.at ?? 0;
        deepLink.current = null;
        setPosition(Math.max(0, Math.min(data.shots.length - 1, at)));
        setAcknowledged(new Set());
        setActionChecks({});
        setSelected(null);
        setError(null);
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [api, scenarioId]);

  const last = scenario ? scenario.shots.length - 1 : 0;

  // 재생 타이머: 속도(shot/초)마다 한 shot
  useEffect(() => {
    if (!playing || !scenario) return undefined;
    const timer = setInterval(() => {
      setPosition((p) => {
        if (p >= last) {
          setPlaying(false);
          return p;
        }
        return p + 1;
      });
    }, 1000 / speed);
    return () => clearInterval(timer);
  }, [playing, speed, scenario, last]);

  const seek = useCallback((p) => setPosition(Math.max(0, Math.min(last, p))), [last]);
  const step = useCallback((delta) => setPosition((p) => Math.max(0, Math.min(last, p + delta))), [last]);

  // 키보드: Space 재생/정지, ←/→ 한 shot, Shift+←/→ 50 shot, 1·2·5·0 속도
  useEffect(() => {
    function onKey(event) {
      const tag = event.target.tagName;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(tag) || event.target.isContentEditable) return;
      if (event.code === "Space") {
        event.preventDefault();
        setPlaying((v) => !v);
      } else if (event.key === "ArrowRight") {
        step(event.shiftKey ? 50 : 1);
      } else if (event.key === "ArrowLeft") {
        step(event.shiftKey ? -50 : -1);
      } else if (["1", "2", "5", "0"].includes(event.key)) {
        setSpeed(event.key === "0" ? 10 : Number(event.key));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  const ledger = useMemo(
    () =>
      new InspectionLedger({ ratio, scoreKey, shots: scenario?.shots ?? [] }),
    [ratio, scoreKey, scenario],
  );
  const alarmCenter = useMemo(() => new AlarmCenter(scenario?.alarms ?? []), [scenario]);
  // 재생 시계: shot마다 사이클 타임을 더한 경과 초 (구간 사이 정지 시간은 데이터에 없다)
  const elapsed = useMemo(() => cumulativeSum((scenario?.shots ?? []).map((s) => s.x.Cycle_Time)), [scenario]);
  const variables = useMemo(
    () => Object.fromEntries((meta?.variables ?? []).map((v) => [v.name, v])),
    [meta],
  );

  // 새 경고가 울리면 소리
  const activeCritical = scenario
    ? alarmCenter.active(position).filter((a) => a.level === "critical").length
    : 0;
  const previousCritical = useRef(0);
  useEffect(() => {
    if (sound && activeCritical > previousCritical.current) beep();
    previousCritical.current = activeCritical;
  }, [activeCritical, sound]);

  const acknowledge = useCallback((id) => setAcknowledged((s) => new Set(s).add(id)), []);
  const toggleAction = useCallback(
    (id, index) =>
      setActionChecks((c) => {
        const list = [...(c[id] ?? [])];
        list[index] = !list[index];
        return { ...c, [id]: list };
      }),
    [],
  );

  const value = {
    api,
    meta,
    summary,
    scenarioId,
    setScenarioId,
    scenario,
    loading,
    error,
    position,
    seek,
    step,
    playing,
    setPlaying,
    speed,
    setSpeed,
    ratio,
    setRatio,
    scoreKey,
    setScoreKey,
    theme,
    setTheme,
    sound,
    setSound,
    ledger,
    alarmCenter,
    elapsed,
    variables,
    acknowledged,
    acknowledge,
    actionChecks,
    toggleAction,
    selected,
    setSelected,
  };
  return <ReplayContext.Provider value={value}>{children}</ReplayContext.Provider>;
}

export function useReplay() {
  const context = useContext(ReplayContext);
  if (!context) throw new Error("useReplay는 ReplayProvider 안에서 써야 합니다");
  return context;
}
