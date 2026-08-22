from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Authority, Base, Complaint, ComplaintStatus, Contractor

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./urbanpulse.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all SQLAlchemy tables used by the UrbanPulse backend."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_sample_data() -> dict:
    """Insert a representative authority, contractor, and complaint for local testing."""
    db = SessionLocal()
    try:
        authority = db.query(Authority).filter_by(email="ops@urbanpulse.gov").first()
        if authority is None:
            authority = Authority(
                username="city_ops",
                email="ops@urbanpulse.gov",
                password_hash="demo_hash",
                department="Public Works",
            )
            db.add(authority)

        contractor = db.query(Contractor).filter_by(email="contact@metrofix.com").first()
        if contractor is None:
            contractor = Contractor(
                company_name="MetroFix Contractors",
                email="contact@metrofix.com",
                phone="+15551234567",
                password_hash="demo_contract_hash",
            )
            db.add(contractor)

        complaint = db.query(Complaint).filter_by(reporter_phone="+15557654321").first()
        if complaint is None:
            complaint = Complaint(
                reporter_phone="+15557654321",
                location_lat=17.3871,
                location_lon=78.4867,
                manual_address="Near MG Road, Hyderabad",
                severity_level="HIGH",
                estimated_depth_cm=18.5,
                image_path="/tmp/sample_pothole.jpg",
                status=ComplaintStatus.PENDING_VERIFICATION,
                authority=authority,
                contractor=contractor,
            )
            db.add(complaint)

        db.commit()
        db.refresh(complaint)
        return {
            "authority_id": authority.id,
            "contractor_id": contractor.id,
            "complaint_id": complaint.id,
            "status": complaint.status.value,
            "reporter_phone": complaint.reporter_phone,
            "manual_address": complaint.manual_address,
        }
    finally:
        db.close()
