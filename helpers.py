import os
import re
import qrcode
from datetime import datetime

def validate_email_format(email: str) -> bool:
    """Validates whether an email string adheres to a standard email format."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    # RFC 5322 simplified pattern
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return bool(re.match(pattern, email)) and '..' not in email and email.endswith(tuple(email.split('.')[-1])) and len(email.split('.')[-1]) >= 2

def generate_appointment_qr(appointment_uid: str, output_folder: str) -> str:
    """
    Generates a QR code image for digital appointment verification.
    Returns the relative filename of the generated QR code image.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    filename = f"qr_{appointment_uid}.png"
    filepath = os.path.join(output_folder, filename)

    if not os.path.exists(filepath):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=3,
        )
        # Digital verification payload
        verification_payload = f"CARECONNECT-APPT:{appointment_uid}"
        qr.add_data(verification_payload)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#0f766e", back_color="white")
        img.save(filepath)

    return filename

def format_date(dt, fmt: str = "%B %d, %Y") -> str:
    """Formats date or datetime object into a user-friendly string."""
    if not dt:
        return "N/A"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
    return dt.strftime(fmt)
