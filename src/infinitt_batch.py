"""Infinitt 배치 자동화.

흐름 (환자 1명):
  1. 환자번호 검색
  2. 검사명 컬럼 클릭 → 정렬
  3. 목록 전체 스캔 (스크롤) → "periapical" 행만, 5년 이내만 수집
  4. 각 행 더블클릭 → 이미지 저장 → 목록으로 복귀
  5. 다음 환자 검색창으로 이동

저장 구조:
  infinitt_export/{patient_id}/{patient_id}(YYYY-MM-DD)/  ← Convert Study가 여기에 저장
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
    """N년 전 날짜를 YYYYMMDD 문자열로 반환."""
    cutoff = datetime.date.today() - datetime.timedelta(days=years_back * 365)
    return cutoff.strftime("%Y%m%d")


def _yyyymmdd_to_dash(yyyymmdd: str) -> str:
    """YYYYMMDD → YYYY-MM-DD. 형식이 안 맞으면 원본 반환."""
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
    return yyyymmdd


def _parse_date_to_yyyymmdd(text: str) -> str:
    """텍스트에서 날짜를 추출해 YYYYMMDD 반환. 실패 시 빈 문자열."""
    patterns = [
        (r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', "YMD"),   # 2024-01-15
        (r'(\d{4})(\d{2})(\d{2})',                 "YMD"),   # 20240115
        (r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})',  "DMY"),   # 15/01/2024
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
# 스터디 목록 읽기 (pywinauto UIA)
# ──────────────────────────────────────────────────────────────

def _read_visible_rows(title_contains: str) -> list[dict]:
    """
    pywinauto UIA로 현재 화면에 보이는 스터디 목록 행을 읽는다.
    반환: [{"text": "...", "date": "YYYYMMDD", "cx": x, "cy": y}, ...]
    """
    from pywinauto import Desktop

    rows = []
    try:
        desktop = Desktop(backend="uia")
        for win in desktop.windows():
            if title_contains.lower() not in win.window_text().lower():
                continue
            for ctrl_type in ("DataGrid", "Table", "List", "ListView", "Custom"):
                try:
                    container = win.child_window(control_type=ctrl_type)
                    for item in container.children():
                        try:
                            # 행 안의 모든 셀 텍스트 합치기
                            children = item.children()
                            if children:
                                row_text = "  ".join(
                                    c.window_text() for c in children if c.window_text().strip()
                                )
                            else:
                                row_text = item.window_text()

                            if not row_text.strip():
                                continue

                            rect = item.rectangle()
                            cy = (rect.top + rect.bottom) // 2
                            cx = (rect.left + rect.right) // 2
                            rows.append({
                                "text": row_text,
                                "date": _parse_date_to_yyyymmdd(row_text),
                                "cx": cx,
                                "cy": cy,
                            })
                        except Exception:
                            continue

                    if rows:
                        return rows
                except Exception:
                    continue
            break
    except Exception as e:
        logger.debug(f"UIA 읽기 실패: {e}")

    return rows


def _scroll_and_collect_periapical_rows(
    title_contains: str,
    positions: dict,
    ui_cfg: dict,
) -> list[dict]:
    """
    검사명 정렬 후 목록을 끝까지 스크롤하며 키워드에 맞는 행을 모두 수집.
    수집 후 5년 날짜 필터를 적용해 반환한다.

    주의: 검사명 정렬 시 날짜가 섞이므로 날짜 기준 조기 종료를 하지 않는다.
    """
    keywords   = ui_cfg.get("study_name_filter", ["DS periapical view (implant)"])
    years_back = ui_cfg.get("years_back", 5)
    max_scroll = ui_cfg.get("max_scroll_pages", 30)
    delay      = ui_cfg.get("action_delay", 0.6)
    cutoff     = _cutoff_date(years_back)

    list_cx = positions["study_row_1"][0]
    list_cy = positions["study_row_1"][1]

    # 목록 맨 위로
    pyautogui.click(list_cx, list_cy)
    pyautogui.hotkey("ctrl", "home")
    time.sleep(delay)

    all_keyword_rows: list[dict] = []
    seen: set[str] = set()

    for page in range(max_scroll + 1):
        visible = _read_visible_rows(title_contains)

        new_this_page = 0
        for row in visible:
            key = row["text"][:80]
            if key in seen:
                continue
            seen.add(key)
            new_this_page += 1

            text_lower = row["text"].lower()
            if any(kw.lower() in text_lower for kw in keywords):
                all_keyword_rows.append(row)
                logger.debug(f"  키워드 일치: {row['text'][:60]}  날짜={row['date']}")

        # 새로 보이는 행이 없으면 목록 끝
        if page > 0 and new_this_page == 0:
            logger.debug(f"  목록 끝 (page {page})")
            break

        pyautogui.click(list_cx, list_cy)
        pyautogui.press("pagedown")
        time.sleep(delay)

    # 날짜 필터: 5년 이내만, 최신순 정렬
    in_period = [
        r for r in all_keyword_rows
        if r["date"] >= cutoff or not r["date"]   # 날짜 미상은 일단 포함
    ]
    in_period.sort(key=lambda r: r["date"], reverse=True)   # 최신순

    logger.info(
        f"  DS periapical view (implant) 전체 {len(all_keyword_rows)}개 발견 "
        f"→ 5년 이내 {len(in_period)}개"
    )
    return in_period


# ──────────────────────────────────────────────────────────────
# 이미지 저장 — Convert Study (왼쪽 패널 우클릭)
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
    """저장 대화상자에서 경로를 입력하고 저장 버튼을 누른다."""
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
                pyautogui.press("enter")   # 덮어쓰기 확인
                return True
    except Exception as e:
        logger.debug(f"저장 대화상자 처리 실패: {e}")
    return True


def _convert_study(lx: int, ly: int, save_dir: Path, ui_cfg: dict) -> bool:
    """왼쪽 패널 우클릭 → Convert Study → 저장 대화상자 처리."""
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
    1. 환자번호 검색
    2. 검사명 컬럼으로 정렬
    3. 스크롤하며 periapical + 5년 이내 행 수집
    4. 각 행 열기 → 이미지 저장 → 목록 복귀
    5. 검색창으로 커서 이동 (다음 환자 준비)
    """
    ui_cfg     = cfg.get("ui", {})
    delay      = ui_cfg.get("action_delay", 0.6)
    wait_search = ui_cfg.get("wait_after_search", 2.0)
    wait_open  = ui_cfg.get("wait_after_open", 3.0)
    back_key   = ui_cfg.get("back_key", "escape")
    title      = ui_cfg.get("window_title_contains", "Infinitt")
    ext        = ui_cfg.get("save_extension", "png").lstrip(".")

    left_panel  = positions.get("left_panel")
    back_btn    = positions.get("back_button")
    sort_header = positions.get("sort_column_header")
    sx, sy      = positions["search_box"]

    if not _bring_to_front(title):
        logger.warning(f"[{patient_id}] Infinitt 창 없음")
        return {"studies": 0, "images": 0, "ok": False}

    time.sleep(delay)

    # ① 환자번호 검색
    pyautogui.click(sx, sy)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(patient_id, interval=0.05)
    pyautogui.press("enter")
    time.sleep(wait_search)

    # ② 검사명 컬럼 클릭 → 정렬
    if sort_header:
        pyautogui.click(sort_header[0], sort_header[1])
        time.sleep(delay * 2)
        logger.debug(f"[{patient_id}] 검사명 정렬 완료")
    else:
        logger.warning(f"[{patient_id}] sort_column_header 미설정 → 정렬 건너뜀. --setup 을 다시 하세요.")

    # ③ 목록 스캔 → periapical 행 수집
    target_rows = _scroll_and_collect_periapical_rows(title, positions, ui_cfg)

    if not target_rows:
        logger.info(f"[{patient_id}] periapical 스터디 없음 (기간 내)")
        _return_to_search(sx, sy, delay)
        return {"studies": 0, "images": 0, "ok": False}

    # ④ 각 행 열기 → 저장 → 복귀
    total_images = 0
    total_studies = 0

    for study_num, row in enumerate(target_rows, 1):
        try:
            row_date = row["date"] or "unknown"
            logger.info(f"[{patient_id}] study {study_num}/{len(target_rows)}  날짜={row_date}")

            # 행 더블클릭으로 스터디 열기
            pyautogui.doubleClick(row["cx"], row["cy"])
            time.sleep(wait_open)

            # 왼쪽 패널 우클릭 → Convert Study → 날짜 폴더에 저장
            date_dash = _yyyymmdd_to_dash(row_date)
            save_dir = base_save_dir / patient_id / f"{patient_id}({date_dash})"
            ok = False
            if left_panel:
                ok = _convert_study(left_panel[0], left_panel[1], save_dir, ui_cfg)
            else:
                logger.warning(f"[{patient_id}] left_panel 미설정 — --setup 을 다시 하세요.")

            total_studies += 1
            if ok:
                total_images += 1   # Convert Study는 한 번에 전체 저장
            logger.info(f"  → {'저장 완료' if ok else '저장 실패'}  ({save_dir})")

            # 목록으로 복귀
            if back_btn:
                pyautogui.click(back_btn[0], back_btn[1])
            else:
                pyautogui.press(back_key)
            time.sleep(delay)

        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logger.warning(f"[{patient_id}] study {study_num} 오류: {e}")
            # 안전하게 목록으로 복귀 시도
            try:
                pyautogui.press(back_key)
                time.sleep(delay)
            except Exception:
                pass

    # ⑤ 검색창으로 커서 이동 (다음 환자 준비)
    _return_to_search(sx, sy, delay)

    return {
        "studies": total_studies,
        "images":  total_images,
        "ok":      total_studies > 0,
    }


def _return_to_search(sx: int, sy: int, delay: float) -> None:
    """검색창 클릭 후 내용 지우기 — 다음 환자 검색 준비."""
    pyautogui.click(sx, sy)
    time.sleep(delay * 0.5)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("delete")


# ──────────────────────────────────────────────────────────────
# Setup 마법사
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
        print("  [STEP 1/6] 환자번호 검색창")
        pos["search_box"] = list(_wait_click("환자번호를 입력하는 검색창을 클릭하세요"))

        # STEP 2: 검사명 컬럼 헤더
        print()
        print("  [STEP 2/6] '검사명' 컬럼 헤더")
        print("  ※ 아무 환자로 검색해서 스터디 목록이 보이는 상태로 만드세요.")
        pos["sort_column_header"] = list(_wait_click("검사명 컬럼 헤더를 클릭하세요 (정렬에 사용)"))

        # STEP 3: 스터디 목록 첫 번째 행
        print()
        print("  [STEP 3/6] 스터디 목록 — 첫 번째 행")
        pos["study_row_1"] = list(_wait_click("스터디 목록의 첫 번째 데이터 행을 클릭하세요"))

        # STEP 4: 스터디 목록 두 번째 행 (행 높이 계산)
        print()
        print("  [STEP 4/6] 스터디 목록 — 두 번째 행")
        pos["study_row_2"] = list(_wait_click("스터디 목록의 두 번째 행을 클릭하세요"))
        row_height = abs(pos["study_row_2"][1] - pos["study_row_1"][1])
        pos["study_row_height"] = row_height
        print(f"    → 행 높이 자동 계산: {row_height}px")

        # STEP 5: 왼쪽 패널 (Convert Study 우클릭 위치)
        print()
        print("  [STEP 5/6] 왼쪽 썸네일 패널")
        print("  ※ 스터디를 하나 열어서 왼쪽 작은 사진 창이 보이는 상태로 만드세요.")
        print("     이 위치를 우클릭하면 'Convert Study' 메뉴가 뜨는 곳입니다.")
        pos["left_panel"] = list(_wait_click("왼쪽 썸네일 패널 위를 클릭하세요"))
        print(f"    → 왼쪽 패널 위치 기록 완료")

        # STEP 6: 뒤로가기
        print()
        print("  [STEP 6/6] 뒤로 가기 버튼")
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
    ui_cfg       = cfg.get("ui", {})
    base_save_dir = Path(ui_cfg.get("infinitt_save_dir", r"C:\infinitt_export"))
    base_save_dir.mkdir(parents=True, exist_ok=True)

    positions    = load_positions()
    progress_file = dirs["base"] / "batch_progress.json"

    done: list[str] = []
    failed: list[str] = []
    if progress_file.exists() and resume_from == 0:
        prev  = json.loads(progress_file.read_text())
        done  = prev.get("done", [])
        failed = prev.get("failed", [])
        if done:
            logger.info(f"이전 진행 복원: {len(done)}명 완료 / {len(failed)}명 실패")

    done_set  = set(done)
    remaining = [p for p in patient_ids if p not in done_set]
    if resume_from:
        remaining = remaining[resume_from:]

    keywords   = ui_cfg.get("study_name_filter", ["DS periapical view (implant)"])
    years_back = ui_cfg.get("years_back", 5)

    logger.info("=" * 65)
    logger.info("배치 시작")
    logger.info(f"  전체 환자    : {len(patient_ids)}명")
    logger.info(f"  처리 예정    : {len(remaining)}명")
    logger.info(f"  검색 키워드  : {keywords}")
    logger.info(f"  수집 기간    : 최근 {years_back}년")
    logger.info(f"  저장 폴더    : {base_save_dir}")
    logger.info("  긴급 정지    : 마우스를 화면 왼쪽 위 모서리로 빠르게 이동")
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
                    f"  완료: {result['studies']}개 스터디 / {result['images']}장"
                    f"  (누적 {total_images}장)"
                )
            else:
                failed.append(pid)
                logger.warning("  해당 기간 내 periapical 스터디 없음 — 건너뜀")

        except pyautogui.FailSafeException:
            logger.warning("긴급 정지!")
            break
        except Exception as e:
            logger.error(f"[{pid}] 예외: {e}")
            failed.append(pid)
        finally:
            progress_file.write_text(
                json.dumps(
                    {"done": done, "failed": failed, "total_images": total_images},
                    ensure_ascii=False, indent=2,
                )
            )

    logger.info("=" * 65)
    logger.info(f"완료  성공: {len(done)}명 / 실패: {len(failed)}명 / 총 이미지: {total_images}장")

    if failed:
        failed_file = dirs["base"] / "failed_patients.txt"
        failed_file.write_text("\n".join(failed), encoding="utf-8")
        logger.info(f"  실패 목록: {failed_file}")
