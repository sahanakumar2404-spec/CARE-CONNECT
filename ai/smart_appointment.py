"""
Care Connect - AI Smart Appointment Recommendation Engine
Phase 11: Modular, explainable scheduling optimization for patients.

Strictly non-diagnostic: Provides appointment scheduling optimization only.
Never diagnoses conditions or prescribes treatments.
Integrates directly with Phase 6 slot generation without duplicate logic.
"""

from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
from database import db
from models.doctor import Doctor
from models.hospital import Hospital
from models.appointment import Appointment
from models.user import User
from services.booking_service import (
    generate_doctor_slots,
    doctor_works_on_date,
    parse_time_str,
    normalize_time_slot
)

# Mandatory Operational Disclaimer
SMART_APPOINTMENT_DISCLAIMER = (
    "This recommendation is for appointment scheduling optimization only and is not "
    "a medical diagnosis, clinical consultation, or emergency guidance."
)


def classify_time_period(time_obj) -> str:
    """Classifies a time object into morning, afternoon, or evening."""
    hour = time_obj.hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"


def normalize_preference_str(val: Optional[str], default: str = "") -> str:
    """Normalizes input strings for robust case-insensitive comparison."""
    if not val:
        return default
    return val.strip().lower().replace("-", "_").replace(" ", "_")


def get_candidate_dates(preferred_date: date, flexibility: str) -> List[date]:
    """
    Computes candidate dates based on user flexibility preferences.
    All dates strictly require date >= date.today().
    """
    today = date.today()
    base_date = preferred_date if preferred_date >= today else today
    norm_flex = normalize_preference_str(flexibility, "exact")

    candidates = []
    if norm_flex in ["somewhat_flexible", "somewhat", "flexible_1_2_days"]:
        # Preferred date + up to 2 days forward, and 1 day back if >= today
        day_offsets = [0, 1, 2]
        if base_date > today:
            day_offsets.insert(0, -1)
        for offset in day_offsets:
            d = base_date + timedelta(days=offset)
            if d >= today and d not in candidates:
                candidates.append(d)
    elif norm_flex in ["flexible", "very_flexible", "flexible_3_5_days"]:
        # Preferred date + up to 5 days forward, and up to 2 days back if >= today
        day_offsets = [0, 1, 2, 3, 4, 5]
        if (base_date - timedelta(days=1)) >= today:
            day_offsets.insert(0, -1)
        if (base_date - timedelta(days=2)) >= today:
            day_offsets.insert(0, -2)
        for offset in day_offsets:
            d = base_date + timedelta(days=offset)
            if d >= today and d not in candidates:
                candidates.append(d)
    else:
        # Exact match
        candidates = [base_date]

    return candidates


def generate_recommendation_reason(
    is_exact_date: bool,
    is_time_match: bool,
    preferred_period: str,
    has_light_schedule: bool,
    is_earlier_slot: bool,
    flexibility: str
) -> str:
    """Generates an intuitive, explainable explanation for why the slot was recommended."""
    parts = []
    if is_exact_date:
        parts.append("Matches your preferred date")
    else:
        parts.append("Accommodates your schedule flexibility")

    if is_time_match and preferred_period != "any_time":
        parts.append(f"falls in your preferred {preferred_period} window")
    elif preferred_period == "any_time":
        parts.append("features immediate slot availability")

    if has_light_schedule:
        parts.append("with the physician having a light clinic schedule that day")

    sentence = ", ".join(parts)
    if not sentence.endswith("."):
        sentence += "."
    return sentence[0].upper() + sentence[1:]


def recommend_smart_slots(
    hospital_id: int,
    specialization: str,
    doctor_id: Optional[int] = None,
    preferred_date: Optional[date] = None,
    preferred_time_period: str = "any_time",
    flexibility: str = "exact",
    max_results: int = 5
) -> Dict[str, Any]:
    """
    Evaluates real database doctors and generates scored, explainable appointment recommendations.
    
    Scoring Weight Architecture:
    - +3 pts: Preferred time period match (or any-time preference)
    - +2 pts: Exact preferred date match
    - +1 pt:  Doctor has fewer than 3 active appointments on that day (less congested)
    - +1 pt:  Earlier suitable slot in consultation hours
    - +1 pt:  Flexibility accommodation satisfied
    """
    today = date.today()

    # 1. Validate Hospital Facility
    hospital = db.session.get(Hospital, hospital_id)
    if not hospital:
        return {
            "status": "error",
            "message": "Selected healthcare facility does not exist.",
            "recommendations": [],
            "disclaimer": SMART_APPOINTMENT_DISCLAIMER
        }

    # 2. Parse & Validate Preferred Date
    if not preferred_date:
        preferred_date = today
    elif isinstance(preferred_date, str):
        try:
            preferred_date = datetime.strptime(preferred_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            preferred_date = today

    if preferred_date < today:
        preferred_date = today

    # 3. Normalize Preferences
    norm_time_period = normalize_preference_str(preferred_time_period, "any_time")
    if norm_time_period not in ["morning", "afternoon", "evening", "any_time"]:
        norm_time_period = "any_time"

    norm_flexibility = normalize_preference_str(flexibility, "exact")

    # 4. Resolve Eligible Registered Physicians from Real SQLite Database
    doctor_query = Doctor.query.join(User).filter(
        Doctor.hospital_id == hospital.id,
        Doctor.is_available == True,
        User.is_active == True
    )

    if specialization and specialization.strip():
        spec_clean = specialization.strip()
        doctor_query = doctor_query.filter(Doctor.specialization.ilike(f"%{spec_clean}%"))

    if doctor_id:
        doctor_query = doctor_query.filter(Doctor.id == doctor_id)

    eligible_doctors = doctor_query.all()

    if not eligible_doctors:
        return {
            "status": "no_slots",
            "message": "No available physicians match the selected hospital and specialization.",
            "recommendations": [],
            "disclaimer": SMART_APPOINTMENT_DISCLAIMER
        }

    # 5. Expand Candidate Dates Based on Flexibility
    candidate_dates = get_candidate_dates(preferred_date, norm_flexibility)

    # 6. Evaluate Slots using Phase 6 Booking Engine
    candidate_slots = []

    for doctor in eligible_doctors:
        for cand_date in candidate_dates:
            # Respect doctor working days
            if not doctor_works_on_date(doctor, cand_date):
                continue

            # Generate slots using Phase 6 logic (excluding booked & cancelled appointments)
            day_slots = generate_doctor_slots(doctor, cand_date)
            if not day_slots:
                continue

            # Query doctor's existing appointment count on this day to evaluate congestion
            existing_count = db.session.query(Appointment).filter(
                Appointment.doctor_id == doctor.id,
                Appointment.appointment_date == cand_date,
                Appointment.status != Appointment.STATUS_CANCELLED
            ).count()

            has_light_schedule = (existing_count < 3)

            for slot in day_slots:
                # Never recommend booked or unavailable slots
                if slot.get("is_booked", False):
                    continue

                slot_time_str = slot.get("start_time", "09:00 AM")
                slot_time_obj = parse_time_str(slot_time_str)
                slot_period = classify_time_period(slot_time_obj)

                # Check if slot matches time period preference
                is_time_match = False
                if norm_time_period == "any_time" or norm_time_period == slot_period:
                    is_time_match = True

                # If flexibility is exact and user specified a time period that does not match, skip
                if norm_flexibility == "exact" and norm_time_period != "any_time" and not is_time_match:
                    continue

                # Compute Explainable Weighted Score
                score = 0
                breakdown = []

                # +3 pts for time preference match
                if is_time_match:
                    score += 3
                    if norm_time_period == "any_time":
                        breakdown.append("Matches any-time consultation preference (+3 pts)")
                    else:
                        breakdown.append(f"Matches preferred {norm_time_period} time period (+3 pts)")
                else:
                    # Alternative period considered due to flexibility
                    breakdown.append(f"Alternative {slot_period} time offered for schedule flexibility (+0 pts)")

                # +2 pts for preferred date match
                is_exact_date = (cand_date == preferred_date)
                if is_exact_date:
                    score += 2
                    breakdown.append("Exact match for preferred consultation date (+2 pts)")
                else:
                    score += 1
                    days_diff = abs((cand_date - preferred_date).days)
                    breakdown.append(f"Accommodates date flexibility within {days_diff} day(s) (+1 pt)")

                # +1 pt for light doctor workload
                if has_light_schedule:
                    score += 1
                    breakdown.append("Physician has low appointment density on this day (+1 pt)")

                # +1 pt for earlier slot in the day
                is_earlier_slot = (slot_time_obj.hour < 12)
                if is_earlier_slot:
                    score += 1
                    breakdown.append("Earlier morning consultation slot in daily schedule (+1 pt)")

                # +1 pt for satisfying flexibility window
                if norm_flexibility != "exact":
                    score += 1
                    breakdown.append("Flexibility criteria successfully satisfied (+1 pt)")

                explanation = generate_recommendation_reason(
                    is_exact_date=is_exact_date,
                    is_time_match=is_time_match,
                    preferred_period=norm_time_period,
                    has_light_schedule=has_light_schedule,
                    is_earlier_slot=is_earlier_slot,
                    flexibility=norm_flexibility
                )

                candidate_slots.append({
                    "hospital_id": hospital.id,
                    "hospital_name": hospital.name,
                    "hospital_city": hospital.city,
                    "doctor_id": doctor.id,
                    "doctor_name": doctor.user.full_name if doctor.user else f"Doctor #{doctor.id}",
                    "specialization": doctor.specialization,
                    "consultation_fee": float(doctor.consultation_fee or 0.0),
                    "date": cand_date.strftime("%Y-%m-%d"),
                    "date_formatted": cand_date.strftime("%d %B %Y"),
                    "day_name": cand_date.strftime("%A"),
                    "time_slot": slot["time_slot"],
                    "start_time": slot["start_time"],
                    "end_time": slot["end_time"],
                    "time_period": slot_period.capitalize(),
                    "score": score,
                    "score_breakdown": breakdown,
                    "explanation": explanation
                })

    if not candidate_slots:
        return {
            "status": "no_slots",
            "message": "No available consultation slots matched your preferences. Try broadening your date or time flexibility.",
            "recommendations": [],
            "disclaimer": SMART_APPOINTMENT_DISCLAIMER
        }

    # 7. Sort Recommendations:
    # Primary: score (descending)
    # Secondary: date (ascending)
    # Tertiary: start_time (ascending)
    candidate_slots.sort(
        key=lambda s: (
            -s["score"],
            s["date"],
            parse_time_str(s["start_time"])
        )
    )

    top_recommendations = candidate_slots[:max_results]

    return {
        "status": "success",
        "message": f"Identified {len(top_recommendations)} top recommended consultation slots.",
        "recommendations": top_recommendations,
        "total_evaluated": len(candidate_slots),
        "disclaimer": SMART_APPOINTMENT_DISCLAIMER
    }
