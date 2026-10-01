import os
import qrcode
from flask import current_app, has_request_context, request

def get_verification_url(appointment, base_url: str = None) -> str:
    """
    Constructs the absolute verification URL for an appointment's secure token.
    Contains NO sensitive patient PHI.
    """
    token = appointment.verification_token or str(appointment.appointment_uid)
    endpoint_path = f"/verify/appointment/{token}"
    
    if base_url:
        return f"{base_url.rstrip('/')}{endpoint_path}"
    
    if has_request_context():
        # Use request's host_url (e.g. http://localhost:5000/)
        return f"{request.host_url.rstrip('/')}{endpoint_path}"
    
    return f"http://127.0.0.1:5000{endpoint_path}"

def generate_appointment_qr_code(appointment, output_dir: str = None, base_url: str = None) -> str:
    """
    Generates a high-resolution QR code PNG encoding the public verification URL.
    Saves the file to the configured QR_CODES_DIR and returns the relative filename.
    """
    if not output_dir:
        if current_app:
            output_dir = current_app.config.get('QR_CODES_DIR')
        if not output_dir:
            output_dir = os.path.join(os.getcwd(), 'static', 'generated', 'qr_codes')
    
    os.makedirs(output_dir, exist_ok=True)
    
    file_identifier = appointment.appointment_number or appointment.appointment_uid or str(appointment.id)
    filename = f"qr_{file_identifier}.png"
    filepath = os.path.join(output_dir, filename)
    
    verification_url = get_verification_url(appointment, base_url=base_url)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#0f766e", back_color="white")
    img.save(filepath)
    
    return filename

def get_or_create_appointment_qr(appointment, base_url: str = None) -> tuple[str, str]:
    """
    Ensures a QR code exists on disk for the given appointment.
    Returns (filename, absolute_filepath).
    """
    output_dir = None
    if current_app:
        output_dir = current_app.config.get('QR_CODES_DIR')
    if not output_dir:
        output_dir = os.path.join(os.getcwd(), 'static', 'generated', 'qr_codes')
    
    os.makedirs(output_dir, exist_ok=True)
    
    file_identifier = appointment.appointment_number or appointment.appointment_uid or str(appointment.id)
    filename = f"qr_{file_identifier}.png"
    filepath = os.path.join(output_dir, filename)
    
    if not os.path.exists(filepath):
        filename = generate_appointment_qr_code(appointment, output_dir=output_dir, base_url=base_url)
        filepath = os.path.join(output_dir, filename)
        
    return filename, filepath
