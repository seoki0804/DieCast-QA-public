// 보고서 .docx → PDF(LibreOffice), 그리고 PDF에서 제목별 쪽 번호를 읽어 toc_pages.json에 쓴다.
// build_report.mjs가 이 쪽 번호로 목차를 채운다(Word에서 열면 Word가 다시 갱신한다).
// 실행: npm run pdf  (LibreOffice와 uv 필요)
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(HERE, "..", "docs", "report");
const DOCX = join(OUT_DIR, "DieCast-QA_최종보고서.docx");
const PDF = DOCX.replace(/\.docx$/, ".pdf");
const SOFFICE = [
  process.env.SOFFICE,
  "C:/Program Files/LibreOffice/program/soffice.exe",
  "/Applications/LibreOffice.app/Contents/MacOS/soffice",
  "/usr/bin/soffice",
].find((p) => p && existsSync(p));

if (!SOFFICE) throw new Error("LibreOffice(soffice)를 찾지 못했다. SOFFICE 환경 변수로 경로를 지정한다.");
execFileSync(SOFFICE, ["--headless", "--convert-to", "pdf", "--outdir", OUT_DIR, DOCX], { stdio: "ignore" });
execFileSync("uv", ["run", "-q", "--with", "pymupdf>=1.24", "python", "-I", join(HERE, "toc_pages.py"), PDF, join(HERE, "toc_pages.json")], { stdio: "inherit", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
console.log(`PDF: ${PDF}`);
