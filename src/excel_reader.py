"""엑셀 파일에서 환자 번호 목록을 읽어오는 모듈."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_patient_ids(excel_path: str | Path) -> list[str]:
    """엑셀 파일에서 환자번호 목록을 읽어 반환.

    - 첫 번째 열에서 환자번호를 읽음 (헤더 자동 감지)
    - 빈 셀, 중복 제거
    - .xlsx / .xls / .csv 모두 지원
    """
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"파일 없음: {path}")

    suffix = path.suffix.lower()

    if suffix == ".csv":
        return _read_csv(path)
    else:
        return _read_excel(path)


def _read_excel(path: Path) -> list[str]:
    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl 설치 필요: pip install openpyxl")

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    ws = wb.active

    ids: list[str] = []
    for row in ws.iter_rows(values_only=True):
        for cell in row:
            if cell is None:
                continue
            val = str(cell).strip()
            if not val:
                continue
            # 헤더 행 건너뛰기: 숫자가 아닌 첫 행은 헤더일 가능성
            if val.lower() in ("환자번호", "patient_id", "patientid", "id", "번호"):
                continue
            ids.append(val)
        break  # 첫 열만 읽기 위해 각 행의 첫 셀만 사용

    # 실제로는 모든 행의 첫 번째 열을 읽어야 함
    ids = []
    first_row = True
    for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
        cell = row[0]
        if cell is None:
            continue
        val = str(cell).strip()
        if not val:
            continue
        if first_row and val.lower() in ("환자번호", "patient_id", "patientid", "id", "번호"):
            first_row = False
            continue
        first_row = False
        ids.append(val)

    wb.close()
    return _deduplicate(ids)


def _read_csv(path: Path) -> list[str]:
    import csv

    ids = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row:
                continue
            val = row[0].strip()
            if not val:
                continue
            if i == 0 and val.lower() in ("환자번호", "patient_id", "patientid", "id", "번호"):
                continue
            ids.append(val)

    return _deduplicate(ids)


def _deduplicate(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result
