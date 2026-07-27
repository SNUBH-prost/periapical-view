"""
추출 규칙 모음  ★★★ 여기가 제일 중요하고, 실제 차트에 맞게 고치는 곳입니다 ★★★

각 규칙은 함수 하나입니다:
    입력 = 차트 텍스트(문자열)
    출력 = 엑셀 칸에 넣을 값 (없으면 빈 문자열 "")

아래 패턴들은 "흔한 형태"를 가정한 예시입니다.
실제 차트 문장을 보고 정규식(re.search(...))만 바꿔주면 됩니다.
"""
from __future__ import annotations

import re


# ── 공통 도우미 ─────────────────────────────────────────────
def _search(pattern, text, group=1, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else ""


def _first_date(text):
    """YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD / YYYYMMDD 를 찾아 표준형으로."""
    m = re.search(r"(19|20)\d{2}[.\-/]?\s?\d{1,2}[.\-/]?\s?\d{1,2}", text)
    if not m:
        return ""
    nums = re.findall(r"\d+", m.group(0))
    if len(nums) >= 3:
        return f"{int(nums[0]):04d}-{int(nums[1]):02d}-{int(nums[2]):02d}"
    return m.group(0)


# ── 인적사항 ────────────────────────────────────────────────
def age(text):
    return _search(r"(\d{1,3})\s*세", text)


def birthdate(text):
    # "생년월일 1970-01-01" 또는 주민번호 앞자리 등. 실제 형식에 맞게 수정.
    m = re.search(r"생년월일[^\d]{0,5}((19|20)\d{2}[.\-/]?\d{1,2}[.\-/]?\d{1,2})", text)
    return _first_date(m.group(1)) if m else ""


def sex(text):
    if re.search(r"\b(남자|남|M|Male)\b", text, re.IGNORECASE):
        return "남"
    if re.search(r"\b(여자|여|F|Female)\b", text, re.IGNORECASE):
        return "여"
    return ""


# ── 임플란트 ────────────────────────────────────────────────
def implant_site(text):
    # 상악/하악 + 치식번호(#26 등)를 함께 잡아본다.
    tooth = _search(r"#\s?(\d{1,2})", text)
    arch = ""
    if re.search(r"상악|maxilla", text, re.IGNORECASE):
        arch = "상악"
    elif re.search(r"하악|mandible", text, re.IGNORECASE):
        arch = "하악"
    elif tooth:  # 치식번호로 상/하악 자동 판별 (FDI 기준)
        d = int(tooth[0])
        arch = "상악" if d in (1, 2) else "하악" if d in (3, 4) else ""
    return (arch + (f" #{tooth}" if tooth else "")).strip()


def implant_date(text):
    # "식립" 근처의 날짜를 우선. 없으면 첫 날짜.
    m = re.search(r"((19|20)\d{2}[.\-/]?\d{1,2}[.\-/]?\d{1,2})[^\n]{0,15}식립", text)
    if not m:
        m = re.search(r"식립[^\n]{0,15}((19|20)\d{2}[.\-/]?\d{1,2}[.\-/]?\d{1,2})", text)
    return _first_date(m.group(1)) if m else ""


# 임플란트 회사 사전 (왼쪽 표기가 보이면 오른쪽 대표이름으로 통일)
_COMPANIES = {
    r"osstem|오스템|TSIII|TS\s?III": "오스템(Osstem)",
    r"straumann|스트라우만|SLA|BLT|BLX": "스트라우만(Straumann)",
    r"dentium|덴티움|superline|implantium": "덴티움(Dentium)",
    r"megagen|메가젠|anyone|anyridge": "메가젠(Megagen)",
    r"nobel|노벨|replace|active": "노벨바이오케어(Nobel)",
    r"dio|디오": "디오(Dio)",
    r"neobiotech|네오|neo\b": "네오바이오텍(Neo)",
    r"astra|아스트라|osseospeed": "아스트라(Astra)",
}


def implant_company(text):
    for pat, name in _COMPANIES.items():
        if re.search(pat, text, re.IGNORECASE):
            return name
    return ""


def implant_diameter(text):
    # "Ø4.0", "D4.0", "4.0 x 10", "4.0*10", "직경 4.0"
    m = re.search(r"(?:Ø|직경|D)\s?(\d\.\d)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d\.\d)\s?[x*×]\s?\d{1,2}", text)  # 4.0 x 10 의 앞 숫자
    return m.group(1) if m else ""


def implant_length(text):
    # "10mm", "L10", "4.0 x 10", "길이 10"
    m = re.search(r"(?:길이|L)\s?(\d{1,2}(?:\.\d)?)\s?mm?", text, re.IGNORECASE)
    if not m:
        m = re.search(r"\d\.\d\s?[x*×]\s?(\d{1,2}(?:\.\d)?)", text)  # 4.0 x 10 의 뒤 숫자
    return m.group(1) if m else ""


def bone_graft(text):
    if re.search(r"골이식|bone\s?graft|GBR|sinus|상악동|이식재|xenograft", text, re.IGNORECASE):
        return "Y"
    return "N"


# ── 당화혈색소 (HbA1c) ──────────────────────────────────────
def _hba1c_values(text):
    """텍스트에서 (날짜, 값) 쌍을 나온 순서대로 모두 뽑는다."""
    pairs = []
    for m in re.finditer(
        r"(?:HbA1c|당화혈색소|A1c)[^\d]{0,20}(\d{1,2}\.\d)\s?%?", text, re.IGNORECASE
    ):
        # 값 바로 뒤(30자)에서 날짜를 먼저 찾고, 없으면 값 앞(40자)에서 찾는다.
        fwd = text[m.end():m.end() + 30]
        back = text[max(0, m.start() - 40):m.start()]
        pairs.append((_first_date(fwd) or _first_date(back), m.group(1)))
    return pairs


def hba1c_pre(text):
    v = _hba1c_values(text)
    return v[0][1] if len(v) >= 1 else ""


def hba1c_pre_date(text):
    v = _hba1c_values(text)
    return v[0][0] if len(v) >= 1 else ""


def hba1c_post(text):
    v = _hba1c_values(text)
    return v[1][1] if len(v) >= 2 else ""


def hba1c_post_date(text):
    v = _hba1c_values(text)
    return v[1][0] if len(v) >= 2 else ""


def hba1c_delta(text):
    v = _hba1c_values(text)
    if len(v) >= 2:
        try:
            return round(float(v[0][1]) - float(v[1][1]), 1)
        except ValueError:
            return ""
    return ""


# ── ISQ (임플란트 안정성 지수) ──────────────────────────────
def _isq_after(label_pat, text):
    m = re.search(label_pat + r"[^\d]{0,10}(\d{2,3})", text, re.IGNORECASE)
    return m.group(1) if m else ""


def isq_buccal(text):
    return _isq_after(r"(?:협|buccal|B)\s*ISQ|ISQ[^\d]{0,6}(?:협|buccal)", text) \
        or _isq_after(r"협", text)


def isq_lingual(text):
    return _isq_after(r"(?:설|lingual|L)\s*ISQ|ISQ[^\d]{0,6}(?:설|lingual)", text) \
        or _isq_after(r"설", text)


def isq_mean(text):
    b, l = isq_buccal(text), isq_lingual(text)
    if b and l:
        return round((int(b) + int(l)) / 2, 1)
    m = re.search(r"ISQ[^\d]{0,10}(?:평균|mean|avg)[^\d]{0,6}(\d{2,3})", text, re.IGNORECASE)
    return m.group(1) if m else ""


# ── 규칙 등록표 (config.yaml 의 rule 이름과 연결) ────────────
RULES = {
    "age": age,
    "birthdate": birthdate,
    "sex": sex,
    "implant_site": implant_site,
    "implant_date": implant_date,
    "implant_company": implant_company,
    "implant_diameter": implant_diameter,
    "implant_length": implant_length,
    "bone_graft": bone_graft,
    "hba1c_pre": hba1c_pre,
    "hba1c_pre_date": hba1c_pre_date,
    "hba1c_post": hba1c_post,
    "hba1c_post_date": hba1c_post_date,
    "hba1c_delta": hba1c_delta,
    "isq_buccal": isq_buccal,
    "isq_lingual": isq_lingual,
    "isq_mean": isq_mean,
}
