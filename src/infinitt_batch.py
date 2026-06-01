"""Infinitt 배치 자동화 모듈.

엑셀에서 환자번호를 읽어 Infinitt에서 순서대로:
  검색 → 첫 번째 결과 열기 → 치근단 이미지 저장

첫 실행 시 `setup` 명령으로 Infinitt UI 좌표를 기록합니다.
이후 배치 실행 시 저장된 좌표를 자동으로 사용합니다.
"""
import json
import logging
import time
from pathlib import Path

import pyautogui
import win32con
import win32gui
from pynput import keyboard as kb_module

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

POSITIONS_FILE = Path("./ui_positions.json")


# ──────────────────────────────────────────────────────────────
# UI 좌표 기록 (최초 1회 setup)
# ──────────────────────────────────────────────────────────────

def _wait_for_click(prompt: str, timeout: int = 30) -> tuple[int, int]:
    """사용자가 클릭한 위치를 기록. timeout 초 안에 클릭하지 않으면 예외 발생."""
    print(f"\n  → {prompt}")
    print(f"    {timeout}초 안에 해당 위치를 마우스로 클릭하세요...", end="", flush=True)

    clicked: list[tuple[int, int]] = []

    def on_click(x, y, button, pressed):
        if pressed:
            clicked.append((x, y))
            return False  # 리스너 종료

    from pynput import mouse as mouse_module
    with mouse_module.Listener(on_click=on_click) as listener:
        listener.join(timeout=timeout)

    if not clicked:
        raise TimeoutError(f"좌표 기록 시간 초과: {prompt}")

    x, y = clicked[0]
    print(f" 완료 ({x}, {y})")
    return x, y


def run_setup() -> None:
    """Infinitt UI 요소 위치를 대화형으로 기록."""
    print()
    print("━" * 60)
    print("  Infinitt UI 좌표 설정 (최초 1회)")
    print("━" * 60)
    print()
    print("  Infinitt 클라이언트를 열어두고 아래 안내에 따라")
    print("  각 UI 요소를 직접 클릭하세요.")
    print()

    positions = {}

    try:
        # 1. 환자 검색창
        positions["search_box"] = list(_wait_for_click(
            "환자번호 입력 검색창을 클릭하세요 (검색어를 입력하는 텍스트 박스)"
        ))

        # 2. 검색 결과 첫 번째 행
        print()
        print("  ※ 먼저 아무 환자번호로 검색해서 결과 목록을 띄워두세요.")
        positions["first_result"] = list(_wait_for_click(
            "검색 결과 목록의 첫 번째 행을 클릭하세요"
        ))

        # 3. 이미지 영역
        print()
        print("  ※ 아무 환자 스터디를 열어서 이미지가 보이도록 해두세요.")
        positions["image_area"] = list(_wait_for_click(
            "X-ray 이미지 표시 영역 (검은 배경) 안쪽을 클릭하세요"
        ))

        # 저장
        POSITIONS_FILE.write_text(json.dumps(positions, ensure_ascii=False, indent=2))
        print()
        print(f"  좌표 저장 완료: {POSITIONS_FILE}")
        print()
        print("  이제 배치 실행 명령을 사용할 수 있습니다:")
        print("    run.bat --mode batch --excel 환자목록.xlsx")

    except (TimeoutError, KeyboardInterrupt) as e:
        print(f"\n  설정 중단: {e}")


def load_positions() -> dict:
    if not POSITIONS_FILE.exists():
        raise FileNotFoundError(
            f"UI 좌표 파일이 없습니다: {POSITIONS_FILE}\n"
            "  먼저 run.bat --setup 을 실행하여 좌표를 기록하세요."
        )
    return json.loads(POSITIONS_FILE.read_text())


# ──────────────────────────────────────────────────────────────
# 단일 환자 처리
# ──────────────────────────────────────────────────────────────

def _bring_infinitt_to_front(title_contains: str) -> int | None:
    result = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if title_contains.lower() in win32gui.GetWindowText(hwnd).lower():
                result.append(hwnd)

    win32gui.EnumWindows(enum_cb, None)
    if not result:
        return None

    hwnd = result[0]
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    return hwnd


def _click_menu_item(menu_items: list[str], delay: float) -> bool:
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
        logger.debug(f"pywinauto 실패: {e}")
    pyautogui.press("escape")
    return False


def _handle_save_dialog(save_dir: Path, save_btn_text: str, delay: float) -> None:
    time.sleep(delay * 2)
    try:
        from pywinauto import Desktop
        for win in Desktop(backend="uia").windows():
            title = win.window_text()
            if any(k in title for k in ("저장", "Save", "다른 이름")):
                try:
                    win.child_window(control_type="Edit").set_text(str(save_dir))
                except Exception:
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.typewrite(str(save_dir), interval=0.05)
                time.sleep(delay)
                try:
                    win.child_window(title=save_btn_text, control_type="Button").click_input()
                except Exception:
                    pyautogui.press("enter")
                return
    except Exception:
        pass


def process_one_patient(
    patient_id: str,
    positions: dict,
    cfg: dict,
    save_dir: Path,
) -> bool:
    """환자번호 하나에 대해 Infinitt 검색 → 열기 → 저장 수행."""
    ui_cfg = cfg.get("ui", {})
    delay = ui_cfg.get("action_delay", 0.8)
    menu_items = ui_cfg.get("save_menu_items", ["Save Image", "이미지 저장"])
    save_btn_text = ui_cfg.get("save_dialog_button", "저장")
    wait_search = ui_cfg.get("wait_after_search", 2.0)
    wait_open = ui_cfg.get("wait_after_open", 3.0)

    title = ui_cfg.get("window_title_contains", "Infinitt")
    hwnd = _bring_infinitt_to_front(title)
    if not hwnd:
        logger.warning(f"[{patient_id}] Infinitt 창 없음 - 건너뜀")
        return False

    time.sleep(delay)

    # ① 검색창 클릭 → 환자번호 입력 → Enter
    sx, sy = positions["search_box"]
    pyautogui.click(sx, sy)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(patient_id, interval=0.05)
    pyautogui.press("enter")
    logger.info(f"[{patient_id}] 검색 완료")
    time.sleep(wait_search)

    # ② 첫 번째 결과 더블클릭 → 스터디 열기
    rx, ry = positions["first_result"]
    pyautogui.doubleClick(rx, ry)
    logger.info(f"[{patient_id}] 스터디 열기")
    time.sleep(wait_open)

    # ③ 이미지 영역 우클릭 → 저장 메뉴
    ix, iy = positions["image_area"]
    pyautogui.rightClick(ix, iy)

    found = _click_menu_item(menu_items, delay)
    if not found:
        logger.warning(f"[{patient_id}] 저장 메뉴 없음 - 건너뜀")
        return False

    _handle_save_dialog(save_dir, save_btn_text, delay)
    logger.info(f"[{patient_id}] 저장 완료")
    return True


# ──────────────────────────────────────────────────────────────
# 배치 실행
# ──────────────────────────────────────────────────────────────

def run_batch(patient_ids: list[str], cfg: dict, dirs: dict, resume_from: int = 0) -> None:
    """엑셀에서 읽은 환자번호 목록 전체를 자동 처리."""
    ui_cfg = cfg.get("ui", {})
    save_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    save_dir.mkdir(parents=True, exist_ok=True)

    positions = load_positions()
    progress_file = dirs["base"] / "batch_progress.json"

    total = len(patient_ids)
    done: list[str] = []
    failed: list[str] = []

    # 이전 실행 진행 상황 복원
    if progress_file.exists() and resume_from == 0:
        prev = json.loads(progress_file.read_text())
        done = prev.get("done", [])
        failed = prev.get("failed", [])
        if done:
            logger.info(f"이전 진행 복원: {len(done)}건 완료, {len(failed)}건 실패")

    done_set = set(done)
    remaining = [p for p in patient_ids if p not in done_set][resume_from:]

    logger.info("=" * 60)
    logger.info(f"배치 시작: 총 {total}명 / 처리 예정: {len(remaining)}명")
    logger.info(f"저장 폴더: {save_dir}")
    logger.info("종료: 화면 왼쪽 위 모서리로 마우스 이동 → 자동 중지")
    logger.info("=" * 60)

    for i, pid in enumerate(remaining, 1):
        try:
            logger.info(f"[{i}/{len(remaining)}] 처리 중: {pid}")
            ok = process_one_patient(pid, positions, cfg, save_dir)
            if ok:
                done.append(pid)
            else:
                failed.append(pid)
        except pyautogui.FailSafeException:
            logger.warning("긴급 정지! 마우스가 화면 왼쪽 위로 이동됨.")
            break
        except Exception as e:
            logger.error(f"[{pid}] 오류: {e}")
            failed.append(pid)
        finally:
            # 진행 상황 저장
            progress_file.write_text(
                json.dumps({"done": done, "failed": failed}, ensure_ascii=False, indent=2)
            )

    logger.info("=" * 60)
    logger.info(f"배치 완료 — 성공: {len(done)}, 실패: {len(failed)}")
    if failed:
        logger.warning(f"실패 목록: {failed}")
        failed_file = dirs["base"] / "failed_patients.txt"
        failed_file.write_text("\n".join(failed), encoding="utf-8")
        logger.info(f"실패 목록 저장: {failed_file}")
