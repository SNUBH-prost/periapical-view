import yaml
from pathlib import Path


def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_output_dirs(cfg: dict) -> dict:
    base = Path(cfg["output"]["base_dir"])
    dirs = {
        "base": base,
        "dicom": base / cfg["output"]["dicom_dir"],
        "images": base / cfg["output"]["image_dir"],
        "logs": base / "logs",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs
