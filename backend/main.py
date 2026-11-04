from datetime import date
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.solar import chat
from backend.models.schemas import ChatRequest
from backend.services import data as demo_data
from backend.services import imports, real_data

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Bike Link Analysis API", version="0.2.0")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"], allow_headers=["*"])


def check_region(region_id):
    if region_id not in {r["region_id"] for r in real_data.REGIONS}:
        raise HTTPException(404, "지역을 찾을 수 없습니다.")


def period(start: date | None, end: date | None):
    if start and end and start > end:
        raise HTTPException(400, "시작일이 종료일보다 늦습니다.")
    return start.isoformat() if start else None, end.isoformat() if end else None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/regions")
def regions():
    return {"regions": [
        {**region, "availability": real_data.source_meta(region["region_id"])["verification_status"],
         "has_usage": bool(real_data.profiles(region["region_id"])),
         "has_od": bool(real_data.snapshot()["od"] and any(
             e["region_id"] == region["region_id"] for e in real_data.snapshot()["od"]))}
        for region in real_data.REGIONS]}


@app.get("/api/regions/{region_id}/overview")
def overview(region_id: str, date_start: date | None = None, date_end: date | None = None):
    check_region(region_id)
    return real_data.overview(region_id, *period(date_start, date_end))


@app.get("/api/regions/{region_id}/stations")
def stations(region_id: str, date_start: date | None = None, date_end: date | None = None,
             q: str | None = None, limit: int = 10000):
    check_region(region_id)
    items = real_data.region_stations(region_id, *period(date_start, date_end))
    if q:
        items = [s for s in items if q.lower() in (s["station_id"] + " " + (s["station_name"] or "")).lower()]
    return {**real_data.source_meta(region_id), "stations": items[:max(1, min(limit, 10000))],
            "total": len(items), "available": bool(items),
            "period_start": (real_data.observed_dates(region_id, *period(date_start, date_end)) or [None])[0],
            "period_end": (real_data.observed_dates(region_id, *period(date_start, date_end)) or [None])[-1],
            "message": None if items else "대여소 데이터 미확보"}


@app.get("/api/regions/{region_id}/stations/{station_id}")
def station(region_id: str, station_id: str, date_start: date | None = None, date_end: date | None = None):
    check_region(region_id)
    start, end = period(date_start, date_end)
    item = next((s for s in real_data.region_stations(region_id, start, end) if s["station_id"] == station_id), None)
    if item is None:
        raise HTTPException(404, "대여소를 찾을 수 없습니다.")
    cluster = next((c for c in real_data.clusters(region_id, start, end)["clusters"] if c["station_id"] == station_id), None)
    return {**real_data.source_meta(region_id), "station": item, "cluster": cluster}


@app.get("/api/regions/{region_id}/clusters")
def clusters(region_id: str, date_start: date | None = None, date_end: date | None = None):
    check_region(region_id)
    return real_data.clusters(region_id, *period(date_start, date_end))


@app.get("/api/regions/{region_id}/network")
def network(region_id: str, date_start: date | None = None, date_end: date | None = None,
            node_limit: int = 40):
    check_region(region_id)
    if node_limit not in (30, 40, 50):
        raise HTTPException(400, "node_limit은 30, 40, 50 중 하나여야 합니다.")
    return real_data.network(region_id, *period(date_start, date_end), node_limit)


@app.get("/api/regions/{region_id}/centrality")
def centrality(region_id: str, date_start: date | None = None, date_end: date | None = None):
    check_region(region_id)
    return real_data.centrality_result(region_id, *period(date_start, date_end))


@app.get("/api/regions/{region_id}/similarity")
def similarity(region_id: str, station_id: str, date_start: date | None = None, date_end: date | None = None):
    check_region(region_id)
    try:
        return real_data.similarity_result(region_id, station_id, *period(date_start, date_end))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/compare")
def compare(region_ids: str | None = None, date_start: date | None = None, date_end: date | None = None):
    ids = list(dict.fromkeys(x.strip() for x in region_ids.split(","))) if region_ids else None
    if ids is not None:
        if not 1 <= len(ids) <= 4:
            raise HTTPException(400, "1~4개 지역을 선택하세요.")
        for rid in ids:
            check_region(rid)
    return real_data.compare(ids, *period(date_start, date_end))


@app.get("/api/data-sources")
def data_sources(region_id: str | None = None):
    if region_id:
        check_region(region_id)
    return {"data_sources": [s for s in real_data.snapshot()["sources"]
                             if region_id is None or s["region_id"] == region_id]}


@app.get("/api/data-quality")
def data_quality(region_id: str | None = None):
    if region_id:
        check_region(region_id)
    quality = real_data.snapshot()["quality"]
    return {"quality": quality.get(region_id, {}) if region_id else quality}


@app.get("/api/data-validation")
def data_validation():
    return real_data.read_json("validation_stage3.json", {"message": "검증 결과 미생성"})


@app.post("/api/regions/{region_id}/upload")
async def upload(region_id: str, kind: str = Form(...), dataset_name: str = Form(...), file: UploadFile = File(...)):
    check_region(region_id)
    return await imports.import_csv(region_id, kind, file, dataset_name)


@app.get("/api/agent/status")
def agent_status():
    return {"configured": bool(os.getenv("UPSTAGE_API_KEY")), "provider": "Upstage Solar"}


@app.post("/api/agent/chat")
def agent_chat(body: ChatRequest):
    return chat(body.message)


# The old synthetic fixture is reachable only through explicit Demo Mode routes.
@app.get("/api/demo/regions")
def demo_regions():
    return {"metadata": demo_data.metadata(), "regions": demo_data.regions()}


@app.get("/api/demo/overview")
def demo_overview(region_id: str = "seoul"):
    if region_id not in {r["region_id"] for r in demo_data.regions()}:
        raise HTTPException(404, "데모 지역을 찾을 수 없습니다.")
    return demo_data.overview(region_id)
