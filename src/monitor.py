"""Infinitt 클라이언트가 열어보는 DICOM 파일을 실시간으로 감시/수집하는 모듈.

작동 원리:
  Infinitt 클라이언트가 이미지를 화면에 표시하려면 반드시 PC 로컬 디스크의
  임시 폴더에 DICOM 파일을 저장합니다. 이 폴더를 watchdog으로 감시하다가
  새 파일이 생기면 자동으로 복사/변환합니다.
"""
import logging
import os
import shutil
import time
from pathlib import Path

import pydicom
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from dicom_converter import convert_dicom_to_image, deidentify_dicom, build_study_subpath

logger = logging.getLogger(__name__)


def _is_dicom(path: Path) -> bool:
    """파일이 DICOM인지 magic bytes로 확인."""
    try:
        if path.stat().st_size < 132:
            return False
        with open(path, "rb") as f:
            f.seek(128)
            return f.read(4) == b"DICM"
    except Exception:
        return False


def _passes_filter(ds: pydicom.Dataset, cfg: dict) -> bool:
    """설정된 필터 조건(모달리티, 크기)에 맞는 영상인지 확인."""
    filter_cfg = cfg.get("filter", {})

    allowed = filter_cfg.get("allowed_modalities", [])
    if allowed:
        modality = str(getattr(ds, "Modality", "")).upper()
        if modality not in [m.upper() for m in allowed]:
            logger.debug(f"모달리티 필터 제외: {modality}")
            return False

    min_px = filter_cfg.get("min_pixel_size", 100)
    rows = int(getattr(ds, "Rows", 0))
    cols = int(getattr(ds, "Columns", 0))
    if rows < min_px or cols < min_px:
        logger.debug(f"크기 필터 제외: {rows}x{cols}")
        return False

    return True


class DicomFileHandler(FileSystemEventHandler):
    def __init__(self, cfg: dict, dirs: dict, processed_log: Path):
        self.cfg = cfg
        self.dirs = dirs
        self.processed_log = processed_log
        self._processed: set[str] = self._load_processed()
        self.stats = {"collected": 0, "skipped": 0, "error": 0}

    def _load_processed(self) -> set[str]:
        if self.processed_log.exists():
            return set(self.processed_log.read_text(encoding="utf-8").splitlines())
        return set()

    def _mark_processed(self, file_id: str) -> None:
        self._processed.add(file_id)
        with open(self.processed_log, "a", encoding="utf-8") as f:
            f.write(file_id + "\n")

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_new_file(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        self._handle_new_file(Path(event.dest_path))

    def _handle_new_file(self, path: Path) -> None:
        monitor_cfg = self.cfg.get("monitor", {})
        min_size = monitor_cfg.get("min_file_size", 10000)
        settle = monitor_cfg.get("settle_seconds", 2)

        # 파일 쓰기 완료 대기
        time.sleep(settle)

        try:
            if not path.exists():
                return
            if path.stat().st_size < min_size:
                return

            # 중복 체크
            file_id = f"{path}:{path.stat().st_size}"
            if file_id in self._processed:
                return

            # DICOM 확인
            if not _is_dicom(path):
                return

            self._process_dicom(path, file_id)

        except Exception as e:
            logger.debug(f"파일 처리 스킵 [{path.name}]: {e}")

    def _process_dicom(self, src: Path, file_id: str) -> None:
        try:
            ds = pydicom.dcmread(str(src), stop_before_pixels=False)
        except Exception as e:
            logger.debug(f"DICOM 읽기 실패 [{src.name}]: {e}")
            self.stats["error"] += 1
            return

        if not _passes_filter(ds, self.cfg):
            self.stats["skipped"] += 1
            self._mark_processed(file_id)
            return

        output_cfg = self.cfg["output"]
        organize = output_cfg.get("organize_by_patient", True)
        sub = build_study_subpath(ds, include_patient_id=organize)
        fmt = output_cfg.get("image_format", "png")
        quality = output_cfg.get("image_quality", 95)

        modality = getattr(ds, "Modality", "??")
        patient_id = getattr(ds, "PatientID", "unknown")
        study_date = getattr(ds, "StudyDate", "")
        logger.info(f"[{modality}] 수집: {patient_id} {study_date} {src.name}")

        # 비식별화 DICOM 저장
        if output_cfg.get("save_dicom", True):
            dcm_out = self.dirs["dicom"] / f"{sub}.dcm"
            deidentify_dicom(src, dcm_out, self.cfg)

        # 이미지 변환
        if output_cfg.get("save_image", True):
            img_out = self.dirs["images"] / f"{sub}.{fmt}"
            convert_dicom_to_image(src, img_out, fmt, quality)

        self.stats["collected"] += 1
        self._mark_processed(file_id)


def run_monitor(cfg: dict, dirs: dict) -> None:
    """감시 모드 실행. Ctrl+C로 종료합니다."""
    monitor_cfg = cfg.get("monitor", {})
    processed_log = Path(monitor_cfg.get("processed_log", "./output/processed_files.txt"))
    processed_log.parent.mkdir(parents=True, exist_ok=True)

    # 감시할 폴더 목록 결정
    watch_dirs = monitor_cfg.get("watch_dirs", [])
    watch_dirs = [
        d.replace("%USERNAME%", os.environ.get("USERNAME", ""))
        for d in watch_dirs
    ]

    # 실제 존재하는 폴더만 감시
    valid_dirs = [d for d in watch_dirs if Path(d).exists()]

    if not valid_dirs:
        logger.warning(
            "감시할 폴더가 없습니다. Infinitt 클라이언트를 한 번 실행 후 다시 시도하거나,\n"
            "config.yaml의 monitor.watch_dirs를 직접 설정하세요."
        )
        # TEMP 폴더는 항상 감시
        temp = Path(os.environ.get("TEMP", r"C:\Windows\Temp"))
        if temp.exists():
            valid_dirs = [str(temp)]
            logger.info(f"기본 TEMP 폴더 감시: {temp}")

    handler = DicomFileHandler(cfg, dirs, processed_log)
    observer = Observer()

    for watch_dir in valid_dirs:
        observer.schedule(handler, watch_dir, recursive=True)
        logger.info(f"감시 시작: {watch_dir}")

    logger.info("=" * 60)
    logger.info("Infinitt 클라이언트에서 치근단 사진을 열어보세요.")
    logger.info("열어본 IO(구내방사선) 영상이 자동으로 output\\ 폴더에 저장됩니다.")
    logger.info("종료: Ctrl+C")
    logger.info("=" * 60)

    observer.start()
    try:
        while True:
            time.sleep(5)
            if handler.stats["collected"] > 0:
                logger.info(
                    f"진행 상황 — 수집: {handler.stats['collected']}, "
                    f"제외: {handler.stats['skipped']}, "
                    f"오류: {handler.stats['error']}"
                )
    except KeyboardInterrupt:
        logger.info("사용자 종료 요청")
    finally:
        observer.stop()
        observer.join()
        logger.info(
            f"완료 — 최종 수집: {handler.stats['collected']}개, "
            f"저장 위치: {dirs['base']}"
        )
