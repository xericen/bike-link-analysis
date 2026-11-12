from pydantic import BaseModel, Field

class Metadata(BaseModel):
    source: str
    period_start: str
    period_end: str
    is_real: bool
    has_od: bool

class Region(BaseModel):
    region_id: str
    name: str

class Station(BaseModel):
    region_id: str
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    hourly: list[int]
    rental_count: int
    timestamp: str

class Cluster(BaseModel):
    station_id: str
    cluster_id: int
    role: str
    description: str

class Edge(BaseModel):
    origin_station_id: str
    destination_station_id: str
    trip_count: int

class Centrality(BaseModel):
    station_id: str
    station_name: str
    pagerank: float
    degree_centrality: float

class HealthResponse(BaseModel):
    status: str

class RegionsResponse(BaseModel):
    metadata: Metadata
    regions: list[Region]

class OverviewResponse(BaseModel):
    metadata: Metadata
    region_id: str
    total_rentals: int
    station_count: int
    hourly: list[int]
    stations: list[Station]

class StationsResponse(BaseModel):
    metadata: Metadata
    stations: list[Station]

class StationResponse(BaseModel):
    metadata: Metadata
    station: Station
    cluster: Cluster | None

class ClustersResponse(BaseModel):
    metadata: Metadata
    clusters: list[Cluster]

class NetworkResponse(BaseModel):
    metadata: Metadata
    available: bool
    nodes: list[Station]
    edges: list[Edge]
    message: str

class CentralityResponse(BaseModel):
    metadata: Metadata
    available: bool
    rankings: list[Centrality]
    message: str

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: dict | None = None

class ToolTrace(BaseModel):
    tool: str
    arguments: dict
    result: dict

class ChatResponse(BaseModel):
    answer: str
    metadata: Metadata
    evidence: list[ToolTrace]
