"""설정 로딩 및 출력 폴더 구성."""
import yaml
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"설정 파일을 찾을 수 없습니다: {config_path}\n"
            "  프로그램 폴더 안에서 실행했는지 확인하세요."
        )
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"config.yaml 형식이 올바르지 않습니다: {config_path}")
    return cfg


def get_output_dirs(cfg: dict) -> dict:
    """출력 폴더를 생성하고 경로 딕셔너리를 반환. 키 누락에 안전하게 동작."""
    output = cfg.get("output", {}) or {}
    base = Path(output.get("base_dir", "./output"))
    dirs = {
        "base": base,
        "dicom": base / output.get("dicom_dir", "dicom"),
        "images": base / output.get("image_dir", "images"),
        "logs": base / "logs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs
