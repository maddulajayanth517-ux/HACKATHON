from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import MongoClient

from app.auth import hash_password


MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "urbanpulse")


class MongoStore:
    """Single MongoDB repository for authorities, pincode routing, complaints, and GIS defects."""

    def __init__(self) -> None:
        self._client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500) if MONGO_URI else None
        self._database = self._client[MONGO_DATABASE] if self._client else None
        self._memory: dict[str, list[dict[str, Any]]] = {
            "authorities": [], "contractors": [], "pincode_areas": [], "complaints": [], "defects": [],
        }
        self._next_id = 1

    @property
    def demo_mode(self) -> bool:
        return self._database is None

    def collection(self, name: str):
        return self._database[name] if self._database is not None else _MemoryCollection(self._memory[name])

    def init(self) -> None:
        if self._database is not None:
            try:
                self._client.admin.command("ping")
            except Exception:
                self._client.close()
                self._client = None
                self._database = None
                return
            self.collection("authorities").create_index("email", unique=True)
            self.collection("pincode_areas").create_index("pincode", unique=True)
            self.collection("complaints").create_index("complaint_id", unique=True)
            self.collection("complaints").create_index([("pincode", 1), ("status", 1), ("created_at", -1)])
            self.collection("complaints").create_index([("location_point", "2dsphere")])
            self.collection("defects").create_index([("latitude", 1), ("longitude", 1)])

    def seed(self) -> dict:
        authorities = self.collection("authorities")
        if not authorities.find_one({"email": "roads.ward12@example.gov.in"}):
            authorities.insert_one({
                "authority_id": "AUTH001", "authority_name": "Vijayawada Municipal Corporation",
                "department": "Roads & Engineering", "contact_person": "Public Works Desk",
                "email": "roads.ward12@example.gov.in", "phone": "+91-866-000-0012",
                "office_address": "Vijayawada Municipal Office", "city": "Vijayawada",
                "district": "NTR", "state": "Andhra Pradesh", "active": True,
                "complaint_types": ["Pothole", "Road Damage", "Drainage", "Waterlogging", "Flooding"],
                "username": "city_ops", "password_hash": hash_password("urbanpulse-demo"),
                "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
            })
        if not authorities.find_one({"email": "roads.ward12@example.gov.in"}):
            return {"status": "seed_failed"}
        contractors = self.collection("contractors")
        if not contractors.find_one({"email": "contact@metrofix.com"}):
            contractors.insert_one({
                "contractor_id": "CONTRACTOR001", "company_name": "MetroFix Contractors",
                "email": "contact@metrofix.com", "phone": "+15551234567",
                "password_hash": hash_password("urbanpulse-contractor"), "active": True,
            })
        areas = self.collection("pincode_areas")
        if not areas.find_one({"pincode": "520010"}):
            areas.insert_one({
                "pincode": "520010", "area": "Benz Circle", "ward_number": "12",
                "city": "Vijayawada", "district": "NTR", "state": "Andhra Pradesh",
                "authority_id": "AUTH001", "authority_name": "Vijayawada Municipal Corporation",
                "department": "Roads & Engineering", "authority_email": "roads.ward12@example.gov.in",
                "active": True,
            })
        complaints = self.collection("complaints")
        if not complaints.find_one({"complaint_id": "CMP-2026-00001"}):
            complaints.insert_one({
                "complaint_id": "CMP-2026-00001", "reporter_phone": "+15557654321",
                "citizen_name": "Demo Citizen", "complaint_type": "Pothole",
                "title": "Large pothole near MG Road", "description": "Demo complaint for dashboard testing.",
                "pincode": "520010", "area": "Benz Circle", "ward_number": "12",
                "city": "Vijayawada", "district": "NTR", "state": "Andhra Pradesh",
                "latitude": 16.4978, "longitude": 80.6498,
                "location_point": {"type": "Point", "coordinates": [80.6498, 16.4978]},
                "severity_level": "HIGH", "estimated_depth_cm": 18.5,
                "authority_id": "AUTH001", "authority_name": "Vijayawada Municipal Corporation",
                "department": "Roads & Engineering", "authority_email": "roads.ward12@example.gov.in",
                "status": "PENDING_VERIFICATION", "email_status": "Demo",
                "duplicate_status": "New", "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
        item = complaints.find_one({"complaint_id": "CMP-2026-00001"})
        return {"complaint_id": item["complaint_id"], "status": item["status"], "authority_email": item["authority_email"]}

    def next_complaint_id(self) -> str:
        year = datetime.now(timezone.utc).year
        count = self.collection("complaints").count_documents({}) + 1
        return f"CMP-{year}-{count:05d}"


class _MemoryCollection:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    def find_one(self, query: dict) -> dict | None:
        return next((record for record in self.records if all(record.get(k) == v for k, v in query.items())), None)

    def insert_one(self, record: dict) -> None:
        self.records.append(dict(record))

    def count_documents(self, query: dict) -> int:
        return sum(1 for record in self.records if all(record.get(k) == v for k, v in query.items()))

    def find(self, query: dict | None = None, sort=None):
        query = query or {}
        records = [record for record in self.records if all(record.get(k) == v for k, v in query.items())]
        if sort:
            for key, direction in reversed(sort):
                records.sort(key=lambda item: item.get(key, ""), reverse=direction < 0)
        return records

    def find_one_and_update(self, query: dict, update: dict, return_document=None):
        record = self.find_one(query)
        if record:
            record.update(update.get("$set", {}))
        return record


store = MongoStore()
