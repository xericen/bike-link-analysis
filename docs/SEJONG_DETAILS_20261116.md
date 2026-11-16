# 세종 상세 자료 실제 확보 — 2026-11-16
공식 출처 https://www.data.go.kr/data/15106191/fileData.do 의 공개 다운로드를 확인했다. CAPTCHA 요구가 없는 공식 경로로 ZIP 약230MiB·24개 분기 CSV를 확보했다. API 인증 우회 없음. 공식 설명의 전체 기간은2020~2025이며 이번 최초 서비스 적용은 **2025-10-01~31만**이다.
HWP2개 본문을 실제 추출했고 (1) 버전에서15106191 URL을 확인했다. 원문 텍스트는 ignored data/raw/hwp-extracted, 해시·성공 여부는 [추출 기록](transit/hwp-extraction-20261116.json)에 남겼다. 시각적 서식과 그림은 자동 재현하지 않았다.

2025년4분기 원본654,432행 중 선택10월259,143행, 유효259,143건, source순번 중복0·잘못된Trip0. 실제728개 출발/도착 ID, 일별OD199,042행을 기존 SQLite에 연결했다. 기존 서울·대전 DB/마스터는 sejong_archive에 보관한 뒤 새 파일로 교체했다. [검증 JSON](transit/sejong-details-20261116.json).
CSV 스키마: 순번,자전거고유번호,시작 대여소,대여시간,반납 대여소,반납시간,주행거리,주행시간,환승 유무 (CP949).
SJ_와SJ- 식별자를 임의로 합치지 않았다. 원본 코드만 station_id로 보존하고 station_name·위경도·용량은 null이다. 실제 이력·일별/시간대 추이는 제공하지만 대여소 지도와 정류장 거리는N/A다. 원본의 '환승 유무'는 정의를 검증하지 않아 실제 환승률로 사용하지 않았다.
HWP의653,764행/10월258,498건과 이번 원본 건수는 다르다. 원본 버전·필터 근거 없이 강제로 맞추지 않는다. 보고서 수치를 서비스 결과로 복사하지 않았다.
전체 도시는 기존 서울·대전의2026-10 공통 기간을 유지한다. 세종2025-10은 도시 선택으로 별도 조회하며2026년 자료와 합산하지 않는다.

```bash
python -m scripts.collect.collect_sejong_details
python -m scripts.preprocess.normalize_sejong_details --zip data/raw/sejong-details-15106191.zip --start 2025-10-01 --end 2025-10-31 --report docs/transit/sejong-details-20261116.json
```
최초 적용 스크립트는 한 분기 안의 명시 기간만 허용하며 기존 세종 상세 자료를 덮어쓰지 않는다. 전체6년을 처리 완료했다고 보고하지 않는다.

HWP 추출 선택 의존성은 `python -m pip install olefile`로 준비한다. `python scripts/validate/extract_uploaded_hwp.py --help`의 입력/출력 옵션을 사용한다. 이름 마스터가 없는 세종의 이름 기반 후보 유형은 평가 대상이 제한되므로 후보 수0을 도시 전체에 그런 현상이 없다는 뜻으로 해석하지 않는다.
