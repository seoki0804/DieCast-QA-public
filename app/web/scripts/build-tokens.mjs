// docs/design/tokens.json(디자인 토큰의 유일한 원천) → src/styles/tokens.css(CSS 변수) + 사본 JSON.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../../../docs/design/tokens.json");
const outDir = resolve(here, "../src/styles");
const tokens = JSON.parse(readFileSync(source, "utf8"));

const name = (key) => `--${key.replace(/\./g, "-")}`;
const block = (selector, vars) =>
  `${selector} {\n${Object.entries(vars).map(([k, v]) => `  ${k}: ${v};`).join("\n")}\n}\n`;

function themeVars(mode) {
  const vars = {};
  for (const [key, value] of Object.entries(tokens.semantic[mode])) vars[name(key)] = value;
  tokens.primitive.series[mode].forEach((c, i) => (vars[`--series-${i + 1}`] = c));
  tokens.primitive.diverging[mode].forEach((c, i) => (vars[`--div-${i + 1}`] = c));
  vars["color-scheme"] = mode;
  return vars;
}

const shared = {};
for (const [k, v] of Object.entries(tokens.primitive.status)) shared[`--status-${k}`] = v;
tokens.primitive.sequential.forEach((c, i) => (shared[`--seq-${i + 1}`] = c));
shared["--font-sans"] = tokens.typography.family.sans;
shared["--font-mono"] = tokens.typography.family.mono;
for (const [k, v] of Object.entries(tokens.typography.scale)) {
  shared[`--text-${k}-size`] = `${v.size}px`;
  shared[`--text-${k}-line`] = `${v.line}px`;
  shared[`--text-${k}-weight`] = v.weight;
}
for (const [k, v] of Object.entries(tokens.space)) shared[`--space-${k.replace(".", "_")}`] = `${v}px`;
for (const [k, v] of Object.entries(tokens.radius)) shared[`--radius-${k}`] = `${v}px`;
for (const [k, v] of Object.entries(tokens.shadow)) shared[`--shadow-${k}`] = v;
for (const [k, v] of Object.entries(tokens.motion.duration)) shared[`--dur-${k}`] = `${v}ms`;
for (const [k, v] of Object.entries(tokens.motion.easing)) shared[`--ease-${k}`] = v;
for (const [k, v] of Object.entries(tokens.layout.shell)) shared[`--shell-${k}`] = `${v}px`;
for (const [k, v] of Object.entries(tokens.z)) shared[`--z-${k}`] = v;

const css = [
  `/* 자동 생성: npm run tokens (원본 docs/design/tokens.json ${tokens.$meta.version}) */\n`,
  block(":root", shared),
  block(':root, :root[data-theme="light"]', themeVars("light")),
  block(':root[data-theme="dark"]', themeVars("dark")),
  `@media (prefers-reduced-motion: reduce) {\n  :root { --dur-fast: 0ms; --dur-base: 0ms; --dur-slow: 0ms; }\n}\n`,
].join("\n");

mkdirSync(outDir, { recursive: true });
writeFileSync(resolve(outDir, "tokens.css"), css);
writeFileSync(resolve(outDir, "tokens.json"), JSON.stringify(tokens, null, 2));
console.log(`tokens.css 생성 (${Object.keys(shared).length}개 공통 변수, 밝음·어두움 테마)`);
