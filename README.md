
# HACKATHON

# 🏙️ UrbanPulse AI
**Autonomous Urban Pothole, Structural Defect & Micro-Flooding Lifecycle Engine**

> **Problem Statement 10:** Moving from reactive municipal complaints to proactive lifecycle intelligence. 

UrbanPulse AI is a multi-agent, vision-powered system that ingests citizen dashcam/phone imagery, autonomously segments structural road defects, correlates them with GIS micro-flooding hotspots, and dispatches deduplicated work orders to municipal authorities.

## 🚀 Features
* **Multimodal Perception:** OpenCV/YOLO vision engine to estimate pothole surface area and severity (1-10 scale).
* **Automated Geocoding:** Extracts EXIF data and reverse-geocodes raw coordinates into human-readable street addresses using Nominatim.
* **Agentic Orchestration:** LangGraph state machine handles spatial deduplication (merging reports within 15 meters) and dynamic priority scoring.
* **Human-in-the-Loop Gateway:** Streamlit GIS dashboard for municipal supervisors to review, adjust, and approve agent-generated work orders.

## 🛠️ Architecture Stack
* **Frontend:** Streamlit + Folium (GIS Mapping)
* **Backend:** FastAPI (Python)
* **Agent Framework:** LangGraph
* **Computer Vision:** OpenCV
* **Data Storage:** SQLite (Local)

## 💻 Local Setup Instructions

**1. Clone the repository**
```bash
git clone [https://github.com/YourUsername/UrbanPulse-AI.git](https://github.com/YourUsername/UrbanPulse-AI.git)
cd UrbanPulse-AI

