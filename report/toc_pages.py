"""보고서 PDF에서 줄 전체가 제목과 같은 첫 쪽을 찾아 {제목: 쪽} JSON으로 쓴다 (목차 쪽 제외).

사용: python toc_pages.py 보고서.pdf toc_pages.json
제목 목록은 직전 빌드가 남긴 toc_pages.json의 "headings"를 쓴다.
"""

import json
import sys
from pathlib import Path

import pymupdf


def main(pdf_path: str, json_path: str) -> None:
    out = Path(json_path)
    headings = json.loads(out.read_text(encoding="utf-8"))["headings"]
    doc = pymupdf.open(pdf_path)
    lines_by_page = [{ln.strip() for ln in page.get_text().splitlines()} for page in doc]
    toc_end = next(
        (i for i, lines in enumerate(lines_by_page) if headings[0] in lines and i > 1), 0
    )  # 목차 다음 쪽부터 본문
    pages = {}
    for title in headings:
        found = [i for i in range(toc_end, len(lines_by_page)) if title in lines_by_page[i]]
        if found:
            pages[title] = found[0] + 1
    missing = [t for t in headings if t not in pages]
    out.write_text(
        json.dumps({"headings": headings, "pages": pages}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"제목 {len(pages)}/{len(headings)}개 쪽 번호, 전체 {doc.page_count}쪽")
    if missing:
        print("찾지 못한 제목:", ", ".join(missing))


if __name__ == "__main__":
    main(*sys.argv[1:3])
