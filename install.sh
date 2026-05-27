#!/bin/bash
# 치근단 방사선 사진 수집 도구 설치 스크립트
# 내부망 PC에서 실행하세요

set -e

echo "=== 치근단 방사선 사진 수집 도구 설치 ==="

# Python 3.10+ 확인
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python 버전: $python_version"

# 가상환경 생성
if [ ! -d "venv" ]; then
    echo "가상환경 생성 중..."
    python3 -m venv venv
fi

# 가상환경 활성화
source venv/bin/activate

# 의존성 설치
echo "패키지 설치 중..."
pip install --upgrade pip
pip install -r requirements.txt

# Playwright 브라우저 설치 (Chromium)
echo "Playwright Chromium 브라우저 설치 중..."
playwright install chromium

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "다음 단계:"
echo "1. config.yaml 에서 PACS 접속 정보를 설정하세요"
echo "   - pacs.url: PACS 서버 주소 (예: http://192.168.1.100:8080)"
echo "   - pacs.username / password: 접속 계정"
echo ""
echo "2. 셀렉터 탐색 (처음 실행 시 권장):"
echo "   source venv/bin/activate"
echo "   python src/main.py --inspect"
echo ""
echo "3. 소량 테스트:"
echo "   python src/main.py --limit 5"
echo ""
echo "4. 전체 수집:"
echo "   python src/main.py"
