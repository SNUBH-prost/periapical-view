"""
차트 추출기 — 실행 진입점

사용법:
    python -m src.main --excel 환자목록.xlsx
    python -m src.main --excel 환자목록.xlsx --check      (엑셀만 점검, 쓰지 않음)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import excel_io
from .rules import RULES


def load_config():
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _norm(s):
    return " ".join(str(s).split()).strip() if s is not None else ""


def run(excel_path: str, check_only: bool = False):
    cfg = load_config()
    header = excel_io.read_header(excel_path)

    # 1) 필요한 열이 엑셀에 다 있는지 확인
    text_col = _norm(cfg["chart_text_column"])
    if text_col not in header:
        print(f"[오류] 차트 내용 열 '{text_col}' 을 엑셀에서 못 찾았습니다.")
        print(f"       엑셀 첫 줄의 열 제목: {list(header)}")
        return 1
    text_idx = header[text_col]
    key_idx = header.get(_norm(cfg.get("key_column", "")))

    targets = []          # (열번호, rule함수, overwrite, 열이름)
    missing = []
    for col in cfg["columns"]:
        name = _norm(col["name"])
        rule = RULES.get(col["rule"])
        if name not in header:
            missing.append(col["name"])
            continue
        if rule is None:
            print(f"[경고] 규칙 '{col['rule']}' 이 rules.py 에 없습니다. 건너뜁니다.")
            continue
        targets.append((header[name], rule, col.get("overwrite", False), col["name"]))

    if missing:
        print(f"[경고] 엑셀에 없는 열(채우지 않음): {missing}")

    print(f"채울 항목 {len(targets)}개, 차트 열 = '{text_col}'")
    if check_only:
        n = sum(1 for _ in excel_io.iter_rows_text(excel_path, text_idx, key_idx))
        print(f"[점검] 데이터 {n}행 확인. 문제 없으면 --check 빼고 다시 실행하세요.")
        return 0

    # 2) 행마다 규칙 적용
    updates = {}
    filled_cells = 0
    rows = 0
    for row_idx, text, key in excel_io.iter_rows_text(excel_path, text_idx, key_idx):
        rows += 1
        if not text.strip():
            continue
        for col_idx, rule, overwrite, _name in targets:
            try:
                value = rule(text)
            except Exception as e:            # 한 칸이 실패해도 전체가 멈추지 않도록
                print(f"  [행 {row_idx}] 규칙 오류: {e}")
                value = ""
            if value != "" and value is not None:
                updates[(row_idx, col_idx)] = value
                filled_cells += 1

    print(f"데이터 {rows}행 처리, {filled_cells}칸 채움.")

    # 3) 저장
    src = Path(excel_path)
    if cfg.get("in_place", False):
        dst = str(src)
    else:
        dst = str(src.with_name(src.stem + cfg.get("output_suffix", "_결과") + src.suffix))
    out = excel_io.write_values(excel_path, dst, updates, make_backup=True)
    print(f"저장 완료 → {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="차트 내용에서 항목을 추출해 엑셀에 채웁니다.")
    ap.add_argument("--excel", required=True, help="입력 엑셀 파일 경로 (.xlsx)")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 점검만")
    args = ap.parse_args()

    if not Path(args.excel).exists():
        print(f"[오류] 파일이 없습니다: {args.excel}")
        sys.exit(1)
    sys.exit(run(args.excel, check_only=args.check))


if __name__ == "__main__":
    main()
