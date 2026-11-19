// 보고서 서식 도구: 제목·문단·목록·표·그림을 같은 스타일로 만들고 그림·표 번호를 매긴다.
import { readFileSync } from "node:fs";

import {
  AlignmentType,
  BorderStyle,
  Footer,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  PageNumber,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";

export const FONT = "맑은 고딕";
export const COLORS = { ink: "0B0B0B", secondary: "52514E", muted: "898781", accent: "256ABF", rule: "C3C2B7", header: "EEF4FC", note: "F4F3EF" };
const CM = 567; // 1 cm = 567 DXA
export const CONTENT_CM = 16.6; // A4 21cm - 좌우 여백 2.2cm

/** CSV 한 파일 → 객체 배열 (따옴표 안의 쉼표 지원). 숫자처럼 보이는 값은 숫자로. */
export function readCsv(path) {
  const text = readFileSync(path, "utf8").replace(/^﻿/, "");
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell || row.length) rows.push([...row, cell]);
  const [header, ...body] = rows.filter((r) => r.length > 1 || r[0]);
  return body.map((r) =>
    Object.fromEntries(header.map((h, k) => [h || `col${k}`, r[k] !== "" && !Number.isNaN(Number(r[k])) ? Number(r[k]) : r[k]])),
  );
}

/** PNG 머리에서 가로·세로 픽셀. */
function pngSize(buffer) {
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

export const pct = (v, d = 1) => (v == null || v === "" ? "–" : `${(v * 100).toFixed(d)}%`);
export const num = (v, d = 2) => (v == null || v === "" ? "–" : Number(v).toFixed(d));

/** '**굵게**'와 '^{위첨자}' 표시를 TextRun으로 (예: 2^{4−1}). */
export function runs(text, base = {}) {
  const pieces = String(text)
    .split("**")
    .flatMap((part, k) => part.split(/\^\{([^}]*)\}/).map((piece, j) => ({ piece, bold: k % 2 === 1, sup: j % 2 === 1 })))
    .filter(({ piece }) => piece);
  if (!pieces.length) pieces.push({ piece: "", bold: false, sup: false }); // 빈 칸도 글자 크기를 유지
  return pieces.map(({ piece, bold, sup }) => new TextRun({ font: FONT, ...base, text: piece, bold: bold || base.bold, superScript: sup || undefined }));
}

/** 본문 폭과 문단·목록 간격. 제안서처럼 여백이 다른 문서는 바꿔 넘긴다. */
// h1Rule: 장 제목 아래 가는 선. 장마다 쪽을 넘기지 않고 이어 쓸 때 장 경계를 보이게 한다.
export const REPORT_LAYOUT = { contentCm: CONTENT_CM, body: { after: 120, line: 300 }, list: { after: 60, line: 290 }, h1Rule: true };

export class ReportBuilder {
  constructor(layout = REPORT_LAYOUT) {
    this.layout = layout;
    this.children = [];
    this.figures = 0;
    this.tables = 0;
    this.lists = 0;
    this.headings = []; // 목차용 [{ title, level }]
  }

  heading(text, level) {
    const style = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][level - 1];
    this.headings.push({ title: String(text).replaceAll("**", ""), level });
    const rule = level === 1 && this.layout.h1Rule ? { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLORS.rule, space: 6 } } : undefined;
    this.children.push(new Paragraph({ heading: style, border: rule, children: runs(text) }));
  }

  /** 참고문헌 한 항목: [번호] 뒤로 내어쓰기. */
  reference(number, text) {
    this.children.push(
      new Paragraph({
        children: runs(`[${number}]  ${text}`, { size: 19 }),
        indent: { left: 520, hanging: 520 },
        spacing: { after: 70, line: 280 },
      }),
    );
  }

  h1(text) {
    this.heading(text, 1);
  }

  h2(text) {
    this.heading(text, 2);
  }

  h3(text) {
    this.heading(text, 3);
  }

  p(text, options = {}) {
    const { size, after, line } = this.layout.body;
    this.children.push(new Paragraph({ children: runs(text, { size, ...options.run }), spacing: { after, line }, alignment: options.align ?? AlignmentType.JUSTIFIED }));
  }

  /** 글머리표 목록. 항목이 배열이면 [본문, [하위 항목…]]. */
  bullets(items, level = 0) {
    for (const item of items) {
      const [text, children] = Array.isArray(item) ? item : [item, null];
      const { size, after, line } = this.layout.list;
      this.children.push(new Paragraph({ numbering: { reference: "bullets", level }, children: runs(text, { size }), spacing: { after, line } }));
      if (children) this.bullets(children, level + 1);
    }
  }

  numbered(items) {
    this.lists += 1;
    for (const text of items) {
      const { size, after, line } = this.layout.list;
      this.children.push(new Paragraph({ numbering: { reference: "numbers", level: 0, instance: this.lists }, children: runs(text, { size }), spacing: { after, line } }));
    }
  }

  /** 강조 상자 (요약·핵심 메시지). */
  callout(title, lines) {
    const shading = { type: ShadingType.CLEAR, fill: COLORS.note, color: "auto" };
    const border = { left: { style: BorderStyle.SINGLE, size: 18, color: COLORS.accent, space: 8 } };
    this.children.push(new Paragraph({ children: runs(title, { bold: true, color: COLORS.accent }), shading, border, spacing: { before: 120, after: 0 } }));
    lines.forEach((line, k) =>
      this.children.push(new Paragraph({ children: runs(line), shading, border, spacing: { after: k === lines.length - 1 ? 160 : 40, line: 276 } })),
    );
  }

  caption(text) {
    this.children.push(new Paragraph({ children: runs(text, { size: 18, color: COLORS.secondary }), alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 } }));
  }

  figure(path, caption, widthCm = this.layout.contentCm) {
    const data = readFileSync(path);
    const { width, height } = pngSize(data);
    const px = (widthCm / 2.54) * 96;
    this.figures += 1;
    this.children.push(
      new Paragraph({
        alignment: AlignmentType.CENTER,
        keepNext: true,
        spacing: { before: 120 },
        children: [new ImageRun({ type: "png", data, transformation: { width: Math.round(px), height: Math.round((px * height) / width) }, altText: { title: caption, description: caption, name: `figure-${this.figures}` } })],
      }),
    );
    this.caption(`그림 ${this.figures}. ${caption}`);
  }

  /**
   * 표: columns = [{ label, width(cm), align?: "right"|"center" }], rows = 문자열 배열의 배열.
   * 열 너비 합이 본문 너비를 넘으면 비율대로 줄인다.
   */
  table(caption, columns, rows) {
    const total = columns.reduce((a, c) => a + c.width, 0);
    const scale = Math.min(1, this.layout.contentCm / total);
    const widths = columns.map((c) => Math.round(c.width * scale * CM));
    const border = { style: BorderStyle.SINGLE, size: 4, color: COLORS.rule };
    const borders = { top: border, bottom: border, left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" } };
    // keepNext: 마지막 행만 빼고 다음 행과 붙여, 짧은 표가 쪽 경계에서 갈라지지 않게 한다
    const cell = (text, k, header, keepNext) =>
      new TableCell({
        width: { size: widths[k], type: WidthType.DXA },
        borders,
        shading: header ? { type: ShadingType.CLEAR, fill: COLORS.header, color: "auto" } : undefined,
        margins: { top: 50, bottom: 50, left: 90, right: 90 },
        children: [
          new Paragraph({
            keepNext,
            alignment: columns[k].align === "right" ? AlignmentType.RIGHT : columns[k].align === "center" ? AlignmentType.CENTER : AlignmentType.LEFT,
            children: runs(text ?? "", { size: 17, bold: header }),
          }),
        ],
      });
    this.tables += 1;
    this.children.push(new Paragraph({ children: runs(`표 ${this.tables}. ${caption}`, { size: 18, bold: true, color: COLORS.secondary }), keepNext: true, spacing: { before: 160, after: 60 } }));
    this.children.push(
      new Table({
        width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
        columnWidths: widths,
        rows: [
          new TableRow({ tableHeader: true, children: columns.map((c, k) => cell(c.label, k, true, true)) }),
          ...rows.map((r, i) => new TableRow({ cantSplit: true, children: r.map((v, k) => cell(String(v), k, false, i < rows.length - 1)) })),
        ],
      }),
    );
    this.children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
  }

  pageBreak() {
    this.children.push(new Paragraph({ pageBreakBefore: true, children: [] }));
  }
}

export const STYLES = {
  default: { document: { run: { font: FONT, size: 21, color: COLORS.ink } } },
  paragraphStyles: [
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 32, bold: true, color: COLORS.ink }, paragraph: { spacing: { before: 360, after: 160 }, keepNext: true, outlineLevel: 0 } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 26, bold: true, color: COLORS.ink }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 1 } },
    { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 23, bold: true, color: COLORS.secondary }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 2 } },
  ],
};

export const NUMBERING = {
  config: [
    {
      reference: "bullets",
      levels: [0, 1, 2].map((level) => ({
        level,
        format: LevelFormat.BULLET,
        text: ["•", "–", "·"][level],
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360 + level * 360, hanging: 260 } } },
      })),
    },
    {
      reference: "numbers",
      levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 300 } } } }],
    },
  ],
};

export function pageFooter() {
  return new Footer({
    children: [
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: COLORS.muted })],
      }),
    ],
  });
}
