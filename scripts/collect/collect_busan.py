"""부산은 여러 운영기관의 단일 공식 이용 원본이 확인되지 않았다."""
import argparse
from scripts.collect.common import RAW, cli

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="운영기관에서 받은 CSV (현재 자동 스키마 매핑 없음)")
    args = parser.parse_args()
    if args.file:
        raise SystemExit("부산 자료의 제공기관·컬럼을 검증한 뒤 수집 프로필을 추가해야 합니다.")
    print("UNAVAILABLE: 부산 통합 공공자전거 이용 데이터의 공식 다운로드/API를 확인하지 못했습니다.")
