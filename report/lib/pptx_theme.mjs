// pptxgenjs가 쓴 .pptx에 덱의 테마 색·이름과 한글 글꼴을 넣는다.
// pptxgenjs는 테마 글꼴(라틴)만 쓰고 색은 Office 기본 팔레트로 고정하므로, 저장 후 theme1.xml을 고친다.
// 함께 고치는 것: <c:crossesAt val="autoZero"/>(PowerPoint가 복구를 요구), 폴더 항목(일부 공유 서비스가 거부).
import { readFileSync, writeFileSync } from "node:fs";

import JSZip from "jszip";

const SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];

/** theme = { name, eastAsianFont, colors: { dk1 … folHlink } } (색은 # 없는 6자리 16진수) */
export async function applyTheme(path, theme) {
  for (const k of SLOTS) {
    if (!/^[0-9A-F]{6}$/i.test(theme.colors[k] ?? "")) throw new Error(`테마 색 ${k}가 6자리 16진수가 아님: ${theme.colors[k]}`);
  }
  const zip = await JSZip.loadAsync(readFileSync(path));
  const part = "ppt/theme/theme1.xml";
  const scheme = `<a:clrScheme name="${theme.name}">${SLOTS.map((k) => `<a:${k}><a:srgbClr val="${theme.colors[k].toUpperCase()}"/></a:${k}>`).join("")}</a:clrScheme>`;
  const xml = (await zip.file(part).async("string"))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${theme.name}"`)
    .replaceAll('<a:ea typeface=""/>', `<a:ea typeface="${theme.eastAsianFont}"/>`);
  if (!xml.includes(scheme)) throw new Error("theme1.xml에 <a:clrScheme>이 없음");
  zip.file(part, xml);

  for (const name of Object.keys(zip.files)) {
    if (!name.endsWith(".xml")) continue;
    const text = await zip.file(name).async("string");
    // 16진수만 받는 옵션(그리드 선·그림자·한 계열 막대 색)에 테마 색 이름을 넘기면 잘못된 색이 된다
    const bad = text.match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) throw new Error(`${name}: 16진수가 아닌 색 "${bad[1]}" (16진수만 받는 옵션에 테마 색 이름을 넘김)`);
    if (text.includes('<c:crossesAt val="autoZero"/>')) zip.file(name, text.replaceAll('<c:crossesAt val="autoZero"/>', '<c:crosses val="autoZero"/>'));
  }
  // 폴더 항목만 지운다 (zip.remove(폴더)는 안의 파일까지 지우므로 쓰지 않는다)
  for (const name of Object.keys(zip.files)) if (zip.files[name].dir) delete zip.files[name];
  writeFileSync(path, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}
