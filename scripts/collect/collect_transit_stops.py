"""Official transit downloads / TAGO pagination / local CSV fallback. Never logs keys."""
import argparse
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
SEOUL = {
    "버스": ("OA-15067", "58", "1", "transit-seoul-bus-20260902.xlsx"),
    "지하철": ("OA-22534", "1", "2", "transit-seoul-subway-20250814.csv"),
}
TAGO = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService"

def store(payload, target, metadata):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != payload:
        raise ValueError("기존 원본과 다릅니다. 새 --output 경로를 사용하세요.")
    if not target.exists():
        with target.open("xb") as f:
            f.write(payload)
    meta = target.with_suffix(target.suffix + ".source.json")
    if not meta.exists():
        with meta.open("x", encoding="utf-8") as f:
            json.dump({**metadata, "sha256": hashlib.sha256(payload).hexdigest(),
                       "collected_at": datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False, indent=2)
    return target

def collect(city, kind="버스", local=None, output=None):
    load_dotenv(ROOT / ".env")
    if local:
        target = Path(output) if output else RAW / ("transit-" + city + "-local" + Path(local).suffix)
        return store(Path(local).read_bytes(), target,
                     {"city": city, "type": kind, "method": "local_import",
                      "source_url": None, "note": "공식 출처를 별도 문서/sidecar로 확인해야 합니다."})
    if city == "seoul":
        dataset, seq, infseq, filename = SEOUL[kind]
        url = f"https://data.seoul.go.kr/dataList/{dataset}/F/1/datasetView.do"
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.post("https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false",
                data={"infId": dataset, "seq": seq, "seqNo": "", "infSeq": infseq},
                headers={"Referer": url})
            if response.status_code != 200 or response.content.lstrip().startswith(b"<"):
                raise RuntimeError("공식 파일 다운로드 실패. 공식 페이지에서 CSV/XLSX를 받아 --local로 지정하세요.")
        return store(response.content, output or RAW / filename,
                     {"city": city, "type": kind, "source_url": url, "method": "official_download",
                      "dataset": dataset, "seq": seq, "inf_seq": infseq,
                      "reference_date": "2026-09-02" if kind == "버스" else "2025-08-14"})
    if kind != "버스":
        raise ValueError("대전/세종 지하철 수집기는 없습니다. 공식 파일 --local을 사용하세요.")
    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        raise ValueError("DATA_GO_KR_API_KEY 미설정: TAGO 활용신청 후 .env 설정 또는 --local CSV 사용")
    with httpx.Client(timeout=40) as client:
        def request(operation, **params):
            try:
                r = client.get(TAGO + "/" + operation, params={"serviceKey": unquote(key), "_type": "json", **params})
                body = r.json()["response"]
                if r.status_code != 200 or str(body["header"]["resultCode"]) not in {"00", "0"}:
                    raise ValueError()
                return body["body"]
            except Exception:
                # HTTP exceptions can contain the serviceKey URL; never forward them.
                raise RuntimeError("TAGO 인증/응답 오류: 활용신청·쿼터·서비스 상태를 확인하세요.") from None
        cities = request("getCtyCodeList")["items"]["item"]
        if isinstance(cities, dict):
            cities = [cities]
        label = "대전" if city == "daejeon" else "세종"
        codes = [x["citycode"] for x in cities if label in x["cityname"]]
        if len(codes) != 1:
            raise ValueError("TAGO 공식 도시코드를 유일하게 확인하지 못했습니다.")
        rows = []
        for page in range(1, 1001):
            body = request("getSttnNoList", cityCode=codes[0], pageNo=page, numOfRows=1000)
            item = (body.get("items") or {}).get("item", [])
            if isinstance(item, dict):
                item = [item]
            rows.extend(item)
            if len(rows) >= int(body["totalCount"]):
                break
            if not item:
                raise ValueError("TAGO 불완전 페이지: 원본 저장을 중단합니다.")
        else:
            raise ValueError("TAGO 페이지 제한 초과")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["nodeid", "nodenm", "gpslati", "gpslong"], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return store(buf.getvalue().encode("utf-8"), output or RAW / f"transit-{city}-tago.csv",
                 {"city": city, "type": "버스", "method": "official_api",
                  "source_url": "https://www.data.go.kr/data/15098534/openapi.do"})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, choices=["seoul", "daejeon", "sejong"])
    parser.add_argument("--type", default="버스", choices=["버스", "지하철"])
    parser.add_argument("--local")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        print(collect(args.city, args.type, args.local, args.output))
    except (ValueError, RuntimeError, httpx.HTTPError) as error:
        print(str(error) if not isinstance(error, httpx.HTTPError) else "공식 사이트 연결 실패: --local을 사용하세요.")
        raise SystemExit(1)
