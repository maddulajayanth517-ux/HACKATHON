import os
import secrets
import tempfile
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from app.database import init_db as init_sqlalchemy_db, seed_sample_data
from app.geo.database import get_all_defects, init_db as init_geo_db
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import verify_password
from app.database import get_db
from app.geo.geo_dispatch import (
    get_coordinates_from_address,
    get_elevation_and_flood_risk,
    get_reverse_geocode,
    process_and_dispatch_defect,
    render_folium_map,
)
from app.vision.vision_engine import analyze_media
from app.models import Authority, Complaint, ComplaintStatus, Contractor

app = FastAPI(
    title="UrbanPulse-AI API",
    description="Autonomous Road Defect & Micro-Flooding Lifecycle Engine",
    version="1.0.0",
)

# Initialize the SQLAlchemy database tables at startup.
@app.on_event("startup")
def startup_event():
    init_sqlalchemy_db()
    init_geo_db()
    seed_sample_data()

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_db_and_map():
    """Initializes the database and pre-renders the dispatch map."""
    init_geo_db()
    render_folium_map("dispatch_map.html")


class DispatchRequest(BaseModel):
    defect_type: str = "Pothole"
    severity: str = "High"
    latitude: float | None = None
    longitude: float | None = None
    manual_address: str | None = None
    contractor_email: str = "contractor@cityworks.gov"


class LoginRequest(BaseModel):
    role: str
    identifier: str
    password: str


class ComplaintStatusRequest(BaseModel):
    status: ComplaintStatus
    contractor_id: int | None = None


ACTIVE_TOKENS: dict[str, dict] = {}


def require_role(authorization: str | None, role: str) -> dict:
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    session = ACTIVE_TOKENS.get(token)
    if not session or session["role"] != role:
        raise HTTPException(status_code=401, detail=f"{role.title()} login required.")
    return session


def complaint_payload(complaint: Complaint) -> dict:
    return {
        "id": complaint.id,
        "reporter_phone": complaint.reporter_phone,
        "latitude": complaint.location_lat,
        "longitude": complaint.location_lon,
        "address": complaint.manual_address,
        "severity_level": complaint.severity_level,
        "estimated_depth_cm": complaint.estimated_depth_cm,
        "status": complaint.status.value,
        "authority_id": complaint.authority_id,
        "contractor_id": complaint.assigned_contractor_id,
        "created_at": complaint.created_at.isoformat(),
        "updated_at": complaint.updated_at.isoformat(),
    }


def build_email_draft(
    defect_type: str,
    severity: str,
    address: str,
    latitude: float,
    longitude: float,
    vision_result: dict,
    elevation: float,
    is_flood_prone: bool,
) -> dict:
    """Create a reviewable municipal email from the analyzed report."""

    subject = f"UrbanPulse infrastructure report: {defect_type}"
    body = f"""Dear Municipal Corporation Team,

I would like to report a suspected {defect_type.lower()} identified by UrbanPulse AI.

Report details:
- Suggested severity: {severity}
- AI severity: {vision_result.get('severity_level', 'Not available')}
- Estimated depth: ~{vision_result.get('estimated_depth_cm', 'Not available')} cm
- Automated assessment: {vision_result.get('email_report_string', 'Not available')}
- Vision confidence: {vision_result.get('confidence', 'Not available')}
- Address: {address}
- Coordinates: {latitude:.6f}, {longitude:.6f}
- Elevation: {elevation} meters
- Flood risk: {'High' if is_flood_prone else 'Normal'}
- Evidence file: {vision_result.get('source_file', 'Uploaded media')}

Please inspect this location and create a maintenance work order if the issue is confirmed.

Regards,
UrbanPulse citizen report
"""
    return {
        "subject": subject,
        "body": body,
        "gmail_url": (
            "https://mail.google.com/mail/?view=cm&fs=1"
            f"&su={quote(subject)}&body={quote(body)}"
        ),
    }


@app.post("/api/report/analyze")
async def analyze_report_media(
    media: UploadFile = File(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    manual_address: str = Form(default=""),
    severity: str = Form(default="High"),
    reporter_phone: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Analyze uploaded evidence, resolve location via GPS/Geocoding, and return a reviewable email draft."""

    if not media.filename:
        raise HTTPException(status_code=400, detail="A photo or video is required.")
    if (latitude is None or longitude is None) and not manual_address.strip():
        raise HTTPException(
            status_code=400,
            detail="Provide browser coordinates or a manual address.",
        )

    # 1. Resolve GPS Coordinates: If GPS not granted, forward-geocode the text address
    if (latitude is None or longitude is None or (latitude == 0.0 and longitude == 0.0)) and manual_address.strip():
        latitude, longitude = get_coordinates_from_address(manual_address.strip())

    if latitude is None or longitude is None:
        latitude, longitude = 12.9352, 77.6245  # Bangalore fallback

    suffix = os.path.splitext(media.filename)[1].lower()
    temporary_path = None
    try:
        content = await media.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
            temporary_file.write(content)
            temporary_path = temporary_file.name

        # 2. Vision Engine Analysis
        vision_result = analyze_media(temporary_path)
        if vision_result.get("error"):
            raise HTTPException(status_code=422, detail=vision_result["error"])

        # 3. Address and Flood Hazard Profiling
        if manual_address.strip():
            address = manual_address.strip()
        else:
            address = get_reverse_geocode(latitude, longitude)

        elevation, is_flood_prone = get_elevation_and_flood_risk(latitude, longitude)

        if not vision_result.get("defect_detected"):
            return {
                "status": "NO_DEFECT_DETECTED",
                "message": "No supported road defect was confirmed in the uploaded media.",
                "vision": vision_result,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
            }

        if not reporter_phone.strip():
            raise HTTPException(
                status_code=400,
                detail="A phone number is required to track this complaint.",
            )

        defect_type = vision_result.get("defect_type", "Road defect")
        confidence = vision_result.get("confidence", "Confirmed by repeated evidence")
        vision_result["source_file"] = media.filename

        # 4. Dispatch, Save to Database, and Update Folium Map
        dispatch_result = process_and_dispatch_defect(
            defect_type=defect_type,
            severity=severity,
            lat=latitude,
            lon=longitude,
            manual_address=address,
        )

        email = build_email_draft(
            defect_type,
            severity,
            address,
            latitude,
            longitude,
            {**vision_result, "confidence": confidence},
            elevation,
            is_flood_prone,
        )
        # Render updated HTML map
        render_folium_map("dispatch_map.html")
        complaint = Complaint(
            reporter_phone=reporter_phone.strip(),
            location_lat=latitude,
            location_lon=longitude,
            manual_address=address,
            severity_level=vision_result.get("severity_level") or severity,
            estimated_depth_cm=vision_result.get("estimated_depth_cm"),
            image_path=media.filename,
            status=ComplaintStatus.PENDING_VERIFICATION,
        )
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
        return {
            "status": "ANALYZED",
            "vision": vision_result,
            "complaint": complaint_payload(complaint),
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "elevation_meters": elevation,
            "is_flood_prone": is_flood_prone,
            "email": email,
            "dispatch": dispatch_result,
        }
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Issue a short-lived in-memory role token for verified staff accounts."""
    role = payload.role.strip().lower()
    if role not in {"authority", "contractor"}:
        raise HTTPException(status_code=400, detail="Only authority or contractor login is supported.")
    model = Authority if role == "authority" else Contractor
    account = db.scalar(
        select(model).where((model.email == payload.identifier) | (model.username == payload.identifier))
        if role == "authority"
        else select(model).where(model.email == payload.identifier)
    )
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Invalid staff credentials.")
    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS[token] = {"role": role, "account_id": account.id}
    return {"access_token": token, "role": role, "account_id": account.id}


@app.get("/api/complaints/{complaint_id}")
def get_complaint_status(complaint_id: int, reporter_phone: str, db: Session = Depends(get_db)):
    """Allow a citizen to view a complaint only with its matching phone number."""
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.reporter_phone != reporter_phone.strip():
        raise HTTPException(status_code=404, detail="Complaint not found.")
    return complaint_payload(complaint)


@app.get("/api/authority/complaints")
def authority_complaints(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    session = require_role(authorization, "authority")
    complaints = db.scalars(select(Complaint).order_by(Complaint.created_at.desc())).all()
    return {"authority_id": session["account_id"], "complaints": [complaint_payload(item) for item in complaints]}


@app.patch("/api/authority/complaints/{complaint_id}")
def update_complaint(
    complaint_id: int,
    payload: ComplaintStatusRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    session = require_role(authorization, "authority")
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found.")
    complaint.status = payload.status
    complaint.authority_id = session["account_id"]
    if payload.contractor_id is not None:
        if db.get(Contractor, payload.contractor_id) is None:
            raise HTTPException(status_code=404, detail="Contractor not found.")
        complaint.assigned_contractor_id = payload.contractor_id
        complaint.status = ComplaintStatus.ASSIGNED_TO_CONTRACTOR
    db.commit()
    db.refresh(complaint)
    return complaint_payload(complaint)


@app.patch("/api/contractor/complaints/{complaint_id}")
def contractor_update_complaint(
    complaint_id: int,
    payload: ComplaintStatusRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    session = require_role(authorization, "contractor")
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.assigned_contractor_id != session["account_id"]:
        raise HTTPException(status_code=404, detail="Assigned complaint not found.")
    if payload.status not in {ComplaintStatus.IN_PROGRESS, ComplaintStatus.RESOLVED}:
        raise HTTPException(status_code=400, detail="Contractors can set only IN_PROGRESS or RESOLVED.")
    complaint.status = payload.status
    db.commit()
    db.refresh(complaint)
    return complaint_payload(complaint)


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "UrbanPulse-AI GIS & Dispatch Backend",
    }


@app.post("/api/geo/dispatch")
def dispatch_defect(payload: DispatchRequest):
    """Processes a defect: geocoding, flood hazard assessment, duplicate check, and contractor alert."""
    lat, lon = payload.latitude, payload.longitude
    if (lat is None or lon is None) and payload.manual_address:
        lat, lon = get_coordinates_from_address(payload.manual_address)

    if lat is None or lon is None:
        lat, lon = 12.9352, 77.6245

    result = process_and_dispatch_defect(
        defect_type=payload.defect_type,
        severity=payload.severity,
        lat=lat,
        lon=lon,
        contractor_email=payload.contractor_email,
        manual_address=payload.manual_address,
    )
    render_folium_map("dispatch_map.html")
    return result


@app.get("/api/geo/defects")
def list_defects():
    """Returns all stored defect logs with elevation and flood status."""
    return {"count": len(get_all_defects()), "defects": get_all_defects()}


@app.get("/api/geo/map")
def generate_map():
    """Generates and returns the path to the updated Folium defect map."""
    map_file = render_folium_map("dispatch_map.html")
    return {"status": "success", "map_path": map_file}


@app.get("/api/sample-db")
def sample_db_status():
    """Returns a sample authority, contractor, and complaint record for demo verification."""
    return seed_sample_data()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)