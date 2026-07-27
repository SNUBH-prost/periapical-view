"""엑셀 읽기/쓰기 — 원본 서식을 유지한 채 지정한 열만 채워 넣는다."""
from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import load_workbook


def _norm(s) -> str:
    """열 제목 비교용: 앞뒤 공백/중복 공백을 무시한다 (엑셀 제목의 오타성 공백 대응)."""
    if s is None:
        return ""
    return " ".join(str(s).split()).strip()


def read_header(path: str):
    """첫 번째 시트의 헤더(제목행)를 읽어 {정규화이름: 열번호(1-base)} 를 돌려준다."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    header = {}
    for col_idx, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1)), start=1):
        name = _norm(cell.value)
        if name:
            header[name] = col_idx
    wb.close()
    return header


def iter_rows_text(path: str, text_col_idx: int, key_col_idx: int | None):
    """(행번호, 차트텍스트, 키값) 을 데이터 행마다 순서대로 내보낸다."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        text = row[text_col_idx - 1].value if len(row) >= text_col_idx else None
        key = None
        if key_col_idx and len(row) >= key_col_idx:
            key = row[key_col_idx - 1].value
        yield row_idx, ("" if text is None else str(text)), key
    wb.close()


def write_values(src_path: str, dst_path: str, updates: dict, make_backup: bool = True):
    """updates = {(행번호, 열번호): 값} 을 엑셀에 써 넣고 dst_path 로 저장한다."""
    if make_backup and Path(src_path).resolve() == Path(dst_path).resolve():
        backup = str(Path(src_path).with_suffix("")) + "_백업" + Path(src_path).suffix
        shutil.copy2(src_path, backup)

    wb = load_workbook(src_path)          # 서식 유지를 위해 read_only 아님
    ws = wb.active
    for (r, c), value in updates.items():
        ws.cell(row=r, column=c, value=value)
    wb.save(dst_path)
    wb.close()
    return dst_path
