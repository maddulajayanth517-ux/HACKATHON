from __future__ import annotations

import math
from datetime import datetime, timezone

from app.mongo_store import store


def init_db() -> None:
    """Initialize MongoDB indexes; no local SQLite file is created."""
    try:
        store.init()
    except Exception:
        pass


def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def is_duplicate_complaint(lat: float, lon: float, threshold_meters: float = 50.0) -> bool:
    for record in store.collection("defects").find():
        if calculate_distance_meters(lat, lon, record["latitude"], record["longitude"]) <= threshold_meters:
            return True
    return False


def insert_defect(defect_type: str, severity: str, lat: float, lon: float, address: str, elevation: float, is_flood_prone: bool, manual_address: str | None = None) -> str:
    record = {
        "defect_type": defect_type, "severity": severity, "latitude": lat, "longitude": lon,
        "address": manual_address or address, "elevation": elevation, "is_flood_prone": is_flood_prone,
        "status": "Pending", "reported_at": datetime.now(timezone.utc).isoformat(),
    }
    collection = store.collection("defects")
    record["id"] = collection.count_documents({}) + 1
    collection.insert_one(record)
    return str(record["id"])


def get_all_defects() -> list[dict]:
    records = store.collection("defects").find(sort=[("reported_at", -1)])
    return [{key: value for key, value in record.items() if not key.startswith("_")} for record in records]


init_db()
