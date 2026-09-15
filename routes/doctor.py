from datetime import date, datetime
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from database import db
from models.user import User
from models.doctor import Doctor
from models.hospital import Hospital
from models.patient import Patient
from models.appointment import Appointment
from services.auth_service import role_required, get_current_user

doctor_bp = Blueprint('doctor', __name__)

def get_authenticated_doctor(current_user):
    """Helper to retrieve the Doctor record associated with the authenticated user."""
    if not current_user:
        return None
    return Doctor.query.filter_by(user_id=current_user.id).first()

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

# ============================================================================
# 1. DOCTOR DASHBOARD
# ============================================================================
@doctor_bp.route('/dashboard')
@role_required(User.ROLE_DOCTOR)
def dashboard():
    """Doctor Dashboard strictly displaying the authenticated doctor's schedule, metrics, and queue."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if not doctor:
        flash('Doctor profile not found for this account.', 'warning')
        return redirect(url_for('main.index'))

    today = date.today()

    # Query appointments belonging exclusively to this doctor
    all_appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(
        Appointment.appointment_date.asc(),
        Appointment.time_slot.asc()
    ).all()

    today_appointments = [a for a in all_appointments if a.appointment_date == today]
    upcoming_appointments = [
        a for a in all_appointments 
        if a.appointment_date > today and a.status in [Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED]
    ]

    # Unique patients who have had appointments with this doctor
    unique_patient_ids = set(a.patient_id for a in all_appointments)
    total_patients = len(unique_patient_ids)

    hospital = doctor.hospital

    return render_template(
        'dashboards/doctor.html',
        doctor=doctor,
        hospital=hospital,
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        all_appointments=all_appointments,
        total_patients=total_patients,
        today_count=len(today_appointments),
        upcoming_count=len(upcoming_appointments),
        total_patients_seen=len(all_appointments),
        appointments=all_appointments,
        user=current_user
    )

# ============================================================================
# 2. DOCTOR PROFILE (VIEW & EDIT)
# ============================================================================
@doctor_bp.route('/profile', methods=['GET', 'POST'])
@role_required(User.ROLE_DOCTOR)
def profile():
    """View and update doctor profile strictly for the authenticated doctor."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('doctor.dashboard'))

    hospitals = Hospital.query.order_by(Hospital.name.asc()).all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        specialization = request.form.get('specialization', '').strip()
        qualification = request.form.get('qualification', '').strip()
        experience_str = request.form.get('experience_years', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip().lower()
        fee_str = request.form.get('consultation_fee', '').strip()
        room_number = request.form.get('room_number', '').strip()
        hospital_id_str = request.form.get('hospital_id', '').strip()
        bio = request.form.get('bio', '').strip()

        # Validation
        errors = []
        if not full_name:
            errors.append('Doctor full name cannot be empty.')
        if not specialization:
            errors.append('Specialization cannot be empty.')
        if not qualification:
            errors.append('Qualification cannot be empty.')

        if not email or not EMAIL_REGEX.match(email):
            errors.append('Please provide a valid email address.')
        else:
            # Check email uniqueness against other users
            existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing_user:
                errors.append('Email address is already in use by another account.')

        # Experience validation
        try:
            experience_years = int(experience_str)
            if experience_years < 0:
                errors.append('Experience years cannot be negative.')
        except (ValueError, TypeError):
            errors.append('Experience years must be a valid number.')
            experience_years = doctor.experience_years

        # Fee validation
        try:
            consultation_fee = float(fee_str)
            if consultation_fee < 0:
                errors.append('Consultation fee cannot be negative.')
        except (ValueError, TypeError):
            errors.append('Consultation fee must be a valid number.')
            consultation_fee = doctor.consultation_fee

        # Hospital ID validation
        hospital_id = doctor.hospital_id
        if hospital_id_str:
            try:
                selected_hosp_id = int(hospital_id_str)
                hosp = db.session.get(Hospital, selected_hosp_id)
                if hosp:
                    hospital_id = selected_hosp_id
                else:
                    errors.append('Selected hospital facility was not found.')
            except (ValueError, TypeError):
                errors.append('Invalid hospital selection.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'dashboards/doctor_profile.html',
                doctor=doctor,
                hospitals=hospitals,
                form_data=request.form
            )

        # Apply updates
        current_user.full_name = full_name
        current_user.email = email
        if phone:
            current_user.phone = phone

        doctor.specialization = specialization
        doctor.qualification = qualification
        doctor.experience_years = experience_years
        doctor.consultation_fee = consultation_fee
        doctor.room_number = room_number or doctor.room_number
        doctor.hospital_id = hospital_id
        doctor.bio = bio

        db.session.commit()
        flash('Doctor profile updated successfully!', 'success')
        return redirect(url_for('doctor.profile'))

    return render_template(
        'dashboards/doctor_profile.html',
        doctor=doctor,
        hospitals=hospitals,
        hospital=doctor.hospital
    )

@doctor_bp.route('/profile/<int:target_doctor_id>', methods=['GET', 'POST'])
@role_required(User.ROLE_DOCTOR)
def cross_doctor_profile_block(target_doctor_id):
    """Explicitly blocks a doctor from viewing or editing another doctor's profile by ID."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)
    if not doctor or doctor.id != target_doctor_id:
        flash('Access Denied: You cannot view or modify another physician’s profile.', 'danger')
        abort(403)
    return redirect(url_for('doctor.profile'))

# ============================================================================
# 3. AVAILABILITY MANAGEMENT
# ============================================================================
@doctor_bp.route('/availability', methods=['GET', 'POST'])
@role_required(User.ROLE_DOCTOR)
def availability():
    """Doctor availability and weekly consultation schedule management."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('doctor.dashboard'))

    if request.method == 'POST':
        # Available switch
        is_available_val = request.form.get('is_available')
        doctor.is_available = True if is_available_val in ['1', 'true', 'on'] else False

        # Working days: check both multi-checkbox 'days' and text input 'available_days'
        selected_days = request.form.getlist('days')
        available_days_text = request.form.get('available_days', '').strip()

        if selected_days:
            doctor.available_days = ", ".join(selected_days)
        elif available_days_text:
            doctor.available_days = available_days_text

        # Working hours
        start_time = request.form.get('start_time', '').strip()
        end_time = request.form.get('end_time', '').strip()
        available_time_text = request.form.get('available_time', '').strip()

        if start_time and end_time:
            doctor.available_time = f"{start_time} - {end_time}"
        elif available_time_text:
            doctor.available_time = available_time_text

        db.session.commit()
        status_str = "Available" if doctor.is_available else "Away / Off-Duty"
        flash(f"Availability updated to {status_str} and schedule saved successfully!", 'success')
        return redirect(url_for('doctor.availability'))

    return render_template(
        'dashboards/doctor_availability.html',
        doctor=doctor,
        hospital=doctor.hospital
    )

@doctor_bp.route('/toggle-availability', methods=['POST'])
@role_required(User.ROLE_DOCTOR)
def toggle_availability():
    """Toggles doctor availability status for the authenticated doctor only."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if doctor:
        doctor.is_available = not doctor.is_available
        db.session.commit()
        status_text = "Available" if doctor.is_available else "Away / Off-Duty"
        flash(f"Availability status updated to: {status_text}", "info")

    next_page = request.referrer or url_for('doctor.dashboard')
    return redirect(next_page)

@doctor_bp.route('/availability/<int:target_doctor_id>', methods=['POST'])
@role_required(User.ROLE_DOCTOR)
def cross_doctor_availability_block(target_doctor_id):
    """Explicitly blocks a doctor from modifying another doctor's availability."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)
    if not doctor or doctor.id != target_doctor_id:
        flash('Access Denied: You cannot modify another physician’s availability.', 'danger')
        abort(403)
    return redirect(url_for('doctor.availability'))

# ============================================================================
# 4. APPOINTMENTS VIEW (TODAY, UPCOMING, PAST)
# ============================================================================
@doctor_bp.route('/appointments')
@role_required(User.ROLE_DOCTOR)
def appointments():
    """
    Doctor appointment management page with Today's, Upcoming, Completed, and Cancelled sections.
    Supports patient search and date/status filtering.
    """
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('doctor.dashboard'))

    today = date.today()
    search_patient = request.args.get('q', '').strip()
    date_filter = request.args.get('date', '').strip()
    status_filter = request.args.get('status', '').strip().lower()

    # Query strictly scoped to this doctor
    query = Appointment.query.filter_by(doctor_id=doctor.id)

    # Date filter
    if date_filter:
        try:
            parsed_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(Appointment.appointment_date == parsed_date)
        except ValueError:
            pass

    # Status filter
    if status_filter:
        if status_filter == 'today':
            query = query.filter(
                Appointment.appointment_date == today,
                Appointment.status.in_([Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED])
            )
        elif status_filter == 'upcoming':
            query = query.filter(
                Appointment.appointment_date > today,
                Appointment.status.in_([Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED])
            )
        elif status_filter == 'completed':
            query = query.filter(
                (Appointment.status == Appointment.STATUS_COMPLETED) |
                ((Appointment.appointment_date < today) & (Appointment.status != Appointment.STATUS_CANCELLED))
            )
        elif status_filter == 'cancelled':
            query = query.filter(Appointment.status == Appointment.STATUS_CANCELLED)
        else:
            query = query.filter(Appointment.status == status_filter)

    all_appointments = query.order_by(
        Appointment.appointment_date.asc(),
        Appointment.time_slot.asc()
    ).all()

    # Patient name / appointment number search
    if search_patient:
        sp = search_patient.lower()
        filtered = []
        for a in all_appointments:
            p_name = (a.patient.user.full_name if a.patient and a.patient.user else "").lower()
            appt_no = (a.appointment_number or "").lower()
            uid = (a.appointment_uid or "").lower()
            if sp in p_name or sp in appt_no or sp in uid:
                filtered.append(a)
        all_appointments = filtered

    today_appointments = [
        a for a in all_appointments 
        if a.appointment_date == today and a.status not in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
    ]
    upcoming_appointments = [
        a for a in all_appointments 
        if a.appointment_date > today and a.status not in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
    ]
    completed_appointments = [
        a for a in all_appointments 
        if a.status == Appointment.STATUS_COMPLETED or (a.appointment_date < today and a.status != Appointment.STATUS_CANCELLED)
    ]
    cancelled_appointments = [
        a for a in all_appointments 
        if a.status == Appointment.STATUS_CANCELLED
    ]

    return render_template(
        'dashboards/doctor_appointments.html',
        doctor=doctor,
        today=today,
        all_appointments=all_appointments,
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments,
        total_count=len(all_appointments),
        today_count=len(today_appointments),
        upcoming_count=len(upcoming_appointments),
        completed_count=len(completed_appointments),
        cancelled_count=len(cancelled_appointments),
        search_patient=search_patient,
        date_filter=date_filter,
        status_filter=status_filter
    )

@doctor_bp.route('/appointments/<int:appointment_id>/status', methods=['POST'])
@role_required(User.ROLE_DOCTOR)
def update_appointment_status(appointment_id):
    """
    Allows doctor to update consultation status (e.g. mark Confirmed or Completed).
    Strictly verifies ownership: doctor cannot modify another doctor's appointments (HTTP 403).
    Enforces appointment status lifecycle transitions.
    """
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)
    appointment = db.session.get(Appointment, appointment_id)

    if not appointment:
        abort(404)

    # Doctor ownership check
    if not doctor or appointment.doctor_id != doctor.id:
        flash('Access Denied: You cannot modify appointments assigned to another physician.', 'danger')
        abort(403)

    new_status = request.form.get('status', '').strip().lower()
    if new_status not in [Appointment.STATUS_CONFIRMED, Appointment.STATUS_COMPLETED]:
        flash('Invalid status update requested.', 'warning')
        return redirect(url_for('doctor.appointments'))

    can_transition, err_msg = appointment.can_transition_to(new_status)
    if not can_transition:
        flash(f"Status Update Failed: {err_msg}", 'danger')
        return redirect(url_for('doctor.appointments'))

    appointment.status = new_status
    db.session.commit()

    ref = appointment.appointment_number or appointment.appointment_uid[:8]
    flash(f"Appointment {ref} marked as {new_status.capitalize()} successfully.", 'success')
    return redirect(url_for('doctor.appointments'))

# ============================================================================
# 5. PATIENT HISTORY
# ============================================================================
@doctor_bp.route('/patients')
@role_required(User.ROLE_DOCTOR)
def patients():
    """Patient history based strictly on existing appointment records with this doctor."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('doctor.dashboard'))

    # Retrieve unique patients who have appointments with this doctor
    distinct_patients = Patient.query.join(Appointment, Appointment.patient_id == Patient.id)\
        .filter(Appointment.doctor_id == doctor.id)\
        .distinct().all()

    patient_records = []
    for p in distinct_patients:
        # Query appointment history with this doctor
        doctor_appts = Appointment.query.filter_by(
            doctor_id=doctor.id, 
            patient_id=p.id
        ).order_by(Appointment.appointment_date.desc()).all()

        last_visit = doctor_appts[0] if doctor_appts else None
        patient_records.append({
            'patient': p,
            'total_visits': len(doctor_appts),
            'last_visit': last_visit,
            'all_appointments': doctor_appts
        })

    return render_template(
        'dashboards/doctor_patients.html',
        doctor=doctor,
        patient_records=patient_records
    )

# ============================================================================
# 6. ASSOCIATED HOSPITAL INFORMATION
# ============================================================================
@doctor_bp.route('/hospital')
@role_required(User.ROLE_DOCTOR)
def hospital_info():
    """View doctor's associated hospital facility information."""
    current_user = get_current_user()
    doctor = get_authenticated_doctor(current_user)

    if not doctor:
        flash('Doctor profile not found.', 'danger')
        return redirect(url_for('doctor.dashboard'))

    hospital = doctor.hospital

    return render_template(
        'dashboards/doctor_hospital.html',
        doctor=doctor,
        hospital=hospital
    )
