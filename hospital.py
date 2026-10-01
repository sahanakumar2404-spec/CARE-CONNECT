import json
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from sqlalchemy import func, distinct
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.appointment import Appointment
from services.auth_service import role_required, get_current_user
from utils.helpers import validate_email_format

hospital_bp = Blueprint('hospital', __name__)

def get_authenticated_hospital(current_user):
    """Retrieves strictly the hospital facility owned by the current authenticated user."""
    if not current_user:
        return None
    return Hospital.query.filter_by(user_id=current_user.id).first()

@hospital_bp.route('/dashboard')
@role_required(User.ROLE_HOSPITAL)
def dashboard():
    """Hospital Management Dashboard - strictly scoped to the authenticated hospital."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)

    doctors = []
    appointments = []
    total_doctors = 0
    available_doctors = 0
    total_patients = 0
    today_appointments = 0
    upcoming_appointments = 0
    available_slots = 0
    specialty_counts = []
    status_counts = []

    if hospital:
        # 1. Doctors metrics
        doctors = Doctor.query.filter_by(hospital_id=hospital.id).all()
        total_doctors = len(doctors)
        available_doctors = sum(1 for d in doctors if d.is_available)

        # 2. Patients count (unique patients with appointments at this hospital)
        total_patients = (
            db.session.query(func.count(distinct(Appointment.patient_id)))
            .filter(Appointment.hospital_id == hospital.id)
            .scalar() or 0
        )

        # 3. Appointments metrics
        today = date.today()
        today_appointments = Appointment.query.filter(
            Appointment.hospital_id == hospital.id,
            Appointment.appointment_date == today
        ).count()

        upcoming_appointments = Appointment.query.filter(
            Appointment.hospital_id == hospital.id,
            Appointment.appointment_date >= today,
            Appointment.status.in_([Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED])
        ).count()

        # Calculated available slots based on active doctors (standard 8 consultation slots per day)
        available_slots = max(0, (available_doctors * 8) - today_appointments)

        # 4. Department / Specialization summary
        specialty_counts = (
            db.session.query(Doctor.specialization, func.count(Doctor.id))
            .filter(Doctor.hospital_id == hospital.id)
            .group_by(Doctor.specialization)
            .all()
        )

        # 5. Recent Appointments (strictly scoped)
        appointments = (
            Appointment.query.filter_by(hospital_id=hospital.id)
            .order_by(Appointment.appointment_date.desc())
            .limit(10)
            .all()
        )

        # 6. Appointment status distribution for analytics
        status_counts = (
            db.session.query(Appointment.status, func.count(Appointment.id))
            .filter(Appointment.hospital_id == hospital.id)
            .group_by(Appointment.status)
            .all()
        )

    # Prepare analytics payload as JSON for frontend Chart.js rendering
    analytics_data = {
        'specialties': {
            'labels': [s[0] for s in specialty_counts],
            'counts': [s[1] for s in specialty_counts]
        },
        'availability': {
            'labels': ['Available Doctors', 'Off-Duty Doctors'],
            'counts': [available_doctors, max(0, total_doctors - available_doctors)]
        },
        'appointment_status': {
            'labels': [sc[0].capitalize() for sc in status_counts],
            'counts': [sc[1] for sc in status_counts]
        }
    }

    ai_prediction = None
    if hospital:
        from ai.patient_load_predictor import predict_patient_load
        ai_prediction = predict_patient_load(hospital.id)

    return render_template(
        'dashboards/hospital.html',
        hospital=hospital,
        doctors=doctors,
        appointments=appointments,
        total_doctors=total_doctors,
        available_doctors=available_doctors,
        total_patients=total_patients,
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        available_slots=available_slots,
        specialty_counts=specialty_counts,
        analytics_json=json.dumps(analytics_data),
        ai_prediction=ai_prediction,
        user=current_user
    )

@hospital_bp.route('/profile', methods=['GET', 'POST'])
@role_required(User.ROLE_HOSPITAL)
def profile():
    """Views and manages the authenticated hospital's profile."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)

    if not hospital:
        flash('No hospital facility is currently associated with this account.', 'warning')
        return redirect(url_for('hospital.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        hospital_type = request.form.get('hospital_type', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        contact_email = request.form.get('contact_email', '').strip().lower()
        contact_phone = request.form.get('contact_phone', '').strip()
        total_beds_str = request.form.get('total_beds', '0').strip()
        available_beds_str = request.form.get('available_beds', '0').strip()
        emergency_available = request.form.get('emergency_available') == 'on'
        operational_status = request.form.get('operational_status', 'Normal Operations').strip()
        daily_notice = request.form.get('daily_notice', '').strip()

        # Validations
        if not name:
            flash('Hospital name cannot be empty.', 'danger')
            return render_template('dashboards/hospital_profile.html', hospital=hospital, user=current_user)

        if contact_email and not validate_email_format(contact_email):
            flash('Please provide a valid email format for hospital contact.', 'danger')
            return render_template('dashboards/hospital_profile.html', hospital=hospital, user=current_user)

        try:
            total_beds = max(0, int(total_beds_str))
            available_beds = max(0, int(available_beds_str))
        except ValueError:
            flash('Bed numbers must be valid integers.', 'danger')
            return render_template('dashboards/hospital_profile.html', hospital=hospital, user=current_user)

        if available_beds > total_beds:
            flash('Available beds cannot exceed total inpatient beds capacity.', 'danger')
            return render_template('dashboards/hospital_profile.html', hospital=hospital, user=current_user)

        # Update hospital entity
        hospital.name = name
        hospital.hospital_type = hospital_type or 'General Hospital'
        hospital.address = address
        hospital.city = city
        hospital.contact_email = contact_email
        hospital.contact_phone = contact_phone
        hospital.total_beds = total_beds
        hospital.available_beds = available_beds
        hospital.emergency_available = emergency_available
        hospital.operational_status = operational_status
        hospital.daily_notice = daily_notice

        # Keep current user's full_name updated to match hospital
        current_user.full_name = f"{name} Admin"
        if contact_phone:
            current_user.phone = contact_phone

        db.session.commit()
        flash('Hospital profile updated successfully!', 'success')
        return redirect(url_for('hospital.profile'))

    return render_template('dashboards/hospital_profile.html', hospital=hospital, user=current_user)

@hospital_bp.route('/doctors')
@role_required(User.ROLE_HOSPITAL)
def doctors():
    """Dedicated medical staff roster view for the authenticated hospital."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)
    doctors_list = Doctor.query.filter_by(hospital_id=hospital.id).all() if hospital else []

    return render_template(
        'dashboards/hospital_doctors.html',
        hospital=hospital,
        doctors=doctors_list,
        user=current_user
    )

@hospital_bp.route('/doctors/<int:doctor_id>/edit', methods=['GET', 'POST'])
@role_required(User.ROLE_HOSPITAL)
def edit_doctor(doctor_id):
    """Edits clinical profile for a doctor associated with the authenticated hospital."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)
    doctor = db.session.get(Doctor, doctor_id)

    # Strict tenant isolation check
    if not doctor or not hospital or doctor.hospital_id != hospital.id:
        flash('Unauthorized: Doctor record does not belong to your hospital facility.', 'danger')
        return redirect(url_for('hospital.doctors'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        specialization = request.form.get('specialization', '').strip()
        qualification = request.form.get('qualification', '').strip()
        room_number = request.form.get('room_number', '').strip()
        available_days = request.form.get('available_days', '').strip()
        available_time = request.form.get('available_time', '').strip()
        experience_str = request.form.get('experience_years', '0').strip()
        fee_str = request.form.get('consultation_fee', '0.0').strip()
        phone = request.form.get('phone', '').strip()
        bio = request.form.get('bio', '').strip()

        if not full_name or not specialization or not qualification:
            flash('Doctor name, specialization, and qualifications are required.', 'danger')
            return render_template('dashboards/hospital_doctor_edit.html', doctor=doctor, hospital=hospital)

        try:
            exp = max(0, int(experience_str))
            fee = max(0.0, float(fee_str))
        except ValueError:
            flash('Experience must be an integer and fee must be a valid number.', 'danger')
            return render_template('dashboards/hospital_doctor_edit.html', doctor=doctor, hospital=hospital)

        doctor.specialization = specialization
        doctor.qualification = qualification
        doctor.room_number = room_number
        doctor.available_days = available_days or "Monday - Friday"
        doctor.available_time = available_time or "09:00 AM - 05:00 PM"
        doctor.experience_years = exp
        doctor.consultation_fee = fee
        doctor.bio = bio

        if doctor.user:
            doctor.user.full_name = full_name
            if phone:
                doctor.user.phone = phone

        db.session.commit()
        flash(f"Doctor details for {full_name} updated successfully!", 'success')
        return redirect(url_for('hospital.doctors'))

    return render_template('dashboards/hospital_doctor_edit.html', doctor=doctor, hospital=hospital)

@hospital_bp.route('/doctors/<int:doctor_id>/toggle-availability', methods=['POST'])
@role_required(User.ROLE_HOSPITAL)
def toggle_doctor_availability(doctor_id):
    """Toggles availability status for a doctor affiliated with this hospital."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)
    doctor = db.session.get(Doctor, doctor_id)

    # Strict tenant isolation check
    if not doctor or not hospital or doctor.hospital_id != hospital.id:
        flash('Unauthorized: Doctor record does not belong to your hospital facility.', 'danger')
        return redirect(url_for('hospital.doctors'))

    doctor.is_available = not doctor.is_available
    db.session.commit()
    status_str = "Available" if doctor.is_available else "Off-Duty / Unavailable"
    flash(f"Availability for Dr. {doctor.user.full_name if doctor.user else doctor.id} is now: {status_str}.", 'info')

    next_page = request.referrer or url_for('hospital.dashboard')
    return redirect(next_page)

@hospital_bp.route('/doctors/<int:doctor_id>/schedule', methods=['POST'])
@role_required(User.ROLE_HOSPITAL)
def update_doctor_schedule(doctor_id):
    """Updates doctor consultation hours and days."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)
    doctor = db.session.get(Doctor, doctor_id)

    if not doctor or not hospital or doctor.hospital_id != hospital.id:
        flash('Unauthorized: Doctor record does not belong to your hospital facility.', 'danger')
        return redirect(url_for('hospital.dashboard'))

    available_days = request.form.get('available_days', '').strip()
    available_time = request.form.get('available_time', '').strip()

    if available_days:
        doctor.available_days = available_days
    if available_time:
        doctor.available_time = available_time

    db.session.commit()
    flash(f"Schedule for {doctor.user.full_name} updated successfully!", 'success')
    return redirect(request.referrer or url_for('hospital.dashboard'))

@hospital_bp.route('/daily-updates', methods=['POST'])
@role_required(User.ROLE_HOSPITAL)
def daily_updates():
    """Updates operational information: bed counts, emergency availability, and daily notice."""
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)

    if not hospital:
        flash('No hospital facility linked to this account.', 'warning')
        return redirect(url_for('hospital.dashboard'))

    operational_status = request.form.get('operational_status', 'Normal Operations').strip()
    daily_notice = request.form.get('daily_notice', '').strip()
    total_beds_str = request.form.get('total_beds', str(hospital.total_beds)).strip()
    available_beds_str = request.form.get('available_beds', str(hospital.available_beds)).strip()
    emergency_available = request.form.get('emergency_available') == 'on'

    try:
        total_beds = max(0, int(total_beds_str))
        available_beds = max(0, int(available_beds_str))
    except ValueError:
        flash('Bed numbers must be valid integers.', 'danger')
        return redirect(url_for('hospital.dashboard'))

    if available_beds > total_beds:
        flash('Available beds cannot exceed total hospital capacity.', 'danger')
        return redirect(url_for('hospital.dashboard'))

    hospital.operational_status = operational_status
    hospital.daily_notice = daily_notice
    hospital.total_beds = total_beds
    hospital.available_beds = available_beds
    hospital.emergency_available = emergency_available

    db.session.commit()
    flash('Daily hospital updates and operational notice saved successfully!', 'success')
    return redirect(url_for('hospital.dashboard'))

@hospital_bp.route('/appointments')
@role_required(User.ROLE_HOSPITAL)
def appointments():
    """
    Hospital appointment management hub.
    Displays appointments belonging exclusively to the currently authenticated hospital facility.
    Provides sections: Today's, Upcoming, Completed, and Cancelled.
    Provides operational metrics: Today's total, Confirmed, Completed, Cancelled.
    Supports filtering by practicing doctor, consultation date, and status.
    """
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)

    if not hospital:
        flash('No hospital facility linked to this account.', 'danger')
        return redirect(url_for('hospital.dashboard'))

    today = date.today()
    doctor_filter = request.args.get('doctor_id', type=int)
    date_filter = request.args.get('date', '').strip()
    status_filter = request.args.get('status', '').strip().lower()
    search_query = request.args.get('q', '').strip()

    # Query strictly scoped to this hospital facility
    query = Appointment.query.filter_by(hospital_id=hospital.id)

    # Doctor filter
    if doctor_filter:
        query = query.filter(Appointment.doctor_id == doctor_filter)

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

    all_hospital_appts = query.order_by(
        Appointment.appointment_date.desc(),
        Appointment.time_slot.asc()
    ).all()

    # Search query
    if search_query:
        sq = search_query.lower()
        filtered = []
        for a in all_hospital_appts:
            p_name = (a.patient.user.full_name if a.patient and a.patient.user else "").lower()
            d_name = (a.doctor.user.full_name if a.doctor and a.doctor.user else "").lower()
            spec = (a.doctor.specialization if a.doctor else "").lower()
            appt_no = (a.appointment_number or "").lower()
            uid = (a.appointment_uid or "").lower()
            if sq in p_name or sq in d_name or sq in spec or sq in appt_no or sq in uid:
                filtered.append(a)
        all_hospital_appts = filtered

    # Four sections
    today_appointments = [
        a for a in all_hospital_appts 
        if a.appointment_date == today and a.status not in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
    ]
    upcoming_appointments = [
        a for a in all_hospital_appts 
        if a.appointment_date > today and a.status not in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
    ]
    completed_appointments = [
        a for a in all_hospital_appts 
        if a.status == Appointment.STATUS_COMPLETED or (a.appointment_date < today and a.status != Appointment.STATUS_CANCELLED)
    ]
    cancelled_appointments = [
        a for a in all_hospital_appts 
        if a.status == Appointment.STATUS_CANCELLED
    ]

    # Operational summary metrics
    base_hosp_query = Appointment.query.filter_by(hospital_id=hospital.id)
    today_total = base_hosp_query.filter(Appointment.appointment_date == today).count()
    confirmed_total = base_hosp_query.filter(Appointment.status.in_([Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED])).count()
    completed_total = base_hosp_query.filter(
        (Appointment.status == Appointment.STATUS_COMPLETED) |
        ((Appointment.appointment_date < today) & (Appointment.status != Appointment.STATUS_CANCELLED))
    ).count()
    cancelled_total = base_hosp_query.filter(Appointment.status == Appointment.STATUS_CANCELLED).count()

    # Practicing doctors for doctor filter dropdown
    doctors = Doctor.query.filter_by(hospital_id=hospital.id).all()

    return render_template(
        'dashboards/hospital_appointments.html',
        hospital=hospital,
        doctors=doctors,
        today=today,
        all_appointments=all_hospital_appts,
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments,
        today_total=today_total,
        confirmed_total=confirmed_total,
        completed_total=completed_total,
        cancelled_total=cancelled_total,
        doctor_filter=doctor_filter,
        date_filter=date_filter,
        status_filter=status_filter,
        search_query=search_query
    )


# ============================================================================
# 8. AI PATIENT LOAD PREDICTION
# ============================================================================
@hospital_bp.route('/ai-load-prediction')
@role_required(User.ROLE_HOSPITAL)
def ai_load_prediction():
    """
    AI Patient Load Prediction page for Hospital Management.
    Displays operational patient volume predictions, 7-day multi-day forecast,
    trend analysis, Chart.js visualization, and specialization breakdowns.
    Scoped strictly to the authenticated hospital.
    """
    current_user = get_current_user()
    hospital = get_authenticated_hospital(current_user)

    if not hospital:
        flash("Hospital facility record not found.", "danger")
        return redirect(url_for('hospital.dashboard'))

    from ai.patient_load_predictor import predict_patient_load
    prediction = predict_patient_load(hospital.id)

    return render_template(
        'dashboards/hospital_ai_load.html',
        hospital=hospital,
        user=current_user,
        prediction=prediction,
        chart_data=prediction['chart_data'],
        has_sufficient_data=prediction['has_sufficient_data']
    )
