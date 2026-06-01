"""Infinitt 배치 자동화 — 환자당 5년치 스터디 × 스터디당 전체 이미지 수집.

흐름 (환자 1명):
  검색 → 스터디 목록 → 스터디 N개 반복:
      스터디 열기 → 이미지 슬롯 M개 각각 우클릭 저장 → 뒤로

저장 폴더 구조:
  infinitt_export/
    {patient_id}/
      study_01/   ← 스터디 번호 (Infinitt 목록 순서)
        img_01.*
        img_02.*
      study_02/
        ...

사용 순서:
  1. run.bat --setup   → UI 좌표 기록 (최초 1회)
  2. run.bat --excel 환자목록.xlsx
"""
import json
import logging
import time
from pathlib import Path

import pyautogui
import win32con
import win32gui

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

POSITIONS_FILE = Path("./ui_positions.json")


# ──────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────

def _bring_to_front(title_contains: str) -> bool:
    result = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if title_contains.lower() in win32gui.GetWindowText(hwnd).lower():
                result.append(hwnd)

    win32gui.EnumWindows(cb, None)
    if not result:
        return False
    hwnd = result[0]
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    return True


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
                            logger.debug(f"메뉴 클릭: '{text}'")
                            return True
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"pywinauto 메뉴 탐색 실패: {e}")
    pyautogui.press("escape")
    return False


def _handle_save_dialog(full_path: Path, save_btn_text: str, delay: float) -> bool:
    """저장 대화상자의 파일명 칸에 전체 경로(폴더+파일명)를 입력하고 저장.

    full_path: 예) C:\\infinitt_export\\1234567\\study_01\\img_01.png
    파일명까지 지정해야 여러 이미지가 덮어쓰기 없이 각각 저장됨.
    """
    full_path.parent.mkdir(parents=True, exist_ok=True)
    path_str = str(full_path)
    time.sleep(delay * 2)
    try:
        from pywinauto import Desktop
        for win in Desktop(backend="uia").windows():
            if any(k in win.window_text() for k in ("저장", "Save", "다른 이름", "내보내기", "Export")):
                # 파일명 입력 칸에 전체 경로 입력
                try:
                    edit = win.child_window(control_type="Edit")
                    edit.set_focus()
                    edit.set_text(path_str)
                except Exception:
                    pyautogui.hotkey("ctrl", "a")
                    pyautogui.press("delete")
                    pyautogui.typewrite(path_str, interval=0.03)
                time.sleep(delay)
                # 저장 버튼 클릭
                try:
                    win.child_window(title=save_btn_text, control_type="Button").click_input()
                except Exception:
                    pyautogui.press("enter")
                time.sleep(delay)
                # 덮어쓰기 확인 대화상자가 뜨면 Enter (Yes)
                pyautogui.press("enter")
                return True
    except Exception as e:
        logger.debug(f"저장 대화상자 처리 실패: {e}")
    # 대화상자가 안 보이면 Infinitt가 기본 경로에 바로 저장한 경우 → 성공으로 간주
    return True


# ──────────────────────────────────────────────────────────────
# Setup 마법사
# ──────────────────────────────────────────────────────────────

def _wait_click(prompt: str, timeout: int = 40) -> tuple[int, int]:
    """사용자가 클릭한 좌표를 캡처."""
    print(f"\n  → {prompt}")
    print(f"    {timeout}초 안에 해당 위치를 마우스로 클릭하세요...", end="", flush=True)

    clicked: list[tuple[int, int]] = []

    def on_click(x, y, button, pressed):
        if pressed:
            clicked.append((x, y))
            return False

    from pynput import mouse as _mouse
    with _mouse.Listener(on_click=on_click) as listener:
        listener.join(timeout=timeout)

    if not clicked:
        raise TimeoutError(f"시간 초과: {prompt}")
    x, y = clicked[0]
    print(f" ({x}, {y})")
    return x, y


def run_setup() -> None:
    """Infinitt UI 좌표 기록 — 최초 1회 실행."""
    print()
    print("━" * 65)
    print("  Infinitt UI 좌표 설정  (--setup)")
    print("━" * 65)
    print()
    print("  Infinitt 클라이언트를 켜두고 안내에 따라 클릭하세요.")
    print("  기록된 좌표는 ui_positions.json 에 저장됩니다.")
    print()

    pos = {}

    try:
        # ── STEP 1: 검색창 ──────────────────────────────────────
        print("  [STEP 1/5] 환자번호 검색창")
        print("  Infinitt 상단 검색창(환자번호 입력 텍스트박스)에 커서를 올리세요.")
        pos["search_box"] = list(_wait_click("검색창을 클릭하세요"))

        # ── STEP 2: 스터디 목록 첫 번째 행 ──────────────────────
        print()
        print("  [STEP 2/5] 스터디 목록 — 첫 번째 행")
        print("  ※ 아무 환자번호로 검색하여 스터디 목록이 보이도록 하세요.")
        print("     (날짜 목록이 줄줄이 뜨는 그 화면)")
        pos["study_row_1"] = list(_wait_click("스터디 목록의 첫 번째 행(가장 위 날짜)을 클릭하세요"))

        # ── STEP 3: 스터디 목록 두 번째 행 (행 높이 계산) ────────
        print()
        print("  [STEP 3/5] 스터디 목록 — 두 번째 행")
        pos["study_row_2"] = list(_wait_click("스터디 목록의 두 번째 행을 클릭하세요"))

        row_height = abs(pos["study_row_2"][1] - pos["study_row_1"][1])
        pos["study_row_height"] = row_height
        print(f"    → 행 높이 자동 계산: {row_height}px")

        # ── STEP 4: 이미지 슬롯들 (한 스터디에서 보이는 이미지 전체) ──
        print()
        print("  [STEP 4/5] 이미지 슬롯 위치")
        print("  ※ 아무 스터디를 열어서 이미지가 모두 보이는 상태로 만드세요.")
        print("     치근단 사진이 여러 칸(격자)으로 보이는 그 화면입니다.")
        print()

        n_str = input("  화면에 보이는 이미지 칸(슬롯)이 몇 개인가요? (예: 14): ").strip()
        n_slots = int(n_str) if n_str.isdigit() else 1

        slots = []
        for i in range(n_slots):
            slot = list(_wait_click(f"이미지 슬롯 {i+1}/{n_slots} 의 중앙을 클릭하세요"))
            slots.append(slot)
        pos["image_slots"] = slots
        print(f"    → {n_slots}개 슬롯 기록 완료")

        # ── STEP 5: 뒤로 가기 버튼 (스터디 → 목록으로 복귀) ─────
        print()
        print("  [STEP 5/5] 뒤로 가기 버튼")
        print("  스터디에서 스터디 목록으로 돌아가는 버튼(또는 Esc 키 위치)을 클릭하세요.")
        print("  ※ Infinitt가 Esc 키로 돌아간다면 아무 곳이나 클릭 후")
        print("     나중에 config.yaml 의 back_key 를 'escape' 로 설정하세요.")
        back = list(_wait_click("뒤로 가기 버튼을 클릭하세요"))
        pos["back_button"] = back

        # 저장
        POSITIONS_FILE.write_text(json.dumps(pos, ensure_ascii=False, indent=2))
        print()
        print(f"  ✓ 좌표 저장 완료: {POSITIONS_FILE.resolve()}")
        print()
        print("  이제 배치를 실행할 수 있습니다:")
        print("    run.bat --excel 환자목록.xlsx")

    except (TimeoutError, KeyboardInterrupt, ValueError) as e:
        print(f"\n  설정 중단: {e}")


def load_positions() -> dict:
    if not POSITIONS_FILE.exists():
        raise FileNotFoundError(
            f"UI 좌표 파일 없음: {POSITIONS_FILE}\n"
            "  먼저  run.bat --setup  을 실행하여 좌표를 기록하세요."
        )
    return json.loads(POSITIONS_FILE.read_text())


# ──────────────────────────────────────────────────────────────
# 이미지 저장 (슬롯 하나)
# ──────────────────────────────────────────────────────────────

def _save_slot(ix: int, iy: int, full_path: Path, ui_cfg: dict) -> bool:
    """이미지 슬롯(ix, iy)에서 우클릭 → 저장 메뉴 → full_path로 저장."""
    delay = ui_cfg.get("action_delay", 0.6)
    menu_items = ui_cfg.get("save_menu_items", ["Save Image", "이미지 저장"])
    save_btn_text = ui_cfg.get("save_dialog_button", "저장")

    pyautogui.rightClick(ix, iy)
    found = _click_menu_item(menu_items, delay)
    if not found:
        return False
    return _handle_save_dialog(full_path, save_btn_text, delay)


# ──────────────────────────────────────────────────────────────
# 스터디 처리 (한 내원 날짜)
# ──────────────────────────────────────────────────────────────

def _process_study(
    study_idx: int,
    patient_id: str,
    positions: dict,
    ui_cfg: dict,
    base_save_dir: Path,
) -> int:
    """
    study_idx 번째 스터디를 열고 모든 이미지 슬롯을 저장.
    저장된 이미지 수를 반환. 0이면 스터디가 없는 것으로 간주.
    """
    delay = ui_cfg.get("action_delay", 0.6)
    wait_open = ui_cfg.get("wait_after_open", 3.0)
    back_key = ui_cfg.get("back_key", "escape")

    row_x = positions["study_row_1"][0]
    row_y_base = positions["study_row_1"][1]
    row_height = positions.get("study_row_height", 30)
    slots: list[list[int]] = positions.get("image_slots", [])
    back_btn = positions.get("back_button")

    # 스터디 목록에서 study_idx 번째 행 더블클릭
    target_y = row_y_base + study_idx * row_height
    pyautogui.doubleClick(row_x, target_y)
    time.sleep(wait_open)

    study_dir = base_save_dir / patient_id / f"study_{study_idx + 1:02d}"
    ext = ui_cfg.get("save_extension", "png").lstrip(".")
    saved = 0

    for img_idx, (ix, iy) in enumerate(slots):
        full_path = study_dir / f"img_{img_idx + 1:02d}.{ext}"
        ok = _save_slot(ix, iy, full_path, ui_cfg)
        if ok:
            saved += 1
            time.sleep(delay * 0.5)
        else:
            logger.debug(f"  슬롯 {img_idx+1} 저장 실패 (빈 슬롯일 수 있음)")

    # 스터디 목록으로 복귀
    if back_btn:
        pyautogui.click(back_btn[0], back_btn[1])
    else:
        pyautogui.press(back_key)
    time.sleep(delay)

    return saved


# ──────────────────────────────────────────────────────────────
# 환자 처리 (5년치 전체)
# ──────────────────────────────────────────────────────────────

def process_one_patient(
    patient_id: str,
    positions: dict,
    cfg: dict,
    base_save_dir: Path,
) -> dict:
    """환자번호 하나에 대해 모든 스터디 × 모든 이미지 슬롯 저장.

    Returns:
        {"studies": int, "images": int, "ok": bool}
    """
    ui_cfg = cfg.get("ui", {})
    delay = ui_cfg.get("action_delay", 0.6)
    wait_search = ui_cfg.get("wait_after_search", 2.0)
    max_studies = ui_cfg.get("max_studies_per_patient", 20)
    title = ui_cfg.get("window_title_contains", "Infinitt")

    if not _bring_to_front(title):
        logger.warning(f"[{patient_id}] Infinitt 창 없음")
        return {"studies": 0, "images": 0, "ok": False}

    time.sleep(delay)

    # ① 환자번호 검색
    sx, sy = positions["search_box"]
    pyautogui.click(sx, sy)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(patient_id, interval=0.05)
    pyautogui.press("enter")
    time.sleep(wait_search)

    # ② 스터디 목록 순회
    total_images = 0
    total_studies = 0

    for study_idx in range(max_studies):
        try:
            saved = _process_study(study_idx, patient_id, positions, ui_cfg, base_save_dir)
            if saved == 0 and study_idx > 0:
                # 이미지가 하나도 없는 스터디 → 더 이상 스터디 없는 것으로 판단
                logger.debug(f"[{patient_id}] study_{study_idx+1:02d}: 이미지 없음 → 종료")
                break
            if saved > 0:
                total_studies += 1
                total_images += saved
                logger.info(
                    f"[{patient_id}] study_{study_idx+1:02d}: {saved}장 저장"
                )
        except pyautogui.FailSafeException:
            raise  # 긴급 정지는 상위로 전파
        except Exception as e:
            logger.warning(f"[{patient_id}] study_{study_idx+1:02d} 오류: {e}")
            break

    return {"studies": total_studies, "images": total_images, "ok": total_studies > 0}


# ──────────────────────────────────────────────────────────────
# 배치 실행 (전체 280명)
# ──────────────────────────────────────────────────────────────

def run_batch(patient_ids: list[str], cfg: dict, dirs: dict, resume_from: int = 0) -> None:
    """엑셀에서 읽은 환자 전체를 배치 처리."""
    ui_cfg = cfg.get("ui", {})
    base_save_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    base_save_dir.mkdir(parents=True, exist_ok=True)

    positions = load_positions()
    progress_file = dirs["base"] / "batch_progress.json"

    # 이전 진행 상황 로드
    done: list[str] = []
    failed: list[str] = []
    if progress_file.exists() and resume_from == 0:
        prev = json.loads(progress_file.read_text())
        done = prev.get("done", [])
        failed = prev.get("failed", [])
        if done:
            logger.info(f"이전 진행 복원: {len(done)}명 완료 / {len(failed)}명 실패")

    done_set = set(done)
    remaining = [p for p in patient_ids if p not in done_set]
    if resume_from:
        remaining = remaining[resume_from:]

    max_studies = ui_cfg.get("max_studies_per_patient", 20)
    n_slots = len(positions.get("image_slots", []))

    logger.info("=" * 65)
    logger.info(f"배치 시작")
    logger.info(f"  전체 환자    : {len(patient_ids)}명")
    logger.info(f"  처리 예정    : {len(remaining)}명")
    logger.info(f"  환자당 최대 스터디: {max_studies}개")
    logger.info(f"  스터디당 이미지 슬롯: {n_slots}개")
    logger.info(f"  저장 폴더    : {base_save_dir}")
    logger.info("  긴급 정지: 마우스를 화면 왼쪽 위 모서리로 빠르게 이동")
    logger.info("=" * 65)

    total_images = 0

    for i, pid in enumerate(remaining, 1):
        try:
            logger.info(f"[{i}/{len(remaining)}] 환자: {pid}")
            result = process_one_patient(pid, positions, cfg, base_save_dir)

            if result["ok"]:
                done.append(pid)
                total_images += result["images"]
                logger.info(
                    f"  → 완료: {result['studies']}개 스터디 / {result['images']}장 저장"
                    f"  (누적 {total_images}장)"
                )
            else:
                failed.append(pid)
                logger.warning(f"  → 실패 (이미지 없음 또는 오류)")

        except pyautogui.FailSafeException:
            logger.warning("긴급 정지! 진행 상황을 저장합니다.")
            break
        except Exception as e:
            logger.error(f"[{pid}] 예외: {e}")
            failed.append(pid)
        finally:
            progress_file.write_text(
                json.dumps(
                    {"done": done, "failed": failed, "total_images": total_images},
                    ensure_ascii=False,
                    indent=2,
                )
            )

    logger.info("=" * 65)
    logger.info(f"배치 완료")
    logger.info(f"  성공: {len(done)}명 / 실패: {len(failed)}명")
    logger.info(f"  총 저장 이미지: {total_images}장")
    logger.info(f"  저장 위치: {base_save_dir}")

    if failed:
        failed_file = dirs["base"] / "failed_patients.txt"
        failed_file.write_text("\n".join(failed), encoding="utf-8")
        logger.warning(f"  실패 환자 목록: {failed_file}")
        logger.info("  실패 환자만 재시도: run.bat --excel 실패목록.txt")
