"""Infinitt PACS 클라이언트 UI 자동화 모듈.

사용법:
  1. Infinitt에서 치근단 사진을 연다.
  2. 마우스를 이미지 위에 올린다.
  3. F9 를 누른다 → 현재 커서 위치에서 우클릭 → 저장 메뉴 자동 클릭.
"""
import logging
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
# 컨텍스트 메뉴 처리
# ──────────────────────────────────────────────────────────────

def _click_menu_item(menu_items: list[str], delay: float) -> bool:
    """우클릭 후 뜬 컨텍스트 메뉴에서 저장 항목을 클릭."""
    time.sleep(delay)
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")

        for win in desktop.windows():
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
        "저장 메뉴를 찾지 못했습니다.\n"
        "  config.yaml → ui.save_menu_items 에\n"
        "  Infinitt 우클릭 메뉴에 실제로 보이는 텍스트를 추가하세요."
    )
    return False


def _handle_save_dialog(save_dir: Path, ui_cfg: dict, delay: float) -> bool:
    """Windows 파일 저장 대화상자가 뜨면 경로를 입력하고 저장."""
    time.sleep(delay * 2)
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")

        for win in desktop.windows():
            title = win.window_text()
            if any(k in title for k in ("저장", "Save", "다른 이름")):
                logger.debug(f"저장 대화상자 발견: '{title}'")
                try:
                    win.child_window(control_type="Edit").set_text(str(save_dir))
                except Exception:
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.typewrite(str(save_dir), interval=0.05)
                time.sleep(delay)
                try:
                    btn_text = ui_cfg.get("save_dialog_button", "저장")
                    win.child_window(title=btn_text, control_type="Button").click_input()
                except Exception:
                    pyautogui.press("enter")
                logger.info(f"저장 → {save_dir}")
                return True
    except Exception as e:
        logger.debug(f"저장 대화상자 처리 실패: {e}")

    # 대화상자 없이 바로 저장했거나 기본 경로로 저장된 경우
    return True


# ──────────────────────────────────────────────────────────────
# 핵심: 커서 현재 위치에서 우클릭 → 저장
# ──────────────────────────────────────────────────────────────

def save_at_cursor(cfg: dict, save_dir: Path) -> bool:
    """현재 마우스 커서 위치에서 우클릭하여 Infinitt 저장 메뉴를 실행."""
    ui_cfg = cfg.get("ui", {})
    delay = ui_cfg.get("action_delay", 0.5)
    menu_items = ui_cfg.get("save_menu_items", ["Save Image", "이미지 저장"])
    save_dir.mkdir(parents=True, exist_ok=True)

    x, y = pyautogui.position()
    logger.info(f"우클릭 위치: ({x}, {y})")

    pyautogui.rightClick(x, y)

    found = _click_menu_item(menu_items, delay)
    if not found:
        return False

    return _handle_save_dialog(save_dir, ui_cfg, delay)


# ──────────────────────────────────────────────────────────────
# 전역 단축키 (F9)
# ──────────────────────────────────────────────────────────────

class HotkeyCapture:
    """설정된 단축키(기본 F9)를 누르면 커서 위치에서 즉시 저장."""

    def __init__(self, cfg: dict, save_dir: Path):
        self.cfg = cfg
        self.save_dir = save_dir
        self.hotkey = cfg.get("ui", {}).get("hotkey", "f9").lower()
        self._listener = None
        self.count = 0

    def _on_press(self, key):
        try:
            name = key.name if hasattr(key, "name") else str(key).replace("'", "")
            if name.lower() == self.hotkey:
                self._trigger()
        except Exception:
            pass

    def _trigger(self):
        logger.info(f"[{self.hotkey.upper()}] 저장 트리거")
        ok = save_at_cursor(self.cfg, self.save_dir)
        if ok:
            self.count += 1
            logger.info(f"저장 완료 (누적 {self.count}건)")

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
    save_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    save_dir.mkdir(parents=True, exist_ok=True)

    hotkey_name = ui_cfg.get("hotkey", "f9").upper()

    logger.info("=" * 60)
    logger.info("Infinitt UI 자동화 모드 시작")
    logger.info(f"  저장 폴더: {save_dir}")
    logger.info(f"  단축키  : {hotkey_name}")
    logger.info("")
    logger.info(f"  사용법: Infinitt에서 이미지 위에 마우스를 올리고")
    logger.info(f"         {hotkey_name} 키를 누르면 자동으로 저장됩니다.")
    logger.info("  종료  : Ctrl+C")
    logger.info("=" * 60)

    hotkey = HotkeyCapture(cfg, save_dir)
    hotkey.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("사용자 종료 요청")
    finally:
        hotkey.stop()
        logger.info(f"완료 — 저장된 파일: {save_dir}")
        logger.info(f"        처리된 파일: {dirs['base']}")
