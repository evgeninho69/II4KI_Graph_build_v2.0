from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TypedDict, Dict, Any


class Parcel(TypedDict, total=False):
    id: str
    cadastral_number: str
    designation: str
    status: str
    is_main: bool
    boundary_status: str


class BoundaryPoint(TypedDict, total=False):
    id: str
    x: float
    y: float
    kind: str  # CREATED | EXISTING | ...


class Station(TypedDict, total=False):
    id: str
    x: float
    y: float
    name: str
    kind: str  # OMS | GGS


class Direction(TypedDict, total=False):
    from_station_id: str
    to_point_id: str
    length_m_int: int


class Entities(TypedDict, total=False):
    parcels: List[Parcel]
    boundary_points: List[BoundaryPoint]
    stations: List[Station]
    directions: List[Direction]


class CRS(TypedDict, total=False):
    name: str
    unit: str


class ProjectInfo(TypedDict, total=False):
    id: str
    name: str


class ContractData(TypedDict, total=False):
    project: ProjectInfo
    crs: CRS
    scales_allowed: List[int]
    entities: Entities


def load_json(path: Path | str) -> ContractData:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSON не найден: {p}")
    data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "entities" not in data:
        raise ValueError("Некорректный контракт JSON: отсутствует ключ 'entities'")
    return data  # тип: ContractData


# ------------------- SRZU Unified Contract -------------------

class Geometry(TypedDict, total=False):
    type: str  # Polygon | MultiPolygon | LineString
    coordinates: Any
    properties: Dict[str, Any]


class SRZUData(TypedDict, total=False):
    crs: CRS
    target_parcels: List[Geometry]
    adjacent_parcels: List[Geometry]
    quarters: List[Geometry]
    admin_boundaries: List[Geometry]
    zones: List[Geometry]
    labels: List[Dict[str, Any]]


def load_srzu_json(path: Path | str) -> SRZUData:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SRZU JSON не найден: {p}")
    data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    # Минимальная валидация наличия ключей
    srzu: SRZUData = {
        "crs": data.get("crs", {"name": "LOCAL", "unit": "m"}),
        "target_parcels": data.get("target_parcels", []) or [],
        "adjacent_parcels": data.get("adjacent_parcels", []) or [],
        "quarters": data.get("quarters", []) or [],
        "admin_boundaries": data.get("admin_boundaries", []) or [],
        "zones": data.get("zones", []) or [],
        "labels": data.get("labels", []) or [],
    }
    return srzu


