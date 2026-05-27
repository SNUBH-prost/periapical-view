"""pynetdicom을 이용한 DICOM C-FIND / C-MOVE 직접 연결 모듈.

서버 IP와 AE Title을 알고 있을 때 사용합니다.
모를 경우 monitor.py (임시 파일 감시 방식) 를 사용하세요.
"""
import logging
from pathlib import Path

from pynetdicom import AE, evt, StoragePresentationContexts
from pynetdicom.sop_class import (
    StudyRootQueryRetrieveInformationModelFind,
    StudyRootQueryRetrieveInformationModelMove,
    ModalityWorklistInformationFind,
)
from pydicom.dataset import Dataset

logger = logging.getLogger(__name__)


def query_studies(cfg: dict) -> list[Dataset]:
    """C-FIND로 치근단(IO) 스터디 목록 조회."""
    dicom_cfg = cfg["dicom"]
    server = dicom_cfg["server"]

    ae = AE(ae_title=dicom_cfg.get("calling_ae_title", "PERIAPICAL_SCU"))
    ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)

    identifier = Dataset()
    identifier.QueryRetrieveLevel = "STUDY"
    identifier.Modality = dicom_cfg["search"].get("modality", "IO")
    identifier.PatientID = ""
    identifier.StudyDate = _format_date_range(
        dicom_cfg["search"].get("date_from", ""),
        dicom_cfg["search"].get("date_to", ""),
    )
    identifier.StudyInstanceUID = ""
    identifier.StudyDescription = ""
    identifier.NumberOfStudyRelatedInstances = ""

    studies = []
    try:
        assoc = ae.associate(
            server["host"],
            int(server.get("port", 104)),
            ae_title=server.get("ae_title", "INFINITT"),
        )
        if not assoc.is_established:
            logger.error("PACS 서버 연결 실패. IP/포트/AE Title을 확인하세요.")
            return []

        responses = assoc.send_c_find(
            identifier,
            StudyRootQueryRetrieveInformationModelFind,
        )
        for status, dataset in responses:
            if status and status.Status in (0xFF00, 0xFF01) and dataset:
                studies.append(dataset)

        assoc.release()
        logger.info(f"C-FIND 결과: {len(studies)}개 스터디")

    except Exception as e:
        logger.error(f"C-FIND 오류: {e}")

    return studies


def retrieve_study(study_uid: str, cfg: dict, output_dir: Path) -> list[Path]:
    """C-MOVE로 스터디 다운로드."""
    dicom_cfg = cfg["dicom"]
    server = dicom_cfg["server"]
    calling_ae = dicom_cfg.get("calling_ae_title", "PERIAPICAL_SCU")

    received_files: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    def handle_store(event):
        ds = event.dataset
        ds.file_meta = event.file_meta
        fname = f"{ds.SOPInstanceUID}.dcm"
        dest = output_dir / fname
        ds.save_as(str(dest), write_like_original=False)
        received_files.append(dest)
        return 0x0000

    handlers = [(evt.EVT_C_STORE, handle_store)]
    ae = AE(ae_title=calling_ae)
    ae.supported_contexts = StoragePresentationContexts
    ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)

    identifier = Dataset()
    identifier.QueryRetrieveLevel = "STUDY"
    identifier.StudyInstanceUID = study_uid

    try:
        assoc = ae.associate(
            server["host"],
            int(server.get("port", 104)),
            ae_title=server.get("ae_title", "INFINITT"),
            evt_handlers=handlers,
        )
        if not assoc.is_established:
            logger.error(f"연결 실패 [study={study_uid}]")
            return []

        responses = assoc.send_c_move(
            identifier,
            calling_ae,
            StudyRootQueryRetrieveInformationModelMove,
        )
        for status, _ in responses:
            if status:
                logger.debug(f"C-MOVE 상태: 0x{status.Status:04X}")

        assoc.release()
        logger.info(f"C-MOVE 완료: {len(received_files)}개 파일 [{study_uid}]")

    except Exception as e:
        logger.error(f"C-MOVE 오류 [{study_uid}]: {e}")

    return received_files


def _format_date_range(date_from: str, date_to: str) -> str:
    if date_from and date_to:
        return f"{date_from}-{date_to}"
    if date_from:
        return f"{date_from}-"
    if date_to:
        return f"-{date_to}"
    return ""
