"""Infinitt PACS 설정 자동 탐색 + DICOM 직접 연결 모듈."""
import logging
import subprocess
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

# Infinitt 클라이언트 설치 경로 후보
INFINITT_SEARCH_PATHS = [
    r"C:\Program Files\Infinitt Healthcare",
    r"C:\Program Files (x86)\Infinitt Healthcare",
    r"C:\Infinitt",
    r"C:\ProgramData\Infinitt",
    r"C:\Program Files\INFINITT",
    r"C:\Program Files (x86)\INFINITT",
]

# Infinitt 레지스트리 키 후보
INFINITT_REG_KEYS = [
    r"SOFTWARE\Infinitt Healthcare",
    r"SOFTWARE\INFINITT",
    r"SOFTWARE\WOW6432Node\Infinitt Healthcare",
    r"SOFTWARE\WOW6432Node\INFINITT",
]


def find_pacs_settings() -> dict:
    """PC에서 PACS 서버 설정을 자동으로 탐색합니다."""
    result = {
        "host": None,
        "port": None,
        "ae_title": None,
        "source": None,
        "cache_dirs": [],
    }

    # 1. 레지스트리에서 탐색
    reg_result = _search_registry()
    if reg_result:
        result.update(reg_result)
        result["source"] = "registry"
        logger.info(f"레지스트리에서 PACS 설정 발견: {result}")

    # 2. 설정 파일에서 탐색
    if not result["host"]:
        file_result = _search_config_files()
        if file_result:
            result.update(file_result)
            result["source"] = "config_file"

    # 3. 현재 네트워크 연결에서 탐색 (netstat)
    if not result["host"]:
        netstat_result = _search_netstat()
        if netstat_result:
            result.update(netstat_result)
            result["source"] = "netstat"

    # 4. Infinitt 캐시 폴더 탐색
    result["cache_dirs"] = _find_infinitt_cache_dirs()

    return result


def _search_registry() -> dict | None:
    """Windows 레지스트리에서 Infinitt 설정 탐색."""
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in INFINITT_REG_KEYS:
            try:
                key = winreg.OpenKey(root, key_path)
                result = _extract_from_reg_key(key)
                winreg.CloseKey(key)
                if result:
                    return result
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.debug(f"레지스트리 탐색 오류 [{key_path}]: {e}")
    return None


def _extract_from_reg_key(key) -> dict | None:
    host, port, ae = None, None, None
    try:
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                name_lower = name.lower()
                value_str = str(value).strip()
                if any(k in name_lower for k in ("server", "host", "ip", "address")):
                    if _looks_like_ip(value_str) or _looks_like_hostname(value_str):
                        host = value_str
                elif any(k in name_lower for k in ("port",)):
                    try:
                        port = int(value_str)
                    except ValueError:
                        pass
                elif any(k in name_lower for k in ("ae", "aetitle", "ae_title")):
                    ae = value_str
                i += 1
            except OSError:
                break
    except Exception:
        pass

    if host:
        return {"host": host, "port": port or 104, "ae_title": ae or "INFINITT"}
    return None


def _search_config_files() -> dict | None:
    """Infinitt 설치 폴더의 설정 파일 탐색."""
    import re
    ip_pattern = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
    port_pattern = re.compile(r"[Pp]ort[\"'\s:=]+(\d{2,5})")
    ae_pattern = re.compile(r"[Aa][Ee][\w]*[\"'\s:=]+([A-Z0-9_\-]{1,16})")

    for base in INFINITT_SEARCH_PATHS:
        base_path = Path(base)
        if not base_path.exists():
            continue
        for ext in ("*.ini", "*.xml", "*.cfg", "*.config", "*.json", "*.properties"):
            for f in base_path.rglob(ext):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    ips = ip_pattern.findall(text)
                    private_ips = [
                        ip for ip in ips
                        if (ip.startswith("192.168.") or
                            ip.startswith("10.") or
                            ip.startswith("172."))
    ]
                    if private_ips:
                        host = private_ips[0]
                        port_match = port_pattern.search(text)
                        ae_match = ae_pattern.search(text)
                        logger.info(f"설정 파일 발견: {f}")
                        return {
                            "host": host,
                            "port": int(port_match.group(1)) if port_match else 104,
                            "ae_title": ae_match.group(1) if ae_match else "INFINITT",
                        }
                except Exception:
                    continue
    return None


def _search_netstat() -> dict | None:
    """현재 네트워크 연결에서 DICOM 포트(104, 11112, 2762) 탐색."""
    dicom_ports = {104, 11112, 2762, 4104, 4242}
    try:
        out = subprocess.check_output(
            ["netstat", "-n"], capture_output=False, timeout=10, text=True
        )
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            if "ESTABLISHED" not in line and "CLOSE_WAIT" not in line:
                continue
            remote = parts[2] if len(parts) > 2 else ""
            if ":" in remote:
                ip, port_str = remote.rsplit(":", 1)
                try:
                    port = int(port_str)
                    if port in dicom_ports and _looks_like_ip(ip):
                        logger.info(f"netstat에서 DICOM 연결 발견: {ip}:{port}")
                        return {"host": ip, "port": port, "ae_title": "INFINITT"}
                except ValueError:
                    continue
    except Exception as e:
        logger.debug(f"netstat 탐색 실패: {e}")
    return None


def _find_infinitt_cache_dirs() -> list[str]:
    """Infinitt 클라이언트가 임시 파일을 저장하는 폴더를 탐색."""
    import os
    candidates = []

    # 환경 변수 기반 경로
    user_profile = os.environ.get("USERPROFILE", r"C:\Users\Default")
    candidates.extend([
        Path(user_profile) / "AppData" / "Local" / "Temp",
        Path(user_profile) / "AppData" / "Local" / "Infinitt",
        Path(user_profile) / "AppData" / "Roaming" / "Infinitt",
        Path("C:/ProgramData/Infinitt"),
        Path("C:/Infinitt/Cache"),
        Path("C:/Infinitt/Temp"),
    ])

    # 실제 존재하는 폴더만 반환
    existing = [str(p) for p in candidates if p.exists()]
    logger.info(f"발견된 Infinitt 캐시 폴더 ({len(existing)}개): {existing}")
    return existing


def _looks_like_ip(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _looks_like_hostname(s: str) -> bool:
    return bool(s) and " " not in s and len(s) < 64 and not s.startswith("0")
