# Bike Link Analysis

서울·대전·세종·부산 공공자전거 자료를 지역별 확보 범위에 맞춰 보여주는 React + FastAPI 분석 서비스입니다. 기존 1단계 합성 샘플은 별도 **Demo Mode**에서만 사용합니다.

## 현재 연결된 실제 자료

| 지역 | 확보 범위 | 분석 가능 기능 |
|---|---|---|
| 서울 따릉이 | 2026-10-25·29 대여소별 OD 시간 집계, 2026-06 대여소 위치 목록 | 시간대·주말 패턴, K-means, 코사인 유사도, OD 네트워크·중심성, 위치 목록 지도 |
| 대전 타슈 | 2026-06-24 대여소 목록, 2025-12~2026-10 대여이력 ZIP 중 2026-10-25·29 Trip 50,765건 | 시간대·주말 패턴, K-means, 코사인 유사도, Trip 기반 OD·중심성, 실제 좌표 지도 |
| 세종 어울링 | 2017~2025 연간 이용 건수, 2026-08-31 부분 누계 | 연간 총량 조회 |
| 부산 | 시청의 17개소 운영 현황 메타데이터 | 운영 구조·자료 미확보 안내 |

상세 출처·컬럼·라이선스·제약은 [DATA_SOURCES.md](docs/DATA_SOURCES.md), 공통 형식은 [data-contract.md](docs/data-contract.md)를 참고하세요. 서울 2026 OD는 **개별 Trip이 아닌 집계**이며, 위치 목록의 번호와 OD의 ST-ID는 연결하지 않습니다. 대전은 실제 Trip에서 OD를 집계합니다. 두 지역 분석은 공통의 불연속 2일에 한정됩니다.

## 실행

Python 3.11+와 Node.js 20+ 기준입니다. 프로젝트 디렉터리에서:

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
.venv/bin/python -m scripts.collect.collect_all
.venv/bin/python -m scripts.preprocess.normalize
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서:

```bash
cd frontend
npm install
npm run dev
```

Vite 개발 서버는 `/api`를 FastAPI로 프록시합니다. 지역별 수집기는 각각 `python -m scripts.collect.collect_seoul`, `python -m scripts.collect.collect_daejeon`, `python -m scripts.collect.collect_sejong`, `python -m scripts.collect.collect_busan`으로 실행할 수 있습니다. 서울의 특정 원본만 가져올 때는 예를 들어 `python -m scripts.collect.collect_seoul --dataset seoul-od-20261029`를 사용합니다. 파일을 직접 받은 경우 `--dataset <source_id> --file <같은 형식의 파일 경로>`로 가져온 뒤 정규화를 실행합니다. 대전·세종의 공식 자동변환 OpenAPI는 `DATA_GO_KR_API_KEY`를 `.env`에 설정한 뒤 수집기에 `--api`를 주어 호출할 수 있습니다. 인증키가 없어 실제 API 응답은 미검증이며 API 원본은 분석에 자동 연결하지 않습니다.

화면의 **로컬 CSV 업로드** 또는 `POST /api/regions/{region_id}/upload`로 정규화 CSV를 올릴 수 있습니다. `kind=stations|station_usage|od_daily|trips`, `dataset_name`, `file`이 필요합니다. 대여소를 먼저 올리고 이용·OD 자료를 올리세요. 업로드 파일은 스키마만 검증하며 공식 출처·라이선스를 자동 확인하지 않습니다.

## 분석과 API

K-means는 시간대 비율·이용량·주말 비율을 StandardScaler로 정규화하고 Elbow와 Silhouette 지표를 반환합니다. OD가 있을 때만 방향 그래프에서 PageRank·가중 입출차수·표본 매개 중심성·약한 연결요소를 계산합니다. 코사인 유사도는 정규화 패턴을 비교하고 절대 이용량을 별도로 표시합니다. 수치가 없는 지표는 N/A로 남깁니다.

`GET /api/regions`, `/api/regions/{region_id}/{overview|stations|clusters|network|centrality|similarity}`, `/api/compare`, `/api/data-sources`, `/api/data-quality`를 제공합니다. 지역 API와 비교 API는 `date_start`, `date_end`를 지원합니다. `POST /api/agent/chat`은 `UPSTAGE_API_KEY`가 있을 때 Solar를 호출하며 실제 분석 도구 결과를 근거로 사용합니다. 키가 없으면 503을 반환합니다. 실제 Solar 응답은 아직 검증하지 않았습니다.

합성 샘플 API는 명시적인 `/api/demo/*` 아래에 있습니다. 원본·처리 파일은 Git에서 제외되며 배포 환경에서는 수집/정규화를 다시 실행하거나 별도 저장소를 연결해야 합니다.

## 검증

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend && npm run build
```
