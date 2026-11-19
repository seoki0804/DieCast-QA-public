"use client";

// '?' 도움말: 설명 문장을 화면에 펼쳐 두지 않고 마우스·키보드 초점·탭으로 연다. Esc로 닫는다.
import { useId, useState } from "react";

import { useI18n } from "@/components/i18n/I18nProvider";

export default function HelpTip({ text, align = "left" }) {
  const { t } = useI18n();
  const id = useId();
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <span className="help" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        className="help-btn"
        aria-label={t("help")}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
      >
        ?
      </button>
      {open ? (
        <span role="tooltip" id={id} className={`help-tip help-${align}`}>
          {text}
        </span>
      ) : null}
    </span>
  );
}
