"""Lossless presentation labels; never merge raw station identifiers."""
from backend.services import transit
def display_ids():
    ids={r["station_id"] for r in transit.station_master("sejong")}
    return {sid:(sid.replace("SJ-","SJ_",1)+("_H" if sid.startswith("SJ-") and sid.replace("SJ-","SJ_",1) in ids else "")) for sid in ids}
