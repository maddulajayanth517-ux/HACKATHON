import os
import tempfile
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from app.geo.database import get_all_defects
from app.geo.geo_dispatch import (
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

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DispatchRequest(BaseModel):
    defect_type: str = "Pothole"
    severity: str = "High"
    latitude: float
    longitude: float
    contractor_email: str = "contractor@cityworks.gov"


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
):
    """Analyze uploaded evidence and return location plus a reviewable email draft."""

    if not media.filename:
        raise HTTPException(status_code=400, detail="A photo or video is required.")
    if latitude is None or longitude is None:
        if not manual_address.strip():
            raise HTTPException(
                status_code=400,
                detail="Provide browser coordinates or a manual address.",
            )

    suffix = os.path.splitext(media.filename)[1].lower()
    temporary_path = None
    try:
        content = await media.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
            temporary_file.write(content)
            temporary_path = temporary_file.name

        vision_result = analyze_media(temporary_path)
        if vision_result.get("error"):
            raise HTTPException(status_code=422, detail=vision_result["error"])

        if latitude is not None and longitude is not None:
            address = get_reverse_geocode(latitude, longitude)
            elevation, is_flood_prone = get_elevation_and_flood_risk(latitude, longitude)
        else:
            address = manual_address.strip()
            elevation, is_flood_prone = 0.0, False

        if not vision_result.get("defect_detected"):
            return {
                "status": "NO_DEFECT_DETECTED",
                "message": "No supported road defect was confirmed in the uploaded media.",
                "vision": vision_result,
                "address": address,
            }

        defect_type = vision_result.get("defect_type", "Road defect")
        confidence = vision_result.get("confidence", "Confirmed by repeated evidence")
        vision_result["source_file"] = media.filename
        email = build_email_draft(
            defect_type,
            severity,
            address,
            latitude or 0.0,
            longitude or 0.0,
            {**vision_result, "confidence": confidence},
            elevation,
            is_flood_prone,
        )
        return {
            "status": "ANALYZED",
            "vision": vision_result,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "elevation_meters": elevation,
            "is_flood_prone": is_flood_prone,
            "email": email,
        }
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "UrbanPulse-AI GIS & Dispatch Backend",
    }


@app.post("/api/geo/dispatch")
def dispatch_defect(payload: DispatchRequest):
    """Processes a detected defect: reverse geocoding, flood hazard assessment, duplicate check, and contractor alert."""
    result = process_and_dispatch_defect(
        defect_type=payload.defect_type,
        severity=payload.severity,
        lat=payload.latitude,
        lon=payload.longitude,
        contractor_email=payload.contractor_email,
    )
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


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)