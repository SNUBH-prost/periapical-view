"""Infinitt PACS 클라이언트 UI 자동화 모듈.

Infinitt 창에서 이미지를 우클릭 → 저장 메뉴를 자동으로 클릭합니다.
사람이 Infinitt를 직접 조작하는 것을 그대로 자동화합니다.

두 가지 방식:
  1. 단축키(F9) 트리거: 사용자가 보고 있는 이미지를 저장
  2. 자동 감지: 새 이미지가 로드되면 자동으로 우클릭 저장
"""
import logging
import os
import time
from pathlib import Path

import pyautogui
import win32con
import win32gui
import win32process
from pynput import keyboard

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True   # 마우스를 화면 왼쪽 위로 빠르게 옮기면 긴급 정지
pyautogui.PAUSE = 0.1


# ──────────────────────────────────────────────────────────────
# Infinitt 창 찾기
# ──────────────────────────────────────────────────────────────

def find_infinitt_window(title_contains: str = "Infinitt") -> int | None:
    """Infinitt 클라이언트 창의 핸들(hwnd)을 반환."""
    result = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_contains.lower() in title.lower():
                result.append(hwnd)

    win32gui.EnumWindows(enum_cb, None)
    if result:
        logger.debug(f"Infinitt 창 발견: {[win32gui.GetWindowText(h) for h in result]}")
        return result[0]
    return None


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """창의 화면 좌표(left, top, right, bottom) 반환."""
    return win32gui.GetWindowRect(hwnd)


def bring_to_front(hwnd: int) -> None:
    """창을 앞으로 가져오기."""
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    except Exception as e:
        logger.debug(f"창 활성화 실패: {e}")


# ──────────────────────────────────────────────────────────────
# 이미지 영역 탐지
# ──────────────────────────────────────────────────────────────

def find_xray_region(hwnd: int) -> tuple[int, int, int, int] | None:
    """Infinitt 창 내에서 X-ray 이미지 표시 영역을 탐지.

    X-ray 영상은 보통 검은 배경에 흰색/회색 영상으로 표시됩니다.
    창의 중앙 영역에서 가장 어두운 큰 사각형 영역을 찾습니다.
    """
    import mss
    import numpy as np
    from PIL import Image

    left, top, right, bottom = get_window_rect(hwnd)
    w, h = right - left, bottom - top

    if w < 100 or h < 100:
        return None

    with mss.mss() as sct:
        monitor = {"left": left, "top": top, "width": w, "height": h}
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    # 회색조 변환
    gray = np.array(img.convert("L"), dtype=np.float32)

    # 상단 메뉴/툴바 영역 제외 (보통 위쪽 15%, 아래쪽 5%)
    top_margin = int(h * 0.15)
    bottom_margin = int(h * 0.95)
    left_margin = int(w * 0.05)
    right_margin = int(w * 0.95)

    roi = gray[top_margin:bottom_margin, left_margin:right_margin]

    # 어두운 영역(X-ray 배경) 찾기: 평균 밝기가 낮은 사각형 영역
    mean_brightness = float(roi.mean())

    if mean_brightness < 80:
        # 화면 전체가 어두우면 이미지 영역으로 판단
        cx = left + left_margin + (right_margin - left_margin) // 2
        cy = top + top_margin + (bottom_margin - top_margin) // 2
        return (
            left + left_margin,
            top + top_margin,
            left + right_margin,
            top + bottom_margin,
        )

    return None


def get_image_center(hwnd: int) -> tuple[int, int]:
    """이미지 영역의 중앙 좌표 반환. 탐지 실패 시 창 중앙 반환."""
    region = find_xray_region(hwnd)
    if region:
        l, t, r, b = region
        return ((l + r) // 2, (t + b) // 2)

    left, top, right, bottom = get_window_rect(hwnd)
    return ((left + right) // 2, (top + bottom) // 2)


# ──────────────────────────────────────────────────────────────
# 우클릭 → 메뉴 선택 → 저장
# ──────────────────────────────────────────────────────────────

def right_click_and_save(hwnd: int, cfg: dict, save_dir: Path) -> bool:
    """이미지 영역 우클릭 → 저장 메뉴 클릭 → 파일 저장."""
    ui_cfg = cfg.get("ui", {})
    delay = ui_cfg.get("action_delay", 0.5)
    menu_items = ui_cfg.get("save_menu_items", ["Save Image", "이미지 저장"])
    save_dir.mkdir(parents=True, exist_ok=True)

    bring_to_front(hwnd)
    time.sleep(delay)

    cx, cy = get_image_center(hwnd)
    logger.debug(f"우클릭 위치: ({cx}, {cy})")

    # 우클릭
    pyautogui.rightClick(cx, cy)
    time.sleep(delay)

    # 컨텍스트 메뉴에서 저장 항목 찾기
    for item_text in menu_items:
        try:
            pos = pyautogui.locateOnScreen  # 텍스트 기반 대신 pywinauto 사용
            break
        except Exception:
            continue

    # pywinauto로 메뉴 항목 찾기
    found = _click_menu_item_by_text(menu_items, delay)
    if not found:
        logger.warning("저장 메뉴 항목을 찾지 못했습니다. Esc로 메뉴 닫기.")
        pyautogui.press("escape")
        return False

    time.sleep(delay * 2)

    # 저장 대화상자 처리
    return _handle_save_dialog(save_dir, ui_cfg, delay)


def _click_menu_item_by_text(menu_items: list[str], delay: float) -> bool:
    """화면에 표시된 컨텍스트 메뉴에서 텍스트로 항목 찾기."""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        time.sleep(delay)

        # 모든 메뉴 항목 탐색
        for win in desktop.windows():
            try:
                title = win.window_text()
                for item in menu_items:
                    if item.lower() in title.lower():
                        win.click_input()
                        logger.info(f"메뉴 클릭: '{title}'")
                        return True

                # 자식 요소 탐색
                for ctrl in win.descendants():
                    try:
                        ctrl_text = ctrl.window_text()
                        for item in menu_items:
                            if item.lower() in ctrl_text.lower():
                                ctrl.click_input()
                                logger.info(f"메뉴 항목 클릭: '{ctrl_text}'")
                                return True
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"pywinauto 메뉴 탐색 실패: {e}")

    # 대안: 키보드로 메뉴 탐색 (위/아래 화살표)
    logger.debug("키보드로 메뉴 탐색 시도")
    for _ in range(15):
        pyautogui.press("down")
        time.sleep(0.1)
        # 현재 선택된 항목 텍스트 가져오기 어려우므로 Enter 시도는 생략
    pyautogui.press("escape")
    return False


def _handle_save_dialog(save_dir: Path, ui_cfg: dict, delay: float) -> bool:
    """Windows 파일 저장 대화상자 처리."""
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        time.sleep(delay * 2)

        # 저장 대화상자 찾기
        for win in desktop.windows():
            try:
                title = win.window_text()
                if any(k in title for k in ("저장", "Save", "다른 이름")):
                    logger.debug(f"저장 대화상자 발견: {title}")

                    # 파일 경로 입력 필드에 경로 입력
                    try:
                        path_field = win.child_window(control_type="Edit")
                        path_field.set_text(str(save_dir))
                        time.sleep(delay)
                    except Exception:
                        # 직접 경로를 타이핑
                        pyautogui.hotkey("ctrl", "a")
                        pyautogui.typewrite(str(save_dir), interval=0.05)
                        time.sleep(delay)

                    # 저장 버튼 클릭
                    save_btn_text = ui_cfg.get("save_dialog_button", "저장")
                    try:
                        save_btn = win.child_window(title=save_btn_text, control_type="Button")
                        save_btn.click_input()
                    except Exception:
                        pyautogui.press("enter")

                    logger.info(f"파일 저장 경로: {save_dir}")
                    return True
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"저장 대화상자 처리 실패: {e}")

    # 대화상자가 없으면 Infinitt가 기본 경로에 저장했을 가능성
    return True


# ──────────────────────────────────────────────────────────────
# 단축키 트리거 (F9)
# ──────────────────────────────────────────────────────────────

class HotkeyCapture:
    """F9 키를 누르면 현재 Infinitt 이미지를 저장하는 전역 단축키."""

    def __init__(self, cfg: dict, save_dir: Path):
        self.cfg = cfg
        self.save_dir = save_dir
        self.ui_cfg = cfg.get("ui", {})
        self.title = self.ui_cfg.get("window_title_contains", "Infinitt")
        self.hotkey = self.ui_cfg.get("hotkey", "f9").lower()
        self._listener = None
        self.count = 0

    def _on_press(self, key):
        try:
            key_name = key.name if hasattr(key, "name") else str(key).replace("'", "")
            if key_name.lower() == self.hotkey:
                self._trigger()
        except Exception:
            pass

    def _trigger(self):
        hwnd = find_infinitt_window(self.title)
        if not hwnd:
            logger.warning(f"Infinitt 창을 찾을 수 없습니다. (찾는 제목: {self.title!r})")
            return

        logger.info(f"[{self.hotkey.upper()}] 저장 트리거")
        ok = right_click_and_save(hwnd, self.cfg, self.save_dir)
        if ok:
            self.count += 1
            logger.info(f"저장 완료 (누적 {self.count}건)")

    def start(self):
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()
        logger.info(f"단축키 대기 중: {self.hotkey.upper()} 키를 누르면 현재 Infinitt 이미지를 저장합니다.")

    def stop(self):
        if self._listener:
            self._listener.stop()


# ──────────────────────────────────────────────────────────────
# 자동 감지 모드 (새 이미지 로드 시 자동 저장)
# ──────────────────────────────────────────────────────────────

def _capture_window_hash(hwnd: int) -> str | None:
    """창 화면의 해시값 계산 (변화 감지용)."""
    import hashlib
    import mss

    try:
        left, top, right, bottom = get_window_rect(hwnd)
        with mss.mss() as sct:
            monitor = {
                "left": left + (right - left) // 4,
                "top": top + (bottom - top) // 4,
                "width": (right - left) // 2,
                "height": (bottom - top) // 2,
            }
            screenshot = sct.grab(monitor)
        return hashlib.md5(bytes(screenshot.bgra)).hexdigest()
    except Exception:
        return None


def run_ui_mode(cfg: dict, dirs: dict) -> None:
    """UI 자동화 모드 실행 (단축키 + 자동 감지 동시 실행)."""
    ui_cfg = cfg.get("ui", {})
    title = ui_cfg.get("window_title_contains", "Infinitt")
    infinitt_save_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    infinitt_save_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Infinitt UI 자동화 모드 시작")
    logger.info(f"  Infinitt 창 감지 키워드: {title!r}")
    logger.info(f"  저장 폴더: {infinitt_save_dir}")
    logger.info(f"  단축키: {ui_cfg.get('hotkey', 'f9').upper()} → 현재 이미지 즉시 저장")
    logger.info("  Infinitt에서 치근단 사진을 열면 자동으로 감지합니다.")
    logger.info("  종료: Ctrl+C")
    logger.info("=" * 60)

    # 단축키 리스너 시작
    hotkey = HotkeyCapture(cfg, infinitt_save_dir)
    hotkey.start()

    # 자동 감지: 창 내용 변화 감시
    prev_hash = None
    delay = ui_cfg.get("action_delay", 0.5)

    try:
        while True:
            time.sleep(2)

            hwnd = find_infinitt_window(title)
            if not hwnd:
                if prev_hash is not None:
                    logger.info("Infinitt 창이 닫혔습니다. 재시작을 기다립니다...")
                    prev_hash = None
                continue

            curr_hash = _capture_window_hash(hwnd)
            if curr_hash is None:
                continue

            if prev_hash is not None and curr_hash != prev_hash:
                # 창 내용이 변경됨 → 새 이미지 로드 가능성
                time.sleep(1.0)   # 이미지 로드 완료 대기
                logger.info("Infinitt 화면 변화 감지 → 저장 시도")
                right_click_and_save(hwnd, cfg, infinitt_save_dir)

            prev_hash = curr_hash

    except KeyboardInterrupt:
        logger.info("사용자 종료 요청")
    finally:
        hotkey.stop()
        logger.info(f"완료 — 저장된 파일 위치: {infinitt_save_dir}")
        logger.info(f"        처리된 파일 위치: {dirs['base']}")
