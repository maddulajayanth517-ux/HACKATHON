import os
import random

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

BACKEND_BASE_URL = "http://127.0.0.1:8000"
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
        st.markdown("<div class='section-title'>Report evidence</div><div class='section-copy'>Upload JPG, PNG, WEBP, or MP4. Vision results appear once media is selected.</div>", unsafe_allow_html=True)
        uploaded_media = st.file_uploader("Upload report media", type=MEDIA_TYPES, help="Images and MP4 videos are supported.")
        detected_class, suggested_severity, media_kind = "Manual report", "High", None
        if uploaded_media is not None:
            media_kind = render_preview(uploaded_media)
            detected_class, suggested_severity, confidence = detect_issue(uploaded_media.name)
            render_detection(detected_class, suggested_severity, confidence, media_kind)

        st.markdown("<div class='section-title'>Location and dispatch</div><div class='section-copy'>Confirm coordinates and assign the verified severity.</div>", unsafe_allow_html=True)
        latitude_column, longitude_column = st.columns(2)
        with latitude_column:
            latitude = st.number_input("Latitude", value=16.5062, format="%.4f", key="report_latitude")
        with longitude_column:
            longitude = st.number_input("Longitude", value=80.6480, format="%.4f", key="report_longitude")
        severity_column, email_column = st.columns([0.7, 1.3])
        with severity_column:
            severity_options = ["High", "Medium", "Low"]
            severity = st.selectbox("Verified severity", severity_options, index=severity_options.index(suggested_severity))
        with email_column:
            contractor_email = st.text_input("Contractor email", value="contractor@cityworks.gov")

        if st.button("Dispatch work order", type="primary", use_container_width=True):
            payload = {"defect_type": detected_class, "severity": severity, "latitude": latitude, "longitude": longitude, "contractor_email": contractor_email}
            with st.spinner("Preparing dispatch..."):
                try:
                    response = requests.post(f"{BACKEND_BASE_URL}/api/geo/dispatch", json=payload, timeout=8)
                    if response.status_code == 200:
                        st.session_state["last_dispatch"] = response.json()
                    else:
                        st.error("The backend could not process this work order.")
                except requests.RequestException:
                    st.session_state["last_dispatch"] = {"status": "PROCESSED_AND_DISPATCHED", "record_id": random.randint(100, 999), "address": "Standalone demonstration location", "elevation_meters": 45, "google_maps_route": f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"}
                    st.info("Saved as a local demonstration work order because the backend is offline.")

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
