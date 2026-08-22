from app.models import Authority, Base, Complaint, ComplaintStatus, Contractor
from app.email_alerts import build_authority_alert_message
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_sqlalchemy_models_map_relationships():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        authority = Authority(
            username="city_ops",
            email="ops@urbanpulse.gov",
            password_hash="hashed_password",
            department="Public Works",
        )
        contractor = Contractor(
            company_name="MetroFix Contractors",
            email="contact@metrofix.com",
            phone="+15551234567",
            password_hash="contractor_hash",
        )
        complaint = Complaint(
            reporter_phone="+15557654321",
            location_lat=17.3871,
            location_lon=78.4867,
            manual_address="Near MG Road, Hyderabad",
            severity_level="HIGH",
            estimated_depth_cm=18.5,
            status=ComplaintStatus.PENDING_VERIFICATION,
            authority=authority,
            contractor=contractor,
        )

        session.add_all([authority, contractor, complaint])
        session.commit()
        session.refresh(complaint)

        assert complaint.authority.email == "ops@urbanpulse.gov"
        assert complaint.contractor.company_name == "MetroFix Contractors"
        assert complaint.status == ComplaintStatus.PENDING_VERIFICATION


def test_email_message_contains_required_authority_alert():
    complaint_data = {
        "severity_level": "HIGH",
        "manual_address": "Main Street, Telangana",
        "reporter_phone": "+919876543210",
        "estimated_depth_cm": 16,
    }

    subject, body = build_authority_alert_message(complaint_data)

    assert "New HIGH pothole report requires verification" in subject
    assert (
        "A new HIGH pothole has been reported at Main Street, Telangana by user +919876543210. "
        "Estimated depth: 16 cm. Please log into the UrbanPulse Authority Dashboard to verify and assign a contractor."
    ) in body
