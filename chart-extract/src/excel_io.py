"""엑셀 입출력.

입력  : 외래경과 노트가 한 줄에 하나씩 들어있는 엑셀 (환자 한 명이 여러 줄)
출력  : 임플란트 한 개당 한 줄인 새 엑셀
"""
from __future__ import annotations

from openpyxl import Workbook, load_workbook


def _norm(s) -> str:
    return " ".join(str(s).split()).strip() if s is not None else ""


def _find_col(header_norm, candidates):
    """정규화된 헤더 목록에서 후보 키워드를 포함하는 첫 열의 인덱스(0-base)."""
    for i, h in enumerate(header_norm):
        for c in candidates:
            if c in h:
                return i
    return None


def read_notes(path: str):
    """
    엑셀을 읽어 노트 레코드 목록을 돌려준다.
    각 레코드: {patient, age, birth, sex, text, row}
    열은 제목으로 자동 인식하고, 노트 본문 열은 '가장 긴 텍스트 열'로 자동 판별한다.
    """
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []

    header = [_norm(x) for x in rows[0]]
    idx_pat = _find_col(header, ["환자번호", "등록번호", "chart"])
    idx_age = _find_col(header, ["나이", "age", "연령"])
    idx_birth = _find_col(header, ["생년월일", "birth", "생일"])
    idx_sex = _find_col(header, ["성별", "sex", "성"])

    # 본문(노트) 열: 데이터 행에서 평균 글자수가 가장 긴 열
    data = rows[1:]
    ncol = len(header)
    best_col, best_len = None, -1
    for c in range(ncol):
        total = 0
        for r in data[:200]:
            v = r[c] if c < len(r) else None
            total += len(str(v)) if v is not None else 0
        if total > best_len:
            best_len, best_col = total, c
    idx_text = best_col

    records = []
    for ri, r in enumerate(data, start=2):
        def cell(i):
            return r[i] if (i is not None and i < len(r)) else None
        text = cell(idx_text)
        records.append({
            "patient": _norm(cell(idx_pat)),
            "age": cell(idx_age),
            "birth": cell(idx_birth),
            "sex": _norm(cell(idx_sex)),
            "text": "" if text is None else str(text),
            "row": ri,
        })
    return records, {"text_col": header[idx_text] if idx_text is not None else "?"}


def write_table(path: str, headers, rows):
    """headers = [열이름...], rows = [[값...], ...] 를 새 엑셀로 저장."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()
    return path
