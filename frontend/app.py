import os
import random
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
.ai-result strong { color: #152238; }
.status-online { background: #eafaf1; color: #087443; border: 1px solid #b9ebce; border-radius: 6px; padding: 0.65rem 0.75rem; font-size: 0.9rem; }
.status-offline { background: #fff4e8; color: #9a4c08; border: 1px solid #f5c896; border-radius: 6px; padding: 0.65rem 0.75rem; font-size: 0.9rem; }
.map-placeholder { background: #fff; border: 1px solid #dbe3ee; border-radius: 8px; min-height: 360px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; color: #667085; padding: 1.1rem; }
.map-placeholder strong { color: #152238; font-size: 1rem; margin-bottom: 0.35rem; }
div.stButton > button { border-radius: 6px; font-weight: 650; min-height: 2.8rem; }
[data-testid="stFileUploader"] { background: #fff; border: 1px dashed #9aaec6; border-radius: 8px; padding: 0.35rem; }
[data-testid="stMetric"] { background: #fff; border: 1px solid #dbe3ee; border-radius: 8px; padding: 0.85rem; }
</style>
""", unsafe_allow_html=True)


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


def detect_issue(filename):
    """Temporary filename-based detection until the vision service is connected."""
    filename = filename.lower()
    if "crack" in filename:
        return "Road crack", "Medium", 0.88
    if "water" in filename or "wet" in filename or "flood" in filename:
        return "Waterlogging", "High", 0.91
    return "Pothole", "High", 0.94


def render_map(height=520):
    if os.path.exists("dispatch_map.html"):
        with open("dispatch_map.html", "r", encoding="utf-8") as map_file:
            components.html(map_file.read(), height=height)
    else:
        st.markdown("<div class='map-placeholder'><strong>Map data is not available yet</strong>Dispatch a report after connecting the backend to populate the city map.</div>", unsafe_allow_html=True)


def render_preview(media):
    extension = media.name.rsplit(".", 1)[-1].lower()
    if extension in VIDEO_TYPES:
        st.video(media)
        return "video"
    st.image(Image.open(media), caption=media.name, use_container_width=True)
    return "image"


def render_detection(defect_type, severity, confidence, media_kind):
    source = "video" if media_kind == "video" else "image"
    st.markdown(
        f"<div class='ai-result'><div class='ai-result-title'>Vision analysis complete</div>"
        f"<p><strong>{defect_type}</strong> detected from the uploaded {source}. Confidence <strong>{confidence * 100:.0f}%</strong> | Suggested severity <strong>{severity}</strong></p></div>",
        unsafe_allow_html=True,
    )


def analyze_uploaded_media(media, latitude, longitude, manual_address, severity):
    files = {
        "media": (media.name, media.getvalue(), media.type or "application/octet-stream")
    }
    data = {"severity": severity, "manual_address": manual_address}
    if latitude is not None and longitude is not None:
        data.update({"latitude": latitude, "longitude": longitude})
    return requests.post(
        f"{BACKEND_BASE_URL}/api/report/analyze",
        files=files,
        data=data,
        timeout=300,
    )


defects_list = fetch_defects()

with st.sidebar:
    st.markdown("## UrbanPulse AI")
    st.caption("Urban infrastructure intelligence")
    st.divider()
    page = st.radio("Workspace", ["New Report", "Dashboard", "Reports", "Map View", "Work Orders", "Analytics", "Settings"], index=0, label_visibility="collapsed")
    st.divider()
    status_css = "status-online" if backend_is_available() else "status-offline"
    status_text = "Backend connected" if status_css == "status-online" else "Standalone mode: backend offline"
    st.markdown(f"<div class='{status_css}'>{status_text}</div>", unsafe_allow_html=True)


if page == "New Report":
    st.markdown("<div class='eyebrow'>Municipal operations</div>", unsafe_allow_html=True)
    st.title("Submit an infrastructure report")
    st.markdown("<div class='page-subtitle'>Add a photo or short MP4 video, verify the location, and send a work order.</div>", unsafe_allow_html=True)
    report_column, map_column = st.columns([1.08, 0.92], gap="large")

    with report_column:
        st.markdown("<div class='section-title'>Report evidence</div><div class='section-copy'>Upload a photo or MP4 video. The backend will analyze the actual media.</div>", unsafe_allow_html=True)
        uploaded_media = st.file_uploader("Upload report media", type=MEDIA_TYPES, help="Images and MP4 videos are supported.")
        detected_class, suggested_severity, media_kind = "Road defect", "High", None
        if uploaded_media is not None:
            media_kind = render_preview(uploaded_media)

        st.markdown("<div class='section-title'>Location permission</div><div class='section-copy'>Allow location access if you are at the reported place. Otherwise enter its address manually.</div>", unsafe_allow_html=True)
        location = streamlit_geolocation()
        latitude = location.get("latitude") if location else None
        longitude = location.get("longitude") if location else None
        if latitude is not None and longitude is not None:
            st.success(f"Location permission granted: {latitude:.6f}, {longitude:.6f}")
            manual_address = ""
        else:
            st.info("Location was not granted or is unavailable. Manual address is required.")
            manual_address = st.text_input("Reported place or address", placeholder="Street, area, city")

        severity_options = ["High", "Medium", "Low"]
        severity = st.selectbox("Suggested severity", severity_options, index=0)

        if st.button("Analyze uploaded media", type="primary", use_container_width=True):
            if uploaded_media is None:
                st.error("Upload a photo or video first.")
            elif latitude is None and not manual_address.strip():
                st.error("Grant location permission or enter the reported address.")
            else:
                with st.spinner("Analyzing media and resolving location..."):
                    try:
                        response = analyze_uploaded_media(uploaded_media, latitude, longitude, manual_address, severity)
                        if response.status_code == 200:
                            st.session_state["analysis"] = response.json()
                        else:
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
                st.caption(f"Address: {analysis.get('address')} | Flood risk: {'High' if analysis.get('is_flood_prone') else 'Normal'}")
                email = analysis.get("email", {})
                recipient = st.text_input("Municipal corporation email", placeholder="roads@municipality.gov")
                subject = st.text_input("Email subject", value=email.get("subject", "Infrastructure report"))
                body = st.text_area("Review and edit the generated email", value=email.get("body", ""), height=260)
                if recipient.strip():
                    gmail_url = "https://mail.google.com/mail/?view=cm&fs=1&to=" + quote(recipient)
                    gmail_url += "&su=" + quote(subject) + "&body=" + quote(body)
                    st.link_button("Open Gmail draft", gmail_url, use_container_width=True)
                    st.caption("Gmail requires you to review and press Send. This app cannot send email without your explicit action.")

        if "last_dispatch" in st.session_state:
            dispatch = st.session_state["last_dispatch"]
            if dispatch.get("status") == "DUPLICATE_IGNORED":
                st.warning(dispatch.get("message", "A nearby duplicate report was found."))
            else:
                st.success(f"Work order #{dispatch.get('record_id')} dispatched")
                st.caption(f"{dispatch.get('address', 'Location pending')} | Elevation: {dispatch.get('elevation_meters', 'N/A')} m")
                if dispatch.get("google_maps_route"):
                    st.link_button("Open route in Google Maps", dispatch["google_maps_route"])

    with map_column:
        st.markdown("<div class='section-title'>Live city map</div><div class='section-copy'>Active reports and dispatch coverage update here.</div>", unsafe_allow_html=True)
        render_map()

elif page == "Dashboard":
    st.title("Infrastructure overview")
    total = len(defects_list)
    critical = sum(row.get("severity") in ["High", "Critical"] for row in defects_list)
    medium = sum(row.get("severity") == "Medium" for row in defects_list)
    flood = sum(row.get("is_flood_prone") in [1, True, "True"] for row in defects_list)
    for column, label, value in zip(st.columns(4), ["Recorded reports", "High priority", "Medium priority", "Flood-prone zones"], [total, critical, medium, flood]):
        column.metric(label, value)
    st.divider()
    render_map(500)

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
    render_map(650)

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
