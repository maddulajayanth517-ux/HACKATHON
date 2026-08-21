import folium
from geopy.geocoders import Nominatim
import requests

from app.geo.database import (
    get_all_defects,
    insert_defect,
    is_duplicate_complaint,
)

# Initialize Nominatim Geocoder
geolocator = Nominatim(user_agent="urban_pulse_ai_dispatch_engine")


def get_reverse_geocode(lat: float, lon: float) -> str:
    """Converts GPS coordinates into a human-readable street address."""
    try:
        location = geolocator.reverse((lat, lon), exactly_one=True, timeout=10)
        return location.address if location else f"Coordinates ({lat}, {lon})"
    except Exception as e:
        return f"Lat: {lat}, Lon: {lon} (Address lookup offline)"


def get_elevation_and_flood_risk(
    lat: float, lon: float, flood_threshold_meters: float = 15.0
) -> tuple[float, bool]:
    """Fetches real-time elevation in meters and assesses micro-flooding risk."""
    try:
        url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
        response = requests.get(url, timeout=5).json()
        elevation = response.get("elevation", [0.0])[0]
    except Exception:
        elevation = 10.0  # Fallback default elevation

    # Low elevation relative to surrounding threshold is marked flood-prone
    is_flood_prone = elevation < flood_threshold_meters
    return elevation, is_flood_prone


def generate_google_maps_route(lat: float, lon: float) -> str:
    """Generates direct turnkey contractor dispatch navigation URL."""
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=driving"


def send_contractor_dispatch_alert(
    contractor_email: str, defect_data: dict, routing_url: str
) -> dict:
    """Simulates/dispatches work-order alerts to municipal maintenance contractors."""
    alert_payload = {
        "to": contractor_email,
        "subject": f"URGENT WORK ORDER: {defect_data.get('defect_type', 'Defect')} - Priority {defect_data.get('severity', 'Medium')}",
        "address": defect_data.get("address"),
        "flood_risk": (
            "HIGH (Low-lying basin)"
            if defect_data.get("is_flood_prone")
            else "NORMAL"
        ),
        "navigation_route": routing_url,
        "dispatch_status": "DISPATCHED_TO_CONTRACTOR",
    }
    print(
        f"\n[EMAIL DISPATCH] Alert sent to {contractor_email} -> Defect at: {defect_data.get('address')}"
    )
    return alert_payload


def process_and_dispatch_defect(
    defect_type: str,
    severity: str,
    lat: float,
    lon: float,
    contractor_email: str = "contractor@cityworks.gov",
) -> dict:
    """Main pipeline for Member 3: GIS processing, duplicate filter, DB recording, and dispatch."""
    # 1. Duplicate check
    if is_duplicate_complaint(lat, lon, threshold_meters=15.0):
        return {
            "status": "DUPLICATE_IGNORED",
            "message": "A defect has already been reported at or near this location.",
            "lat": lat,
            "lon": lon,
        }

    # 2. Reverse Geocode address
    address = get_reverse_geocode(lat, lon)

    # 3. Elevation & flood hazard profiling
    elevation, is_flood_prone = get_elevation_and_flood_risk(lat, lon)

    # 4. Save into Database
    record_id = insert_defect(
        defect_type=defect_type,
        severity=severity,
        lat=lat,
        lon=lon,
        address=address,
        elevation=elevation,
        is_flood_prone=is_flood_prone,
    )

    # 5. Routing Link & Contractor Alert
    route_url = generate_google_maps_route(lat, lon)
    defect_summary = {
        "id": record_id,
        "defect_type": defect_type,
        "severity": severity,
        "address": address,
        "is_flood_prone": is_flood_prone,
    }
    alert_info = send_contractor_dispatch_alert(
        contractor_email, defect_summary, route_url
    )

    return {
        "status": "PROCESSED_AND_DISPATCHED",
        "record_id": record_id,
        "address": address,
        "elevation_meters": elevation,
        "is_flood_prone": is_flood_prone,
        "google_maps_route": route_url,
        "alert": alert_info,
    }


def render_folium_map(output_html_path: str = "static_map.html") -> str:
    """Renders all defects stored in DB into an interactive HTML map."""
    defects = get_all_defects()

    if defects:
        center_lat = defects[0]["latitude"]
        center_lon = defects[0]["longitude"]
    else:
        center_lat, center_lon = 16.234, 80.548

    folium_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="OpenStreetMap",
    )

    for item in defects:
        lat = item["latitude"]
        lon = item["longitude"]
        is_flood = bool(item["is_flood_prone"])
        route_url = generate_google_maps_route(lat, lon)

        marker_color = "red" if is_flood else "orange"
        icon_type = "tint" if is_flood else "warning-sign"

        popup_html = f"""
        <div style="font-family: Arial; min-width: 180px;">
            <h4><b>{item['defect_type']}</b></h4>
            <p><b>Severity:</b> {item['severity']}</p>
            <p><b>Flood Hotspot:</b> {'YES' if is_flood else 'NO'}</p>
            <p><b>Elevation:</b> {item['elevation']} m</p>
            <p><b>Address:</b> {item['address']}</p>
            <a href="{route_url}" target="_blank" style="color: blue; text-decoration: underline;">Open Turn-by-Turn Navigation</a>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{item['defect_type']} ({item['severity']})",
            icon=folium.Icon(color=marker_color, icon=icon_type),
        ).add_to(folium_map)

    folium_map.save(output_html_path)
    return output_html_path