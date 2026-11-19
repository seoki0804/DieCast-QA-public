// 제안서 서식: 기존 제안서(v2)와 같은 모양. A4, 여백 0.9cm, 맑은 고딕, 남색 제목과 밑줄, 라벨 칸 음영 표.
import {
  AlignmentType,
  BorderStyle,
  Footer,
  PageNumber,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";

import { FONT, ReportBuilder, runs } from "./doc.mjs";

const CM = 567;
export const P_COLORS = { navy: "194874", ink: "1F2937", gray: "646E78", fill: "EAF0F7", light: "F7F9FC", rule: "D5DCE6" };
export const PROPOSAL_MARGIN = 510; // 0.9cm
export const PROPOSAL_LAYOUT = {
  contentCm: 21 - (2 * PROPOSAL_MARGIN) / CM,
  body: { size: 19, after: 30, line: 276 },
  list: { size: 19, after: 0, line: 276 },
};

const ALIGN = { right: AlignmentType.RIGHT, center: AlignmentType.CENTER };

export class ProposalBuilder extends ReportBuilder {
  constructor() {
    super(PROPOSAL_LAYOUT);
  }

  /** 맨 위 머리 줄, 제목, 팀원 줄. */
  masthead(eyebrow, title, meta) {
    const line = (text, run, spacing) => new Paragraph({ spacing, children: [new TextRun({ text, font: FONT, ...run })] });
    this.children.push(
      line(eyebrow, { size: 16, bold: true, color: P_COLORS.navy }, { after: 10, line: 276 }),
      line(title, { size: 30, bold: true, color: P_COLORS.ink }, { after: 10, line: 300 }),
      line(meta, { size: 16, color: P_COLORS.gray }, { after: 20, line: 276 }),
    );
  }

  /** 표 위 작은 제목 ("검증 방식" 같은). */
  subhead(text) {
    this.children.push(new Paragraph({ keepNext: true, spacing: { before: 60, after: 30, line: 264 }, children: runs(text, { size: 18, bold: true, color: P_COLORS.ink }) }));
  }

  /** 연한 바탕에 왼쪽 남색 선이 있는 안내 상자. */
  note(title, lines) {
    const shading = { type: ShadingType.CLEAR, fill: P_COLORS.light, color: "auto" };
    const border = { left: { style: BorderStyle.SINGLE, size: 18, color: P_COLORS.navy, space: 6 } };
    this.children.push(new Paragraph({ shading, border, spacing: { before: 60, after: 0, line: 276 }, children: runs(title, { size: 18, bold: true, color: P_COLORS.navy }) }));
    lines.forEach((text, k) =>
      this.children.push(new Paragraph({ shading, border, spacing: { after: k === lines.length - 1 ? 80 : 0, line: 276 }, children: runs(text, { size: 18 }) })),
    );
  }

  /**
   * 격자 표. columns = [{ label, width(cm), align? }], rows = 문자열 배열의 배열.
   * labelCol이면 첫 열을 라벨 칸(음영, 남색 굵게, 가운데)으로 그린다. header=false면 머리 행 없이 그린다.
   */
  grid(columns, rows, { labelCol = false, header = true } = {}) {
    const total = columns.reduce((a, c) => a + c.width, 0);
    const widths = columns.map((c) => Math.round((c.width / total) * this.layout.contentCm * CM));
    const line = { style: BorderStyle.SINGLE, size: 4, color: P_COLORS.rule };
    const borders = { top: line, bottom: line, left: line, right: line };
    const cell = (text, k, kind, keepNext) => {
      const head = kind === "head" || kind === "label";
      return new TableCell({
        width: { size: widths[k], type: WidthType.DXA },
        borders,
        verticalAlign: "center",
        shading: head ? { type: ShadingType.CLEAR, fill: P_COLORS.fill, color: "auto" } : undefined,
        margins: { top: 40, bottom: 40, left: 80, right: 80 },
        children: [
          new Paragraph({
            keepNext,
            spacing: { after: 0, line: 252 },
            alignment: head ? AlignmentType.CENTER : (ALIGN[columns[k].align] ?? AlignmentType.LEFT),
            children: runs(text ?? "", { size: 17, bold: head, color: head ? P_COLORS.navy : undefined }),
          }),
        ],
      });
    };
    const body = rows.map(
      (r, i) => new TableRow({ cantSplit: true, children: r.map((v, k) => cell(String(v), k, labelCol && k === 0 ? "label" : "body", i < rows.length - 1)) }),
    );
    this.children.push(
      new Table({
        width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
        columnWidths: widths,
        rows: header ? [new TableRow({ tableHeader: true, children: columns.map((c, k) => cell(c.label, k, "head", true)) }), ...body] : body,
      }),
    );
    this.children.push(new Paragraph({ spacing: { after: 40 }, children: [] }));
  }

  /** 끝의 간격 문단을 1pt짜리로 바꿔, 마지막 표 뒤에 빈 쪽이 생기지 않게 한 본문을 돌려준다. */
  finish() {
    if (this.children.at(-1) instanceof Paragraph) this.children.pop();
    this.children.push(new Paragraph({ spacing: { before: 0, after: 0, line: 20, lineRule: "exact" }, children: [new TextRun({ text: "", size: 2 })] }));
    return this.children;
  }

  /** 라벨 | 내용 두 칸 표 (머리 행 없음). */
  labelTable(rows, labelCm = 2.6) {
    this.grid([{ label: "", width: labelCm }, { label: "", width: this.layout.contentCm - labelCm }], rows, { labelCol: true, header: false });
  }
}

export const PROPOSAL_STYLES = {
  default: { document: { run: { font: FONT, size: 19, color: P_COLORS.ink } } },
  paragraphStyles: [
    {
      id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 24, bold: true, color: P_COLORS.navy },
      paragraph: { spacing: { before: 120, after: 60, line: 264 }, keepNext: true, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: P_COLORS.rule, space: 1 } } },
    },
    {
      id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 20, bold: true, color: P_COLORS.ink },
      paragraph: { spacing: { before: 90, after: 30, line: 264 }, keepNext: true, outlineLevel: 1 },
    },
    {
      id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: FONT, size: 19, bold: true, color: P_COLORS.navy },
      paragraph: { spacing: { before: 60, after: 20, line: 264 }, keepNext: true, outlineLevel: 2 },
    },
  ],
};

/** "AI 기반 생산운영관리 · 프로젝트 제안서 · 1 / 5" */
export function proposalFooter(label) {
  const run = (children) => new TextRun({ children, font: FONT, size: 16, color: P_COLORS.gray });
  return new Footer({
    children: [
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [run([`${label}  ·  `]), run([PageNumber.CURRENT]), run([" / "]), run([PageNumber.TOTAL_PAGES])],
      }),
    ],
  });
}
