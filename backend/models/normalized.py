"""Cross-region nullable records. Aggregate OD rows are kept separate from Trip."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field

class Region(BaseModel):
    region_id: Literal["seoul", "daejeon", "sejong", "busan"]
    region_name: str
    service_name: str

class Station(BaseModel):
    region_id: str
    station_id: str
    station_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    capacity: int | None = None

class Trip(BaseModel):
    region_id: str
    origin_station_id: str | None = None
    destination_station_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_minutes: float | None = Field(default=None, ge=0)

class StationUsage(BaseModel):
    region_id: str
    station_id: str
    date: date
    hour: int | None = Field(default=None, ge=0, le=23)
    rental_count: int = Field(ge=0)
    return_count: int | None = Field(default=None, ge=0)

class DataSource(BaseModel):
    source_id: str
    region_id: str
    dataset_name: str
    source_url: str | None = None
    date_start: date | None = None
    date_end: date | None = None
    collected_at: datetime | None = None
    verification_status: Literal["VERIFIED", "ACCESS_REQUIRED", "METADATA_ONLY", "UNAVAILABLE"]
    available_columns: list[str] = []
