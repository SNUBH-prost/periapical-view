"""Infinitt PACS 반자동 수집 (F9 모드).

사용법:
  1. 사람이 직접 환자 검색 → DS periapical view (implant) 스터디를 연다.
  2. 마우스를 왼쪽 썸네일 패널 위에 올린다.
  3. F9 를 누른다 →
       - 화면에서 환자번호·촬영날짜 자동 인식
       - 커서 위치 우클릭 → Convert Study 클릭
       - 저장 대화상자에 C:\\infinitt_export\\{환자번호}\\{환자번호}(YYYY-MM-DD)\\ 경로 입력 후 저장
  4. 다음 스터디로 넘어가서 다시 F9. 반복.

환자번호·날짜를 화면에서 못 읽으면 임시 이름으로 저장하고 로그에 남긴다.
"""
import datetime
import logging
import re
import time
from pathlib import Path

import pyautogui
import win32con
import win32gui
from pynput import keyboard

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True   # 마우스를 화면 왼쪽 위 모서리로 빠르게 옮기면 긴급 정지
pyautogui.PAUSE = 0.05


# ──────────────────────────────────────────────────────────────
# 화면에서 환자번호 · 촬영날짜 읽기
# ──────────────────────────────────────────────────────────────

def _parse_date_to_yyyymmdd(text: str) -> str:
    patterns = [
        (r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', "YMD"),
        (r'(\d{4})(\d{2})(\d{2})',                 "YMD"),
        (r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',  "DMY"),
    ]
    for pat, order in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        g = m.groups()
        if order == "YMD":
            y, mo, d = g[0], g[1].zfill(2), g[2].zfill(2)
        else:
            y, mo, d = g[2], g[0].zfill(2), g[1].zfill(2)
        # 상식적인 날짜 범위만 인정
        if "1990" <= y <= "2100" and "01" <= mo <= "12" and "01" <= d <= "31":
            return f"{y}{mo}{d}"
    return ""


def _yyyymmdd_to_dash(yyyymmdd: str) -> str:
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
    return yyyymmdd


def _collect_window_texts(title_contains: str) -> list[str]:
    """Infinitt 창의 모든 컨트롤 텍스트를 모아서 반환."""
    texts: list[str] = []
    try:
        from pywinauto import Desktop
        for win in Desktop(backend="uia").windows():
            if title_contains.lower() not in win.window_text().lower():
                continue
            texts.append(win.window_text())
            for ctrl in win.descendants():
                try:
                    t = ctrl.window_text()
                    if t and t.strip():
                        texts.append(t.strip())
                except Exception:
                    continue
            break
    except Exception as e:
        logger.debug(f"창 텍스트 수집 실패: {e}")
    return texts


def _detect_patient_id(texts: list[str], id_min: int, id_max: int) -> str:
    """
    텍스트들 중 환자번호로 보이는 숫자를 찾는다.
    - 'ID', '환자', '등록번호' 같은 라벨 근처 숫자를 우선.
    - 없으면 자릿수 범위(id_min~id_max)에 맞는 숫자 중 첫 번째.
    """
    label_keywords = ("id", "환자", "등록", "chart", "mrn", "patient")

    # 1순위: 라벨이 들어간 텍스트 안의 숫자
    for t in texts:
        low = t.lower()
        if any(k in low for k in label_keywords):
            for num in re.findall(r'\d{%d,%d}' % (id_min, id_max), t):
                return num

    # 2순위: 자릿수 범위에 맞는 첫 숫자 (날짜(8자리)와 겹치지 않게 date 제외)
    for t in texts:
        for num in re.findall(r'\b\d{%d,%d}\b' % (id_min, id_max), t):
            # YYYYMMDD 형태(날짜)는 제외
            if len(num) == 8 and _parse_date_to_yyyymmdd(num):
                continue
            return num
    return ""


def _detect_study_date(texts: list[str]) -> str:
    """텍스트들 중 촬영날짜(YYYYMMDD)를 찾는다. 가장 최근 날짜 우선."""
    found = []
    for t in texts:
        d = _parse_date_to_yyyymmdd(t)
        if d:
            found.append(d)
    if not found:
        return ""
    # 여러 개면 가장 큰(최근) 날짜 — 보통 촬영일이 검사일과 같음
    return max(found)


def _resolve_save_dir(base_dir: Path, title_contains: str, ui_cfg: dict) -> tuple[Path, str]:
    """
    화면에서 환자번호·날짜를 읽어 저장 폴더 경로를 만든다.
    실패하면 임시 폴더명을 쓰고 그 사유를 반환.
    반환: (save_dir, label)  label 은 로그용 설명
    """
    id_min = ui_cfg.get("patient_id_min_digits", 6)
    id_max = ui_cfg.get("patient_id_max_digits", 10)

    texts = _collect_window_texts(title_contains)
    pid  = _detect_patient_id(texts, id_min, id_max)
    date = _detect_study_date(texts)

    if pid and date:
        date_dash = _yyyymmdd_to_dash(date)
        return base_dir / pid / f"{pid}({date_dash})", f"{pid}({date_dash})"

    # 부분 실패 → 있는 정보만이라도 사용, 나머지는 UNKNOWN + 순번
    stamp = datetime.datetime.now().strftime("%H%M%S")
    pid_part  = pid if pid else "UNKNOWN_ID"
    date_part = _yyyymmdd_to_dash(date) if date else f"UNKNOWN_DATE_{stamp}"
    label = f"{pid_part}({date_part})  [자동인식 일부 실패 — 폴더명 확인 필요]"
    return base_dir / pid_part / f"{pid_part}({date_part})", label


# ──────────────────────────────────────────────────────────────
# Convert Study 메뉴 & 저장 대화상자
# ──────────────────────────────────────────────────────────────

def _click_menu_item(menu_items: list[str], delay: float) -> bool:
    """우클릭 후 뜬 컨텍스트 메뉴에서 Convert Study 항목을 클릭."""
    time.sleep(delay)
    try:
        from pywinauto import Desktop
        for win in Desktop(backend="uia").windows():
            for ctrl in win.descendants():
                try:
                    text = ctrl.window_text()
                    for item in menu_items:
                        if item.lower() in text.lower():
                            ctrl.click_input()
                            logger.info(f"메뉴 클릭: '{text}'")
                            return True
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"pywinauto 메뉴 탐색 실패: {e}")

    pyautogui.press("escape")
    logger.warning(
        "Convert Study 메뉴를 찾지 못했습니다.\n"
        "  config.yaml → ui.convert_study_menu 에\n"
        "  Infinitt 우클릭 메뉴에 실제로 보이는 텍스트를 추가하세요."
    )
    return False


def _handle_save_dialog(save_dir: Path, ui_cfg: dict, delay: float) -> bool:
    """저장/변환 대화상자가 뜨면 경로를 입력하고 저장."""
    save_dir.mkdir(parents=True, exist_ok=True)
    path_str = str(save_dir)
    time.sleep(delay * 2)
    try:
        from pywinauto import Desktop
        for win in Desktop(backend="uia").windows():
            title = win.window_text()
            if any(k in title for k in ("저장", "Save", "다른 이름", "Export", "내보내기", "Convert", "변환")):
                logger.debug(f"저장 대화상자: '{title}'")
                try:
                    edit = win.child_window(control_type="Edit")
                    edit.set_focus()
                    edit.set_text(path_str)
                except Exception:
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.press("delete")
                    pyautogui.typewrite(path_str, interval=0.03)
                time.sleep(delay)
                try:
                    btn_text = ui_cfg.get("save_dialog_button", "저장")
                    win.child_window(title=btn_text, control_type="Button").click_input()
                except Exception:
                    pyautogui.press("enter")
                time.sleep(delay)
                pyautogui.press("enter")   # 덮어쓰기 확인 등
                logger.info(f"저장 → {save_dir}")
                return True
    except Exception as e:
        logger.debug(f"저장 대화상자 처리 실패: {e}")

    return True


# ──────────────────────────────────────────────────────────────
# 핵심: F9 → Convert Study + 저장
# ──────────────────────────────────────────────────────────────

def convert_at_cursor(cfg: dict, base_dir: Path) -> bool:
    """현재 커서(왼쪽 패널) 위치에서 우클릭 → Convert Study → 자동 폴더에 저장."""
    ui_cfg     = cfg.get("ui", {})
    delay      = ui_cfg.get("action_delay", 0.5)
    title      = ui_cfg.get("window_title_contains", "Infinitt")
    menu_items = ui_cfg.get("convert_study_menu", ["Convert Study", "Convert", "스터디 변환", "변환"])

    # 1) 화면에서 환자번호·날짜 읽어 저장 경로 결정
    save_dir, label = _resolve_save_dir(base_dir, title, ui_cfg)
    logger.info(f"저장 대상: {label}")

    # 2) 커서 위치에서 우클릭 → Convert Study
    x, y = pyautogui.position()
    pyautogui.rightClick(x, y)
    if not _click_menu_item(menu_items, delay):
        return False

    # 3) 저장 대화상자 처리
    return _handle_save_dialog(save_dir, ui_cfg, delay)


# ──────────────────────────────────────────────────────────────
# 전역 단축키 (F9)
# ──────────────────────────────────────────────────────────────

class HotkeyCapture:
    def __init__(self, cfg: dict, base_dir: Path):
        self.cfg = cfg
        self.base_dir = base_dir
        self.hotkey = cfg.get("ui", {}).get("hotkey", "f9").lower()
        self._listener = None
        self._busy = False
        self.count = 0

    def _on_press(self, key):
        try:
            name = key.name if hasattr(key, "name") else str(key).replace("'", "")
            if name.lower() == self.hotkey:
                self._trigger()
        except Exception:
            pass

    def _trigger(self):
        if self._busy:
            return   # 처리 중 중복 F9 무시
        self._busy = True
        try:
            logger.info(f"[{self.hotkey.upper()}] Convert Study 트리거")
            ok = convert_at_cursor(self.cfg, self.base_dir)
            if ok:
                self.count += 1
                logger.info(f"완료 (누적 {self.count}건)")
            else:
                logger.warning("이번 저장 실패 — 위 메시지 확인")
        finally:
            self._busy = False

    def start(self):
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()


# ──────────────────────────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────────────────────────

def run_ui_mode(cfg: dict, dirs: dict) -> None:
    ui_cfg = cfg.get("ui", {})
    base_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    base_dir.mkdir(parents=True, exist_ok=True)

    hotkey_name = ui_cfg.get("hotkey", "f9").upper()

    logger.info("=" * 60)
    logger.info("Infinitt 반자동 수집 모드 (F9)")
    logger.info(f"  저장 폴더: {base_dir}")
    logger.info(f"  단축키  : {hotkey_name}")
    logger.info("")
    logger.info("  [사용법]")
    logger.info("   1. 환자 검색 -> DS periapical view (implant) 스터디를 연다")
    logger.info("   2. 마우스를 왼쪽 썸네일 패널 위에 올린다")
    logger.info(f"   3. {hotkey_name} 를 누른다 -> 자동으로 Convert Study + 저장")
    logger.info("   4. 다음 스터디에서 다시 반복")
    logger.info("")
    logger.info("  종료  : Ctrl+C")
    logger.info("  긴급정지: 마우스를 화면 왼쪽 위 모서리로 빠르게 이동")
    logger.info("=" * 60)

    hotkey = HotkeyCapture(cfg, base_dir)
    hotkey.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("사용자 종료 요청")
    finally:
        hotkey.stop()
        logger.info(f"완료 — 총 {hotkey.count}건 저장 -> {base_dir}")
