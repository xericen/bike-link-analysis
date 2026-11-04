import logging
from scripts.collect.common import collect, setup_logging
from scripts.collect.sources import SEOUL, DAEJEON, SEJONG

if __name__ == "__main__":
    setup_logging()
    failures = []
    for source in SEOUL + DAEJEON + SEJONG:
        try:
            collect(source)
        except Exception as exc:
            logging.error("%s: %s", source["source_id"], exc)
            failures.append(source["source_id"])
    print("부산: 공식 통합 이용 데이터 미확보")
    if failures:
        raise SystemExit(f"수집 실패: {', '.join(failures)}")
