"use client";

// 화면 언어(한국어·English). 주소의 ?lang=en이 먼저, 없으면 브라우저에 저장한 선택, 기본은 한국어.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { LANGS, Localizer } from "@/lib/i18n";

const I18nContext = createContext(null);
const KEY = "diecast.lang";

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState("ko");

  useEffect(() => {
    const linked = new URLSearchParams(window.location.search).get("lang");
    let saved = null;
    try {
      saved = JSON.parse(window.localStorage.getItem(KEY));
    } catch {
      // 저장소를 못 읽어도 기본값으로 동작한다
    }
    setLangState(LANGS.includes(linked) ? linked : LANGS.includes(saved) ? saved : "ko");
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((value) => {
    setLangState(value);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(value));
    } catch {
      // 저장하지 못해도 이번 화면에는 적용된다
    }
  }, []);

  const value = useMemo(() => {
    const L = new Localizer(lang);
    return { lang, setLang, L, t: (key, params) => L.t(key, params) };
  }, [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n은 I18nProvider 안에서 써야 합니다");
  return context;
}
