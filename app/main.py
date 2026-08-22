import os
import secrets
import tempfile
from datetime import datetime, timezone
import re
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from app.geo.database import get_all_defects, init_db as init_geo_db
from app.mongo_store import store
from app.auth import verify_password
from app.email_alerts import alert_authority_via_email
from app.geo.geo_dispatch import (
    get_coordinates_from_address,
    get_elevation_and_flood_risk,
    get_reverse_geocode,
    process_and_dispatch_defect,
    render_folium_map,
)
from app.vision.vision_engine import analyze_media

app = FastAPI(
    title="UrbanPulse-AI API",
    description="Autonomous Road Defect & Micro-Flooding Lifecycle Engine",
    version="1.0.0",
)

# Initialize the MongoDB collections and indexes at startup.
@app.on_event("startup")
def startup_event():
    store.init()
    init_geo_db()
    store.seed()

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
    """Pre-renders the dispatch map."""
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
    status: str
    contractor_id: int | None = None


ACTIVE_TOKENS: dict[str, dict] = {}


def require_role(authorization: str | None, role: str) -> dict:
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    session = ACTIVE_TOKENS.get(token)
    if not session or session["role"] != role:
        raise HTTPException(status_code=401, detail=f"{role.title()} login required.")
    return session


def complaint_payload(complaint: dict) -> dict:
    payload = {key: value for key, value in complaint.items() if not key.startswith("_")}
    payload.setdefault("id", payload.get("complaint_id"))
    payload.setdefault("address", payload.get("manual_address"))
    return payload


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
    pincode: str = Form(default=""),
    severity: str = Form(default="High"),
    reporter_phone: str = Form(default=""),
):
    """Analyze uploaded evidence, resolve location via GPS/Geocoding, and return a reviewable email draft."""

    if not media.filename:
        raise HTTPException(status_code=400, detail="A photo or video is required.")
    pincode = pincode.strip()
    if not re.fullmatch(r"\d{6}", pincode):
        raise HTTPException(status_code=400, detail="Enter a valid 6-digit pincode.")
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
        authority = store.collection("pincode_areas").find_one({"pincode": pincode})
        if authority is None or not authority.get("active", False):
            raise HTTPException(status_code=422, detail="No active authority is mapped to this pincode.")

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
        complaint = {
            "complaint_id": store.next_complaint_id(),
            "reporter_phone": reporter_phone.strip(),
            "complaint_type": defect_type,
            "title": f"{defect_type} reported by citizen",
            "description": "AI-analyzed urban infrastructure complaint.",
            "pincode": pincode,
            "area": authority.get("area") if authority else None,
            "ward_number": authority.get("ward_number") if authority else None,
            "location_lat": latitude,
            "location_lon": longitude,
            "latitude": latitude,
            "longitude": longitude,
            "location_point": {"type": "Point", "coordinates": [longitude, latitude]},
            "manual_address": address,
            "severity_level": vision_result.get("severity_level") or severity,
            "estimated_depth_cm": vision_result.get("estimated_depth_cm"),
            "image_path": media.filename,
            "status": "PENDING_VERIFICATION",
            "authority_id": authority.get("authority_id") if authority else None,
            "authority_name": authority.get("authority_name") if authority else None,
            "department": authority.get("department") if authority else None,
            "authority_email": authority.get("authority_email") if authority else os.getenv("AUTHORITY_ALERT_EMAIL", "ops@urbanpulse.gov"),
            "email_status": "Demo" if not os.getenv("SMTP_PASSWORD") else "Sent",
            "duplicate_status": "New",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        store.collection("complaints").insert_one(complaint)
        notification_sent = alert_authority_via_email(
            {
                "complaint_id": complaint["complaint_id"],
                "severity_level": complaint["severity_level"],
                "manual_address": complaint["manual_address"],
                "reporter_phone": complaint["reporter_phone"],
                "estimated_depth_cm": complaint["estimated_depth_cm"],
            },
            complaint["authority_email"],
        )
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
            "notification_status": "Demo or sent" if notification_sent else "Failed",
            "dispatch": dispatch_result,
        }
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    """Issue a short-lived in-memory role token for verified staff accounts."""
    role = payload.role.strip().lower()
    if role not in {"authority", "contractor"}:
        raise HTTPException(status_code=400, detail="Only authority or contractor login is supported.")
    collection = store.collection("authorities" if role == "authority" else "contractors")
    account = collection.find_one(
        {"username": payload.identifier} if role == "authority" else {"email": payload.identifier}
    )
    if account is None or not verify_password(payload.password, account.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid staff credentials.")
    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS[token] = {"role": role, "account_id": account.get("authority_id", account.get("contractor_id", account.get("email")))}
    return {"access_token": token, "role": role, "account_id": ACTIVE_TOKENS[token]["account_id"]}


@app.get("/api/complaints/{complaint_id}")
def get_complaint_status(complaint_id: str, reporter_phone: str):
    """Allow a citizen to view a complaint only with its matching phone number."""
    complaint = store.collection("complaints").find_one({"complaint_id": complaint_id})
    if complaint is None or complaint.get("reporter_phone") != reporter_phone.strip():
        raise HTTPException(status_code=404, detail="Complaint not found.")
    return complaint_payload(complaint)


@app.get("/api/pincodes/{pincode}")
def lookup_pincode(pincode: str):
    """Return the active authority mapped to a six-digit pincode."""
    if not re.fullmatch(r"\d{6}", pincode.strip()):
        raise HTTPException(status_code=400, detail="Pincode must contain exactly 6 digits.")
    area = store.collection("pincode_areas").find_one({"pincode": pincode.strip()})
    if area is None or not area.get("active", False):
        raise HTTPException(status_code=404, detail="No active authority is mapped to this pincode.")
    return {key: value for key, value in area.items() if not key.startswith("_")}


@app.get("/api/authority/complaints")
def authority_complaints(authorization: str | None = Header(default=None)):
    session = require_role(authorization, "authority")
    complaints = store.collection("complaints").find(sort=[("created_at", -1)])
    return {"authority_id": session["account_id"], "complaints": [complaint_payload(item) for item in complaints]}


@app.patch("/api/authority/complaints/{complaint_id}")
def update_complaint(
    complaint_id: int,
    payload: ComplaintStatusRequest,
    authorization: str | None = Header(default=None),
):
    session = require_role(authorization, "authority")
    complaint = store.collection("complaints").find_one({"complaint_id": complaint_id})
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found.")
    complaint["status"] = payload.status
    complaint["authority_id"] = session["account_id"]
    if payload.contractor_id is not None:
        complaint["assigned_contractor_id"] = payload.contractor_id
        complaint["status"] = "ASSIGNED_TO_CONTRACTOR"
    store.collection("complaints").find_one_and_update(
        {"complaint_id": complaint_id}, {"$set": complaint}
    )
    return complaint_payload(complaint)


@app.patch("/api/contractor/complaints/{complaint_id}")
def contractor_update_complaint(
    complaint_id: int,
    payload: ComplaintStatusRequest,
    authorization: str | None = Header(default=None),
):
    session = require_role(authorization, "contractor")
    complaint = store.collection("complaints").find_one({"complaint_id": complaint_id})
    if complaint is None or complaint.get("assigned_contractor_id") != session["account_id"]:
        raise HTTPException(status_code=404, detail="Assigned complaint not found.")
    if payload.status not in {"IN_PROGRESS", "RESOLVED"}:
        raise HTTPException(status_code=400, detail="Contractors can set only IN_PROGRESS or RESOLVED.")
    complaint["status"] = payload.status
    store.collection("complaints").find_one_and_update(
        {"complaint_id": complaint_id}, {"$set": complaint}
    )
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
    return store.seed()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)