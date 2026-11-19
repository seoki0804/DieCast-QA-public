"use client";

// ⑤ 설정·정보: 테마·언어·소리, 분석 가정, 알람 규칙 파라미터, 모델 학습 기록.
import { useI18n } from "@/components/i18n/I18nProvider";
import { useReplay } from "@/components/replay/ReplayProvider";
import { Card, DataTable, Segmented } from "@/components/ui/primitives";
import { int, pct } from "@/lib/format";

export default function SettingsView() {
  const { theme, setTheme, sound, setSound, meta, scenario, variables } = useReplay();
  const { L, t, lang, setLang } = useI18n();
  return (
    <div className="stack">
      <h1 className="page-title">{t("se.title")}</h1>
      <div className="grid-2">
        <Card title={t("se.screen")}>
          <div className="controls">
            <div className="control">
              <div className="control-label">{t("se.theme")}</div>
              {/* aria-label은 e2e가 찾는 이름이라 언어와 관계없이 '테마' */}
              <Segmented
                label="테마"
                value={theme}
                onChange={setTheme}
                options={[
                  { value: "light", label: t("se.light") },
                  { value: "dark", label: t("se.dark") },
                ]}
              />
            </div>
            <div className="control">
              <div className="control-label">{t("se.lang")}</div>
              <Segmented
                label={t("se.lang")}
                value={lang}
                onChange={setLang}
                options={[
                  { value: "ko", label: "한국어" },
                  { value: "en", label: "English" },
                ]}
              />
            </div>
            <div className="control">
              <div className="control-label">{t("se.sound")}</div>
              <Segmented
                label={t("se.sound")}
                value={sound}
                onChange={setSound}
                options={[
                  { value: false, label: t("se.off") },
                  { value: true, label: t("se.on") },
                ]}
              />
            </div>
          </div>
          <p className="caption">{t("se.keys")}</p>
        </Card>
        <Card title={t("se.assumptions")}>
          <ul className="checks">
            {(meta?.assumptions ?? []).map((a) => (
              <li key={a}>{L.text(a)}</li>
            ))}
            <li>{t("se.units")}</li>
            <li>{t("se.data")}</li>
          </ul>
        </Card>
      </div>
      {scenario ? (
        <div className="grid-2">
          <Card title={t("se.rules")} meta={t("ref", { n: 9 })} flush>
            <DataTable
              columns={[
                { key: "label", label: t("col.item") },
                { key: "value", label: t("col.value"), numeric: true },
              ]}
              rows={Object.entries(scenario.meta.settings).map(([k, v]) => ({ label: t(`set.${k}`), value: v }))}
            />
          </Card>
          <Card title={t("se.models")} help={t("se.models.help")} meta={L.scenarioLabel(scenario.meta)} flush>
            <DataTable
              columns={[
                // shot 번호는 구간마다 다시 시작하므로 구간과 함께 쓴다
                { key: "position", label: t("col.appliedAt"), format: (v) => t("se.at", { run: scenario.shots[v].run, shot: int(scenario.shots[v].shot) }) },
                { key: "n_train", label: t("col.trainParts"), numeric: true, format: (v) => int(v) },
                { key: "prior", label: t("col.trainRate"), numeric: true, format: (v) => pct(v) },
                { key: "top", label: t("col.topVar"), format: (_, r) => L.variable(r.importance[0]?.[0], variables[r.importance[0]?.[0]]?.label) },
              ]}
              rows={scenario.meta.models}
            />
          </Card>
        </div>
      ) : null}
    </div>
  );
}
