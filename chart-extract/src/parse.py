"""
차트 노트 파싱 핵심 로직.

한 환자의 외래경과 노트 여러 개를 읽어서:
  - 식립기록(Implant installation)에서: 치아번호 / 규격(직경·길이) / 골이식 / 날짜
  - 모든 노트에서: 회사(제품명), ISQ 측정값
을 뽑아 치아번호로 묶는다.

★ 실제 차트 표기가 예시와 다르면 아래 정규식/사전만 고치면 됩니다.
"""
from __future__ import annotations

import re
import statistics

# ── 회사/제품 사전 ──────────────────────────────────────────
#   왼쪽 키워드가 보이면 오른쪽 이름으로 출력. 실제 회사명으로 자유롭게 바꾸세요.
BRANDS = {
    "superline": "Superline",
    "luna": "Luna",
    "implantium": "Implantium",
    "anyridge": "AnyRidge",
    "anyone": "AnyOne",
    "tsiii": "TSIII",
    "ts iii": "TSIII",
    "blt": "Straumann BLT",
    "blx": "Straumann BLX",
    "sla": "Straumann SLA",
}

# 골이식으로 인정할 표현. (주의: "graft 확인" 같은 정형문구는 제외)
_GBR_POS = re.compile(r"with\s*GBR|GBR\s*with|골\s*이식|자가골|bone\s*graft\s*함|이식재", re.I)

# 식립 스펙:  #15i superline : 4.0 mm X 10mm  /  #35i: 4.0mm X 8.5mm  /  #24 superline : 3.6 mm X 10 mm
_SPEC = re.compile(
    r"#\s*(\d{1,2})\s*i?\b[^\n)]*?(\d(?:\.\d)?)\s*mm\s*[xX×*]\s*(\d{1,2}(?:\.\d)?)\s*mm",
    re.I,
)
# 괄호 안 직경만 있는 경우:  #24i(3.6)  /  #15i(4.0)
_DIA_ONLY = re.compile(r"#\s*(\d{1,2})\s*i?\s*\(\s*(\d\.\d)\s*\)")

_NOTE_DATE = re.compile(r"\(\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s*\)")

# 한 줄에서 치아별 값:  #24i:80/77   #34i: 89/90/89/90
_TOOTH_VALS = re.compile(r"#\s*(\d{1,2})\s*i?\s*:\s*([0-9]{1,3}(?:\s*/\s*[0-9]{1,3}){1,3})")
# 치아번호 없는 ISQ:  ISQ: 80/80
_BARE_VALS = re.compile(r"ISQ\s*:?\s*([0-9]{2,3}\s*/\s*[0-9]{2,3})", re.I)

# ISQ 블록을 끊는 다른 섹션 머리말 (이게 나오면 ISQ 구간 종료)
_SECTION_BREAK = re.compile(
    r"thickness|gingival|tissue|두께|shade|mob|fixture|bite|per\s*\(|동의|발거|installation|Tx\s*>|처방",
    re.I,
)


def note_date(text: str) -> str:
    """노트 헤더의 ( YYYY-MM-DD ) 를 표준형 문자열로. 없으면 ''."""
    m = _NOTE_DATE.search(text)
    if not m:
        return ""
    y, mo, d = (int(x) for x in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def arch_from_tooth(tooth: int) -> str:
    """FDI 치식 앞자리로 상악/하악 판별."""
    d = tooth // 10
    if d in (1, 2):
        return "상악"
    if d in (3, 4):
        return "하악"
    return ""


def find_brand(text: str) -> str:
    low = text.lower()
    for key, name in BRANDS.items():
        if key in low:
            return name
    return ""


def is_installation_note(text: str) -> bool:
    return bool(re.search(r"Implant\s*installation|임플란트\s*(installation|식립|installation)", text, re.I))


def has_gbr(text: str) -> bool:
    return bool(_GBR_POS.search(text))


def parse_specs(text: str):
    """식립 노트에서 (치아번호, 직경, 길이) 목록. 규격이 안 잡히면 직경만이라도."""
    out = {}
    for m in _SPEC.finditer(text):
        tooth = int(m.group(1))
        out[tooth] = {"diameter": m.group(2), "length": m.group(3)}
    for m in _DIA_ONLY.finditer(text):
        tooth = int(m.group(1))
        out.setdefault(tooth, {"diameter": m.group(2), "length": ""})
    return out


def _clean_vals(raw: str):
    """'80/77' → [80,77]. ISQ 범위(30~99)를 벗어나면 (조직두께 등) 버린다."""
    vals = [int(x) for x in re.findall(r"\d{1,3}", raw)]
    if not (2 <= len(vals) <= 4):
        return None
    if any(v < 30 or v > 99 for v in vals):   # 조직두께(4/4/5/4) 같은 값 걸러냄
        return None
    return vals


def find_isq(text: str):
    """
    노트에서 ISQ 측정값을 뽑는다.
    반환: [(치아번호 or None, [값들]), ...]
    'ISQ' 라벨 아래 구간에서만 읽어 조직두께와 혼동하지 않는다.
    """
    results = []
    in_isq = False
    for line in text.splitlines():
        stripped = line.strip()
        has_isq_word = re.search(r"\bISQ\b", stripped, re.I)

        if has_isq_word:
            in_isq = True
            # 같은 줄에 치아번호 없는 값(ISQ: 80/80)이 있으면 잡는다
            bm = _BARE_VALS.search(stripped)
            if bm:
                v = _clean_vals(bm.group(1))
                if v:
                    results.append((None, v))
            # 같은 줄에 치아별 값이 있으면 잡는다 (ISQ #24i:80/77)
            for tm in _TOOTH_VALS.finditer(stripped):
                v = _clean_vals(tm.group(2))
                if v:
                    results.append((int(tm.group(1)), v))
            continue

        if not stripped:                       # 빈 줄 → ISQ 구간 종료
            in_isq = False
            continue
        if _SECTION_BREAK.search(stripped):     # 다른 섹션 시작 → 종료
            in_isq = False
            continue

        if in_isq:
            matched = False
            for tm in _TOOTH_VALS.finditer(stripped):
                v = _clean_vals(tm.group(2))
                if v:
                    results.append((int(tm.group(1)), v))
                    matched = True
            if not matched:                     # ISQ 구간인데 값 형식이 아니면 종료
                in_isq = False
    return results


def isq_fields(vals):
    """[협,설,...] → (협, 설, 평균).  앞=협, 뒤=설. 평균은 잡힌 값 전체 평균."""
    buccal = vals[0] if len(vals) >= 1 else ""
    lingual = vals[1] if len(vals) >= 2 else ""
    mean = round(statistics.mean(vals), 1) if vals else ""
    return buccal, lingual, mean
