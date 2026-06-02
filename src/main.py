"""치근단 방사선 사진 자동 수집 도구.

실행 모드:
  python src/main.py --check                  → 설정 점검 (Infinitt 없이 안전하게 검증)
  python src/main.py --setup                  → Infinitt UI 좌표 기록 (배치 전 1회)
  python src/main.py --excel 환자목록.xlsx    → 배치: 엑셀 환자 280명 자동 수집
  python src/main.py --mode ui                → Infinitt 우클릭 자동화 + F9 단축키
  python src/main.py --mode monitor           → 임시 파일 폴더 실시간 감시
  python src/main.py --mode dicom             → DICOM 직접 연결 (서버 IP 필요)
  python src/main.py --find-pacs              → PC에서 PACS 서버 설정 자동 탐색
  python src/main.py --convert-only DIR       → 기존 파일 이미지 변환
"""
import argparse
import logging
import sys
from pathlib import Path

from config import load_config, get_output_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def setup_file_logging(log_dir: Path) -> None:
    log_file = log_dir / "run.log"
    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(handler)


def cmd_find_pacs() -> None:
    try:
        from pacs_scraper import find_pacs_settings
    except Exception as e:
        print(f"[오류] {e}")
        print("Windows 환경에서만 실행 가능합니다.")
        return

    print("\n=== PACS 서버 설정 탐색 중... ===\n")
    result = find_pacs_settings()

    if result.get("host"):
        print(f"  서버 IP   : {result['host']}")
        print(f"  포트      : {result['port']}")
        print(f"  AE Title : {result['ae_title']}")
        print(f"  탐색 출처: {result['source']}")
        print()
        print("→ config.yaml의 dicom.server 섹션에 위 값을 입력하고")
        print("  mode: dicom 으로 변경 후 run.bat 을 실행하세요.")
    else:
        print("[결과] PACS 설정을 자동으로 찾지 못했습니다.")
        _print_it_questions()

    if result.get("cache_dirs"):
        print(f"\nInfinitt 캐시 폴더 발견 ({len(result['cache_dirs'])}개):")
        for d in result["cache_dirs"]:
            print(f"  {d}")


def _print_it_questions() -> None:
    print()
    print("━" * 60)
    print("  정보팀에 문의할 내용 (아래 그대로 전달하세요)")
    print("━" * 60)
    print()
    print("  안녕하세요, 연구 목적으로 PACS에서 치근단 방사선 영상을")
    print("  Python 스크립트로 자동 수집하려고 합니다.")
    print("  아래 정보를 알 수 있을까요?")
    print()
    print("  1. PACS 서버 IP 주소")
    print("  2. DICOM 서비스 포트 번호 (보통 104)")
    print("  3. PACS AE Title")
    print("  4. 외부 DICOM SCU(C-FIND/C-MOVE)가 허용되어 있는지 여부")
    print()
    print("━" * 60)


def cmd_ui(cfg: dict, dirs: dict) -> None:
    from infinitt_ui import run_ui_mode
    from monitor import run_monitor
    import threading

    # UI 자동화 + 임시 파일 감시를 동시에 실행
    # 임시 파일 감시: 별도 스레드 (Infinitt가 저장한 파일 자동 처리)
    monitor_thread = threading.Thread(
        target=run_monitor, args=(cfg, dirs), daemon=True
    )
    monitor_thread.start()

    # UI 자동화: 메인 스레드 (단축키 + 화면 변화 감지)
    run_ui_mode(cfg, dirs)


def cmd_monitor(cfg: dict, dirs: dict) -> None:
    from monitor import run_monitor
    run_monitor(cfg, dirs)


def cmd_dicom(cfg: dict, dirs: dict) -> None:
    import pydicom
    from tqdm import tqdm
    from dicom_query import query_studies, retrieve_study
    from dicom_converter import convert_dicom_to_image, deidentify_dicom, build_study_subpath

    server = cfg.get("dicom", {}).get("server", {})
    if not server.get("host"):
        logger.error(
            "PACS 서버 IP가 없습니다.\n"
            "  run.bat --find-pacs  로 자동 탐색하거나\n"
            "  config.yaml의 dicom.server.host에 직접 입력하세요."
        )
        _print_it_questions()
        sys.exit(1)

    studies = query_studies(cfg)
    if not studies:
        logger.warning("검색된 스터디가 없습니다.")
        return

    raw_dir = dirs["dicom"] / "raw"
    fmt = cfg["output"].get("image_format", "png")
    quality = cfg["output"].get("image_quality", 95)
    organize = cfg["output"].get("organize_by_patient", True)

    for study in tqdm(studies, desc="다운로드"):
        uid = str(getattr(study, "StudyInstanceUID", ""))
        patient_id = str(getattr(study, "PatientID", "unknown"))
        study_date = str(getattr(study, "StudyDate", "00000000"))
        study_dir = raw_dir / patient_id / study_date

        for dcm_path in retrieve_study(uid, cfg, study_dir):
            try:
                ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=False)
                sub = build_study_subpath(ds, include_patient_id=organize)
                if cfg["output"].get("save_dicom"):
                    deidentify_dicom(dcm_path, dirs["dicom"] / f"{sub}.dcm", cfg)
                if cfg["output"].get("save_image"):
                    convert_dicom_to_image(
                        dcm_path, dirs["images"] / f"{sub}.{fmt}", fmt, quality
                    )
            except Exception as e:
                logger.error(f"처리 오류 [{dcm_path.name}]: {e}")


def cmd_convert_only(dicom_dir: Path, cfg: dict, dirs: dict) -> None:
    import pydicom
    from tqdm import tqdm
    from dicom_converter import convert_dicom_to_image, build_study_subpath

    all_files = (
        list(dicom_dir.rglob("*.dcm"))
        + list(dicom_dir.rglob("*.DCM"))
        + list(dicom_dir.rglob("*.jpg"))
        + list(dicom_dir.rglob("*.jpeg"))
        + list(dicom_dir.rglob("*.png"))
    )
    logger.info(f"변환 대상: {len(all_files)}개")

    fmt = cfg["output"].get("image_format", "png")
    quality = cfg["output"].get("image_quality", 95)
    ok = fail = 0

    for f in tqdm(all_files, desc="변환"):
        try:
            if f.suffix.lower() in (".dcm", ""):
                ds = pydicom.dcmread(str(f), stop_before_pixels=False)
                sub = build_study_subpath(ds, include_patient_id=True)
                out = dirs["images"] / f"{sub}.{fmt}"
                ok += 1 if convert_dicom_to_image(f, out, fmt, quality) else 0
            else:
                out = dirs["images"] / f.name
                out.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(f, out)
                ok += 1
        except Exception as e:
            logger.warning(f"실패 [{f.name}]: {e}")
            fail += 1

    logger.info(f"변환 완료 — 성공: {ok}, 실패: {fail}")


def cmd_batch(excel_path: str, cfg: dict, dirs: dict, resume_from: int = 0) -> None:
    from excel_reader import read_patient_ids
    from infinitt_batch import run_batch

    patient_ids = read_patient_ids(excel_path)
    logger.info(f"엑셀 로드 완료: {len(patient_ids)}명 ({excel_path})")
    run_batch(patient_ids, cfg, dirs, resume_from=resume_from)


def cmd_check(args, cfg: dict, dirs: dict) -> None:
    """Infinitt 없이 설정·환경을 점검. 배치 실행 전 안전 확인용."""
    print()
    print("=" * 60)
    print("  설정 점검 (--check)")
    print("=" * 60)

    ok = True

    # 1) 필수 패키지 확인
    print("\n[1] 필수 패키지 확인")
    for mod, label in [
        ("openpyxl", "엑셀 읽기"),
        ("pyautogui", "마우스/키보드 자동화"),
        ("pynput", "좌표 기록/단축키"),
        ("win32gui", "Windows 창 제어"),
        ("pywinauto", "메뉴/대화상자 자동화"),
        ("PIL", "이미지 처리"),
    ]:
        try:
            __import__(mod)
            print(f"    OK   {mod:12s} ({label})")
        except ImportError:
            print(f"    없음 {mod:12s} ({label}) → install.bat을 다시 실행하세요")
            ok = False

    # 2) 설정 파일 확인
    print("\n[2] config.yaml 확인")
    ui = cfg.get("ui", {})
    print(f"    저장 폴더        : {ui.get('infinitt_save_dir', '(미설정)')}")
    print(f"    최대 스터디/환자 : {ui.get('max_studies_per_patient', 20)}")
    print(f"    검색 후 대기     : {ui.get('wait_after_search', 2.0)}초")
    print(f"    스터디 열기 후 대기: {ui.get('wait_after_open', 3.0)}초")
    print(f"    저장 메뉴 후보   : {ui.get('save_menu_items', [])}")

    # 3) UI 좌표 파일 확인 (패키지 없이 직접 JSON 읽기 → 절대 안 죽음)
    print("\n[3] UI 좌표 기록 확인 (ui_positions.json)")
    import json
    pos_file = Path("./ui_positions.json")
    if pos_file.exists():
        try:
            pos = json.loads(pos_file.read_text())
            required = {"search_box": "검색창", "study_row_1": "목록 첫 행", "left_panel": "왼쪽 패널", "back_button": "뒤로가기"}
            for key, label in required.items():
                if pos.get(key):
                    print(f"    OK   {label:12s}: {pos[key]}")
                else:
                    print(f"    없음 {label:12s}: run.bat --setup 을 다시 하세요.")
                    ok = False
            print(f"    OK   행 높이      : {pos.get('study_row_height', '(자동측정 안됨)')}px")
        except Exception as e:
            print(f"    오류: ui_positions.json을 읽을 수 없습니다 ({e})")
            ok = False
    else:
        print("    없음: 아직 좌표를 기록하지 않았습니다.")
        print("          run.bat --setup 을 먼저 실행하세요.")
        ok = False

    # 4) 엑셀 파일 확인 (지정된 경우)
    if args.excel:
        print(f"\n[4] 엑셀 파일 확인: {args.excel}")
        try:
            from excel_reader import read_patient_ids
            ids = read_patient_ids(args.excel)
            print(f"    OK   환자 {len(ids)}명 읽음")
            print(f"         처음 5명: {ids[:5]}")
        except Exception as e:
            print(f"    오류: {e}")
            ok = False

    # 5) Infinitt 창 확인 (Windows에서만, 패키지 없으면 건너뜀)
    print("\n[5] Infinitt 실행 여부")
    title = cfg.get("ui", {}).get("window_title_contains", "Infinitt")
    try:
        from infinitt_batch import _bring_to_front
        if _bring_to_front(title):
            print(f"    OK   '{title}' 창을 찾았습니다.")
        else:
            print(f"    없음: '{title}' 창을 찾지 못했습니다. (Infinitt를 켜세요)")
    except Exception as e:
        print(f"    건너뜀 (Windows 아님 또는 패키지 미설치): {type(e).__name__}")

    print("\n" + "=" * 60)
    if ok:
        print("  점검 통과 — 배치를 실행할 수 있습니다:")
        print("    run.bat --excel 환자목록.xlsx")
    else:
        print("  일부 항목에 문제가 있습니다. 위의 '없음/오류'를 해결하세요.")
    print("=" * 60)


def _run(args) -> None:
    """실제 작업 수행 (예외는 main에서 처리)."""
    if args.setup:
        from infinitt_batch import run_setup
        run_setup()
        return

    if args.find_pacs:
        cmd_find_pacs()
        return

    cfg = load_config(args.config)
    dirs = get_output_dirs(cfg)
    setup_file_logging(dirs["logs"])

    if args.check:
        cmd_check(args, cfg, dirs)
        return

    if args.excel:
        cmd_batch(args.excel, cfg, dirs, resume_from=args.resume)
        return

    if args.convert_only:
        src = Path(args.convert_only)
        if not src.exists():
            logger.error(f"폴더 없음: {src}")
            sys.exit(1)
        cmd_convert_only(src, cfg, dirs)
        return

    mode = args.mode or cfg.get("mode", "ui")
    {"ui": cmd_ui, "monitor": cmd_monitor, "dicom": cmd_dicom}[mode](cfg, dirs)


def main() -> None:
    parser = argparse.ArgumentParser(description="치근단 방사선 사진 자동 수집 도구")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--mode", choices=["ui", "monitor", "dicom"])
    parser.add_argument("--check", action="store_true", help="설정 점검 (Infinitt 없이 검증)")
    parser.add_argument("--setup", action="store_true", help="Infinitt UI 좌표 기록 (배치 전 1회 실행)")
    parser.add_argument("--excel", metavar="FILE", help="환자번호 엑셀 파일로 배치 수집")
    parser.add_argument("--resume", type=int, default=0, metavar="N", help="N번째 환자부터 재시작")
    parser.add_argument("--find-pacs", action="store_true", help="PACS 서버 설정 자동 탐색")
    parser.add_argument("--convert-only", metavar="DIR", help="파일 이미지 변환만 실행")
    args = parser.parse_args()

    try:
        _run(args)
    except KeyboardInterrupt:
        print("\n사용자가 중단했습니다.")
    except Exception as e:
        # 창이 즉시 닫히지 않도록 에러를 보여주고 대기
        import traceback
        print("\n" + "!" * 60)
        print("  오류가 발생했습니다:")
        print(f"    {type(e).__name__}: {e}")
        print("!" * 60)
        print("\n[상세 내용]")
        traceback.print_exc()
        print()
        try:
            input("Enter 키를 누르면 종료합니다... ")
        except EOFError:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
