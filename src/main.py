"""치근단 방사선 사진 자동 수집 메인 스크립트.

사용법:
  python src/main.py [options]

옵션:
  --config PATH       설정 파일 경로 (기본값: config.yaml)
  --inspect           PACS UI 셀렉터 디버깅용 대화형 탐색 모드
  --convert-only DIR  이미 다운로드된 DICOM 폴더를 이미지로만 변환
  --no-deidentify     비식별화 건너뛰기
  --limit N           처리할 최대 스터디 수
"""
import argparse
import logging
import sys
from pathlib import Path

import pydicom
from tqdm import tqdm

from config import load_config, get_output_dirs
from dicom_converter import convert_dicom_to_image, deidentify_dicom, build_study_subpath
from pacs_scraper import InfinittPACSScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def setup_file_logging(log_dir: Path) -> None:
    log_file = log_dir / "run.log"
    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(handler)
    logger.info(f"로그 파일: {log_file}")


def convert_dicom_folder(
    dicom_dir: Path,
    image_dir: Path,
    cfg: dict,
    deidentify: bool = True,
) -> None:
    """이미 다운로드된 DICOM 폴더를 이미지로 변환하는 독립 실행 모드."""
    dcm_files = list(dicom_dir.rglob("*.dcm")) + list(dicom_dir.rglob("*.DCM"))
    logger.info(f"변환 대상 DICOM 파일: {len(dcm_files)}개")

    fmt = cfg["output"].get("image_format", "png")
    quality = cfg["output"].get("image_quality", 95)
    organize = cfg["output"].get("organize_by_patient", True)

    ok, fail = 0, 0
    for dcm_path in tqdm(dcm_files, desc="변환 중"):
        try:
            ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=False)
            sub = build_study_subpath(ds, include_patient_id=organize)
            out_img = image_dir / f"{sub}.{fmt}"

            if convert_dicom_to_image(dcm_path, out_img, fmt, quality):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            logger.warning(f"처리 실패 [{dcm_path.name}]: {e}")
            fail += 1

    logger.info(f"변환 완료 — 성공: {ok}, 실패: {fail}")


def run_scraper(cfg: dict, dirs: dict, inspect_mode: bool, no_deidentify: bool) -> None:
    """PACS 스크래퍼 실행."""
    output_cfg = cfg["output"]
    fmt = output_cfg.get("image_format", "png")
    quality = output_cfg.get("image_quality", 95)
    organize = output_cfg.get("organize_by_patient", True)

    raw_dicom_dir = dirs["dicom"] / "raw"
    clean_dicom_dir = dirs["dicom"] / "clean"
    raw_dicom_dir.mkdir(parents=True, exist_ok=True)
    clean_dicom_dir.mkdir(parents=True, exist_ok=True)

    stats = {"downloaded": 0, "converted": 0, "failed": 0}

    with InfinittPACSScraper(cfg) as scraper:
        scraper.login()

        if inspect_mode:
            scraper.interactive_inspect()
            return

        scraper.navigate_to_worklist()
        scraper.set_search_filters()

        study_count = scraper.get_study_count()
        logger.info(f"검색된 스터디 수: {study_count}")

        for study in tqdm(scraper.iter_studies(), total=study_count, desc="스터디 수집"):
            patient_id = study.get("patient_id", "unknown")
            study_date = study.get("study_date", "00000000")

            study_raw_dir = raw_dicom_dir / patient_id / study_date
            study_raw_dir.mkdir(parents=True, exist_ok=True)

            dcm_files = scraper.download_study_dicom(study, study_raw_dir)
            if not dcm_files:
                logger.warning(f"다운로드 파일 없음 [{patient_id}]")
                stats["failed"] += 1
                continue

            stats["downloaded"] += len(dcm_files)

            for dcm_path in dcm_files:
                try:
                    ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=False)
                    sub = build_study_subpath(ds, include_patient_id=organize)

                    # 비식별화 DICOM 저장
                    if output_cfg.get("save_dicom", True) and not no_deidentify:
                        clean_path = clean_dicom_dir / f"{sub}.dcm"
                        deidentify_dicom(dcm_path, clean_path, cfg)

                    # 이미지 변환
                    if output_cfg.get("save_image", True):
                        img_path = dirs["images"] / f"{sub}.{fmt}"
                        if convert_dicom_to_image(dcm_path, img_path, fmt, quality):
                            stats["converted"] += 1

                except Exception as e:
                    logger.error(f"처리 오류 [{dcm_path.name}]: {e}")
                    stats["failed"] += 1

    logger.info(
        f"완료 — 다운로드: {stats['downloaded']}, "
        f"변환: {stats['converted']}, "
        f"실패: {stats['failed']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="치근단 방사선 사진 자동 수집 도구")
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    parser.add_argument("--inspect", action="store_true", help="PACS UI 탐색 모드")
    parser.add_argument("--convert-only", metavar="DICOM_DIR", help="DICOM 폴더 → 이미지 변환만 실행")
    parser.add_argument("--no-deidentify", action="store_true", help="비식별화 건너뛰기")
    parser.add_argument("--limit", type=int, help="최대 스터디 수 (config 값 덮어쓰기)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dirs = get_output_dirs(cfg)
    setup_file_logging(dirs["logs"])

    if args.limit is not None:
        cfg["search"]["max_studies"] = args.limit

    if args.convert_only:
        dicom_dir = Path(args.convert_only)
        if not dicom_dir.exists():
            logger.error(f"DICOM 디렉토리 없음: {dicom_dir}")
            sys.exit(1)
        convert_dicom_folder(dicom_dir, dirs["images"], cfg, not args.no_deidentify)
    else:
        run_scraper(cfg, dirs, inspect_mode=args.inspect, no_deidentify=args.no_deidentify)


if __name__ == "__main__":
    main()
