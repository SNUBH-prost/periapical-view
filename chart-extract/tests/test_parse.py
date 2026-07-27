"""
파서 검증 — 실제 노트 형식을 본뜬 익명 샘플(환자식별자 제거).
실행:  python -m tests.test_parse
"""
from src.main import process

# 한 환자의 노트들 (환자번호=0000000, 생년월일/의사명 제거). 임상 문장 형식만 유지.
_NOTES = [
    # 2024-06-18 : 보철 노트 — #24,#26 ISQ
    """■ 외래경과\t작성과 : 치과 ( 2024-06-18 )
소견
#24i(3.6),26i(4.5) superline 2024.02.13 1st OP
ISQ
#24i:80/77
#26i:81/81
fixture level imp for #24i=26i
""",
    # 2022-08-11 : #15 식립
    """■ 외래경과\t작성과 : 치과 ( 2022-08-11 )
소견
   #15 Implant with GBR / 임플란트동의서 작성
Tx>
1.#15 Implant installation
(#15i superline : 4.0 mm X 10mm)  hand tight healing abutment 연결
""",
    # 2021-12-13 : #35 식립 (설치노트 ISQ 80/80, bone graft)
    """■ 외래경과\t작성과 : 치과 ( 2021-12-13 )
소견
   #35 Implant with GBR / 임플란트동의서 작성
Tx>
1.#35 Implant installation
(#35i: 4.0mm X 8.5mm) ISQ: 80/80 /healing abutment 연결
note) drilling시 채취한 자가골 buccal부위에 bone graft함.
""",
    # 2023-03-02 : #15 보철 — ISQ 85/90, tissue thickness 3/3/3/3 (혼동 금지)
    """■ 외래경과\t작성과 : 치과 ( 2023-03-02 )
소견
   #15i(4.0) superline, 2022.08.11
ISQ
#15i:85/90
tissue thickness
#15i:3/3/3/3
""",
    # 2024-02-13 : #24,#26 식립 (superline, GBR)
    """■ 외래경과\t작성과 : 치과 ( 2024-02-13 )
소견
   Implant with GBR / 임플란트동의서 작성
Tx>
Flapless surgery
1.#24,26 Implant installation with digital guide stent
 (#24 superline : 3.6 mm X 10 mm) X HA연결
 (#26 superline : 4.5mm X 10 mm) X HA연결
  - ISQ: hand tight good
  - GBR with ( bone :  /membrane :   )
""",
    # 2022-04-18 : #35 보철 — luna, ISQ 81/81, tissue thickness 3/3/3/3
    """■ 외래경과\t작성과 : 치과 ( 2022-04-18 )
소견
   #35i(4.0), luna, 2021-12-13
ISQ
#35i:81/81
tissue thickness
#35i:3/3/3/3
""",
    # 2016-06-30 : #45 는 직경만 언급된 과거 타원 식립 참조(상세 규격/수술기록 없음) → 제외돼야 함
    """■ 외래경과\t작성과 : 치과 ( 2016-06-30 )
소견
   #45i(4.0) stock, PFM 다른 병원 식립
""",
]


def _records():
    return [{"patient": "0000000", "age": 81, "birth": "1900-01-01",
             "sex": "여", "text": t, "row": i} for i, t in enumerate(_NOTES, 2)]


def _check(cond, msg):
    print(("  OK  " if cond else "FAIL  ") + msg)
    assert cond, msg


def main():
    rows = process(_records())
    by_tooth = {r[17]: r for r in rows}   # 보조열 '치식' = "#NN"
    print(f"추출된 임플란트: {sorted(by_tooth)}  (총 {len(rows)}건)\n")

    _check(len(rows) == 4, "상세규격(1차수술) 있는 임플란트만 4건 (#15,#24,#26,#35)")
    _check(set(by_tooth) == {"#15", "#24", "#26", "#35"}, "치아번호 정확")
    _check("#45" not in by_tooth, "#45(직경만 언급, 상세규격 없음)은 제외")

    r15 = by_tooth["#15"]
    _check(r15[4] == "#15i", "#15 부위=#15i")
    _check(r15[5] == "2022-08-11", "#15 식립일")
    _check(r15[6] == "Dentium Superline", "#15 회사=Dentium Superline")
    _check(r15[7] == "4.0" and r15[8] == "10", "#15 규격 4.0x10")
    _check(r15[9] == "0", "#15 골이식=0 (정형문구뿐, 실제 재료 없음)")
    _check(r15[14] == 85 and r15[15] == 90, "#15 ISQ 협85/설90")

    r35 = by_tooth["#35"]
    _check(r35[4] == "#35i", "#35 부위=#35i")
    _check(r35[6] == "Dentium Luna", "#35 회사=Dentium Luna (보철노트에서)")
    _check(r35[7] == "4.0" and r35[8] == "8.5", "#35 규격 4.0x8.5")
    _check(r35[14] == 81 and r35[15] == 81, "#35 ISQ=식립 다음차트 81/81 (설치당일 80/80 아님)")
    _check(r35[9] == "1(자가골)", "#35 골이식=1(자가골)")

    r24 = by_tooth["#24"]
    _check(r24[7] == "3.6" and r24[8] == "10", "#24 규격 3.6x10")
    _check(r24[14] == 80 and r24[15] == 77, "#24 ISQ 80/77")
    _check(r24[9] == "0", "#24 골이식=0 (bone/membrane 비어있음)")

    r26 = by_tooth["#26"]
    _check(r26[7] == "4.5" and r26[8] == "10", "#26 규격 4.5x10")
    _check(r26[14] == 81 and r26[15] == 81, "#26 ISQ 81/81")

    print("\n모든 검증 통과 ✅")


if __name__ == "__main__":
    main()
