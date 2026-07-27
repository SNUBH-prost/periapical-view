"""
차트 노트 파싱 핵심 로직 (v3 — 실제 SNUBH 노트의 다양한 형식 대응).

임플란트 1차 수술 노트에서 치아별로 직경·길이·회사·골이식을, 모든 노트에서 ISQ를 뽑는다.
표기 형식이 매우 다양해서 여러 패턴을 순서대로 시도한다.
"""
from __future__ import annotations

import re
import statistics

# ── 회사/제품 사전 (키워드 → 출력명). 실제 회사명으로 자유롭게 수정/추가 ──
BRANDS = {
    "superline": "Dentium Superline",
    "luna": "Dentium Luna",
    "implantium": "Dentium Implantium",
    "tsiii": "Osstem TS", "ts iii": "Osstem TS", "ts3": "Osstem TS", "ts": "Osstem TS",
    "us ": "Osstem US",
    "anyridge": "Megagen AnyRidge",
    "anyone": "Osstem AnyOne",
    "cmi": "CMI IS",
    "evertis": "Evertis",
    "blt": "Straumann BLT", "blx": "Straumann BLX", "sla": "Straumann SLA",
}
# '상표:' 뒤 토큰을 회사로 잡을 때, 회사가 아닌 단어(오탐 방지)
_NOT_BRAND = {"the", "bone", "graft", "with", "and"}

# 골이식 재료 후보 (본문에 보이면 재료로 인정)
GRAFT_PRODUCTS = [
    "자가골", "이종골", "동종골", "합성골", "탈회골", "자가치아골",
    "AutoBT", "Allomix", "Bio-Oss", "Bio-Gide", "OCS-B", "The graft", "The Graft",
    "Osteon", "Regenoss", "Ossix", "Cytoplast", "ICB", "lego graft", "legograft",
    "oss guide", "ossguide", "collagen", "티타늄메쉬", "Ti-mesh", "Xeno", "Zionics",
]

_NOTE_DATE = re.compile(r"\(\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s*\)")
_TOOTH = re.compile(r"#\s*0*(\d{1,2})")

# 규격에서 잘라낼 뒷부분(여기부터는 임플란트 규격이 아님: healing/cover 크기, ISQ 등)
_SEG_CUT = re.compile(r"ISQ|healing|cover|hand|연결|drilling|abutment|/", re.I)


def note_date(text: str) -> str:
    m = _NOTE_DATE.search(text)
    if not m:
        return ""
    y, mo, d = (int(x) for x in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def arch_from_tooth(tooth: int) -> str:
    d = tooth // 10
    return "상악" if d in (1, 2) else "하악" if d in (3, 4) else ""


def _extract_dims(seg: str):
    """규격 문자열에서 (직경, 길이). 여러 형식 순서대로 시도. 못 찾으면 ('','')."""
    seg = seg.replace("×", "x").replace("X", "x")
    # 1) 5.0D/10L
    m = re.search(r"(\d(?:\.\d)?)\s*D\s*/\s*(\d{1,2}(?:\.\d)?)\s*L", seg, re.I)
    if m:
        return m.group(1), m.group(2)
    # 2) A [mm] (x|*) B mm   예: 4.0mm X 8mm / 4.5*8.5mm / 4mm X  8.5mm
    m = re.search(r"(\d(?:\.\d)?)\s*(?:mm)?\s*[x*]\s*(\d{1,2}(?:\.\d)?)\s*mm", seg, re.I)
    if m:
        return m.group(1), m.group(2)
    # 3) A : B mm   예: 4.5 : 10 mm (X mm 비어있는 형식)
    m = re.search(r"(\d(?:\.\d)?)\s*:\s*(\d{1,2}(?:\.\d)?)\s*mm", seg)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def _brand_in(seg: str) -> str:
    low = seg.lower()
    # '상표:' 뒤 토큰 우선
    m = re.search(r"상표[^:]*:\s*([A-Za-z][A-Za-z0-9]+)", seg)
    if m and m.group(1).lower() not in _NOT_BRAND:
        tok = m.group(1)
        return BRANDS.get(tok.lower(), tok)
    for key, name in BRANDS.items():
        if key.strip() and key in low:
            return name
    return ""


def parse_specs(text: str):
    """
    노트에서 상세규격(직경·길이)이 있는 임플란트 목록.
    반환: {치아번호: {diameter, length, brand}}
    치아번호 위치마다 뒤쪽 창(window)을 잘라 규격을 추출한다. 다치아 공유 규격도 처리.
    """
    text = text.replace("_x000D_", "")
    out = {}
    # 그룹형 다치아: "#45 47 ... (상표: ... 4mm X 8.5mm)" → 45,47 에 같은 규격
    for m in _TOOTH.finditer(text):
        tooth = int(m.group(1))
        start = m.end()
        window = text[start:start + 90]
        cut = _SEG_CUT.search(window)
        seg = window[:cut.start()] if cut else window
        # 규격을 못 찾으면 창을 조금 더 넓혀 (뒤에 붙는 경우)
        dia, length = _extract_dims(seg)
        if not dia:
            dia, length = _extract_dims(window)
        if dia and length:
            brand_seg = text[max(0, m.start() - 40):start + 60]
            out.setdefault(tooth, {"diameter": dia, "length": length,
                                   "brand": _brand_in(brand_seg)})
    return out


def find_brand(text: str) -> str:
    return _brand_in(text.replace("_x000D_", ""))


def graft_material(text: str) -> str:
    """수술 노트에서 사용된 골이식 재료. 못 찾으면 ''(=이식 안 함으로 간주)."""
    text = text.replace("_x000D_", "")
    parts = []
    # "bone 상표명: XXX / membrane 상표명: YYY"
    for label in ("bone", "membrane"):
        m = re.search(label + r"[^:]{0,6}:\s*([^/)\n]+)", text, re.I)
        if m:
            v = m.group(1).strip(" .")
            if v and not v.lower().startswith("membrane"):
                parts.append(f"{label}: {v[:30]}")
    low = text.lower()
    for kw in GRAFT_PRODUCTS:
        if kw.lower() in low and not any(kw.lower() in p.lower() for p in parts):
            parts.append(kw)
    # 중복/정형문구 정리
    return " / ".join(dict.fromkeys(parts))


def has_gbr(text: str) -> bool:
    """실제 골이식 재료가 확인될 때만 True (정형문구 'Implant with GBR'만으론 False)."""
    return bool(graft_material(text))


# ── ISQ ─────────────────────────────────────────────────────
_BARE_VALS = re.compile(r"ISQ\s*:?\s*([0-9]{2,3}\s*/\s*[0-9]{2,3}(?:\s*/\s*[0-9]{2,3})*)", re.I)
_TOOTH_VALS = re.compile(r"#\s*0*(\d{1,2})\s*i?\s*:\s*([0-9]{1,3}(?:\s*/\s*[0-9]{1,3}){1,3})")
_SECTION_BREAK = re.compile(
    r"thickness|gingival|tissue|두께|shade|mob|fixture level|bite|per\s*\(|동의|발거|처방",
    re.I,
)


def _clean_vals(raw: str):
    vals = [int(x) for x in re.findall(r"\d{1,3}", raw)]
    if not (2 <= len(vals) <= 4):
        return None
    if any(v < 30 or v > 99 for v in vals):   # 조직두께(4/4/5/4) 등 제외
        return None
    return vals


def find_isq(text: str):
    """
    ISQ 측정값 추출. 반환: [(치아번호 or None, [값들]), ...]
    - 한 줄에 치아+값이 같이 있으면 그 치아에 귀속
    - 'ISQ:'만 있고 치아 없으면 (None, vals) → 같은 노트 임플란트에 귀속(main에서)
    - 'ISQ' 라벨 아래 블록의 '#NNi: vals'도 수집 (조직두께 혼동 방지: 30~99 범위)
    """
    text = text.replace("_x000D_", "")
    results = []
    in_isq = False
    for line in text.splitlines():
        s = line.strip()
        toothvals = list(_TOOTH_VALS.finditer(s))
        has_isq = re.search(r"\bISQ\b", s, re.I)

        if toothvals and (has_isq or in_isq):
            # 같은 줄 치아별 값
            for tm in toothvals:
                v = _clean_vals(tm.group(2))
                if v:
                    results.append((int(tm.group(1)), v))
            if has_isq:
                in_isq = True
            continue

        if has_isq:
            in_isq = True
            # 같은 줄에 치아 있고 ISQ 값(bare)도 있으면 그 치아에 귀속
            line_tooth = _TOOTH.search(s)
            bm = _BARE_VALS.search(s)
            if bm:
                v = _clean_vals(bm.group(1))
                if v:
                    results.append((int(line_tooth.group(1)) if line_tooth else None, v))
            continue

        if not s or _SECTION_BREAK.search(s):
            in_isq = False
            continue

        if in_isq:
            matched = False
            for tm in toothvals:
                v = _clean_vals(tm.group(2))
                if v:
                    results.append((int(tm.group(1)), v))
                    matched = True
            if not matched:
                in_isq = False
    return results


def isq_fields(vals):
    """[협,설,...] → (협, 설, 평균). 앞=협, 뒤=설. 평균은 잡힌 값 전체 평균."""
    buccal = vals[0] if len(vals) >= 1 else ""
    lingual = vals[1] if len(vals) >= 2 else ""
    mean = round(statistics.mean(vals), 1) if vals else ""
    return buccal, lingual, mean
