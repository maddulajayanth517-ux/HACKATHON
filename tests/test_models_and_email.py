from app.email_alerts import build_authority_alert_message


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
