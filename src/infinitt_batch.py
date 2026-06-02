"""Infinitt 배치 자동화.

전제: Infinitt에서 검사명 필터를 'DS periapical view (implant)' 로 미리 설정해둔 상태.

흐름 (환자 1명):
  1. 환자번호 검색 → 목록에 DS periapical 항목들만 표시됨
  2. 목록 맨 위부터 한 행씩 클릭 → 날짜 읽기
  3. 5년 이내이면 더블클릭으로 열고 → 왼쪽 패널 우클릭 → Convert Study
  4. 뒤로 가기 → 다음 행 반복
  5. 5년 초과 or 빈 행 → 중단, 다음 환자로

저장 구조:
  infinitt_export/{patient_id}/{patient_id}(YYYY-MM-DD)/
"""
import datetime
import json
import logging
import re
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
# 날짜 유틸
# ──────────────────────────────────────────────────────────────

def _cutoff_date(years_back: int = 5) -> str:
    cutoff = datetime.date.today() - datetime.timedelta(days=years_back * 365)
    return cutoff.strftime("%Y%m%d")


def _yyyymmdd_to_dash(yyyymmdd: str) -> str:
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
    return yyyymmdd


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
            return f"{g[0]}{g[1].zfill(2)}{g[2].zfill(2)}"
        else:
            return f"{g[2]}{g[0].zfill(2)}{g[1].zfill(2)}"
    return ""


# ──────────────────────────────────────────────────────────────
# Infinitt 창 관리
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


# ──────────────────────────────────────────────────────────────
# 클릭된 행의 텍스트 읽기 (UIA)
# ──────────────────────────────────────────────────────────────

def _read_focused_row_text(title_contains: str) -> str:
    """
    클릭/선택된 행의 텍스트를 UIA get_focus()로 읽는다.
    셀 단위로 포커스된 경우 형제 셀까지 합쳐 전체 행 텍스트를 반환.
    """
    try:
        from pywinauto import Desktop
        ctrl = Desktop(backend="uia").get_focus()
        if ctrl is None:
            return ""

        text = ctrl.window_text().strip()
        if text:
            # 형제 셀까지 합쳐서 전체 행 반환 (날짜 셀 포함)
            try:
                siblings = [c.window_text().strip() for c in ctrl.parent().children()]
                full = "  ".join(s for s in siblings if s)
                if full:
                    return full
            except Exception:
                pass
            return text

        # 텍스트 없음 → 부모·조부모 자식 셀 합치기
        for get_ancestor in (lambda: ctrl.parent(), lambda: ctrl.parent().parent()):
            try:
                row = get_ancestor()
                cells = [c.window_text().strip() for c in row.children()]
                full = "  ".join(c for c in cells if c)
                if full:
                    return full
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"UIA get_focus: {e}")

    return ""


# ──────────────────────────────────────────────────────────────
# Convert Study 저장
# ──────────────────────────────────────────────────────────────

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
        logger.debug(f"메뉴 탐색 실패: {e}")
    pyautogui.press("escape")
    return False


def _handle_save_dialog(save_dir: Path, save_btn_text: str, delay: float) -> bool:
    save_dir.mkdir(parents=True, exist_ok=True)
    path_str = str(save_dir)
    time.sleep(delay * 2)
    try:
        from pywinauto import Desktop
        for win in Desktop(backend="uia").windows():
            if any(k in win.window_text() for k in ("저장", "Save", "다른 이름", "Export", "내보내기", "Convert")):
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
                    win.child_window(title=save_btn_text, control_type="Button").click_input()
                except Exception:
                    pyautogui.press("enter")
                time.sleep(delay)
                pyautogui.press("enter")
                return True
    except Exception as e:
        logger.debug(f"저장 대화상자 처리 실패: {e}")
    return True


def _convert_study(lx: int, ly: int, save_dir: Path, ui_cfg: dict) -> bool:
    """왼쪽 패널 우클릭 → Convert Study → 저장."""
    delay      = ui_cfg.get("action_delay", 0.6)
    menu_items = ui_cfg.get("convert_study_menu", ["Convert Study", "Convert", "스터디 변환", "변환"])
    save_btn   = ui_cfg.get("save_dialog_button", "저장")

    pyautogui.rightClick(lx, ly)
    if not _click_menu_item(menu_items, delay):
        logger.warning("Convert Study 메뉴를 찾지 못했습니다.")
        return False
    return _handle_save_dialog(save_dir, save_btn, delay)


# ──────────────────────────────────────────────────────────────
# 환자 1명 처리
# ──────────────────────────────────────────────────────────────

def process_one_patient(
    patient_id: str,
    positions: dict,
    cfg: dict,
    base_save_dir: Path,
) -> dict:
    """
    목록은 이미 DS periapical view (implant) 로 필터된 상태.
    행 1번 좌표 + 행 높이로 각 행을 클릭해 날짜 확인 → 5년 이내이면 더블클릭 → Convert Study.
    """
    ui_cfg      = cfg.get("ui", {})
    delay       = ui_cfg.get("action_delay", 0.6)
    wait_search = ui_cfg.get("wait_after_search", 2.0)
    wait_open   = ui_cfg.get("wait_after_open", 3.0)
    back_key    = ui_cfg.get("back_key", "escape")
    title       = ui_cfg.get("window_title_contains", "Infinitt")
    years_back  = ui_cfg.get("years_back", 5)
    max_studies = ui_cfg.get("max_studies_per_patient", 30)
    cutoff      = _cutoff_date(years_back)

    row_x, row_y   = positions["study_row_1"]
    row_height      = positions.get("study_row_height", 25)
    left_panel      = positions.get("left_panel")
    back_btn        = positions.get("back_button")
    sx, sy          = positions["search_box"]

    if not _bring_to_front(title):
        logger.warning(f"[{patient_id}] Infinitt 창 없음")
        return {"studies": 0, "ok": False}

    time.sleep(delay)

    # ① 환자번호 검색
    pyautogui.click(sx, sy)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(patient_id, interval=0.05)
    pyautogui.press("enter")
    time.sleep(wait_search)

    # ② 목록 맨 위로
    pyautogui.click(row_x, row_y)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "home")
    time.sleep(delay)

    total_studies = 0

    for i in range(max_studies):
        y = row_y + i * row_height

        # 해당 행 클릭(선택)
        pyautogui.click(row_x, y)
        time.sleep(0.3)

        # 날짜 읽기
        text = _read_focused_row_text(title)
        if not text:
            logger.debug(f"[{patient_id}] 행 {i+1}: 텍스트 없음 → 목록 끝")
            break

        date = _parse_date_to_yyyymmdd(text)
        logger.debug(f"[{patient_id}] 행 {i+1}: date={date}  text={text[:60]}")

        if date and date < cutoff:
            logger.info(f"[{patient_id}] 5년 초과({date}) → 중단")
            break

        date_dash = _yyyymmdd_to_dash(date) if date else "unknown"
        save_dir  = base_save_dir / patient_id / f"{patient_id}({date_dash})"
        total_studies += 1
        logger.info(f"[{patient_id}] study {total_studies}  날짜={date_dash}")

        # 더블클릭으로 스터디 열기
        pyautogui.doubleClick(row_x, y)
        time.sleep(wait_open)

        # 왼쪽 패널 우클릭 → Convert Study
        if left_panel:
            ok = _convert_study(left_panel[0], left_panel[1], save_dir, ui_cfg)
            logger.info(f"  → {'저장 완료' if ok else '저장 실패'}  {save_dir.name}")
        else:
            logger.warning(f"[{patient_id}] left_panel 미설정 — --setup 다시 하세요.")

        # 목록으로 복귀
        if back_btn:
            pyautogui.click(back_btn[0], back_btn[1])
        else:
            pyautogui.press(back_key)
        time.sleep(delay)

    logger.info(f"[{patient_id}] 완료: {total_studies}개")

    # 다음 환자 준비
    _return_to_search(sx, sy, delay)

    return {"studies": total_studies, "ok": total_studies > 0}


def _return_to_search(sx: int, sy: int, delay: float) -> None:
    pyautogui.click(sx, sy)
    time.sleep(delay * 0.5)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("delete")


# ──────────────────────────────────────────────────────────────
# Setup 마법사  (4단계)
# ──────────────────────────────────────────────────────────────

def _wait_click(prompt: str, timeout: int = 40) -> tuple[int, int]:
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
    print()
    print("━" * 65)
    print("  Infinitt UI 좌표 설정  (--setup)")
    print("━" * 65)
    print()
    print("  Infinitt 클라이언트를 켜두고 안내에 따라 클릭하세요.")
    print()

    pos = {}

    try:
        # STEP 1: 검색창
        print("  [STEP 1/4] 환자번호 검색창")
        pos["search_box"] = list(_wait_click("환자번호를 입력하는 검색창을 클릭하세요"))

        # STEP 2: 스터디 목록 첫 번째 행 + 행 높이 자동 측정
        print()
        print("  [STEP 2/4] 스터디 목록 — 첫 번째 행")
        print("  ※ 아무 환자 검색 후 목록이 보이는 상태에서 첫 번째 행을 클릭하세요.")
        pos["study_row_1"] = list(_wait_click("스터디 목록의 첫 번째 데이터 행을 클릭하세요"))

        # 행 높이 자동 측정: Down 한 번 누르고 UIA로 위치 읽기
        print("    행 높이 자동 측정 중...", end="", flush=True)
        row_height = 25  # 기본값
        try:
            pyautogui.press("down")
            time.sleep(0.4)
            from pywinauto import Desktop
            ctrl = Desktop(backend="uia").get_focus()
            if ctrl:
                rect = ctrl.rectangle()
                y2 = (rect.top + rect.bottom) // 2
                measured = abs(y2 - pos["study_row_1"][1])
                if 10 < measured < 100:
                    row_height = measured
            pyautogui.press("up")
            time.sleep(0.2)
        except Exception:
            pass
        pos["study_row_height"] = row_height
        print(f" {row_height}px")

        # STEP 3: 왼쪽 썸네일 패널
        print()
        print("  [STEP 3/4] 왼쪽 썸네일 패널 (Convert Study)")
        print("  ※ 스터디를 하나 열어서 왼쪽 작은 사진 창이 보이는 상태로 만드세요.")
        print("     우클릭하면 'Convert Study' 메뉴가 뜨는 곳을 클릭하세요.")
        pos["left_panel"] = list(_wait_click("왼쪽 썸네일 패널 위를 클릭하세요"))

        # STEP 4: 뒤로가기
        print()
        print("  [STEP 4/4] 뒤로 가기 버튼")
        print("  스터디에서 목록으로 돌아가는 버튼을 클릭하세요.")
        print("  Esc 키로 돌아간다면 아무 곳이나 클릭 후 config.yaml의 back_key를 escape로 유지.")
        pos["back_button"] = list(_wait_click("뒤로 가기 버튼을 클릭하세요"))

        POSITIONS_FILE.write_text(json.dumps(pos, ensure_ascii=False, indent=2))
        print()
        print(f"  완료: {POSITIONS_FILE.resolve()}")
        print()
        print("  이제 실행:")
        print("    .\\run.bat --excel 환자목록.xlsx")

    except (TimeoutError, KeyboardInterrupt, ValueError) as e:
        print(f"\n  설정 중단: {e}")


def load_positions() -> dict:
    if not POSITIONS_FILE.exists():
        raise FileNotFoundError(
            f"UI 좌표 파일 없음: {POSITIONS_FILE}\n"
            "  먼저  .\\run.bat --setup  을 실행하세요."
        )
    return json.loads(POSITIONS_FILE.read_text())


# ──────────────────────────────────────────────────────────────
# 배치 실행
# ──────────────────────────────────────────────────────────────

def run_batch(patient_ids: list[str], cfg: dict, dirs: dict, resume_from: int = 0) -> None:
    ui_cfg        = cfg.get("ui", {})
    base_save_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    base_save_dir.mkdir(parents=True, exist_ok=True)

    positions     = load_positions()
    progress_file = dirs["base"] / "batch_progress.json"

    done: list[str] = []
    failed: list[str] = []
    if progress_file.exists() and resume_from == 0:
        prev   = json.loads(progress_file.read_text())
        done   = prev.get("done", [])
        failed = prev.get("failed", [])
        if done:
            logger.info(f"이전 진행 복원: {len(done)}명 완료 / {len(failed)}명 실패")

    done_set  = set(done)
    remaining = [p for p in patient_ids if p not in done_set]
    if resume_from:
        remaining = remaining[resume_from:]

    years_back = ui_cfg.get("years_back", 5)

    logger.info("=" * 65)
    logger.info("배치 시작")
    logger.info(f"  전체 환자  : {len(patient_ids)}명")
    logger.info(f"  처리 예정  : {len(remaining)}명")
    logger.info(f"  수집 기간  : 최근 {years_back}년")
    logger.info(f"  저장 폴더  : {base_save_dir}")
    logger.info("  긴급 정지  : 마우스를 화면 왼쪽 위 모서리로 빠르게 이동")
    logger.info("=" * 65)

    total = 0

    for i, pid in enumerate(remaining, 1):
        try:
            logger.info(f"[{i}/{len(remaining)}] 환자: {pid}")
            result = process_one_patient(pid, positions, cfg, base_save_dir)

            if result["ok"]:
                done.append(pid)
                total += result["studies"]
                logger.info(f"  완료: {result['studies']}개 스터디  (누적 {total}건)")
            else:
                failed.append(pid)
                logger.warning("  5년 이내 DS periapical 없음 — 건너뜀")

        except pyautogui.FailSafeException:
            logger.warning("긴급 정지!")
            break
        except Exception as e:
            logger.error(f"[{pid}] 예외: {e}")
            failed.append(pid)
        finally:
            progress_file.write_text(
                json.dumps(
                    {"done": done, "failed": failed, "total": total},
                    ensure_ascii=False, indent=2,
                )
            )

    logger.info("=" * 65)
    logger.info(f"완료  성공: {len(done)}명 / 실패: {len(failed)}명 / 총 {total}건")

    if failed:
        failed_file = dirs["base"] / "failed_patients.txt"
        failed_file.write_text("\n".join(failed), encoding="utf-8")
        logger.info(f"  실패 목록: {failed_file}")
