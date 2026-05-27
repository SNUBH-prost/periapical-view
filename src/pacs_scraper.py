"""Infinitt PACS 웹 UI 자동화 스크래퍼.

Playwright를 사용해 Infinitt PACS 워크리스트에서 치근단(IO) 영상을 탐색하고
DICOM 파일을 다운로드합니다.

주의: PACS UI 셀렉터는 설치 버전에 따라 다를 수 있습니다.
      config.yaml의 selectors 섹션을 실제 PACS에 맞게 조정하세요.
"""
import logging
import time
from pathlib import Path
from typing import Iterator
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright

logger = logging.getLogger(__name__)


class InfinittPACSScraper:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pacs = cfg["pacs"]
        self.search = cfg["search"]
        self.sel = cfg["selectors"]
        self.browser_cfg = cfg["browser"]
        self._page: Page | None = None
        self._browser = None
        self._pw = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.browser_cfg.get("headless", False),
            slow_mo=self.browser_cfg.get("slow_mo", 100),
            args=["--no-sandbox", "--disable-web-security"],
        )
        context = self._browser.new_context(
            accept_downloads=True,
            ignore_https_errors=True,
        )
        self._page = context.new_page()
        self._page.set_default_timeout(self.browser_cfg.get("timeout", 30000))
        return self

    def __exit__(self, *args):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ──────────────────────────────────────────────
    # 로그인
    # ──────────────────────────────────────────────

    def login(self) -> None:
        base = self.pacs["url"]
        login_url = urljoin(base, self.pacs["login_path"])
        logger.info(f"PACS 로그인 중: {login_url}")

        self._page.goto(login_url)
        self._page.wait_for_load_state("networkidle")

        s = self.sel["login"]
        self._page.fill(s["username_field"], self.pacs["username"])
        self._page.fill(s["password_field"], self.pacs["password"])
        self._page.click(s["submit_button"])
        self._page.wait_for_load_state("networkidle")
        logger.info("로그인 완료")

    # ──────────────────────────────────────────────
    # 워크리스트 검색
    # ──────────────────────────────────────────────

    def navigate_to_worklist(self) -> None:
        base = self.pacs["url"]
        wl_url = urljoin(base, self.pacs["worklist_path"])
        self._page.goto(wl_url)
        self._page.wait_for_load_state("networkidle")

    def set_search_filters(self) -> None:
        s = self.sel["worklist"]
        modality = self.search.get("modality", "IO")
        date_from = self.search.get("date_from", "")
        date_to = self.search.get("date_to", "")

        # 모달리티 선택
        if self._page.locator(s["modality_select"]).count() > 0:
            self._page.select_option(s["modality_select"], modality)
            logger.debug(f"모달리티 필터 설정: {modality}")

        # 날짜 범위 설정
        if date_from and self._page.locator(s["date_from_field"]).count() > 0:
            self._page.fill(s["date_from_field"], date_from)
        if date_to and self._page.locator(s["date_to_field"]).count() > 0:
            self._page.fill(s["date_to_field"], date_to)

        # 검색 실행
        self._page.click(s["search_button"])
        self._page.wait_for_load_state("networkidle")
        logger.info("워크리스트 검색 완료")

    def get_study_count(self) -> int:
        rows = self._page.locator(self.sel["worklist"]["study_rows"])
        return rows.count()

    # ──────────────────────────────────────────────
    # 스터디별 DICOM 다운로드
    # ──────────────────────────────────────────────

    def iter_studies(self) -> Iterator[dict]:
        """워크리스트의 각 스터디 정보를 순회."""
        s = self.sel["worklist"]
        rows = self._page.locator(s["study_rows"])
        count = rows.count()
        max_studies = self.search.get("max_studies", 0)
        if max_studies > 0:
            count = min(count, max_studies)

        logger.info(f"총 {count}개 스터디 처리 예정")

        for i in range(count):
            row = rows.nth(i)
            try:
                patient_id = self._extract_cell_text(row, "patientId")
                study_date = self._extract_cell_text(row, "studyDate")
                study_uid = self._extract_cell_text(row, "studyUID")
                yield {
                    "index": i,
                    "patient_id": patient_id,
                    "study_date": study_date,
                    "study_uid": study_uid,
                    "row_locator": row,
                }
            except Exception as e:
                logger.warning(f"스터디 {i} 정보 추출 실패: {e}")
                continue

    def _extract_cell_text(self, row, data_attr: str) -> str:
        cell = row.locator(f"td[data-col='{data_attr}']")
        if cell.count() > 0:
            return cell.first.inner_text().strip()
        return ""

    def download_study_dicom(self, study: dict, download_dir: Path) -> list[Path]:
        """스터디를 클릭하고 DICOM 파일을 다운로드."""
        downloaded = []
        s = self.sel["worklist"]

        try:
            # 스터디 행 클릭 → 뷰어 열기
            link = study["row_locator"].locator(s["study_link"])
            if link.count() == 0:
                study["row_locator"].dbl_click()
            else:
                link.first.click()

            self._page.wait_for_load_state("networkidle")
            time.sleep(1)

            downloaded = self._try_export_dicom(download_dir, study)

        except Exception as e:
            logger.error(f"스터디 다운로드 실패 [{study.get('patient_id')}]: {e}")

        return downloaded

    def _try_export_dicom(self, download_dir: Path, study: dict) -> list[Path]:
        """PACS 뷰어에서 DICOM 내보내기 시도."""
        downloaded = []
        sel = self.sel["viewer"]

        # 방법 1: 내보내기 메뉴 버튼 클릭
        export_btn = self._page.locator(sel["export_menu"])
        if export_btn.count() > 0:
            export_btn.first.click()
            time.sleep(0.5)

            download_link = self._page.locator(sel["download_dicom"])
            if download_link.count() > 0:
                timeout = self.browser_cfg.get("download_timeout", 60000)
                with self._page.expect_download(timeout=timeout) as dl_info:
                    download_link.first.click()
                download = dl_info.value
                dest = download_dir / (download.suggested_filename or f"{study.get('study_uid', 'study')}.dcm")
                download.save_as(str(dest))
                downloaded.append(dest)
                logger.info(f"다운로드 완료: {dest.name}")
                return downloaded

        # 방법 2: 네트워크에서 WADO URL 가로채기
        wado_files = self._intercept_wado_downloads(download_dir, study)
        downloaded.extend(wado_files)

        return downloaded

    def _intercept_wado_downloads(self, download_dir: Path, study: dict) -> list[Path]:
        """WADO 요청을 가로채서 DICOM 파일 수동 다운로드."""
        import requests

        downloaded = []
        base_url = self.pacs["url"]
        study_uid = study.get("study_uid", "")

        if not study_uid:
            return downloaded

        # 일반적인 WADO URL 패턴 시도
        wado_patterns = [
            f"{base_url}/wado?requestType=WADO&studyUID={study_uid}",
            f"{base_url}/wado/rs/studies/{study_uid}",
            f"{base_url}/infinitt/wado?studyUID={study_uid}",
        ]

        # 현재 페이지 쿠키를 requests 세션에 전달
        cookies = {c["name"]: c["value"] for c in self._page.context.cookies()}

        for pattern in wado_patterns:
            try:
                resp = requests.get(
                    pattern,
                    cookies=cookies,
                    timeout=30,
                    verify=False,
                )
                if resp.status_code == 200 and resp.content:
                    dest = download_dir / f"{study_uid}.dcm"
                    dest.write_bytes(resp.content)
                    downloaded.append(dest)
                    logger.info(f"WADO 다운로드 완료: {dest.name}")
                    break
            except Exception:
                continue

        return downloaded

    # ──────────────────────────────────────────────
    # 대화형 탐색 모드 (셀렉터 디버깅용)
    # ──────────────────────────────────────────────

    def interactive_inspect(self) -> None:
        """헤드리스 모드 OFF 상태에서 페이지 구조를 탐색."""
        logger.info("대화형 탐색 모드. 브라우저 창을 직접 조작하세요.")
        logger.info("엔터를 눌러 현재 페이지 URL과 주요 요소를 출력합니다. 'q' + 엔터로 종료.")
        while True:
            cmd = input(">> ").strip()
            if cmd == "q":
                break
            print(f"URL: {self._page.url}")
            # 테이블/폼 요소 탐색
            for tag in ["table", "input", "select", "button", "a"]:
                els = self._page.locator(tag)
                print(f"  <{tag}> count: {els.count()}")
