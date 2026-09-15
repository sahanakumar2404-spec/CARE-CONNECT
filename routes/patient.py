import io
import re
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app, abort, send_file
from database import db
from models.user import User
from models.patient import Patient
from models.doctor import Doctor
from models.hospital import Hospital
from models.appointment import Appointment
from services.auth_service import role_required, get_current_user
from services.booking_service import (
    generate_doctor_slots,
    doctor_works_on_date,
    normalize_time_slot,
    book_appointment as process_booking
)
from ai.triage import analyze_symptoms
from ai.specialist_recommender import recommend_specialist
from ai.smart_appointment import recommend_smart_slots, SMART_APPOINTMENT_DISCLAIMER
from utils.helpers import generate_appointment_qr

patient_bp = Blueprint('patient', __name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def get_authenticated_patient(current_user):
    """Helper to retrieve the Patient record associated with the authenticated user."""
    if not current_user:
        return None
    return Patient.query.filter_by(user_id=current_user.id).first()

# ============================================================================
# 1. PATIENT DASHBOARD
# ============================================================================
@patient_bp.route('/dashboard')
@role_required(User.ROLE_PATIENT)
def dashboard():
    """Patient Dashboard showing strictly the current patient's appointments and profile."""
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    appointments = []
    upcoming_appointments = []
    past_appointments = []
    today = date.today()

    if patient:
        # Strictly scoped to this patient's ID
        appointments = Appointment.query.filter_by(patient_id=patient.id).order_by(
            Appointment.appointment_date.desc()
        ).all()

        upcoming_appointments = [
            a for a in appointments 
            if a.appointment_date >= today and a.status in [Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED]
        ]
        past_appointments = [
            a for a in appointments 
            if a.appointment_date < today or a.status in [Appointment.STATUS_COMPLETED, Appointment.STATUS_CANCELLED]
        ]

        # Generate QR code for any appointment that doesn't have one yet
        from utils.qr_generator import generate_appointment_qr_code
        for appt in appointments:
            if not appt.qr_code_file:
                try:
                    appt.qr_code_file = generate_appointment_qr_code(appt)
                except Exception:
                    pass
        db.session.commit()

    # Real database statistics
    hospital_count = Hospital.query.count()
    available_doctors_count = Doctor.query.filter_by(is_available=True).count()
    available_doctors = Doctor.query.filter_by(is_available=True).limit(6).all()
    hospitals = Hospital.query.all()

    # Unique medical specializations from practicing doctors
    specialties = [
        s[0] for s in db.session.query(Doctor.specialization).filter(Doctor.is_available == True).distinct().all()
    ]

    return render_template(
        'dashboards/patient.html',
        patient=patient,
        appointments=appointments,
        upcoming_appointments=upcoming_appointments,
        past_appointments=past_appointments,
        available_doctors=available_doctors,
        available_doctors_count=available_doctors_count,
        hospital_count=hospital_count,
        specialties=specialties,
        hospitals=hospitals,
        user=current_user
    )

# ============================================================================
# 2. PATIENT PROFILE (VIEW & EDIT)
# ============================================================================
@patient_bp.route('/profile', methods=['GET', 'POST'])
@role_required(User.ROLE_PATIENT)
def profile():
    """View and edit patient profile for authenticated patient only."""
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    if not patient:
        flash('Patient profile record not found.', 'danger')
        return redirect(url_for('patient.dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        dob_str = request.form.get('date_of_birth', '').strip()
        gender = request.form.get('gender', 'Not Specified').strip()
        blood_group = request.form.get('blood_group', 'O+').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        emergency_contact = request.form.get('emergency_contact', '').strip()

        errors = []
        if not full_name:
            errors.append('Patient full name cannot be empty.')

        if not email or not EMAIL_REGEX.match(email):
            errors.append('Please provide a valid email address.')
        else:
            existing = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing:
                errors.append('Email address is already in use by another account.')

        date_of_birth = patient.date_of_birth
        if dob_str:
            try:
                date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Invalid Date of Birth format. Please use YYYY-MM-DD.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            return render_template(
                'dashboards/patient_profile.html',
                patient=patient,
                form_data=request.form
            )

        # Apply updates
        current_user.full_name = full_name
        current_user.email = email
        if phone:
            current_user.phone = phone

        patient.date_of_birth = date_of_birth
        patient.gender = gender
        patient.blood_group = blood_group
        patient.address = address
        patient.city = city
        patient.emergency_contact = emergency_contact

        db.session.commit()
        flash('Patient profile updated successfully!', 'success')
        return redirect(url_for('patient.profile'))

    return render_template(
        'dashboards/patient_profile.html',
        patient=patient
    )

@patient_bp.route('/profile/<int:target_patient_id>', methods=['GET', 'POST'])
@role_required(User.ROLE_PATIENT)
def cross_patient_profile_block(target_patient_id):
    """Explicitly prevents a patient from accessing or editing another patient's profile."""
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    if not patient or patient.id != target_patient_id:
        flash('Access Denied: You cannot view or modify another patient’s private profile.', 'danger')
        abort(403)

    return redirect(url_for('patient.profile'))

# ============================================================================
# 3. REGISTERED HOSPITAL SEARCH & DISCOVERY
# ============================================================================
@patient_bp.route('/hospitals')
@role_required(User.ROLE_PATIENT)
def hospitals():
    """Search and discover registered healthcare facilities in Care Connect."""
    name_query = request.args.get('name', '').strip()
    city_query = request.args.get('city', '').strip()
    type_query = request.args.get('type', '').strip()

    # Query strictly registered hospitals
    query = Hospital.query

    if name_query:
        query = query.filter(Hospital.name.ilike(f"%{name_query}%"))
    if city_query:
        query = query.filter(Hospital.city.ilike(f"%{city_query}%"))
    if type_query:
        query = query.filter(Hospital.hospital_type.ilike(f"%{type_query}%"))

    hospitals_list = query.order_by(Hospital.name.asc()).all()

    # Metadata for filter dropdowns
    all_cities = [c[0] for c in db.session.query(Hospital.city).distinct().order_by(Hospital.city.asc()).all()]
    all_types = [t[0] for t in db.session.query(Hospital.hospital_type).distinct().order_by(Hospital.hospital_type.asc()).all()]

    return render_template(
        'dashboards/patient_hospitals.html',
        hospitals=hospitals_list,
        all_cities=all_cities,
        all_types=all_types,
        search_name=name_query,
        selected_city=city_query,
        selected_type=type_query
    )

# ============================================================================
# 4. HOSPITAL DETAILS & SPECIALIST BROWSER
# ============================================================================
@patient_bp.route('/hospitals/<int:hospital_id>')
@role_required(User.ROLE_PATIENT)
def hospital_detail(hospital_id):
    """View details, medical specializations, and doctors of a registered hospital."""
    hospital = db.session.get(Hospital, hospital_id)
    if not hospital:
        abort(404)

    # Distinct specializations offered at this hospital
    specialties = [
        s[0] for s in db.session.query(Doctor.specialization)\
            .filter(Doctor.hospital_id == hospital.id)\
            .distinct().order_by(Doctor.specialization.asc()).all()
    ]

    # Filter doctors by specialization if selected
    selected_specialty = request.args.get('specialty', '').strip()
    doc_query = Doctor.query.filter_by(hospital_id=hospital.id)
    if selected_specialty:
        doc_query = doc_query.filter(Doctor.specialization.ilike(f"%{selected_specialty}%"))

    doctors = doc_query.order_by(Doctor.specialization.asc()).all()

    return render_template(
        'dashboards/patient_hospital_detail.html',
        hospital=hospital,
        specialties=specialties,
        doctors=doctors,
        selected_specialty=selected_specialty
    )

# ============================================================================
# 5. DOCTOR DETAILS (PATIENT-FACING)
# ============================================================================
@patient_bp.route('/doctors/<int:doctor_id>')
@role_required(User.ROLE_PATIENT)
def doctor_detail(doctor_id):
    """Patient-facing physician profile with schedule, consultation fee, and booking notice."""
    doctor = db.session.get(Doctor, doctor_id)
    if not doctor:
        abort(404)

    return render_template(
        'dashboards/patient_doctor_detail.html',
        doctor=doctor,
        hospital=doctor.hospital
    )

# ============================================================================
# 6. PRESERVED AI TRIAGE API
# ============================================================================
@patient_bp.route('/ai-triage', methods=['POST'])
@role_required(User.ROLE_PATIENT)
def ai_triage():
    """API endpoint for AI-assisted specialist recommendation based on symptoms."""
    data = request.get_json() or {}
    symptoms = data.get('symptoms', '')
    
    analysis = analyze_symptoms(symptoms)
    
    # Find doctors matching the recommended specialty
    recommended_specialty = analysis.get('recommended_specialty')
    matching_doctors = Doctor.query.filter(
        Doctor.specialization.ilike(f"%{recommended_specialty}%"),
        Doctor.is_available == True
    ).all()

    doctor_list = [
        {
            'id': doc.id,
            'name': doc.user.full_name if doc.user else f"Doctor #{doc.id}",
            'specialization': doc.specialization,
            'hospital': doc.hospital.name if doc.hospital else "Affiliated Hospital",
            'fee': doc.consultation_fee,
            'timing': doc.available_time
        }
        for doc in matching_doctors
    ]

    return jsonify({
        'status': 'success',
        'analysis': analysis,
        'recommended_doctors': doctor_list
    })

# ============================================================================
# 7. APPOINTMENT BOOKING & CONFIRMATION
# ============================================================================
@patient_bp.route('/book', methods=['GET', 'POST'])
@role_required(User.ROLE_PATIENT)
def book_appointment():
    """Interactive appointment booking workflow for authenticated patient."""
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    if not patient:
        flash('Patient record not found.', 'danger')
        return redirect(url_for('patient.dashboard'))

    if request.method == 'POST':
        hospital_id_str = request.form.get('hospital_id', '').strip()
        doctor_id_str = request.form.get('doctor_id', '').strip()
        date_str = request.form.get('appointment_date', '').strip()
        time_slot = request.form.get('time_slot', '').strip()
        symptoms = request.form.get('symptoms', '').strip()

        # Validation of required fields
        if not hospital_id_str or not doctor_id_str or not date_str or not time_slot:
            flash('Please select a hospital, physician, date, and consultation time slot.', 'danger')
            return redirect(url_for('patient.book_appointment', doctor_id=doctor_id_str, hospital_id=hospital_id_str, date=date_str))

        try:
            hospital_id = int(hospital_id_str)
            doctor_id = int(doctor_id_str)
        except ValueError:
            flash('Invalid hospital or doctor selection.', 'danger')
            return redirect(url_for('patient.book_appointment'))

        try:
            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid appointment date format. Please select a valid date.', 'danger')
            return redirect(url_for('patient.book_appointment', doctor_id=doctor_id, hospital_id=hospital_id))

        success, message, appointment = process_booking(
            patient=patient,
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            appointment_date=appointment_date,
            time_slot=time_slot,
            symptoms=symptoms
        )

        if not success:
            flash(message, 'danger')
            return redirect(url_for('patient.book_appointment', doctor_id=doctor_id, hospital_id=hospital_id, date=date_str))

        flash(message, 'success')
        return redirect(url_for('patient.booking_confirmation', appointment_id=appointment.id))

    # GET request: Prepare booking form state
    doctor_id_arg = request.args.get('doctor_id', type=int)
    hospital_id_arg = request.args.get('hospital_id', type=int)
    date_arg = request.args.get('date', '').strip()
    time_slot_arg = request.args.get('time_slot', '').strip()

    selected_doctor = None
    selected_hospital = None

    if doctor_id_arg:
        selected_doctor = db.session.get(Doctor, doctor_id_arg)
        if selected_doctor and selected_doctor.hospital:
            selected_hospital = selected_doctor.hospital
    elif hospital_id_arg:
        selected_hospital = db.session.get(Hospital, hospital_id_arg)

    # Resolve target consultation date
    target_date = date.today()
    if date_arg:
        try:
            target_date = datetime.strptime(date_arg, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()

    # Generate available slots if doctor is selected
    slots = []
    if selected_doctor:
        slots = generate_doctor_slots(selected_doctor, target_date)

    all_hospitals = Hospital.query.order_by(Hospital.name.asc()).all()
    all_doctors = Doctor.query.filter_by(is_available=True).all()

    return render_template(
        'dashboards/patient_book.html',
        patient=patient,
        selected_doctor=selected_doctor,
        selected_hospital=selected_hospital,
        target_date=target_date,
        slots=slots,
        all_hospitals=all_hospitals,
        all_doctors=all_doctors,
        min_date=date.today().strftime('%Y-%m-%d'),
        prefilled_time_slot=time_slot_arg,
        user=current_user
    )

@patient_bp.route('/api/slots')
@role_required(User.ROLE_PATIENT)
def api_slots():
    """AJAX endpoint providing dynamic 30-minute slot availability for a doctor on a target date."""
    doctor_id = request.args.get('doctor_id', type=int)
    date_str = request.args.get('date', '').strip()

    if not doctor_id or not date_str:
        return jsonify({'status': 'error', 'message': 'doctor_id and date are required parameters'}), 400

    doctor = db.session.get(Doctor, doctor_id)
    if not doctor:
        return jsonify({'status': 'error', 'message': 'Physician record not found'}), 404

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid date format (YYYY-MM-DD required)'}), 400

    is_working_day = doctor_works_on_date(doctor, target_date)
    slots = generate_doctor_slots(doctor, target_date)

    return jsonify({
        'status': 'success',
        'doctor_id': doctor.id,
        'doctor_name': doctor.user.full_name if doctor.user else f"Doctor #{doctor.id}",
        'date': target_date.strftime('%Y-%m-%d'),
        'is_available': doctor.is_available,
        'is_working_day': is_working_day,
        'slots': slots
    })

@patient_bp.route('/appointments/<int:appointment_id>/confirmation')
@role_required(User.ROLE_PATIENT)
def booking_confirmation(appointment_id):
    """Digital booking confirmation receipt for authenticated patient."""
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)
    appointment = db.session.get(Appointment, appointment_id)

    if not appointment:
        abort(404)

    # Ownership check: Patient A cannot access Patient B's appointment confirmation
    if not patient or appointment.patient_id != patient.id:
        flash('Access Denied: You cannot view another patient’s private appointment confirmation.', 'danger')
        abort(403)

    # Ensure QR code file exists
    if not appointment.qr_code_file:
        from utils.qr_generator import generate_appointment_qr_code
        try:
            appointment.qr_code_file = generate_appointment_qr_code(appointment)
            db.session.commit()
        except Exception:
            pass

    return render_template(
        'dashboards/patient_booking_confirmation.html',
        appointment=appointment,
        patient=patient,
        doctor=appointment.doctor,
        hospital=appointment.hospital,
        user=current_user
    )

@patient_bp.route('/appointments/<int:appointment_id>/pdf')
@role_required(User.ROLE_PATIENT)
def download_appointment_pdf(appointment_id):
    """
    Downloads the official ReportLab appointment confirmation PDF.
    Strictly verifies ownership: Patient A cannot download Patient B's PDF (HTTP 403).
    """
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)
    appointment = db.session.get(Appointment, appointment_id)

    if not appointment:
        abort(404)

    # Strict ownership check: Patient A cannot download Patient B's PDF
    if not patient or appointment.patient_id != patient.id:
        flash('Access Denied: You cannot download another patient’s appointment confirmation PDF.', 'danger')
        abort(403)

    from utils.pdf_generator import generate_appointment_pdf
    pdf_bytes = generate_appointment_pdf(appointment)

    appt_num = appointment.appointment_number or f"CC-{appointment.id}"
    filename = f"CareConnect_Appointment_{appt_num}.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )

@patient_bp.route('/appointments')
@role_required(User.ROLE_PATIENT)
def appointments():
    """
    Patient appointment history and management page.
    Organizes appointments into Today's, Upcoming, Completed, and Cancelled.
    Supports search and status filtering.
    """
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    if not patient:
        flash('Patient record not found.', 'danger')
        return redirect(url_for('patient.dashboard'))

    today = date.today()
    search_query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip().lower()

    # Query strictly scoped to authenticated patient
    query = Appointment.query.filter_by(patient_id=patient.id)

    if status_filter:
        if status_filter == 'upcoming':
            query = query.filter(
                Appointment.appointment_date > today,
                Appointment.status.in_([Appointment.STATUS_SCHEDULED, Appointment.STATUS_CONFIRMED])
            )
        elif status_filter == 'today':
            query = query.filter(
                Appointment.appointment_date == today,
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

    all_patient_appts = query.order_by(Appointment.appointment_date.desc(), Appointment.time_slot.asc()).all()

    # Apply text search if present
    if search_query:
        sq = search_query.lower()
        filtered_appts = []
        for a in all_patient_appts:
            hosp_name = (a.hospital.name if a.hospital else "").lower()
            doc_name = (a.doctor.user.full_name if a.doctor and a.doctor.user else "").lower()
            spec = (a.doctor.specialization if a.doctor else "").lower()
            appt_no = (a.appointment_number or "").lower()
            if sq in hosp_name or sq in doc_name or sq in spec or sq in appt_no:
                filtered_appts.append(a)
        all_patient_appts = filtered_appts

    # Group into sections
    today_appointments = [
        a for a in all_patient_appts 
        if a.appointment_date == today and a.status not in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
    ]
    upcoming_appointments = [
        a for a in all_patient_appts 
        if a.appointment_date > today and a.status not in [Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED]
    ]
    completed_appointments = [
        a for a in all_patient_appts 
        if a.status == Appointment.STATUS_COMPLETED or (a.appointment_date < today and a.status != Appointment.STATUS_CANCELLED)
    ]
    cancelled_appointments = [
        a for a in all_patient_appts 
        if a.status == Appointment.STATUS_CANCELLED
    ]

    # Metrics for badges
    total_count = len(all_patient_appts)
    today_count = len(today_appointments)
    upcoming_count = len(upcoming_appointments)
    completed_count = len(completed_appointments)
    cancelled_count = len(cancelled_appointments)

    return render_template(
        'dashboards/patient_appointments.html',
        patient=patient,
        user=current_user,
        today=today,
        all_appointments=all_patient_appts,
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        completed_appointments=completed_appointments,
        cancelled_appointments=cancelled_appointments,
        search_query=search_query,
        status_filter=status_filter,
        total_count=total_count,
        today_count=today_count,
        upcoming_count=upcoming_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count
    )

@patient_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@role_required(User.ROLE_PATIENT)
def cancel_appointment(appointment_id):
    """
    Cancels an upcoming appointment belonging to the authenticated patient.
    Enforces strict ownership, lifecycle validation, and slot release.
    """
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)
    appointment = db.session.get(Appointment, appointment_id)

    if not appointment:
        abort(404)

    # Ownership check: Patient A cannot cancel Patient B's appointment
    if not patient or appointment.patient_id != patient.id:
        flash('Access Denied: You cannot cancel another patient’s appointment.', 'danger')
        abort(403)

    # Lifecycle validation
    can_cancel, reason = appointment.can_cancel(by_patient=True)
    if not can_cancel:
        flash(f"Cancellation Failed: {reason}", 'warning')
        return redirect(url_for('patient.appointments'))

    # Mark cancelled and commit (preserves record in DB)
    appointment.status = Appointment.STATUS_CANCELLED
    db.session.commit()

    ref = appointment.appointment_number or appointment.appointment_uid
    flash(f"Appointment {ref} has been cancelled successfully.", 'success')
    return redirect(url_for('patient.appointments'))


# ============================================================================
# 8. AI SPECIALIST RECOMMENDATION
# ============================================================================
@patient_bp.route('/ai-specialist', methods=['GET', 'POST'])
@role_required(User.ROLE_PATIENT)
def ai_specialist():
    """
    AI-assisted specialist recommendation page.
    Analyzes patient concern descriptions, provides explainable specialty recommendation,
    shows matching registered doctors from database, and enforces strict non-diagnostic boundaries.
    """
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    result = None
    concern = ""
    matching_doctors = []
    has_submitted = False

    if request.method == 'POST':
        has_submitted = True
        if request.is_json:
            data = request.get_json() or {}
            concern = data.get('concern', '')
        else:
            concern = request.form.get('concern', '')

        result = recommend_specialist(concern)

        # If a recommendation was made, query matching registered doctors from SQLite
        if result.get('status') == 'success' and result.get('recommended_specialty'):
            specialty = result['recommended_specialty']
            # Search doctors whose specialization contains or equals the recommended specialty
            matching_doctors = Doctor.query.join(User).filter(
                Doctor.specialization.ilike(f"%{specialty}%"),
                User.is_active == True
            ).all()

        if request.is_json:
            return jsonify({
                'result': result,
                'matching_doctors': [
                    {
                        'id': doc.id,
                        'name': doc.user.full_name if doc.user else f"Dr. #{doc.id}",
                        'specialization': doc.specialization,
                        'hospital_name': doc.hospital.name if doc.hospital else "Affiliated Hospital",
                        'hospital_city': doc.hospital.city if doc.hospital else "",
                        'consultation_fee': doc.consultation_fee,
                        'available_time': doc.available_time,
                        'available_days': doc.available_days
                    }
                    for doc in matching_doctors
                ]
            })

    return render_template(
        'dashboards/patient_ai_specialist.html',
        patient=patient,
        user=current_user,
        concern=concern,
        result=result,
        matching_doctors=matching_doctors,
        has_submitted=has_submitted
    )


# ============================================================================
# 9. AI SMART APPOINTMENT RECOMMENDATION
# ============================================================================
@patient_bp.route('/smart-appointment', methods=['GET', 'POST'])
@role_required(User.ROLE_PATIENT)
def smart_appointment():
    """
    AI-assisted smart appointment recommendation portal for authenticated patients.
    Recommends optimal consultation slots based on real database records,
    doctor schedules, preferences, and explainable multi-factor scoring.
    """
    current_user = get_current_user()
    patient = get_authenticated_patient(current_user)

    all_hospitals = Hospital.query.order_by(Hospital.name.asc()).all()
    all_doctors = Doctor.query.filter_by(is_available=True).all()
    specialties = [
        s[0] for s in db.session.query(Doctor.specialization).filter(
            Doctor.is_available == True
        ).distinct().order_by(Doctor.specialization.asc()).all()
        if s[0]
    ]

    # Parameter extraction (supports both GET query parameters and POST / JSON)
    hospital_id = request.values.get('hospital_id', type=int)
    specialization = request.values.get('specialization', '').strip()
    doctor_id = request.values.get('doctor_id', type=int)
    preferred_date_str = request.values.get('preferred_date', '').strip()
    preferred_time_period = request.values.get('preferred_time_period', 'any_time').strip()
    flexibility = request.values.get('flexibility', 'exact').strip()

    result = None
    has_searched = False

    # Execute evaluation if hospital and (specialization or doctor) are provided
    if hospital_id and (specialization or doctor_id):
        has_searched = True

        # If doctor selected but specialization empty, infer from doctor
        if doctor_id and not specialization:
            chosen_doc = db.session.get(Doctor, doctor_id)
            if chosen_doc:
                specialization = chosen_doc.specialization

        result = recommend_smart_slots(
            hospital_id=hospital_id,
            specialization=specialization,
            doctor_id=doctor_id,
            preferred_date=preferred_date_str,
            preferred_time_period=preferred_time_period,
            flexibility=flexibility
        )

        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': result.get('status', 'error'),
                'message': result.get('message', ''),
                'recommendations': result.get('recommendations', []),
                'disclaimer': result.get('disclaimer', SMART_APPOINTMENT_DISCLAIMER)
            })

    return render_template(
        'dashboards/patient_smart_appointment.html',
        patient=patient,
        user=current_user,
        all_hospitals=all_hospitals,
        all_doctors=all_doctors,
        specialties=specialties,
        hospital_id=hospital_id,
        specialization=specialization,
        doctor_id=doctor_id,
        preferred_date=preferred_date_str or date.today().strftime('%Y-%m-%d'),
        preferred_time_period=preferred_time_period,
        flexibility=flexibility,
        result=result,
        has_searched=has_searched,
        min_date=date.today().strftime('%Y-%m-%d')
    )

