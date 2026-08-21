from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from app.geo.database import get_all_defects
from app.geo.geo_dispatch import (
    process_and_dispatch_defect,
    render_folium_map,
)

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