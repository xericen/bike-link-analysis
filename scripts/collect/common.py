"""Official download and local import helpers. No URL is inferred from a catalog page."""
import argparse
import csv
import fcntl
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from shutil import copyfileobj

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
load_dotenv(ROOT / ".env")
LOG = logging.getLogger("bike.collect")


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_stream(stream, target: Path):
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    try:
        with tmp.open("wb") as output:
            copyfileobj(stream, output, length=1024 * 1024)
        if tmp.stat().st_size == 0:
            raise ValueError("빈 파일입니다.")
        if target.exists() and fingerprint(target) == fingerprint(tmp):
            tmp.unlink()
            LOG.info("중복 파일 유지: %s", target.name)
        else:
            tmp.replace(target)
            LOG.info("저장: %s (%s bytes)", target.name, target.stat().st_size)
    finally:
        tmp.unlink(missing_ok=True)


def record(target: Path, source: dict, method: str):
    """Serialize updates so independently run city collectors retain every source."""
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "manifest.json"
    lock_path = RAW / "manifest.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            sha = fingerprint(target)
            previous = manifest.get(target.name, {})
            if method == "existing_file" and previous.get("sha256") == sha and previous.get("verified_download"):
                method = "official_download"
                collected_at = previous["collected_at"]
            else:
                collected_at = datetime.now(timezone.utc).isoformat()
            manifest[target.name] = {
                "source_id": source["source_id"], "region_id": source["region_id"],
                "dataset_name": source["dataset_name"], "source_url": source["source_url"],
                "method": method, "sha256": sha,
                "collected_at": collected_at,
                "verified_download": method in {"official_download", "official_api"},
            }
            temporary = manifest_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(manifest_path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def collect(source: dict, local: str | None = None):
    target = RAW / source["filename"]
    if local:
        path = Path(local).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() not in {".csv", ".zip", ".xlsx"}:
            raise ValueError("CSV, ZIP, XLSX만 가져올 수 있습니다.")
        if path.suffix.lower() != target.suffix.lower():
            raise ValueError(f"이 데이터셋에는 {target.suffix} 파일이 필요합니다.")
        with path.open("rb") as stream:
            save_stream(stream, target)
        method = "local_import"
    elif target.exists():
        LOG.info("기존 파일 사용: %s", target.name)
        method = "existing_file"
    else:
        with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "BikeLinkAnalysis/2.0"}) as client:
            if source["type"] == "seoul_file":
                method, url = "POST", "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
                kwargs = {"data": {"infId": source["inf_id"], "seqNo": "", "seq": source["seq"],
                                    "infSeq": source["inf_seq"]}, "headers": {"Referer": source["source_url"]}}
            elif source["type"] == "portal_file":
                headers = {"X-Requested-With": "XMLHttpRequest", "Referer": source["source_url"]}
                info = client.post(
                    "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do",
                    data={"publicDataDetailPk": source["uddi"], "publicDataPk": source["public_data_pk"],
                          "atchFileId": "", "fileDetailSn": "1", "publicDataTyCode": "PR0051"},
                    headers=headers,
                )
                info.raise_for_status()
                result = info.json()
                if not result.get("status"):
                    raise RuntimeError(result.get("error", "공식 파일 조회 실패"))
                file_id, serial = result["atchFileId"], result["fileDetailSn"]
                check = client.post("https://www.data.go.kr/cmm/cmm/check-limit.json",
                                    data={"atchFileId": file_id, "fileDetailSn": serial}, headers=headers)
                check.raise_for_status()
                if check.json().get("needCaptcha"):
                    raise PermissionError("공공데이터포털 CAPTCHA가 필요합니다. 브라우저에서 내려받아 --file로 가져오세요.")
                method, url = "GET", "https://www.data.go.kr/cmm/cmm/fileDownload.do"
                kwargs = {"params": {"atchFileId": file_id, "fileDetailSn": serial,
                                      "dataNm": result["dataSetFileDetailInfo"]["dataNm"]}, "headers": headers}
            else:
                raise ValueError("검증되지 않은 수집 방식")
            with client.stream(method, url, **kwargs) as response:
                response.raise_for_status()
                chunks = response.iter_bytes(chunk_size=1024 * 1024)
                first = next(chunks, b"")
                magic = b"PK" if target.suffix.lower() in {".zip", ".xlsx"} else None
                if (magic and not first.startswith(magic)) or first.lstrip().startswith(b"<html"):
                    raise RuntimeError("공식 사이트가 데이터 대신 오류 페이지를 반환했습니다.")
                class Stream:
                    def __init__(self):
                        self.pending = first
                    def read(self, size):
                        if self.pending:
                            value, self.pending = self.pending[:size], self.pending[size:]
                            return value
                        return next(chunks, b"")
                save_stream(Stream(), target)
        method = "official_download"
    record(target, source, method)
    return target


def collect_openapi(source: dict):
    """Call only a portal OpenAPI path found in its official Swagger document."""
    if not source.get("api_path"):
        raise ValueError("검증된 OpenAPI 경로가 없습니다.")
    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        raise PermissionError("DATA_GO_KR_API_KEY가 필요합니다. 공공데이터포털 활용신청 후 .env에 설정하세요.")
    target = RAW / source["api_filename"]
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    url = "https://api.odcloud.kr/api" + source["api_path"]
    rows_written = 0
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client, tmp.open("w", encoding="utf-8", newline="") as output:
            writer = None
            for page in range(1, 10001):
                response = client.get(url, params={"serviceKey": key, "page": page, "perPage": 1000, "returnType": "JSON"})
                response.raise_for_status()
                body = response.json()
                rows = body.get("data")
                if not isinstance(rows, list):
                    raise RuntimeError("공식 API 응답에 data 목록이 없습니다.")
                if rows and writer is None:
                    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                    writer.writeheader()
                for row in rows:
                    writer.writerow(row)
                rows_written += len(rows)
                if len(rows) < 1000 or rows_written >= int(body.get("totalCount", rows_written + 1)):
                    break
            if rows_written == 0:
                raise RuntimeError("공식 API가 빈 자료를 반환했습니다.")
        if target.exists() and fingerprint(target) == fingerprint(tmp):
            tmp.unlink()
            LOG.info("중복 API 파일 유지: %s", target.name)
        else:
            tmp.replace(target)
        record(target, source, "official_api")
        LOG.info("OpenAPI 저장: %s (%s rows)", target.name, rows_written)
        return target
    finally:
        tmp.unlink(missing_ok=True)


def cli(sources: list[dict]):
    parser = argparse.ArgumentParser(description="공식 공공자전거 파일 수집")
    parser.add_argument("--file", help="로컬 파일 가져오기 (단일 데이터셋 실행 시)")
    parser.add_argument("--dataset", choices=[s["source_id"] for s in sources], help="수집할 데이터셋 ID")
    parser.add_argument("--api", action="store_true", help="공식 Swagger에 기록된 자동변환 OpenAPI 사용")
    args = parser.parse_args()
    setup_logging()
    if args.dataset:
        sources = [s for s in sources if s["source_id"] == args.dataset]
    if args.file and len(sources) != 1:
        parser.error("--file은 --dataset으로 한 데이터셋을 선택해야 합니다.")
    if args.file and args.api:
        parser.error("--file과 --api를 함께 사용할 수 없습니다.")
    for source in sources:
        try:
            if args.api:
                collect_openapi(source)
            else:
                collect(source, args.file)
        except (httpx.HTTPError, OSError, ValueError, RuntimeError, PermissionError) as exc:
            LOG.error("%s: %s", source["source_id"], exc)
            raise SystemExit(1) from exc


def setup_logging():
    RAW.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(RAW / "collect.log", encoding="utf-8")])
