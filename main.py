import os
from flask import Blueprint, render_template, send_from_directory, current_app
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main public landing page showcasing Care Connect platform."""
    # Retrieve dynamic statistics for the landing page
    hospital_count = Hospital.query.count()
    doctor_count = Doctor.query.count()
    patient_count = Patient.query.count()
    appointment_count = Appointment.query.count()

    # Retrieve featured doctors
    featured_doctors = Doctor.query.filter_by(is_available=True).limit(3).all()

    return render_template(
        'index.html',
        hospital_count=hospital_count,
        doctor_count=doctor_count,
        patient_count=patient_count,
        appointment_count=appointment_count,
        featured_doctors=featured_doctors
    )

@main_bp.route('/about')
def about():
    """Platform overview and college project details."""
    return render_template('about.html')

@main_bp.route('/qr/<filename>')
def serve_qr(filename):
    """Serves generated verification QR code images."""
    qr_dir = current_app.config.get('QR_CODES_DIR')
    return send_from_directory(qr_dir, filename)

@main_bp.route('/verify/appointment/<token>')
def verify_appointment(token):
    """
    Public digital verification gateway accessed via scanning the appointment QR code.
    Safely displays appointment validity status and hospital/doctor scheduling details.
    Zero sensitive patient PHI is exposed.
    """
    appointment = Appointment.query.filter(
        (Appointment.verification_token == token) |
        (Appointment.appointment_uid == token)
    ).first()

    if not appointment:
        return render_template('verify_appointment.html', valid=False, token=token), 200

    return render_template(
        'verify_appointment.html',
        valid=True,
        appointment=appointment,
        hospital=appointment.hospital,
        doctor=appointment.doctor,
        doctor_user=appointment.doctor.user if appointment.doctor else None,
        status=appointment.status
    ), 200
