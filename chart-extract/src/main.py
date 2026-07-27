"""
차트 추출기 — 실행 진입점 (임플란트당 한 줄 출력)

사용법:
    python -m src.main --excel 입력.xlsx
    python -m src.main --excel 입력.xlsx --check     (읽기만, 쓰지 않음)
    python -m src.main --excel 입력.xlsx --out 결과.xlsx
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import excel_io
from . import parse as P

OUTPUT_HEADERS = [
    "Serial No.", "환자번호", "나이", "생년월일", "성별",
    "임플란트 식립 부위(상악/하악)", "임플란트 식립 시기", "임플란트 회사",
    "임플란트 직경", "임플란트길이", "골이식 여부",
    "당화혈색소(수술전)", "당화혈색소 측정시기(수술전)",
    "당화혈색소(수술후)", "당화혈색소 측정시기(수술후)", "당화혈색소 (술전- 술후)",
    "ISQ 측정량(협)", "ISQ 측정량(설)", "ISQ 측정평균",
    # ── 확인용 보조 열 (프로그램이 판단 근거를 남김) ──
    "치식(FDI)", "ISQ원본", "ISQ측정일", "식립노트일",
]


def _brand_for_tooth(notes, tooth):
    """환자의 모든 노트에서 해당 치아번호 옆에 나오는 회사/제품명을 찾는다."""
    pat = re.compile(r"#\s*0*" + str(tooth) + r"\s*i?\b")
    for n in notes:
        for line in n["text"].splitlines():
            if pat.search(line):
                b = P.find_brand(line)
                if b:
                    return b
    # 줄 단위로 못 찾으면 노트 전체에서라도
    for n in notes:
        if pat.search(n["text"]):
            b = P.find_brand(n["text"])
            if b:
                return b
    return ""


def _pick_isq(readings, install_date):
    """식립일 이후 가장 이른 측정을 우선 선택. 없으면 가장 이른 것."""
    if not readings:
        return None
    def key(r):
        return r["date"] or "9999-99-99"
    after = [r for r in readings if (r["date"] or "9999") >= (install_date or "0000")]
    pool = sorted(after or readings, key=key)
    return pool[0]


def process(records):
    """노트 레코드 목록 → 임플란트당 출력 행 목록."""
    # 환자별 그룹 (입력 순서 유지)
    patients = {}
    for r in records:
        patients.setdefault(r["patient"], []).append(r)

    out_rows = []
    serial = 0
    for pat, notes in patients.items():
        # 인적사항: 값이 있는 첫 레코드에서
        age = next((n["age"] for n in notes if n["age"] not in (None, "")), "")
        birth = next((n["birth"] for n in notes if n["birth"] not in (None, "")), "")
        sex = next((n["sex"] for n in notes if n["sex"]), "")

        # 1) 식립기록 수집
        implants = {}          # tooth -> {date, dia, len, gbr}
        isq_all = []           # {tooth, vals, date, install_teeth}
        for n in notes:
            d = P.note_date(n["text"])
            install_teeth = set()
            if P.is_installation_note(n["text"]):
                gbr = P.has_gbr(n["text"])
                for tooth, spec in P.parse_specs(n["text"]).items():
                    install_teeth.add(tooth)
                    if tooth not in implants:
                        implants[tooth] = {
                            "date": d, "diameter": spec["diameter"],
                            "length": spec["length"], "gbr": gbr,
                        }
            for tooth, vals in P.find_isq(n["text"]):
                isq_all.append({"tooth": tooth, "vals": vals, "date": d,
                                "install_teeth": install_teeth})

        # 2) 임플란트당 한 줄
        for tooth in sorted(implants):
            info = implants[tooth]
            # 이 치아에 해당하는 ISQ 후보: 치아번호 일치 + (같은 식립노트의 번호없는 ISQ)
            cand = [r for r in isq_all if r["tooth"] == tooth]
            cand += [r for r in isq_all
                     if r["tooth"] is None and tooth in r["install_teeth"]]
            chosen = _pick_isq(cand, info["date"])

            buccal = lingual = mean = ""
            isq_raw = isq_date = ""
            if chosen:
                buccal, lingual, mean = P.isq_fields(chosen["vals"])
                isq_raw = "/".join(str(v) for v in chosen["vals"])
                isq_date = chosen["date"]

            serial += 1
            out_rows.append([
                serial, pat, age, birth, sex,
                (P.arch_from_tooth(tooth) + f" #{tooth}").strip(),  # 부위
                info["date"],                                       # 식립 시기
                _brand_for_tooth(notes, tooth),                     # 회사
                info["diameter"], info["length"],
                "Y" if info["gbr"] else "N",
                "", "", "", "", "",          # HbA1c 5칸 — 별도 검사결과로 나중에 연결
                buccal, lingual, mean,
                f"#{tooth}", isq_raw, isq_date, info["date"],       # 보조 열
            ])
    return out_rows


def run(excel_path: str, out_path: str | None, check_only: bool):
    result = excel_io.read_notes(excel_path)
    if not result:
        print("[오류] 엑셀에서 데이터를 읽지 못했습니다.")
        return 1
    records, meta = result
    print(f"노트 {len(records)}줄 읽음. (본문으로 인식한 열: '{meta['text_col']}')")
    n_pat = len({r['patient'] for r in records if r['patient']})
    print(f"환자 {n_pat}명.")

    if check_only:
        print("[점검] 읽기 정상. --check 빼고 다시 실행하면 결과 파일이 생깁니다.")
        return 0

    rows = process(records)
    print(f"임플란트 {len(rows)}건 추출.")

    src = Path(excel_path)
    dst = out_path or str(src.with_name(src.stem + "_결과" + src.suffix))
    excel_io.write_table(dst, OUTPUT_HEADERS, rows)
    print(f"저장 완료 → {dst}")
    print("※ HbA1c 5개 열은 비어 있습니다. 검사결과 파일을 주시면 환자번호+날짜로 채웁니다.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="차트 노트에서 임플란트 정보를 뽑아 엑셀로 정리합니다.")
    ap.add_argument("--excel", required=True, help="입력 엑셀 (.xlsx)")
    ap.add_argument("--out", default=None, help="결과 파일 경로 (기본: 입력_결과.xlsx)")
    ap.add_argument("--check", action="store_true", help="읽기만 하고 쓰지 않음")
    args = ap.parse_args()

    if not Path(args.excel).exists():
        print(f"[오류] 파일이 없습니다: {args.excel}")
        sys.exit(1)
    sys.exit(run(args.excel, args.out, args.check))


if __name__ == "__main__":
    main()
