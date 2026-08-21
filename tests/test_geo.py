import os
from app.geo.database import init_db, is_duplicate_complaint
from app.geo.geo_dispatch import (
    generate_google_maps_route,
    get_elevation_and_flood_risk,
    get_reverse_geocode,
    process_and_dispatch_defect,
    render_folium_map,
)


def run_all_tests():
    print("=" * 50)
    print("STARTING GIS & DISPATCH MODULE TESTS (MEMBER 3)")
    print("=" * 50)

    # Test Coordinates (Vadlamudi / Guntur region)
    test_lat = 16.2345
    test_lon = 80.5489

    # 1. Test Reverse Geocoding
    print("\n[1] Testing Reverse Geocoding...")
    address = get_reverse_geocode(test_lat, test_lon)
    print(f"    Result Address: {address}")
    assert address is not None and len(address) > 0
    print("    [PASS] Reverse Geocoding verified.")

    # 2. Test Elevation & Flood Risk
    print("\n[2] Testing Elevation & Flood Hazard Detection...")
    elevation, is_flood = get_elevation_and_flood_risk(test_lat, test_lon)
    print(f"    Elevation: {elevation} m | Flood Hotspot: {is_flood}")
    assert isinstance(elevation, float)
    print("    [PASS] Elevation & Flood Risk verified.")

    # 3. Test Google Maps Link
    print("\n[3] Testing Contractor Turn-by-Turn URL Generation...")
    route_url = generate_google_maps_route(test_lat, test_lon)
    print(f"    Route URL: {route_url}")
    assert "https://www.google.com/maps/dir/" in route_url
    print("    [PASS] Route URL verified.")

    # 4. Test Defect Processing & Duplicate Prevention
    print("\n[4] Testing Defect Ingestion & Duplicate Suppression...")
    first_report = process_and_dispatch_defect(
        defect_type="Severe Pothole",
        severity="High",
        lat=test_lat,
        lon=test_lon,
        contractor_email="contractor@cityworks.gov",
    )
    print(f"    First Insertion Status: {first_report.get('status')}")
    assert first_report.get("status") == "PROCESSED_AND_DISPATCHED"

    duplicate_report = process_and_dispatch_defect(
        defect_type="Severe Pothole",
        severity="High",
        lat=test_lat + 0.00001,  # ~1 meter away
        lon=test_lon + 0.00001,
        contractor_email="contractor@cityworks.gov",
    )
    print(f"    Duplicate Ingestion Status: {duplicate_report.get('status')}")
    assert duplicate_report.get("status") == "DUPLICATE_IGNORED"
    print("    [PASS] Duplicate suppression working.")

    # 5. Test Map Rendering
    print("\n[5] Testing Interactive Folium Map Generator...")
    map_output = render_folium_map(output_html_path="test_map.html")
    assert os.path.exists(map_output)
    print(f"    Interactive map generated at: {map_output}")
    print("    [PASS] Folium Map rendered successfully.")

    print("\n" + "=" * 50)
    print("ALL MEMBER 3 TESTS PASSED SUCCESSFULLY!")
    print("=" * 50)


if __name__ == "__main__":
    run_all_tests()