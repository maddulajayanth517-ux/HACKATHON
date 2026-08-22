import os
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_geolocation import streamlit_geolocation
from PIL import Image

BACKEND_BASE_URL = "http://127.0.0.1:8001"
MEDIA_TYPES = ["jpg", "jpeg", "png", "webp", "mp4"]
VIDEO_TYPES = {"mp4"}

st.set_page_config(page_title="UrbanPulse AI", page_icon="UP", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root { --accent: #12b76a; --ink: #152238; --muted: #667085; }
.stApp { background: #f6f8fb; color: var(--ink); }
.block-container { max-width: 1440px; padding: 2.25rem 3rem 3rem; }
[data-testid="stSidebar"] { background: #10233f; }
[data-testid="stSidebar"] * { color: #f5f8ff; }
[data-testid="stSidebar"] .stCaption { color: #b7c6da !important; }
[data-testid="stSidebar"] .stRadio label { border-radius: 6px; padding: 0.25rem 0.15rem; }
[data-testid="stSidebar"] .stRadio label:hover { background: #1b365b; }
h1, h2, h3 { color: #152238; letter-spacing: 0 !important; }
h1 { font-size: 2.35rem !important; margin-bottom: 0.25rem !important; }
.eyebrow { color: #0c8d54; font-weight: 700; font-size: 0.78rem; letter-spacing: 0.08rem; text-transform: uppercase; }
.page-subtitle { color: #667085; margin: 0 0 1.75rem; font-size: 1rem; }
.section-title { color: #152238; font-size: 1.2rem; font-weight: 700; margin: 0 0 0.35rem; }
.section-copy { color: #667085; font-size: 0.9rem; margin-bottom: 1rem; }
.ai-result { background: #edfcf3; border: 1px solid #a6e8c2; border-left: 5px solid #12b76a; border-radius: 6px; padding: 1rem 1.1rem; margin: 1rem 0 1.25rem; }
.ai-result-title { color: #087443; font-size: 0.96rem; font-weight: 700; margin-bottom: 0.35rem; }
.ai-result p { margin: 0; color: #27553d; font-size: 0.93rem; }
.status-online { background: #eafaf1; color: #087443; border: 1px solid #b9ebce; border-radius: 6px; padding: 0.65rem 0.75rem; font-size: 0.9rem; }
.status-offline { background: #fff4e8; color: #9a4c08; border: 1px solid #f5c896; border-radius: 6px; padding: 0.65rem 0.75rem; font-size: 0.9rem; }
.map-placeholder { background: #fff; border: 1px solid #dbe3ee; border-radius: 8px; min-height: 360px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; color: #667085; padding: 1.1rem; }
div.stButton > button { border-radius: 6px; font-weight: 650; min-height: 2.8rem; }
[data-testid="stFileUploader"] { background: #fff; border: 1px dashed #9aaec6; border-radius: 8px; padding: 0.35rem; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #dbe3ee; border-radius: 8px; padding: 0.85rem; }
[data-testid="stTextArea"] textarea { background: #fff !important; color: #152238 !important; caret-color: #152238 !important; }
[data-testid="stTextInput"] input { background: #fff !important; color: #152238 !important; caret-color: #152238 !important; }
[data-testid="stNumberInput"] input { background: #fff !important; color: #152238 !important; caret-color: #152238 !important; }
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { background: #fff !important; color: #152238 !important; }
[data-testid="stSelectbox"] input { color: #152238 !important; }
[data-testid="stMetric"] label, [data-testid="stMetricLabel"] { color: #667085 !important; }
[data-testid="stMetricValue"] { color: #152238 !important; }
[data-testid="stMetricDelta"] { color: #087443 !important; }
[data-testid="stAlert"] { color: #152238 !important; }
.role-panel { background: #fff; border: 1px solid #dbe3ee; border-radius: 8px; padding: 1.35rem; min-height: 155px; }
.role-panel h3 { margin: 0 0 0.45rem; color: #152238; font-size: 1.05rem; }
.role-panel p { margin: 0 0 1rem; color: #667085; font-size: 0.9rem; }
.session-banner { background: #eafaf1; border: 1px solid #b9ebce; color: #087443; border-radius: 6px; padding: 0.65rem 0.8rem; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)


def geocode_manual_address(address: str):
    """Converts a text address to (lat, lon) using OpenStreetMap."""
    if not address or not address.strip():
        return None, None
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "UrbanPulse-AI-Hackathon-Client"}
    params = {"q": address.strip(), "format": "json", "limit": 1}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None


def fetch_defects():
    try:
        response = requests.get(f"{BACKEND_BASE_URL}/api/geo/defects", timeout=3)
        if response.status_code == 200:
            return response.json().get("defects", [])
    except requests.RequestException:
        pass
    return []


def backend_is_available():
    try:
        return requests.get(f"{BACKEND_BASE_URL}/api/geo/defects", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def render_dynamic_map(lat=None, lon=None, label="Reported Location", height=520):
    """Renders map centered dynamically on current target coordinates or falls back to backend file."""
    if lat is not None and lon is not None:
        leaflet_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>html, body, #map {{ height: 100%; width: 100%; margin: 0; padding: 0; }}</style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                const map = L.map('map').setView([{lat}, {lon}], 16);
                L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '&copy; OpenStreetMap contributors'
                }}).addTo(map);
                L.marker([{lat}, {lon}]).addTo(map)
                    .bindPopup('<b>{label}</b><br>Lat: {lat:.5f}, Lon: {lon:.5f}')
                    .openPopup();
            </script>
        </body>
        </html>
        """
        components.html(leaflet_html, height=height)
    elif os.path.exists("dispatch_map.html"):
        with open("dispatch_map.html", "r", encoding="utf-8") as map_file:
            components.html(map_file.read(), height=height)
    else:
        st.markdown("<div class='map-placeholder'><strong>Map data is not available yet</strong>Dispatch a report to populate the city map.</div>", unsafe_allow_html=True)


def render_preview(media):
    extension = media.name.rsplit(".", 1)[-1].lower()
    if extension in VIDEO_TYPES:
        st.video(media)
        return "video"
    st.image(Image.open(media), caption=media.name, use_container_width=True)
    return "image"


def analyze_uploaded_media(media, latitude, longitude, manual_address, severity, reporter_phone):
    files = {
        "media": (media.name, media.getvalue(), media.type or "application/octet-stream")
    }
    data = {"severity": severity, "manual_address": manual_address, "reporter_phone": reporter_phone}
    if latitude is not None and longitude is not None:
        data.update({"latitude": latitude, "longitude": longitude})
    return requests.post(
        f"{BACKEND_BASE_URL}/api/report/analyze",
        files=files,
        data=data,
        timeout=300,
    )


def api_request(method, path, **kwargs):
    try:
        return requests.request(method, f"{BACKEND_BASE_URL}{path}", timeout=10, **kwargs)
    except requests.RequestException as error:
        st.error(f"Backend unavailable: {error}")
        return None


if "user_role" not in st.session_state:
    st.session_state["user_role"] = None


def render_login_screen():
    """Keep role selection explicit before exposing any workspace navigation."""
    st.markdown("<div class='eyebrow'>UrbanPulse AI</div>", unsafe_allow_html=True)
    st.title("Report safer streets")
    st.markdown(
        "<div class='page-subtitle'>Choose how you want to use the platform.</div>",
        unsafe_allow_html=True,
    )
    citizen_column, authority_column = st.columns(2, gap="large")
    with citizen_column:
        st.markdown(
            "<div class='role-panel'><h3>Citizen</h3>"
            "<p>File a road-damage complaint, add its location, and track progress.</p></div>",
            unsafe_allow_html=True,
        )
        if st.button("Continue as citizen", type="primary", use_container_width=True):
            st.session_state["user_role"] = "citizen"
            st.rerun()
    with authority_column:
        st.markdown(
            "<div class='role-panel'><h3>Municipal authority</h3>"
            "<p>Sign in with your verified staff account to review and manage complaints.</p></div>",
            unsafe_allow_html=True,
        )
        with st.form("authority_login_form"):
            identifier = st.text_input("Username or email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Authority sign in", use_container_width=True)
            if submitted:
                response = api_request(
                    "POST",
                    "/api/auth/login",
                    json={"role": "authority", "identifier": identifier, "password": password},
                )
                if response is not None and response.status_code == 200:
                    st.session_state["user_role"] = "authority"
                    st.session_state["staff_session"] = response.json()
                    st.rerun()
                elif response is not None:
                    st.error(response.json().get("detail", "Invalid authority credentials."))
    st.divider()
    st.caption("Citizen access requires no account. Authority access is restricted to verified credentials.")


if st.session_state["user_role"] is None:
    render_login_screen()
    st.stop()


defects_list = fetch_defects()

with st.sidebar:
    st.markdown("## UrbanPulse AI")
    role_label = "Citizen workspace" if st.session_state["user_role"] == "citizen" else "Authority workspace"
    st.caption(role_label)
    st.divider()
    if st.session_state["user_role"] == "citizen":
        pages = ["New Report", "Track Complaint"]
    else:
        pages = ["Dashboard", "Reports", "Map View", "Work Orders", "Analytics"]
    page = st.radio("Workspace", pages, index=0, label_visibility="collapsed")
    st.divider()
    if st.session_state["user_role"] == "authority":
        st.markdown("<div class='session-banner'>Verified authority session</div>", unsafe_allow_html=True)
    status_css = "status-online" if backend_is_available() else "status-offline"
    status_text = "Backend connected" if status_css == "status-online" else "Standalone mode: backend offline"
    st.markdown(f"<div class='{status_css}'>{status_text}</div>", unsafe_allow_html=True)
    if st.button("Sign out", use_container_width=True):
        st.session_state.pop("staff_session", None)
        st.session_state["user_role"] = None
        st.rerun()


if page == "New Report":
    st.markdown("<div class='eyebrow'>Municipal operations</div>", unsafe_allow_html=True)
    st.title("Submit an infrastructure report")
    st.markdown("<div class='page-subtitle'>Add a photo or short MP4 video, verify the location, and send a work order.</div>", unsafe_allow_html=True)
    report_column, map_column = st.columns([1.08, 0.92], gap="large")

    with report_column:
        st.markdown("<div class='section-title'>Report evidence</div><div class='section-copy'>Upload a photo or MP4 video. The backend will analyze the actual media.</div>", unsafe_allow_html=True)
        uploaded_media = st.file_uploader("Upload report media", type=MEDIA_TYPES, help="Images and MP4 videos are supported.")
        if uploaded_media is not None:
            render_preview(uploaded_media)

        st.markdown("<div class='section-title'>Location permission</div><div class='section-copy'>Allow location access if you are at the reported place. Otherwise enter its address manually.</div>", unsafe_allow_html=True)
        location = streamlit_geolocation()
        latitude = location.get("latitude") if location else None
        longitude = location.get("longitude") if location else None

        active_lat, active_lon = latitude, longitude

        if latitude is not None and longitude is not None:
            st.success(f"Location permission granted: {latitude:.6f}, {longitude:.6f}")
            manual_address = ""
        else:
            st.info("Location was not granted or is unavailable. Manual address is required.")
            manual_address = st.text_input("Reported place or address", value="4th Cross Road, Koramangala 3rd Block, Bangalore, Karnataka 560034, India")
            if manual_address.strip():
                geo_lat, geo_lon = geocode_manual_address(manual_address)
                if geo_lat and geo_lon:
                    active_lat, active_lon = geo_lat, geo_lon

        severity_options = ["High", "Medium", "Low"]
        severity = st.selectbox("Suggested severity", severity_options, index=0)
        reporter_phone = st.text_input("Your phone number", placeholder="Used only to track this complaint")

        if st.button("Analyze uploaded media", type="primary", use_container_width=True):
            if uploaded_media is None:
                st.error("Upload a photo or video first.")
            elif active_lat is None and not manual_address.strip():
                st.error("Grant location permission or enter the reported address.")
            else:
                with st.spinner("Analyzing media and resolving location..."):
                    try:
                        if not reporter_phone.strip():
                            st.error("Enter a phone number so you can track the complaint.")
                            response = None
                        else:
                            response = analyze_uploaded_media(uploaded_media, active_lat, active_lon, manual_address, severity, reporter_phone)
                        if response is not None and response.status_code == 200:
                            analysis_result = response.json()
                            st.session_state["analysis"] = analysis_result
                            complaint = analysis_result.get("complaint", {})
                            if complaint.get("id") is not None:
                                st.session_state["last_complaint_id"] = complaint["id"]
                                st.session_state["last_reporter_phone"] = reporter_phone.strip()
                            requests.get(f"{BACKEND_BASE_URL}/api/geo/map", timeout=5)
                            st.rerun()
                        elif response is not None:
                            st.error(response.json().get("detail", "The backend could not analyze this media."))
                    except requests.RequestException as error:
                        st.error(f"Backend unavailable: {error}")

        analysis = st.session_state.get("analysis")
        if analysis:
            if analysis.get("status") == "NO_DEFECT_DETECTED":
                st.success(analysis.get("message", "No defect was confirmed."))
            else:
                vision = analysis.get("vision", {})
                st.success(f"Confirmed: {vision.get('defect_type', 'Road defect')} | severity {severity}")
                estimate_columns = st.columns(2)
                estimate_columns[0].metric("AI severity", vision.get("severity_level") or "Unavailable")
                depth = vision.get("estimated_depth_cm")
                estimate_columns[1].metric("Estimated depth", f"~{depth} cm" if depth is not None else "Unavailable")
                if vision.get("email_report_string"):
                    st.info(vision["email_report_string"])
                complaint = analysis.get("complaint", {})
                if complaint.get("id") is not None:
                    st.success(f"Complaint registered: #{complaint['id']}. Save this ID to track progress.")
                st.caption(f"Address: {analysis.get('address')} | Flood risk: {'High' if analysis.get('is_flood_prone') else 'Normal'}")
                email = analysis.get("email", {})
                recipient = st.text_input("Municipal corporation email", placeholder="roads@municipality.gov")
                subject = st.text_input("Email subject", value=email.get("subject", "Infrastructure report"))
                body = st.text_area("Review and edit the generated email", value=email.get("body", ""), height=260)
                if recipient.strip():
                    gmail_url = "https://mail.google.com/mail/?view=cm&fs=1&to=" + quote(recipient)
                    gmail_url += "&su=" + quote(subject) + "&body=" + quote(body)
                    st.link_button("Open Gmail draft", gmail_url, use_container_width=True)

    with map_column:
        st.markdown("<div class='section-title'>Live city map</div><div class='section-copy'>Active reports and dispatch coverage update here.</div>", unsafe_allow_html=True)
        render_dynamic_map(lat=active_lat, lon=active_lon, label=manual_address or "Selected Location")

elif page == "Track Complaint":
    st.title("Track your complaint")
    complaint_id = st.number_input(
        "Complaint ID",
        min_value=1,
        step=1,
        value=int(st.session_state.get("last_complaint_id", 1)),
    )
    reporter_phone = st.text_input(
        "Phone number used in the report",
        value=st.session_state.get("last_reporter_phone", ""),
    )
    if st.button("Check status", type="primary"):
        response = api_request("GET", f"/api/complaints/{int(complaint_id)}", params={"reporter_phone": reporter_phone})
        if response is not None and response.status_code == 200:
            complaint = response.json()
            st.success(f"Complaint #{complaint['id']} is {complaint['status']}")
            columns = st.columns(3)
            columns[0].metric("Severity", complaint["severity_level"])
            columns[1].metric("Estimated depth", f"~{complaint['estimated_depth_cm']} cm" if complaint["estimated_depth_cm"] is not None else "Unavailable")
            columns[2].metric("Address", complaint["address"] or "Unavailable")
        elif response is not None:
            st.error(response.json().get("detail", "Complaint not found."))

elif page == "Dashboard":
    st.title("Infrastructure overview")
    total = len(defects_list)
    critical = sum(row.get("severity") in ["High", "Critical"] for row in defects_list)
    medium = sum(row.get("severity") == "Medium" for row in defects_list)
    flood = sum(row.get("is_flood_prone") in [1, True, "True"] for row in defects_list)
    for column, label, value in zip(st.columns(4), ["Recorded reports", "High priority", "Medium priority", "Flood-prone zones"], [total, critical, medium, flood]):
        column.metric(label, value)
    st.divider()
    render_dynamic_map(height=500)
    staff_session = st.session_state.get("staff_session")
    if staff_session:
        st.divider()
        st.subheader("Complaint review queue")
        headers = {"Authorization": f"Bearer {staff_session['access_token']}"}
        response = api_request("GET", "/api/authority/complaints", headers=headers)
        if response is not None and response.status_code == 200:
            complaints = response.json().get("complaints", [])
            if complaints:
                st.dataframe(pd.DataFrame(complaints), use_container_width=True)
                selected_id = st.number_input("Complaint ID to update", min_value=1, step=1)
                selected_status = st.selectbox(
                    "New complaint status",
                    ["PENDING_VERIFICATION", "IN_PROGRESS", "RESOLVED"],
                )
                if st.button("Update complaint status", type="primary"):
                    update = api_request(
                        "PATCH",
                        f"/api/authority/complaints/{int(selected_id)}",
                        headers=headers,
                        json={"status": selected_status},
                    )
                    if update is not None and update.status_code == 200:
                        st.success("Complaint status updated.")
                        st.rerun()
                    elif update is not None:
                        st.error(update.json().get("detail", "Update failed."))
            else:
                st.info("No complaints are waiting for review.")

elif page == "Reports":
    st.title("Recorded reports")
    st.dataframe(pd.DataFrame(defects_list), use_container_width=True) if defects_list else st.info("No recorded reports yet.")

elif page == "Map View":
    st.title("City map")
    if st.button("Refresh map"):
        try:
            requests.get(f"{BACKEND_BASE_URL}/api/geo/map", timeout=5)
            st.rerun()
        except requests.RequestException:
            st.warning("The backend is unavailable, so the map could not be refreshed.")
    render_dynamic_map(height=650)

elif page == "Work Orders":
    st.title("Work orders")
    if defects_list:
        report_frame = pd.DataFrame(defects_list)
        visible_columns = [column for column in ["id", "defect_type", "severity", "status", "reported_at", "address"] if column in report_frame.columns]
        st.dataframe(report_frame[visible_columns], use_container_width=True)
    else:
        st.info("No work orders have been dispatched yet.")

elif page == "Analytics":
    st.title("Defect analytics")
    if defects_list:
        report_frame = pd.DataFrame(defects_list)
        category_column, severity_column = st.columns(2)
        with category_column:
            if "defect_type" in report_frame:
                st.bar_chart(report_frame["defect_type"].value_counts())
        with severity_column:
            if "severity" in report_frame:
                st.bar_chart(report_frame["severity"].value_counts())
    else:
        st.info("Analytics will appear after the backend has stored reports.")

elif page == "Settings":
    st.title("System settings")
    st.text_input("FastAPI base URL", value=BACKEND_BASE_URL)