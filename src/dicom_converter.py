"""DICOM 파일을 PNG/JPEG로 변환하고 비식별화를 수행하는 모듈."""
import hashlib
import logging
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

logger = logging.getLogger(__name__)


def convert_dicom_to_image(
    dcm_path: Path,
    out_path: Path,
    image_format: str = "png",
    quality: int = 95,
) -> bool:
    """DICOM 파일을 PNG 또는 JPEG로 변환."""
    try:
        ds = pydicom.dcmread(str(dcm_path))

        if not hasattr(ds, "PixelData"):
            logger.warning(f"픽셀 데이터 없음: {dcm_path}")
            return False

        arr = ds.pixel_array.astype(np.float32)

        # 치근단 영상은 보통 8bit 또는 16bit grayscale
        arr_min, arr_max = arr.min(), arr.max()
        if arr_max > arr_min:
            arr = (arr - arr_min) / (arr_max - arr_min) * 255.0
        arr = arr.astype(np.uint8)

        # Photometric Interpretation 반전 처리 (MONOCHROME1 = 밝을수록 어둠)
        photometric = getattr(ds, "PhotometricInterpretation", "MONOCHROME2")
        if photometric == "MONOCHROME1":
            arr = 255 - arr

        img = Image.fromarray(arr)
        if img.mode != "L":
            img = img.convert("L")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if image_format.lower() == "jpeg":
            img.save(str(out_path), format="JPEG", quality=quality)
        else:
            img.save(str(out_path), format="PNG")

        return True

    except Exception as e:
        logger.error(f"DICOM 변환 실패 [{dcm_path}]: {e}")
        return False


def deidentify_dicom(dcm_path: Path, out_path: Path, cfg: dict) -> bool:
    """환자 식별 정보 제거 후 저장."""
    try:
        ds = pydicom.dcmread(str(dcm_path))
        deidentify_cfg = cfg.get("deidentify", {})

        if not deidentify_cfg.get("enabled", True):
            import shutil
            shutil.copy2(str(dcm_path), str(out_path))
            return True

        for tag_name in deidentify_cfg.get("remove_tags", []):
            if hasattr(ds, tag_name):
                setattr(ds, tag_name, "")

        if deidentify_cfg.get("anonymize_patient_id", True):
            original_id = str(getattr(ds, "PatientID", "unknown"))
            ds.PatientID = hashlib.sha256(original_id.encode()).hexdigest()[:16]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        ds.save_as(str(out_path))
        return True

    except Exception as e:
        logger.error(f"비식별화 실패 [{dcm_path}]: {e}")
        return False


def build_study_subpath(ds: pydicom.Dataset, include_patient_id: bool = True) -> Path:
    """스터디별 저장 경로를 생성."""
    patient_id = str(getattr(ds, "PatientID", "unknown"))
    study_date = str(getattr(ds, "StudyDate", "00000000"))
    series_num = str(getattr(ds, "SeriesNumber", "0")).zfill(3)
    instance_num = str(getattr(ds, "InstanceNumber", "0")).zfill(4)

    if include_patient_id:
        return Path(patient_id) / study_date / f"s{series_num}_i{instance_num}"
    return Path(study_date) / f"s{series_num}_i{instance_num}"
