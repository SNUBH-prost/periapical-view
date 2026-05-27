# 치근단 방사선 사진 자동 수집 도구 가이드

## 구조

```
periapical-view/
├── src/
│   ├── main.py              # 진입점
│   ├── pacs_scraper.py      # Infinitt PACS 웹 자동화
│   ├── dicom_converter.py   # DICOM → PNG/JPEG 변환 + 비식별화
│   └── config.py            # 설정 로드
├── config.yaml              # PACS 접속 정보 및 설정
├── requirements.txt
└── install.sh               # 설치 스크립트
```

## 설치

```bash
bash install.sh
```

내부망 환경에서 pip 인터넷이 안 될 경우 → 외부망 PC에서 패키지를 다운로드해서 옮기기:
```bash
# 외부망 PC
pip download -r requirements.txt -d ./packages
playwright install chromium --dry-run  # 브라우저 파일 위치 확인 후 수동 복사

# 내부망 PC
pip install --no-index --find-links=./packages -r requirements.txt
```

## 실행 방법

### 1단계: 셀렉터 탐색 (최초 1회)

Infinitt PACS 버전마다 HTML 구조가 다릅니다. 먼저 실제 UI를 확인하세요:

```bash
source venv/bin/activate
python src/main.py --inspect
```

브라우저가 열리면 F12 개발자 도구로 로그인 폼, 워크리스트 테이블 등의 CSS 셀렉터를 확인하고
`config.yaml`의 `selectors` 섹션을 업데이트합니다.

### 2단계: 소량 테스트

```bash
python src/main.py --limit 5
```

`output/` 폴더에 결과가 저장됩니다.

### 3단계: 전체 수집

```bash
python src/main.py
```

## 출력 구조

```
output/
├── dicom/
│   ├── raw/                 # 원본 DICOM
│   │   └── {환자ID}/{날짜}/
│   └── clean/               # 비식별화된 DICOM
│       └── {환자ID}/{날짜}/
├── images/                  # PNG/JPEG 변환본
│   └── {환자ID}/{날짜}/
└── logs/
    └── run.log
```

## 자주 쓰는 명령

```bash
# 이미 받아둔 DICOM 폴더를 PNG로 변환만 할 때
python src/main.py --convert-only ./output/dicom/raw

# 비식별화 없이 원본 그대로 저장
python src/main.py --no-deidentify

# 날짜 범위 변경: config.yaml의 search.date_from / date_to 수정
```

## config.yaml 주요 설정

| 항목 | 설명 |
|------|------|
| `pacs.url` | PACS 서버 주소 (예: `http://192.168.1.100:8080`) |
| `pacs.login_path` | 로그인 페이지 경로 |
| `search.modality` | `IO` = 구내방사선(치근단), `PX` = 파노라마 |
| `search.date_from/to` | 수집 기간 (YYYYMMDD) |
| `search.max_studies` | 최대 수집 수 (`0` = 전체) |
| `output.image_format` | `png` 또는 `jpeg` |
| `deidentify.enabled` | AI 학습용 비식별화 여부 |
| `browser.headless` | `false` = 브라우저 보이게 실행 (디버깅용) |

## Infinitt PACS 셀렉터 찾는 법

1. `python src/main.py --inspect` 실행 후 브라우저에서 F12
2. 로그인 폼 → `input` 태그의 `name` 속성 확인 → `config.yaml` 수정
3. 워크리스트 테이블 → `tr` 태그의 클래스명 확인

일반적인 Infinitt PACS 셀렉터 예시:
```yaml
selectors:
  login:
    username_field: "input[name='userId']"
    password_field: "input[name='password']"
    submit_button: "button#loginBtn"
  worklist:
    study_rows: "tr.wl-row"
    study_link: "td.td-patientId"
```
