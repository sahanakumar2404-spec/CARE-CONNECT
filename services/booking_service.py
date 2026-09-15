from datetime import date, datetime, time, timedelta
from sqlalchemy.exc import IntegrityError
from database import db
from models.appointment import Appointment
from models.doctor import Doctor
from models.hospital import Hospital
from models.patient import Patient

def parse_time_str(time_str: str) -> time:
    """Parses various standard time formats into datetime.time object."""
    if not time_str:
        return time(9, 0)
    time_str = time_str.strip().upper()
    for fmt in ('%I:%M %p', '%I:%M%p', '%H:%M', '%I %p'):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    return time(9, 0)

def normalize_time_slot(time_slot_str: str) -> str:
    """
    Standardizes time slot representations.
    e.g. '09:00 AM' -> '09:00 AM - 09:30 AM'
    e.g. '09:00 AM - 09:30 AM' remains '09:00 AM - 09:30 AM'
    """
    if not time_slot_str:
        return "09:00 AM - 09:30 AM"
    time_slot_str = time_slot_str.strip()
    if '-' in time_slot_str:
        parts = [p.strip() for p in time_slot_str.split('-')]
        t_start = parse_time_str(parts[0])
        t_end = parse_time_str(parts[1])
        return f"{t_start.strftime('%I:%M %p')} - {t_end.strftime('%I:%M %p')}"
    
    t_start = parse_time_str(time_slot_str)
    start_mins = t_start.hour * 60 + t_start.minute
    end_mins = start_mins + 30
    t_end = time((end_mins // 60) % 24, end_mins % 60)
    return f"{t_start.strftime('%I:%M %p')} - {t_end.strftime('%I:%M %p')}"

def doctor_works_on_date(doctor: Doctor, target_date: date) -> bool:
    """Checks whether the given date falls on a scheduled working day for the doctor."""
    if not doctor or not doctor.is_available:
        return False
    if not doctor.available_days:
        return True

    day_name = target_date.strftime('%A').lower()
    days_str = doctor.available_days.lower()

    if day_name in days_str:
        return True
    if "monday - friday" in days_str or "mon - fri" in days_str:
        return target_date.weekday() < 5
    if "monday - saturday" in days_str or "mon - sat" in days_str:
        return target_date.weekday() < 6
    if "daily" in days_str or "all days" in days_str or "everyday" in days_str:
        return True

    return False

def generate_doctor_slots(doctor: Doctor, target_date: date) -> list:
    """
    Generates 30-minute interval consultation slots based on the doctor's
    schedule, working days, and existing appointments.
    """
    if not doctor:
        return []

    # If doctor is marked unavailable or date is not a working day
    if not doctor.is_available or not doctor_works_on_date(doctor, target_date):
        return []

    t_start = parse_time_str(doctor.start_time)
    t_end = parse_time_str(doctor.end_time)

    start_mins = t_start.hour * 60 + t_start.minute
    end_mins = t_end.hour * 60 + t_end.minute

    if end_mins <= start_mins:
        end_mins = start_mins + (8 * 60)  # Default fallback 8 hours

    # Retrieve already booked slots for this doctor on target_date
    booked_records = db.session.query(Appointment.time_slot).filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_date == target_date,
        Appointment.status != Appointment.STATUS_CANCELLED
    ).all()

    # Collect normalized booked keys
    booked_set = set()
    for rec in booked_records:
        slot_text = rec[0].strip()
        booked_set.add(slot_text)
        booked_set.add(normalize_time_slot(slot_text))
        if '-' in slot_text:
            booked_set.add(slot_text.split('-')[0].strip())

    slots = []
    interval = 30
    cur_mins = start_mins

    while cur_mins + interval <= end_mins:
        s_time = time(cur_mins // 60, cur_mins % 60)
        next_mins = cur_mins + interval
        e_time = time((next_mins // 60) % 24, next_mins % 60)

        s_str = s_time.strftime("%I:%M %p")
        e_str = e_time.strftime("%I:%M %p")
        full_slot = f"{s_str} - {e_str}"

        is_booked = (
            full_slot in booked_set or 
            s_str in booked_set or
            normalize_time_slot(s_str) in booked_set
        )

        slots.append({
            'time_slot': full_slot,
            'start_time': s_str,
            'end_time': e_str,
            'is_booked': is_booked,
            'status': 'booked' if is_booked else 'available'
        })

        cur_mins += interval

    return slots

def is_time_slot_within_hours(time_slot_str: str, doctor: Doctor) -> bool:
    """Validates whether a selected time slot falls within the doctor's consultation hours."""
    if not time_slot_str or not doctor:
        return False

    slot_start_str = time_slot_str.split('-')[0].strip() if '-' in time_slot_str else time_slot_str.strip()
    slot_time = parse_time_str(slot_start_str)
    slot_mins = slot_time.hour * 60 + slot_time.minute

    doc_start = parse_time_str(doctor.start_time)
    doc_end = parse_time_str(doctor.end_time)

    start_mins = doc_start.hour * 60 + doc_start.minute
    end_mins = doc_end.hour * 60 + doc_end.minute

    if end_mins <= start_mins:
        end_mins = start_mins + (8 * 60)

    # Must be at or after start time and strictly before end time
    return start_mins <= slot_mins < end_mins

def book_appointment(
    patient: Patient,
    doctor_id: int,
    hospital_id: int,
    appointment_date: date,
    time_slot: str,
    symptoms: str = None
) -> tuple:
    """
    Orchestrates transaction-safe appointment booking with server-side validation
    and database-level double-booking prevention.
    Returns: (success: bool, message: str, appointment: Appointment or None)
    """
    if not patient:
        return False, "Patient profile required to book an appointment.", None

    # 1. Validate Doctor
    doctor = db.session.get(Doctor, doctor_id)
    if not doctor:
        return False, "The selected physician does not exist.", None

    # 2. Validate Hospital
    hospital = db.session.get(Hospital, hospital_id)
    if not hospital:
        return False, "The selected hospital facility does not exist.", None

    # 3. Doctor must belong to the selected hospital
    if doctor.hospital_id != hospital.id:
        return False, "Selected doctor is not affiliated with the selected hospital facility.", None

    # 4. Past date validation
    if appointment_date < date.today():
        return False, "Appointment date cannot be in the past.", None

    # 5. Doctor availability status
    if not doctor.is_available:
        return False, "Doctor is currently not available for appointments.", None

    # 6. Working day validation
    if not doctor_works_on_date(doctor, appointment_date):
        day_name = appointment_date.strftime('%A')
        return False, f"Doctor does not have scheduled hours on this day ({day_name}).", None

    # 7. Within consultation hours validation
    normalized_slot = normalize_time_slot(time_slot)
    if not is_time_slot_within_hours(time_slot, doctor):
        return False, "Selected time slot is outside the doctor's consultation hours.", None

    # 8. Server-side pre-check for existing booked slot
    existing_appointment = Appointment.query.filter(
        Appointment.doctor_id == doctor.id,
        Appointment.appointment_date == appointment_date,
        Appointment.status != Appointment.STATUS_CANCELLED
    ).filter(
        (Appointment.time_slot == normalized_slot) |
        (Appointment.time_slot == time_slot)
    ).first()

    if existing_appointment:
        return False, "This appointment slot is no longer available.", None

    # 9. Generate unique appointment tracking number
    appointment_number = Appointment.generate_appointment_number(appointment_date)

    # 10. Persist with transaction safety against concurrent double bookings
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor.id,
        hospital_id=hospital.id,
        appointment_date=appointment_date,
        time_slot=normalized_slot,
        appointment_number=appointment_number,
        status=Appointment.STATUS_CONFIRMED,
        symptoms=symptoms.strip() if symptoms else "General clinical consultation"
    )

    try:
        import secrets
        if not appointment.verification_token:
            appointment.verification_token = secrets.token_urlsafe(24)
            
        db.session.add(appointment)
        db.session.flush()

        # Generate QR code for physical and digital verification
        try:
            from utils.qr_generator import generate_appointment_qr_code
            appointment.qr_code_file = generate_appointment_qr_code(appointment)
        except Exception:
            pass

        db.session.commit()
        return True, "Appointment booked successfully!", appointment
    except IntegrityError:
        db.session.rollback()
        return False, "This appointment slot is no longer available.", None
    except Exception as e:
        db.session.rollback()
        return False, f"An unexpected error occurred while booking: {str(e)}", None
