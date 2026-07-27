"""
전체 결과 파일 생성 (노트 추출 + HbA1c 조인 + 연구시트 양식으로 출력).

사용법:
    python -m src.deliver --raw 원본노트.xlsx --hba1c HbA1c.xlsx \
                          --template 연구시트.xlsx --out 결과.xlsx

- --raw      : 외래경과 노트 엑셀 (한 줄=한 노트). 필수.
- --hba1c    : HbA1c 검사결과 엑셀 (환자번호+접수일시+수치). 있으면 식립일 기준
               직전(술전)/직후(술후)로 조인. 없으면 HbA1c 칸은 비움.
- --template : 연구시트 엑셀. 있으면 그 첫 줄(열 제목)을 그대로 사용해 채운다.
               없으면 기본 열을 쓴다.
- 당뇨(DM)·투약·결과(골흡수/합병증/fail) 열은 다른 소스라서 '빈칸'으로 둔다.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import excel_io
from .main import process


def _as_date(v):
    """'YYYY-MM-DD' 문자열/날짜를 엑셀 날짜로. 변환 불가(미상 등)면 원본 그대로."""
    if isinstance(v, (datetime, date)):
        return v
    s = str(v)[:10] if v not in (None, "") else ""
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        return v if v not in (None, "") else None

DEFAULT_HEADERS = [
    "Serial No.", "환자번호", "나이", "생년월일", "성별",
    "임플란트 식립 부위(상악/하악)", "임플란트 식립 시기", "임플란트 회사",
    "임플란트 직경", "임플란트길이", "골이식 여부",
    "당화혈색소(수술전)", "당화혈색소 측정시기(수술전)",
    "당화혈색소(수술후)", "당화혈색소 측정시기(수술후)", "당화혈색소 (술전- 술후)",
    "ISQ 측정량(협)", "ISQ 측정량(설)", "ISQ 측정평균",
]
HELP_HEADERS = ["치식", "ISQ원본", "ISQ측정일"]


# 다른 소스라 노트에서 안 뽑는 열 → 기존 수기 입력이 있으면 보존한다.
DM_COLS = [   # 환자 단위
    "DM증 진단 시기", "DM type", "DM증진단시 나이(세)", "투약방법", "투약 약제",
    "약제 성분명", "투약시작 나이", "투약시작시 나이", "임플란트수술전 투약기간(년)",
]
OUTCOME_COLS = [   # 임플란트(치아) 단위
    "osseointagration 성공(1)", "보철 전 골흡수", "보철 후 골흡수", "보철 합병증",
    "치과용 임플란트의 fail여부", "fail시 경과기간", "PA",
]


def _tooth_num(v):
    import re
    m = re.search(r"\d{1,2}", str(v or ""))
    return m.group() if m else ""


def load_hba1c(path):
    """{환자번호: [(날짜, 값float or None, 값원본), ...] 정렬됨}"""
    if not path:
        return {}
    ws = load_workbook(path, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hb = {}
    for r in rows[1:]:
        p = str(r[1]); d = str(r[6])[:10]; v = r[5]
        try:
            vf = float(v)
        except (TypeError, ValueError):
            vf = None
        hb.setdefault(p, []).append((d, vf, v))
    for p in hb:
        hb[p].sort()
    return hb


def join_hba1c(hb, patient, surgery_date):
    """식립일 직전=술전, 직후=술후."""
    s = hb.get(patient, [])
    pre = [x for x in s if surgery_date and x[0] <= surgery_date]
    post = [x for x in s if surgery_date and x[0] > surgery_date]
    return (pre[-1] if pre else None), (post[0] if post else None)


DATE_COLS = ["생년월일", "임플란트 식립 시기", "DM증 진단 시기",
             "당화혈색소 측정시기(수술전)", "당화혈색소 측정시기(수술후)"]
# 노트에서 뽑은 핵심 열(살짝 강조)
KEY_COLS = ["임플란트 식립 부위(상악/하악)", "임플란트 식립 시기", "임플란트 회사",
            "임플란트 직경", "임플란트길이", "골이식 여부",
            "ISQ 측정량(협)", "ISQ 측정량(설)", "ISQ 측정평균"]
WIDE_COLS = {"투약 약제": 34, "약제 성분명": 40, "골이식 여부": 22, "임플란트 회사": 18}


def _style(ws, HDR, HELP, col, row_serials):
    from openpyxl.utils import get_column_letter as gcl
    ncol = len(HDR) + len(HELP)
    last = ws.max_row
    thin = Side(style="thin", color="D0D7DE")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # 헤더
    head_fill = PatternFill("solid", fgColor="2F5496")
    help_fill = PatternFill("solid", fgColor="7F7F7F")
    help_start = len(HDR)
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = help_fill if c > help_start else head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[1].height = 34

    # 열 너비
    for c in range(1, ncol + 1):
        name = str(ws.cell(row=1, column=c).value or "").strip()
        w = WIDE_COLS.get(name, min(max(len(name) + 2, 9), 16))
        ws.column_dimensions[gcl(c)].width = w

    # 날짜 형식 + 핵심열 인덱스
    date_idx = {col(n) for n in DATE_COLS if col(n) is not None}
    key_idx = {col(n) for n in KEY_COLS if col(n) is not None}

    band_a = PatternFill("solid", fgColor="FFFFFF")
    band_b = PatternFill("solid", fgColor="EAF1FB")   # 환자 구분 띠(연파랑)
    key_a = PatternFill("solid", fgColor="FFF8E1")    # 핵심열 강조(연노랑)
    key_b = PatternFill("solid", fgColor="FCEFC7")
    help_band = PatternFill("solid", fgColor="F0F0F0")

    for r in range(2, last + 1):
        serial = row_serials[r - 2]
        even = (serial % 2 == 0)
        for c in range(1, ncol + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = border
            i = c - 1
            if c > help_start:                       # 검증열
                cell.fill = help_band
                cell.font = Font(size=9, color="666666")
            elif i in key_idx:                        # 핵심 추출열
                cell.fill = key_b if even else key_a
            else:
                cell.fill = band_b if even else band_a
            if i in date_idx:
                cell.number_format = "yyyy-mm-dd"
            # 정렬: 대부분 가운데, 약제/성분명만 왼쪽
            name = str(HDR[i]).strip() if i < len(HDR) else ""
            cell.alignment = Alignment(
                horizontal="left" if name in ("투약 약제", "약제 성분명") else "center",
                vertical="center")

    ws.freeze_panes = "C2"      # Serial·환자번호 고정 + 헤더 고정
    ws.auto_filter.ref = f"A1:{gcl(ncol)}{last}"


def build(raw, hba1c_path, template, out):
    records, meta = excel_io.read_notes(raw)
    rows = process(records)

    demo = {}
    for r in records:
        p = str(r["patient"])
        demo.setdefault(p, (r["age"], r["birth"], r["sex"]))

    hb = load_hba1c(hba1c_path)

    cohort = None            # 연구 대상 환자 집합
    dm_by_pat = {}           # 환자 → {열이름: 값} (기존 수기 당뇨/투약)
    out_by_pt = {}           # (환자,치아) → {열이름: 값} (기존 수기 결과)
    pat_serial = {}          # 환자 → 원본 명단의 Serial No.
    pat_order = {}           # 환자 → 원본 명단 등장 순서(순번 없을 때 백업)
    if template:
        trows = list(load_workbook(template, data_only=True).active.iter_rows(values_only=True))
        thdr = [str(x).strip() if x is not None else "" for x in trows[0]]
        HDR = [h for h in trows[0] if h is not None]
        ti = {name: i for i, name in enumerate(thdr)}
        pat_i = ti.get("환자번호"); site_i = ti.get("임플란트 식립 부위(상악/하악)")
        serial_i = ti.get("Serial No.")
        cohort = set()
        for row in trows[1:]:
            if pat_i is None or pat_i >= len(row) or row[pat_i] in (None, ""):
                continue
            p = str(row[pat_i]); cohort.add(p)
            pat_order.setdefault(p, len(pat_order))
            if p not in pat_serial and serial_i is not None and serial_i < len(row) \
                    and row[serial_i] not in (None, ""):
                try:
                    pat_serial[p] = int(float(row[serial_i]))
                except (ValueError, TypeError):
                    pass
            for name in DM_COLS:
                j = ti.get(name)
                if j is not None and j < len(row) and row[j] not in (None, ""):
                    dm_by_pat.setdefault(p, {}).setdefault(name, row[j])
            tnum = _tooth_num(row[site_i]) if site_i is not None and site_i < len(row) else ""
            if tnum:
                for name in OUTCOME_COLS:
                    j = ti.get(name)
                    if j is not None and j < len(row) and row[j] not in (None, ""):
                        out_by_pt.setdefault((p, tnum), {})[name] = row[j]
    else:
        HDR = list(DEFAULT_HEADERS)

    def col(name):
        for i, h in enumerate(HDR):
            if h and str(h).strip() == name.strip():
                return i
        return None

    # 코호트만 남김
    if cohort is not None:
        rows = [r for r in rows if str(r[1]) in cohort]

    # 순번: 원본 명단(연구시트)의 Serial No. 순서를 그대로 따른다.
    #   명단에 순번이 없으면 명단 등장 순서, 그것도 없으면 환자번호 순.
    _base = (max(pat_serial.values()) + 1) if pat_serial else 0
    def _pat_key(p):
        if p in pat_serial:
            return (0, pat_serial[p])
        if p in pat_order:
            return (1, pat_order[p])
        return (2, p)
    rows.sort(key=lambda r: (_pat_key(str(r[1])), int(r[17].lstrip("#") or 0), r[5] or ""))

    def L(name):
        i = col(name)
        return get_column_letter(i + 1) if i is not None else None

    wb = Workbook(); ws = wb.active
    ws.append(HDR + HELP_HEADERS)
    prev_pat = None
    cur_serial = None
    fallback = _base
    n_pat = 0
    n_isq = n_hb = 0
    data_row = 1  # 헤더가 1행
    row_serials = []
    for r in rows:
        pat = str(r[1]); tooth = r[17]; tnum = tooth.lstrip("#"); sdate = r[5]
        age, birth, sex = demo.get(pat, ("", "", ""))
        pre, post = join_hba1c(hb, pat, sdate)
        line = [None] * len(HDR)
        data_row += 1
        rr = data_row

        def put(name, val):
            i = col(name)
            if i is not None:
                line[i] = val

        # Serial No. — 원본 명단의 순번을 그대로, 같은 환자면 같은 번호
        if pat != prev_pat:
            prev_pat = pat
            n_pat += 1
            cur_serial = pat_serial.get(pat)
            if cur_serial is None:
                cur_serial = fallback
                fallback += 1
        put("Serial No.", cur_serial)
        put("환자번호", pat)
        put("성별", sex)
        put("생년월일", _as_date(birth))
        put("임플란트 식립 부위(상악/하악)", f"{tooth}i")
        put("임플란트 식립 시기", _as_date(sdate))
        put("임플란트 회사", r[6])
        put("임플란트 직경", r[7])
        put("임플란트길이", r[8])
        put("골이식 여부", r[9])
        if pre:
            put("당화혈색소(수술전)", pre[1] if pre[1] is not None else pre[2])
            put("당화혈색소 측정시기(수술전)", _as_date(pre[0])); n_hb += 1
        if post:
            put("당화혈색소(수술후)", post[1] if post[1] is not None else post[2])
            put("당화혈색소 측정시기(수술후)", _as_date(post[0]))
        put("ISQ 측정량(협)", r[14]); put("ISQ 측정량(설)", r[15])
        if r[14] != "":
            n_isq += 1
        # 기존 수기 당뇨/투약(환자단위) + 결과(치아단위) 보존
        for name, val in dm_by_pat.get(pat, {}).items():
            put(name, val)
        for name, val in out_by_pt.get((pat, tnum), {}).items():
            put(name, val)

        # ── 원본 시트의 수식 복구 (참조 셀은 위에서 날짜/숫자로 기록됨) ──
        Lb, Ldx, Lpl = L("생년월일"), L("DM증 진단 시기"), L("임플란트 식립 시기")
        Lage = L("DM증진단시 나이(세)")
        Lpre, Lpost = L("당화혈색소(수술전)"), L("당화혈색소(수술후)")
        Lbu, Lli = L("ISQ 측정량(협)"), L("ISQ 측정량(설)")
        if Lb:
            put("나이", f'=IFERROR(DATEDIF({Lb}{rr},TODAY(),"Y"),"")')
        if Lb and Ldx:
            put("DM증진단시 나이(세)", f'=IFERROR(ROUND(YEARFRAC({Lb}{rr},{Ldx}{rr}),1),"")')
        if Lage:
            put("투약시작 나이", f"={Lage}{rr}")
        if Ldx and Lpl:
            put("임플란트수술전 투약기간(년)", f'=IFERROR(ROUND(YEARFRAC({Ldx}{rr},{Lpl}{rr}),1),"")')
        if Lpre and Lpost:
            f = f'=IFERROR({Lpre}{rr}-{Lpost}{rr},"")'
            put("당화혈색소 (술전- 술후)", f); put("딩화혈색소 (술전- 술후)", f)
        if Lbu and Lli:
            put("ISQ 측정평균", f'=IFERROR(({Lbu}{rr}+{Lli}{rr})/2,"")')

        line += [tooth, r[18], r[19]]
        ws.append(line)
        row_serials.append(n_pat)   # 띠 색은 환자 등장 순서로 교대(순번 간격 무관)

    _style(ws, HDR, HELP_HEADERS, col, row_serials)
    wb.save(out)
    print(f"저장 → {out}")
    print(f"임플란트 {len(rows)}건 | 환자 {n_pat}명 | ISQ 채움 {n_isq} | HbA1c(술전) 채움 {n_hb}")
    print("※ 당뇨·투약·결과(골흡수/합병증/fail) 열은 다른 소스라 빈칸입니다.")


def main():
    ap = argparse.ArgumentParser(description="노트 추출 + HbA1c 조인 → 연구시트 결과 생성")
    ap.add_argument("--raw", required=True)
    ap.add_argument("--hba1c", default=None)
    ap.add_argument("--template", default=None)
    ap.add_argument("--out", default="추출결과.xlsx")
    a = ap.parse_args()
    for f in (a.raw, a.hba1c, a.template):
        if f and not Path(f).exists():
            print(f"[오류] 파일 없음: {f}"); return 1
    build(a.raw, a.hba1c, a.template, a.out)
    return 0


if __name__ == "__main__":
    main()
