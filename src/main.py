"""치근단 방사선 사진 자동 수집 도구.

실행 모드:
  python src/main.py                  → config.yaml의 mode 설정에 따라 실행
  python src/main.py --mode monitor   → Infinitt 클라이언트 임시 파일 감시
  python src/main.py --mode dicom     → DICOM 직접 연결 (서버 IP 필요)
  python src/main.py --find-pacs      → PC에서 PACS 서버 설정 자동 탐색
  python src/main.py --convert-only DICOM_DIR  → 기존 DICOM 폴더 이미지 변환
"""
import argparse
import logging
import sys
from pathlib import Path

import pydicom
from tqdm import tqdm

from config import load_config, get_output_dirs
from dicom_converter import convert_dicom_to_image, deidentify_dicom, build_study_subpath

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
    """PACS 설정 자동 탐색 후 결과 출력."""
    try:
        from pacs_scraper import find_pacs_settings
    except ImportError:
        logger.error("pacs_scraper 모듈을 불러올 수 없습니다. Windows에서만 실행 가능합니다.")
        return

    print("\n=== PACS 서버 설정 탐색 중... ===\n")
    result = find_pacs_settings()

    if result.get("host"):
        print(f"[발견] 서버 IP   : {result['host']}")
        print(f"       포트      : {result['port']}")
        print(f"       AE Title : {result['ae_title']}")
        print(f"       탐색 출처: {result['source']}")
        print()
        print("→ config.yaml의 dicom.server 섹션에 위 값을 입력하고")
        print("  mode: dicom 으로 변경 후 실행하세요.")
    else:
        print("[결과] PACS 서버 설정을 자동으로 찾지 못했습니다.")
        print()
        print("다음 방법을 시도해 보세요:")
        print("  1. Infinitt 클라이언트를 실행한 상태에서 다시 시도 (netstat 탐색)")
        print("  2. Infinitt 클라이언트 설정 메뉴에서 직접 확인")
        print("  3. 병원 IT 담당자 또는 방사선사에게 문의")
        print("     - 필요한 정보: 서버 IP, 포트(기본 104), AE Title")

    if result.get("cache_dirs"):
        print()
        print(f"[발견] Infinitt 캐시 폴더 ({len(result['cache_dirs'])}개):")
        for d in result["cache_dirs"]:
            print(f"       {d}")
        print()
        print("→ 이 폴더들이 monitor 모드에서 자동 감시됩니다.")
        print("  config.yaml의 monitor.watch_dirs 에 추가하세요.")


def cmd_monitor(cfg: dict, dirs: dict) -> None:
    """임시 파일 감시 모드 실행."""
    from monitor import run_monitor
    run_monitor(cfg, dirs)


def cmd_dicom(cfg: dict, dirs: dict) -> None:
    """DICOM 직접 연결 모드 실행."""
    from dicom_query import query_studies, retrieve_study
    from dicom_converter import convert_dicom_to_image, deidentify_dicom, build_study_subpath

    dicom_cfg = cfg.get("dicom", {})
    server = dicom_cfg.get("server", {})

    if not server.get("host"):
        logger.error(
            "PACS 서버 IP가 설정되지 않았습니다.\n"
            "  python src/main.py --find-pacs  명령으로 자동 탐색하거나\n"
            "  config.yaml의 dicom.server.host에 직접 입력하세요."
        )
        sys.exit(1)

    studies = query_studies(cfg)
    if not studies:
        logger.warning("검색된 스터디가 없습니다.")
        return

    raw_dir = dirs["dicom"] / "raw"
    fmt = cfg["output"].get("image_format", "png")
    quality = cfg["output"].get("image_quality", 95)
    organize = cfg["output"].get("organize_by_patient", True)

    for study in tqdm(studies, desc="스터디 다운로드"):
        uid = str(getattr(study, "StudyInstanceUID", ""))
        patient_id = str(getattr(study, "PatientID", "unknown"))
        study_date = str(getattr(study, "StudyDate", "00000000"))

        study_dir = raw_dir / patient_id / study_date
        dcm_files = retrieve_study(uid, cfg, study_dir)

        for dcm_path in dcm_files:
            try:
                ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=False)
                sub = build_study_subpath(ds, include_patient_id=organize)

                if cfg["output"].get("save_dicom", True):
                    deidentify_dicom(dcm_path, dirs["dicom"] / f"{sub}.dcm", cfg)

                if cfg["output"].get("save_image", True):
                    convert_dicom_to_image(dcm_path, dirs["images"] / f"{sub}.{fmt}", fmt, quality)

            except Exception as e:
                logger.error(f"처리 오류 [{dcm_path.name}]: {e}")


def cmd_convert_only(dicom_dir: Path, cfg: dict, dirs: dict) -> None:
    """DICOM 폴더 → 이미지 일괄 변환."""
    dcm_files = list(dicom_dir.rglob("*.dcm")) + list(dicom_dir.rglob("*.DCM"))
    logger.info(f"변환 대상: {len(dcm_files)}개")

    fmt = cfg["output"].get("image_format", "png")
    quality = cfg["output"].get("image_quality", 95)
    organize = cfg["output"].get("organize_by_patient", True)
    ok = fail = 0

    for dcm_path in tqdm(dcm_files, desc="변환 중"):
        try:
            ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=False)
            sub = build_study_subpath(ds, include_patient_id=organize)
            if convert_dicom_to_image(dcm_path, dirs["images"] / f"{sub}.{fmt}", fmt, quality):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            logger.warning(f"실패 [{dcm_path.name}]: {e}")
            fail += 1

    logger.info(f"변환 완료 — 성공: {ok}, 실패: {fail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="치근단 방사선 사진 자동 수집 도구")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--mode", choices=["monitor", "dicom"],
                        help="실행 모드 (config.yaml 설정 덮어쓰기)")
    parser.add_argument("--find-pacs", action="store_true",
                        help="PC에서 PACS 서버 설정 자동 탐색")
    parser.add_argument("--convert-only", metavar="DICOM_DIR",
                        help="기존 DICOM 폴더를 이미지로 변환만 실행")
    args = parser.parse_args()

    if args.find_pacs:
        cmd_find_pacs()
        return

    cfg = load_config(args.config)
    dirs = get_output_dirs(cfg)
    setup_file_logging(dirs["logs"])

    if args.convert_only:
        dicom_dir = Path(args.convert_only)
        if not dicom_dir.exists():
            logger.error(f"폴더 없음: {dicom_dir}")
            sys.exit(1)
        cmd_convert_only(dicom_dir, cfg, dirs)
        return

    mode = args.mode or cfg.get("mode", "monitor")

    if mode == "monitor":
        cmd_monitor(cfg, dirs)
    elif mode == "dicom":
        cmd_dicom(cfg, dirs)
    else:
        logger.error(f"알 수 없는 모드: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
