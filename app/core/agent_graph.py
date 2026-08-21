from math import radians, sin, cos, sqrt, atan2
from typing import TypedDict, Optional

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from .config import DUPLICATE_DISTANCE_METERS


class Report(BaseModel):
    report_id: str
    latitude: float
    longitude: float
    defect_type: str
    severity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    status: str = "pending"
    road_type: str = "unknown"
    traffic_level: str = "medium"
    rainfall_risk: str = "medium"
    cluster_count: int = Field(default=1, ge=1)


class DuplicateResult(BaseModel):
    is_duplicate: bool = False
    matched_report_id: Optional[str] = None
    distance_m: Optional[float] = None
    cluster_count: int = 1


class MaterialEstimate(BaseModel):
    asphalt_kg: float = 0
    gravel_kg: float = 0
    concrete_kg: float = 0


class WorkOrder(BaseModel):
    work_order_id: str
    report_id: str
    defect_type: str
    priority_score: float
    urgency: str
    material_estimate: MaterialEstimate
    required_crew_hours: float
    recommended_crew_size: int
    cluster_count: int
    status: str = "PENDING"


class AgentOutput(BaseModel):
    report: Report
    duplicate: DuplicateResult
    priority_score: float
    urgency: str
    work_order: WorkOrder


class UrbanPulseState(TypedDict, total=False):
    report: Report
    existing_reports: list[Report]

    duplicate: DuplicateResult

    priority_score: float
    urgency: str

    material_estimate: MaterialEstimate
    required_crew_hours: float
    recommended_crew_size: int

    work_order: WorkOrder
    final_output: AgentOutput

    error: Optional[str]


# ============================================================
# 1. GEOGRAPHIC DISTANCE
# ============================================================

def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate the distance between two latitude/longitude
    coordinates using the Haversine formula.

    Returns:
        Distance in meters.
    """

    earth_radius = 6371000

    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)

    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad)
        * cos(lat2_rad)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius * c


# ============================================================
# 2. SPATIAL DEDUPLICATION
# ============================================================

def find_duplicate(
    report: Report,
    existing_reports: list[Report]
) -> DuplicateResult:
    """
    Find whether a new report is a spatial duplicate.

    Rule:
        Only pending reports are considered.

        If distance < 15 meters:
            duplicate = True
            cluster count is incremented.

        If distance >= 15 meters:
            report is treated as a new report.
    """

    for existing in existing_reports:

        if existing.status.lower() != "pending":
            continue

        distance = calculate_distance(
            report.latitude,
            report.longitude,
            existing.latitude,
            existing.longitude
        )

        if distance < DUPLICATE_DISTANCE_METERS:

            new_cluster_count = existing.cluster_count + 1

            return DuplicateResult(
                is_duplicate=True,
                matched_report_id=existing.report_id,
                distance_m=round(distance, 2),
                cluster_count=new_cluster_count
            )

    return DuplicateResult(
        is_duplicate=False,
        matched_report_id=None,
        distance_m=None,
        cluster_count=report.cluster_count
    )


def merge_duplicate(
    report: Report,
    duplicate: DuplicateResult,
    existing_reports: list[Report]
) -> Report:
    """
    Merge a duplicate report into the matched pending report.

    The original report object is not modified directly.
    """

    if not duplicate.is_duplicate:
        return report

    for existing in existing_reports:

        if existing.report_id == duplicate.matched_report_id:

            merged_report = existing.model_copy(
                update={
                    "cluster_count": duplicate.cluster_count
                }
            )

            return merged_report

    return report


# ============================================================
# 3. DETERMINISTIC PRIORITY
# ============================================================

def calculate_priority(report: Report) -> float:
    """
    Deterministic priority calculation.

    IMPORTANT:
    Replace the formula inside this function with the exact
    official hackathon formula if your guide provides one.

    Current implementation uses:
        severity
        confidence
        traffic level
        rainfall risk
        cluster count
        road type

    Output:
        Priority score from 0 to 100.
    """

    severity_score = report.severity * 40

    confidence_score = report.confidence * 10

    traffic_weights = {
        "low": 5,
        "medium": 10,
        "high": 20
    }

    rainfall_weights = {
        "low": 0,
        "medium": 5,
        "high": 10
    }

    road_weights = {
        "residential": 2,
        "local": 2,
        "main": 5,
        "highway": 10,
        "unknown": 3
    }

    traffic_score = traffic_weights.get(
        report.traffic_level.lower(),
        10
    )

    rainfall_score = rainfall_weights.get(
        report.rainfall_risk.lower(),
        5
    )

    road_score = road_weights.get(
        report.road_type.lower(),
        3
    )

    cluster_score = min(
        max(report.cluster_count - 1, 0) * 3,
        15
    )

    score = (
        severity_score
        + confidence_score
        + traffic_score
        + rainfall_score
        + road_score
        + cluster_score
    )

    return round(min(score, 100), 2)


# ============================================================
# 4. URGENCY
# ============================================================

def calculate_urgency(priority_score: float) -> str:
    """
    Convert priority score into an urgency category.
    """

    if priority_score >= 80:
        return "CRITICAL"

    if priority_score >= 60:
        return "HIGH"

    if priority_score >= 40:
        return "MEDIUM"

    return "LOW"


# ============================================================
# 5. MATERIAL ESTIMATION
# ============================================================

def estimate_material(
    report: Report
) -> MaterialEstimate:
    """
    Estimate required material based on defect type and severity.

    This is a deterministic simulation for the hackathon.
    """

    severity = report.severity

    defect = report.defect_type.lower()

    if defect == "pothole":
        return MaterialEstimate(
            asphalt_kg=round(100 * severity, 2),
            gravel_kg=round(40 * severity, 2),
            concrete_kg=0
        )

    if defect == "road_crack":
        return MaterialEstimate(
            asphalt_kg=round(60 * severity, 2),
            gravel_kg=round(20 * severity, 2),
            concrete_kg=0
        )

    if defect == "broken_road":
        return MaterialEstimate(
            asphalt_kg=round(180 * severity, 2),
            gravel_kg=round(80 * severity, 2),
            concrete_kg=round(50 * severity, 2)
        )

    if defect == "waterlogging":
        return MaterialEstimate(
            asphalt_kg=round(40 * severity, 2),
            gravel_kg=round(100 * severity, 2),
            concrete_kg=round(80 * severity, 2)
        )

    return MaterialEstimate(
        asphalt_kg=round(50 * severity, 2),
        gravel_kg=round(20 * severity, 2),
        concrete_kg=round(10 * severity, 2)
    )


# ============================================================
# 6. CREW ESTIMATION
# ============================================================

def estimate_crew(
    report: Report,
    priority_score: float
) -> tuple[float, int]:
    """
    Estimate crew hours and crew size.
    """

    base_hours = {
        "pothole": 2.0,
        "road_crack": 2.5,
        "broken_road": 6.0,
        "waterlogging": 5.0
    }

    defect = report.defect_type.lower()

    hours = base_hours.get(defect, 3.0)

    hours = hours * (0.5 + report.severity)

    if report.cluster_count >= 3:
        hours += 1.0

    if priority_score >= 80:
        crew_size = 4
    elif priority_score >= 60:
        crew_size = 3
    else:
        crew_size = 2

    return round(hours, 2), crew_size


# ============================================================
# 7. WORK ORDER
# ============================================================

def create_work_order(
    report: Report,
    priority_score: float,
    urgency: str,
    material_estimate: MaterialEstimate,
    crew_hours: float,
    crew_size: int
) -> WorkOrder:

    work_order_id = f"WO-{report.report_id}"

    return WorkOrder(
        work_order_id=work_order_id,
        report_id=report.report_id,
        defect_type=report.defect_type,
        priority_score=priority_score,
        urgency=urgency,
        material_estimate=material_estimate,
        required_crew_hours=crew_hours,
        recommended_crew_size=crew_size,
        cluster_count=report.cluster_count,
        status="PENDING"
    )


# ============================================================
# 8. LANGGRAPH NODES
# ============================================================

def validate_node(
    state: UrbanPulseState
) -> UrbanPulseState:

    if "report" not in state:
        return {
            "error": "Report data is missing."
        }

    if "existing_reports" not in state:
        state["existing_reports"] = []

    return state


def route_after_validation(state: UrbanPulseState) -> str:
    """Route invalid input to graph termination before processing nodes."""

    if "error" in state:
        return "invalid"

    return "valid"


def deduplication_node(
    state: UrbanPulseState
) -> UrbanPulseState:

    report = state["report"]

    existing_reports = state.get(
        "existing_reports",
        []
    )

    duplicate = find_duplicate(
        report,
        existing_reports
    )

    merged_report = merge_duplicate(
        report,
        duplicate,
        existing_reports
    )

    return {
        **state,
        "report": merged_report,
        "duplicate": duplicate
    }


def priority_node(
    state: UrbanPulseState
) -> UrbanPulseState:

    report = state["report"]

    priority_score = calculate_priority(report)

    urgency = calculate_urgency(
        priority_score
    )

    return {
        **state,
        "priority_score": priority_score,
        "urgency": urgency
    }


def work_order_node(
    state: UrbanPulseState
) -> UrbanPulseState:

    report = state["report"]

    priority_score = state["priority_score"]

    urgency = state["urgency"]

    material_estimate = estimate_material(
        report
    )

    crew_hours, crew_size = estimate_crew(
        report,
        priority_score
    )

    work_order = create_work_order(
        report=report,
        priority_score=priority_score,
        urgency=urgency,
        material_estimate=material_estimate,
        crew_hours=crew_hours,
        crew_size=crew_size
    )

    return {
        **state,
        "material_estimate": material_estimate,
        "required_crew_hours": crew_hours,
        "recommended_crew_size": crew_size,
        "work_order": work_order
    }


def final_node(
    state: UrbanPulseState
) -> UrbanPulseState:

    output = AgentOutput(
        report=state["report"],
        duplicate=state["duplicate"],
        priority_score=state["priority_score"],
        urgency=state["urgency"],
        work_order=state["work_order"]
    )

    return {
        **state,
        "final_output": output
    }


# ============================================================
# 9. BUILD LANGGRAPH
# ============================================================

def build_agent_graph():
    """
    Build and compile the UrbanPulse agent graph.
    """

    graph = StateGraph(UrbanPulseState)

    graph.add_node(
        "validate",
        validate_node
    )

    graph.add_node(
        "deduplicate",
        deduplication_node
    )

    graph.add_node(
        "priority",
        priority_node
    )

    graph.add_node(
        "work_order",
        work_order_node
    )

    graph.add_node(
        "final",
        final_node
    )

    graph.add_edge(
        START,
        "validate"
    )

    graph.add_conditional_edges(
        "validate",
        route_after_validation,
        {
            "valid": "deduplicate",
            "invalid": END
        }
    )

    graph.add_edge(
        "deduplicate",
        "priority"
    )

    graph.add_edge(
        "priority",
        "work_order"
    )

    graph.add_edge(
        "work_order",
        "final"
    )

    graph.add_edge(
        "final",
        END
    )

    return graph.compile()


# ============================================================
# 10. COMPILED GRAPH
# ============================================================

agent_graph = build_agent_graph()


# ============================================================
# 11. PUBLIC FUNCTION FOR OTHER MODULES
# ============================================================

def process_report(
    report: Report,
    existing_reports: Optional[list[Report]] = None
) -> AgentOutput:

    if existing_reports is None:
        existing_reports = []

    initial_state: UrbanPulseState = {
        "report": report,
        "existing_reports": existing_reports
    }

    result = agent_graph.invoke(
        initial_state
    )

    if "error" in result:
        raise ValueError(
            result["error"]
        )

    return result["final_output"]