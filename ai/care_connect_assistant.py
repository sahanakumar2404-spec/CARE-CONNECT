"""
Care Connect - AI Assistant Service
Phase 12: Role-aware platform navigation, information retrieval, and operational guidance.

Strictly non-diagnostic: Provides platform navigation and database retrieval only.
Never diagnoses conditions, prescribes medicines, or gives clinical emergency guidance.
Enforces multi-tenant data isolation and role-based access control.
"""

from datetime import date, datetime, timedelta
import re
from typing import Dict, Any, List, Optional
from database import db
from models.user import User
from models.doctor import Doctor
from models.hospital import Hospital
from models.patient import Patient
from models.appointment import Appointment
from ai.patient_load_predictor import predict_patient_load

# Mandatory Boundaries
ASSISTANT_DIAGNOSIS_BOUNDARY = (
    "I can help you use Care Connect and find an appropriate healthcare specialist, "
    "but I cannot diagnose medical conditions or provide treatment advice. "
    "If you need appointment guidance based on a concern, you can use our "
    "AI Specialist Recommendation feature to find the right department."
)

ASSISTANT_MEDICATION_BOUNDARY = (
    "I cannot prescribe medications or provide dosage instructions. "
    "Please consult a licensed physician on Care Connect for clinical treatment advice."
)

ASSISTANT_UNKNOWN_FALLBACK = (
    "I'm not sure about that Care Connect feature. "
    "I can help with hospitals, doctors, appointments, availability, and Care Connect features."
)

ASSISTANT_NO_RECORD_FOUND = "No matching Care Connect record was found."


def is_diagnosis_query(msg: str) -> bool:
    """Detects medical diagnosis, illness interpretation, or acute symptom queries."""
    m = msg.lower()
    patterns = [
        r'\bdiagnos',
        r'\bam i sick\b',
        r'\bwhat disease\b',
        r'\bwhat illness\b',
        r'\bdo i have (cancer|covid|flu|heart attack|stroke|pneumonia|diabetes|migraine)\b',
        r'\bcure for\b',
        r'\btreat my\b',
        r'\btreatment for (cancer|diabetes|infection|covid|flu)\b',
        r'\bam i having a (heart attack|stroke|seizure)\b',
        r'\bemergency medical\b',
        r'\binterpret symptoms\b',
        r'\bmedical diagnosis\b'
    ]
    for p in patterns:
        if re.search(p, m):
            return True
    return False


def is_medication_query(msg: str) -> bool:
    """Detects drug prescription, medicine recommendation, or dosage queries."""
    m = msg.lower()
    patterns = [
        r'\bprescrib',
        r'\bwhat medicine\b',
        r'\bwhat medication\b',
        r'\bwhat drug\b',
        r'\bdosage\b',
        r'\bdose of\b',
        r'\bhow many mg\b',
        r'\bcan i take (paracetamol|ibuprofen|aspirin|antibiotic|tylenol|advil|amoxicillin)\b',
        r'\bpainkiller\b',
        r'\bwhich pill\b'
    ]
    for p in patterns:
        if re.search(p, m):
            return True
    return False


def format_appointment_card(appt: Appointment) -> str:
    """Formats an appointment into a clean, human-readable structured card."""
    doc_name = f"Dr. {appt.doctor.user.full_name}" if appt.doctor and appt.doctor.user else f"Doctor #{appt.doctor_id}"
    spec = appt.doctor.specialization if appt.doctor else "General Consultation"
    hosp_name = appt.hospital.name if appt.hospital else "Care Connect Facility"
    hosp_city = f" ({appt.hospital.city})" if appt.hospital and appt.hospital.city else ""
    date_str = appt.appointment_date.strftime("%d %B %Y")
    ref = appt.appointment_number or appt.appointment_uid or f"CC-{appt.id}"

    return (
        f"• **Doctor**: {doc_name}\n"
        f"  **Specialization**: {spec}\n"
        f"  **Hospital**: {hosp_name}{hosp_city}\n"
        f"  **Date**: {date_str}\n"
        f"  **Time**: {appt.time_slot}\n"
        f"  **Status**: {appt.status}\n"
        f"  **Appointment No**: {ref}"
    )


def process_assistant_message(user: User, message: str) -> Dict[str, Any]:
    """
    Main entry point for processing Care Connect AI Assistant queries.
    Enforces security, data isolation, role-based access, and safety boundaries.
    """
    if not user:
        return {
            "status": "error",
            "response": "Authentication required. Please sign in to access the Care Connect Assistant.",
            "role": "unauthenticated"
        }

    clean_msg = message.strip() if message else ""
    if not clean_msg:
        return {
            "status": "empty",
            "response": "Please enter a question or message so I can assist you with Care Connect.",
            "role": user.role
        }

    # 1. Safety Boundaries: Medical Diagnosis & Medication Checks
    if is_diagnosis_query(clean_msg):
        return {
            "status": "safety_boundary",
            "response": ASSISTANT_DIAGNOSIS_BOUNDARY,
            "role": user.role
        }

    if is_medication_query(clean_msg):
        return {
            "status": "safety_boundary",
            "response": ASSISTANT_MEDICATION_BOUNDARY,
            "role": user.role
        }

    msg_lower = clean_msg.lower()

    # 2. Cross-Role Unauthorized Access Checks
    if user.is_patient():
        if any(term in msg_lower for term in ["patient load", "load prediction", "hospital management", "hospital financial", "hospital revenue"]):
            return {
                "status": "unauthorized",
                "response": "Access Denied: Patient load prediction and hospital administrative metrics are restricted to Hospital Administrators.",
                "role": user.role
            }
        if any(term in msg_lower for term in ["other patient", "another patient", "patient b", "all patients"]):
            return {
                "status": "unauthorized",
                "response": "Access Denied: You are not authorized to view information belonging to another patient.",
                "role": user.role
            }
        if any(term in msg_lower for term in ["doctor private notes", "physician salary", "doctor confidential"]):
            return {
                "status": "unauthorized",
                "response": "Access Denied: You are not authorized to access private physician or clinical administrative records.",
                "role": user.role
            }

    elif user.is_doctor():
        if any(term in msg_lower for term in ["patient load prediction", "hospital revenue", "hospital admin credentials"]):
            return {
                "status": "unauthorized",
                "response": "Access Denied: Hospital load forecasting and administrative management data are restricted to Hospital Administrators.",
                "role": user.role
            }
        if any(term in msg_lower for term in ["other doctor's appointments", "another doctor's queue", "doctor b's schedule"]):
            return {
                "status": "unauthorized",
                "response": "Access Denied: You are not authorized to view another physician's private consultation queue.",
                "role": user.role
            }

    elif user.is_hospital():
        if any(term in msg_lower for term in ["other hospital", "another hospital's", "hospital b's data", "hospital alpha data"]):
            # Check if attempting to inspect another facility
            hosp = Hospital.query.filter_by(user_id=user.id).first()
            if hosp and hosp.name.lower() not in msg_lower:
                return {
                    "status": "unauthorized",
                    "response": "Access Denied: You are not authorized to view operational data belonging to another hospital facility.",
                    "role": user.role
                }

    # 3. Role-Aware Handling
    try:
        if user.is_patient():
            return handle_patient_query(user, clean_msg, msg_lower)
        elif user.is_doctor():
            return handle_doctor_query(user, clean_msg, msg_lower)
        elif user.is_hospital():
            return handle_hospital_query(user, clean_msg, msg_lower)
        else:
            return {
                "status": "unknown_role",
                "response": "Unrecognized user role.",
                "role": user.role
            }
    except Exception as e:
        return {
            "status": "error",
            "response": "A database error occurred while retrieving Care Connect records. Please try again later.",
            "error_detail": str(e),
            "role": user.role
        }


# ============================================================================
# PATIENT INTENT HANDLERS
# ============================================================================
def handle_patient_query(user: User, raw_msg: str, msg: str) -> Dict[str, Any]:
    patient = Patient.query.filter_by(user_id=user.id).first()
    if not patient:
        return {
            "status": "error",
            "response": "Patient profile record not found. Please complete your patient profile.",
            "role": user.role
        }

    today = date.today()

    # 1. Appointments Today
    if any(q in msg for q in ["appointments today", "appointment today", "have today", "today's appointment"]):
        appts = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date == today,
            Appointment.status != Appointment.STATUS_CANCELLED
        ).order_by(Appointment.time_slot.asc()).all()

        if not appts:
            return {
                "status": "success",
                "response": "You have no appointments scheduled for today.",
                "role": user.role
            }

        lines = ["Here are your scheduled appointments for today:"]
        for a in appts:
            lines.append(format_appointment_card(a))
        return {"status": "success", "response": "\n\n".join(lines), "role": user.role}

    # 2. Next Appointment
    if any(q in msg for q in ["next appointment", "upcoming appointment", "show my upcoming", "when is my appointment"]):
        # If specifically asking for next single appointment
        is_next_only = "next" in msg
        query = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date >= today,
            Appointment.status.in_([Appointment.STATUS_CONFIRMED, Appointment.STATUS_SCHEDULED])
        ).order_by(Appointment.appointment_date.asc(), Appointment.time_slot.asc())

        if is_next_only:
            next_appt = query.first()
            if not next_appt:
                return {
                    "status": "success",
                    "response": "You currently have no upcoming appointments scheduled on Care Connect.",
                    "role": user.role
                }
            return {
                "status": "success",
                "response": f"Your next scheduled consultation is:\n\n{format_appointment_card(next_appt)}",
                "role": user.role
            }
        else:
            all_upcoming = query.all()
            if not all_upcoming:
                return {
                    "status": "success",
                    "response": "You have no upcoming appointments scheduled on Care Connect.",
                    "role": user.role
                }
            lines = [f"You have {len(all_upcoming)} upcoming appointment(s):"]
            for a in all_upcoming:
                lines.append(format_appointment_card(a))
            return {"status": "success", "response": "\n\n".join(lines), "role": user.role}

    # 3. Appointment History
    if any(q in msg for q in ["appointment history", "past appointment", "previous appointment", "my history"]):
        past_appts = Appointment.query.filter(
            Appointment.patient_id == patient.id
        ).filter(
            (Appointment.appointment_date < today) |
            (Appointment.status.in_([Appointment.STATUS_COMPLETED, Appointment.STATUS_CANCELLED]))
        ).order_by(Appointment.appointment_date.desc()).limit(10).all()

        if not past_appts:
            return {
                "status": "success",
                "response": "You have no past consultation records in your appointment history.",
                "role": user.role
            }

        lines = [f"Found {len(past_appts)} past appointment record(s) in your history:"]
        for a in past_appts:
            lines.append(format_appointment_card(a))
        return {"status": "success", "response": "\n\n".join(lines), "role": user.role}

    # 4. Appointment Number Lookup
    if any(q in msg for q in ["appointment number", "tracking number", "booking reference"]):
        latest = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.created_at.desc()).first()
        if not latest:
            return {
                "status": "success",
                "response": "You have not booked any appointments yet on Care Connect.",
                "role": user.role
            }
        ref = latest.appointment_number or latest.appointment_uid
        return {
            "status": "success",
            "response": f"Your most recent appointment number is **{ref}** for your consultation on {latest.appointment_date.strftime('%d %B %Y')}.",
            "role": user.role
        }

    # 5. Status Meaning
    if any(q in msg for q in ["status mean", "appointment status", "what does confirmed mean"]):
        return {
            "status": "success",
            "response": (
                "Care Connect appointment statuses mean:\n"
                "• **Confirmed**: Your 30-minute consultation slot is securely reserved in the hospital database.\n"
                "• **Scheduled**: Your booking is active and awaiting consultation on the target date.\n"
                "• **Completed**: The attending physician has finished your clinical consultation.\n"
                "• **Cancelled**: The appointment was cancelled and the slot was released back into availability."
            ),
            "role": user.role
        }

    # 6. How to Book
    if any(q in msg for q in ["how to book", "how do i book", "book an appointment", "schedule an appointment"]):
        return {
            "status": "success",
            "response": (
                "To book an appointment on Care Connect:\n"
                "1. Go to **Book Consultation** in your dashboard.\n"
                "2. Choose your healthcare facility and specialist physician.\n"
                "3. Select your consultation date.\n"
                "4. Pick an available 30-minute slot and enter your reason for visit.\n"
                "5. Confirm your booking to lock the slot and generate your digital confirmation slip."
            ),
            "role": user.role
        }

    # 7. How to Cancel
    if any(q in msg for q in ["how to cancel", "how do i cancel", "cancel an appointment"]):
        return {
            "status": "success",
            "response": (
                "To cancel an upcoming appointment:\n"
                "1. Open **My Appointments** from your top navigation.\n"
                "2. Find the upcoming appointment in the list.\n"
                "3. Click the **Cancel** button on the appointment card.\n"
                "4. Confirm the cancellation. The consultation slot will be immediately released."
            ),
            "role": user.role
        }

    # 8. Where to find Confirmation / PDF / QR
    if any(q in msg for q in ["confirmation", "download pdf", "where is my pdf", "qr code", "verification code"]):
        return {
            "status": "success",
            "response": (
                "You can access your appointment confirmation slips and verification QR codes anytime:\n"
                "• Go to **My Appointments**.\n"
                "• Click **Download PDF** on any confirmed appointment to get a clinical confirmation slip.\n"
                "• Click **Verify QR** to view the physical verification pass."
            ),
            "role": user.role
        }

    # 9. Phase 9 AI Specialist Guidance
    if any(q in msg for q in ["which specialist", "what specialist", "don't know which doctor", "choose a specialist", "specialist recommendation", "ai specialist"]):
        return {
            "status": "success",
            "response": (
                "You can use Care Connect's AI Specialist Recommendation feature to get a "
                "non-diagnostic specialty suggestion based on the concern you describe. "
                "It will guide you to the most relevant medical department and display matching registered physicians."
            ),
            "role": user.role
        }

    # 10. Phase 11 Smart Appointment Guidance
    if any(q in msg for q in ["smart appointment", "best time to book", "find available slots", "recommend a slot", "flexible slot"]):
        return {
            "status": "success",
            "response": (
                "You can use Smart Appointment to find suitable available slots based on your preferred date and time. "
                "The system ranks verified slots using doctor availability, schedule congestion, and your flexibility preferences."
            ),
            "role": user.role
        }

    # 11. Directory Search fallback (shared)
    dir_res = handle_directory_search(msg)
    if dir_res:
        return {"status": "success", "response": dir_res, "role": user.role}

    return {"status": "fallback", "response": ASSISTANT_UNKNOWN_FALLBACK, "role": user.role}


# ============================================================================
# DOCTOR INTENT HANDLERS
# ============================================================================
def handle_doctor_query(user: User, raw_msg: str, msg: str) -> Dict[str, Any]:
    doctor = Doctor.query.filter_by(user_id=user.id).first()
    if not doctor:
        return {
            "status": "error",
            "response": "Doctor profile record not found.",
            "role": user.role
        }

    today = date.today()

    # 1. Appointments Today
    if any(q in msg for q in ["appointments today", "appointment today", "today's schedule", "my appointments today"]):
        appts = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == today,
            Appointment.status != Appointment.STATUS_CANCELLED
        ).order_by(Appointment.time_slot.asc()).all()

        if not appts:
            return {
                "status": "success",
                "response": "Dr. " + (user.full_name or "Doctor") + ", you have no patient consultations scheduled for today.",
                "role": user.role
            }

        lines = [f"You have {len(appts)} consultation(s) scheduled for today ({today.strftime('%d %B %Y')}):"]
        for a in appts:
            pat_name = a.patient.user.full_name if a.patient and a.patient.user else f"Patient #{a.patient_id}"
            lines.append(f"• **{a.time_slot}** - {pat_name} (Status: {a.status}, Ref: {a.appointment_number or a.id})")
        return {"status": "success", "response": "\n".join(lines), "role": user.role}

    # 2. Upcoming Appointments
    if any(q in msg for q in ["upcoming appointment", "upcoming consultations", "show my upcoming"]):
        appts = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date >= today,
            Appointment.status.in_([Appointment.STATUS_CONFIRMED, Appointment.STATUS_SCHEDULED])
        ).order_by(Appointment.appointment_date.asc(), Appointment.time_slot.asc()).all()

        if not appts:
            return {
                "status": "success",
                "response": "You currently have no upcoming patient consultations scheduled.",
                "role": user.role
            }

        lines = [f"You have {len(appts)} upcoming consultation(s) on your schedule:"]
        for a in appts:
            pat_name = a.patient.user.full_name if a.patient and a.patient.user else f"Patient #{a.patient_id}"
            lines.append(f"• **{a.appointment_date.strftime('%d %b %Y')} at {a.time_slot}** - {pat_name} ({a.status})")
        return {"status": "success", "response": "\n".join(lines), "role": user.role}

    # 3. Working Hours & Availability
    if any(q in msg for q in ["working hours", "my schedule", "my availability", "what are my hours"]):
        status_text = "Active & Available for Bookings" if doctor.is_available else "Off-Duty / Unavailable"
        return {
            "status": "success",
            "response": (
                f"Your clinical practice schedule:\n"
                f"• **Working Days**: {doctor.available_days}\n"
                f"• **Consultation Hours**: {doctor.available_time}\n"
                f"• **Status**: {status_text}\n"
                f"• **Consultation Fee**: ${float(doctor.consultation_fee or 0):.2f}\n"
                f"• **Room**: {doctor.room_number or 'Not assigned'}\n\n"
                f"You can adjust your schedule anytime in **Availability & Schedule**."
            ),
            "role": user.role
        }

    # 4. Affiliated Hospital
    if any(q in msg for q in ["affiliated hospital", "my hospital", "where do i work"]):
        hosp = doctor.hospital
        if not hosp:
            return {
                "status": "success",
                "response": "You are currently not affiliated with a registered hospital.",
                "role": user.role
            }
        return {
            "status": "success",
            "response": (
                f"Your affiliated healthcare facility is:\n"
                f"• **Facility**: {hosp.name}\n"
                f"• **Type**: {hosp.hospital_type}\n"
                f"• **Location**: {hosp.address}, {hosp.city}\n"
                f"• **Registration No**: {hosp.registration_number}"
            ),
            "role": user.role
        }

    # 5. Patient Consultation History
    if any(q in msg for q in ["patient consultation history", "patient history", "completed consultations", "consultation history"]):
        completed = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status == Appointment.STATUS_COMPLETED
        ).order_by(Appointment.appointment_date.desc()).all()

        distinct_patients = len({a.patient_id for a in completed if a.patient_id})
        return {
            "status": "success",
            "response": (
                f"Consultation History Summary for Dr. {user.full_name}:\n"
                f"• **Completed Consultations**: {len(completed)}\n"
                f"• **Unique Patients Attended**: {distinct_patients}\n\n"
                f"You can view your detailed patient history in the **Patient History** portal."
            ),
            "role": user.role
        }

    # 6. Directory Search fallback
    dir_res = handle_directory_search(msg)
    if dir_res:
        return {"status": "success", "response": dir_res, "role": user.role}

    return {"status": "fallback", "response": ASSISTANT_UNKNOWN_FALLBACK, "role": user.role}


# ============================================================================
# HOSPITAL ADMIN INTENT HANDLERS
# ============================================================================
def handle_hospital_query(user: User, raw_msg: str, msg: str) -> Dict[str, Any]:
    hospital = Hospital.query.filter_by(user_id=user.id).first()
    if not hospital:
        return {
            "status": "error",
            "response": "Hospital facility profile record not found.",
            "role": user.role
        }

    today = date.today()

    # 1. Today's Appointment Count & Info
    if any(q in msg for q in ["today's appointment count", "appointment count", "appointments today", "today's count"]):
        today_count = Appointment.query.filter(
            Appointment.hospital_id == hospital.id,
            Appointment.appointment_date == today,
            Appointment.status != Appointment.STATUS_CANCELLED
        ).count()
        return {
            "status": "success",
            "response": f"{hospital.name} has **{today_count}** active appointment(s) scheduled for today ({today.strftime('%d %B %Y')}).",
            "role": user.role
        }

    # 2. Available Doctors & Doctor Availability
    if any(q in msg for q in ["available doctors", "doctor availability", "registered doctors", "specializations", "show doctors"]):
        docs = Doctor.query.join(User).filter(
            Doctor.hospital_id == hospital.id,
            User.is_active == True
        ).all()

        if not docs:
            return {
                "status": "success",
                "response": f"No practicing doctors are currently registered under {hospital.name}.",
                "role": user.role
            }

        lines = [f"Registered physicians at {hospital.name}:"]
        for d in docs:
            status = "Available" if d.is_available else "Unavailable"
            lines.append(f"• **Dr. {d.user.full_name}** ({d.specialization}) - {status} ({d.available_days}, {d.available_time})")
        return {"status": "success", "response": "\n".join(lines), "role": user.role}

    # 3. Hospital Appointment Information
    if any(q in msg for q in ["hospital appointment information", "appointment information", "appointment overview", "facility appointments"]):
        total = Appointment.query.filter_by(hospital_id=hospital.id).count()
        upcoming = Appointment.query.filter(
            Appointment.hospital_id == hospital.id,
            Appointment.appointment_date >= today,
            Appointment.status.in_([Appointment.STATUS_CONFIRMED, Appointment.STATUS_SCHEDULED])
        ).count()
        completed = Appointment.query.filter_by(hospital_id=hospital.id, status=Appointment.STATUS_COMPLETED).count()
        cancelled = Appointment.query.filter_by(hospital_id=hospital.id, status=Appointment.STATUS_CANCELLED).count()

        return {
            "status": "success",
            "response": (
                f"Appointment Overview for {hospital.name}:\n"
                f"• **Total Bookings Recorded**: {total}\n"
                f"• **Active Upcoming Bookings**: {upcoming}\n"
                f"• **Completed Consultations**: {completed}\n"
                f"• **Cancelled Appointments**: {cancelled}"
            ),
            "role": user.role
        }

    # 4. Phase 10 AI Patient Load Prediction
    if any(q in msg for q in ["patient-load prediction", "patient load prediction", "load prediction", "patient load", "forecast"]):
        pred = predict_patient_load(hospital.id)
        if pred.get("status") == "insufficient_data":
            return {
                "status": "success",
                "response": (
                    f"AI Patient Load Prediction for {hospital.name}:\n\n"
                    f"Status: {pred.get('message')}\n\n"
                    f"*Note: This is an operational forecast for hospital resource planning only and is not a medical prediction.*"
                ),
                "role": user.role
            }

        trend = pred.get("trend", "Stable")
        tomorrow_vol = pred.get("tomorrow_predicted_load", 0)
        seven_day_vol = pred.get("next_7_days_total_predicted_load", 0)
        confidence = pred.get("confidence", "Medium")
        peak_day = pred.get("peak_day", "Mid-week")

        return {
            "status": "success",
            "response": (
                f"Operational AI Patient Load Forecast for {hospital.name}:\n"
                f"• **Expected Tomorrow**: ~{tomorrow_vol} appointments\n"
                f"• **Next 7-Day Total**: ~{seven_day_vol} appointments\n"
                f"• **Trend Velocity**: {trend}\n"
                f"• **Peak Volume Day**: {peak_day}\n"
                f"• **Forecast Confidence**: {confidence}\n\n"
                f"*Note: This is an operational forecast for hospital resource planning only and is not a medical prediction.*"
            ),
            "role": user.role
        }

    # 5. Directory Search fallback
    dir_res = handle_directory_search(msg)
    if dir_res:
        return {"status": "success", "response": dir_res, "role": user.role}

    return {"status": "fallback", "response": ASSISTANT_UNKNOWN_FALLBACK, "role": user.role}


# ============================================================================
# DIRECTORY SEARCH (HOSPITALS & PHYSICIANS)
# ============================================================================
def handle_directory_search(msg: str) -> Optional[str]:
    """
    Searches the real Care Connect SQLite database for registered hospitals and doctors.
    Never returns fake or synthetic records.
    """
    # 1. Registered Hospitals Query
    if any(q in msg for q in ["which hospitals are registered", "show hospitals", "registered hospitals", "list hospitals"]):
        hospitals = Hospital.query.order_by(Hospital.name.asc()).all()
        if not hospitals:
            return ASSISTANT_NO_RECORD_FOUND

        lines = [f"Found {len(hospitals)} registered healthcare facility/facilities:"]
        for h in hospitals:
            lines.append(f"• **{h.name}** ({h.city}) - {h.hospital_type}")
        return "\n".join(lines)

    # 2. Doctors by Specialty or Name Query
    specialty_keywords = [
        "cardiolog", "neurolog", "orthoped", "dermatolog",
        "gastroenterolog", "ophthalmolog", "ent", "dentist",
        "pediatric", "gynecolog", "general medicine"
    ]

    matched_spec = None
    for kw in specialty_keywords:
        if kw in msg:
            matched_spec = kw
            break

    is_doc_search = any(term in msg for term in [
        "which doctors", "show doctors", "available doctors",
        "cardiologists", "neurologists", "specialists", "find doctor"
    ]) or (matched_spec is not None)

    if is_doc_search:
        doc_query = Doctor.query.join(User).filter(
            Doctor.is_available == True,
            User.is_active == True
        )

        if matched_spec:
            doc_query = doc_query.filter(Doctor.specialization.ilike(f"%{matched_spec}%"))

        # Check if a specific hospital name is mentioned in the query
        hospitals = Hospital.query.all()
        target_hosp = None
        for h in hospitals:
            if h.name.lower() in msg:
                target_hosp = h
                doc_query = doc_query.filter(Doctor.hospital_id == h.id)
                break

        doctors = doc_query.all()
        if not doctors:
            return ASSISTANT_NO_RECORD_FOUND

        header = f"Found {len(doctors)} available physician(s)"
        if matched_spec:
            header += f" matching '{matched_spec.capitalize()}'"
        if target_hosp:
            header += f" at {target_hosp.name}"
        header += ":"

        lines = [header]
        for d in doctors:
            hosp_name = d.hospital.name if d.hospital else "Affiliated Hospital"
            fee = f"${float(d.consultation_fee or 0):.2f}"
            lines.append(f"• **Dr. {d.user.full_name}** - {d.specialization} at {hosp_name} (Fee: {fee}, Schedule: {d.available_days})")
        return "\n".join(lines)

    return None
