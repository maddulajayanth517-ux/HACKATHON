import streamlit as st
from components.map_view import render_infrastructure_map
from components.sidebar import render_sidebar

st.set_page_config(page_title="UrbanPulse-AI", layout="wide")

selected_page = render_sidebar()

if selected_page in ["New Report", "Dashboard"]:
    # 1. Top KPI Summary Ribbon
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Reports", "248", "+12% this month")
    k2.metric("Critical Issues", "37", "High Priority")
    k3.metric("Moderate", "53")
    k4.metric("Flood Risk Areas", "18")

    st.divider()

    # 2. Main Grid: Citizen Report Feed (Left) & Map (Right)
    col_left, col_right = st.columns([1, 1.4])

    with col_left:
        st.subheader("1. Citizen Report")
        uploaded_file = st.file_uploader("Upload Infrastructure Image (JPG, PNG)", type=["jpg", "png", "jpeg"])
        
        st.markdown("""
        <div style="background-color: #1a1e29; padding: 14px; border-radius: 8px; border-left: 5px solid #FF4B4B;">
            <h4 style="color: #FF4B4B; margin: 0;">⚠️ CRITICAL POTHOLE DETECTED</h4>
            <p style="margin: 5px 0 0 0;"><b>Severity:</b> CRITICAL | <b>Confidence:</b> 92% | <b>Flood Risk:</b> High</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("**Resolved Address:**")
        st.caption("📍 Main Road, Near 7th Cross, Guntur, Andhra Pradesh - 522006, India")

    with col_right:
        st.subheader("2. Infrastructure Map")
        render_infrastructure_map()

    st.divider()

    # 3. Agent Reasoning Trace (LangGraph Member 2 integration)
    st.subheader("3. Agent Reasoning / Thought Trace")
    a1, a2, a3, a4, a5 = st.columns(5)
    
    with a1:
        st.markdown("**👁️ Vision Agent**")
        st.caption("Pothole detected (92% conf).")
        st.success("Completed")
    with a2:
        st.markdown("**🌐 GIS Agent**")
        st.caption("Reverse geocoded: Zone 3.")
        st.success("Completed")
    with a3:
        st.markdown("**📑 Duplicate Agent**")
        st.caption("Found 3 similar reports nearby.")
        st.success("Completed")
    with a4:
        st.markdown("**📊 Priority Agent**")
        st.caption("Priority score: 91/100.")
        st.success("Completed")
    with a5:
        st.markdown("**🛠️ Maintenance Agent**")
        st.caption("Road repair + drainage.")
        st.success("Completed")

    st.divider()

    # 4. Human-in-the-Loop Review
    st.subheader("4. Human-in-the-Loop Review")
    rev1, rev2 = st.columns([1.5, 1])
    with rev1:
        st.write("**Report ID:** UP-1048 | **Priority Score:** 91 / 100")
        st.write("**Assigned Dept:** Roads & Infrastructure | **Est. SLA:** 3 Days")
    with rev2:
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("✅ Authorize Work Order", type="primary", use_container_width=True):
                st.toast("Work order dispatched to field team!")
        with btn_c2:
            if st.button("❌ Reject", use_container_width=True):
                st.toast("Report flagged as false positive.")