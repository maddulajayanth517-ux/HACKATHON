import folium
from streamlit_folium import st_folium

def render_infrastructure_map(lat=16.3067, lon=80.4365, incidents=None):
    m = folium.Map(location=[lat, lon], zoom_start=13, tiles="CartoDB positron")
    
    if not incidents:
        incidents = [
            {"id": "UP-1048", "lat": 16.3067, "lon": 80.4365, "type": "Pothole", "severity": "Critical"},
            {"id": "UP-1047", "lat": 16.3150, "lon": 80.4250, "type": "Waterlogging", "severity": "Moderate"},
            {"id": "UP-1046", "lat": 16.2980, "lon": 80.4480, "type": "Road Crack", "severity": "Low"}
        ]
        
    color_map = {"Critical": "red", "Moderate": "orange", "Low": "blue"}

    for inc in incidents:
        folium.Marker(
            location=[inc["lat"], inc["lon"]],
            tooltip=f"Report ID: {inc['id']}",
            popup=f"<b>ID:</b> {inc['id']}<br><b>Type:</b> {inc['type']}<br><b>Severity:</b> {inc['severity']}",
            icon=folium.Icon(color=color_map.get(inc.get("severity"), "blue"), icon="warning-sign")
        ).add_to(m)

    return st_folium(m, width=None, height=360)