"""엑셀/CSV 파일에서 환자번호 목록을 읽어오는 모듈."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 헤더로 간주하여 건너뛸 첫 행 값들
_HEADER_WORDS = {"환자번호", "등록번호", "patient_id", "patientid", "id", "번호", "patient no", "chart no"}


def read_patient_ids(excel_path: str | Path) -> list[str]:
    """엑셀/CSV 파일의 첫 번째 열에서 환자번호 목록을 읽어 반환.

    - 헤더 행 자동 감지(첫 행이 '환자번호' 등이면 건너뜀)
    - 숫자 셀의 소수점 자동 제거 (1234567.0 → "1234567")
    - 빈 셀 제거, 중복 제거, 순서 유지
    - 지원 형식: .xlsx, .xls, .csv, .txt
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    suffix = path.suffix.lower()
    if suffix in (".csv", ".txt"):
        rows = _read_csv_first_col(path)
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        rows = _read_excel_first_col(path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix} (xlsx/xls/csv/txt만 가능)")

    ids = _clean_and_dedup(rows)
    if not ids:
        raise ValueError(f"환자번호를 하나도 읽지 못했습니다: {path}\n"
                         "  엑셀 첫 번째 열(A열)에 환자번호가 있는지 확인하세요.")
    return ids


def _normalize_cell(value) -> str:
    """셀 값을 환자번호 문자열로 정규화. 빈 값이면 빈 문자열 반환."""
    if value is None:
        return ""
    # openpyxl이 숫자를 float/int로 돌려주는 경우 처리
    if isinstance(value, float):
        # 1234567.0 같은 정수형 float은 소수점 제거
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _read_excel_first_col(path: Path) -> list[str]:
    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl이 필요합니다. install.bat을 실행하세요.")

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        ws = wb.active
        out: list[str] = []
        for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
            out.append(_normalize_cell(row[0]))
    finally:
        wb.close()
    return out


def _read_csv_first_col(path: Path) -> list[str]:
    import csv

    out: list[str] = []
    # utf-8-sig: 엑셀이 저장한 CSV의 BOM 처리. 실패 시 cp949 재시도.
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, newline="", encoding=enc) as f:
                # 콤마/탭 자동 감지
                sample = f.read(2048)
                f.seek(0)
                delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
                reader = csv.reader(f, delimiter=delimiter)
                out = [row[0] if row else "" for row in reader]
            return out
        except UnicodeDecodeError:
            continue
    raise ValueError(f"파일 인코딩을 읽을 수 없습니다: {path}")


def _clean_and_dedup(rows: list[str]) -> list[str]:
    """헤더 제거 + 빈 값 제거 + 중복 제거(순서 유지)."""
    cleaned = [r.strip() for r in rows]

    # 첫 번째 비어있지 않은 값이 헤더 단어면 그 행만 제거
    for i, val in enumerate(cleaned):
        if not val:
            continue
        if val.lower() in _HEADER_WORDS:
            cleaned[i] = ""  # 헤더 제거
        break  # 첫 데이터/헤더 행만 검사

    seen: set[str] = set()
    result: list[str] = []
    for val in cleaned:
        if not val or val in seen:
            continue
        seen.add(val)
        result.append(val)
    return result
