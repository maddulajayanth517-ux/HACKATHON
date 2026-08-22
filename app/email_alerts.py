import smtplib
import os
from email.message import EmailMessage


def build_authority_alert_message(complaint_data: dict) -> tuple[str, str]:
    """Build the subject and body for a new complaint alert sent to the authority team.

    Args:
        complaint_data: Dictionary containing complaint metadata such as severity,
            location, reporter phone number, and estimated depth.

    Returns:
        A tuple of (subject, body) used by the email sender.
    """
    severity = complaint_data.get("severity_level", "UNKNOWN").upper()
    location = complaint_data.get("manual_address") or complaint_data.get(
        "location_address", "Unknown Location"
    )
    reporter_phone = complaint_data.get("reporter_phone", "Unknown")
    depth = complaint_data.get("estimated_depth_cm")
    depth_value = f"{depth} cm" if depth is not None else "Not available"

    subject = f"New {severity} pothole report requires verification"
    body = (
        f"A new {severity} pothole has been reported at {location} by user {reporter_phone}. "
        f"Estimated depth: {depth_value}. Please log into the UrbanPulse Authority Dashboard to verify and assign a contractor."
    )
    return subject, body


def alert_authority_via_email(complaint_data: dict, authority_email: str) -> bool:
    """Send an email notification to the authority when a citizen submits a new complaint.

    This is a standalone SMTP function intended for backend integration. Add your SMTP
    credentials to the environment or replace the placeholder values below in production.

    Args:
        complaint_data: Complaint payload from the public complaint form.
        authority_email: Email address of the authority team receiving the alert.

    Returns:
        True if the message was sent successfully, otherwise False.
    """
    subject, body = build_authority_alert_message(complaint_data)

    smtp_server = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USER") or os.getenv("APP_EMAIL", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_username)

    if not smtp_username or not smtp_password:
        print(
            f"[DEMO EMAIL] from={smtp_from or 'Smart City Complaint System'} "
            f"to={authority_email} subject={subject}"
        )
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = authority_email
    msg.set_content(body)

    # Optional HTML version for more polished email formatting.
    msg.add_alternative(
        """
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2937;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e5e7eb; border-radius: 12px; background-color: #f9fafb;">
              <h2 style="color: #111827; margin-bottom: 12px;">UrbanPulse-AI Authority Alert</h2>
              <p style="margin: 0 0 12px;">
                {body}
              </p>
              <p style="margin-top: 16px; color: #374151;">
                This alert was generated automatically after a new public complaint submission.
              </p>
            </div>
          </body>
        </html>
        """.format(body=body),
        subtype="html",
    )

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        # In production, log this exception with your normal app logger.
        return False
