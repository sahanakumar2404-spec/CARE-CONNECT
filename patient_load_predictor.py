"""
Care Connect - AI Patient Load Prediction Engine
Module: ai/patient_load_predictor.py

Provides explainable, data-driven operational capacity forecasting for hospital administrators.
Estimates upcoming appointment/patient load using real historical Care Connect appointment activity.

OPERATIONAL BOUNDARY:
- This module is strictly an operational capacity planning tool.
- It predicts patient/appointment volume only.
- It NEVER predicts diseases, health outcomes, or medical conditions.
- Uses real database appointment records only.
"""

from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
from sqlalchemy import func
from database import db
from models.appointment import Appointment
from models.doctor import Doctor

# Mandatory operational disclaimer
DISCLAIMER_TEXT = (
    "Predictions are estimates based on historical Care Connect appointment activity "
    "and may differ from actual patient volume."
)

INSUFFICIENT_DATA_TEXT = "Insufficient historical data for reliable prediction."
INSUFFICIENT_SPECIALTY_TEXT = "Insufficient data for specialization-level prediction."

MIN_HISTORICAL_DAYS_REQUIRED = 3
LOOKBACK_DAYS = 30


def get_hospital_daily_counts(hospital_id: int, lookback_days: int = LOOKBACK_DAYS) -> Dict[date, int]:
    """
    Aggregates historical daily non-cancelled appointment counts for a specific hospital facility.
    Cancelled appointments are strictly excluded from active patient load.
    """
    cutoff_date = date.today() - timedelta(days=lookback_days)
    
    # Query non-cancelled appointments within lookback window
    records = db.session.query(
        Appointment.appointment_date,
        func.count(Appointment.id)
    ).filter(
        Appointment.hospital_id == hospital_id,
        Appointment.appointment_date >= cutoff_date,
        Appointment.appointment_date <= date.today(),
        Appointment.status != Appointment.STATUS_CANCELLED
    ).group_by(Appointment.appointment_date).all()

    daily_counts = {record[0]: record[1] for record in records}
    return daily_counts


def predict_patient_load(hospital_id: int) -> Dict[str, Any]:
    """
    Generates explainable operational patient load forecasts for the logged-in hospital.

    Algorithm:
    1. Aggregates historical daily counts (excluding cancelled appointments).
    2. Enforces data sufficiency threshold (minimum 3 active days).
    3. Calculates 7-day recent moving average (MA_7).
    4. Evaluates day-of-week historical patterns (DoW).
    5. Measures recent velocity/trend.
    6. Produces 7-day forward projection (Tomorrow through Day 7).
    7. Computes specialization distribution if sufficient records exist.
    """
    today = date.today()
    daily_counts = get_hospital_daily_counts(hospital_id, LOOKBACK_DAYS)

    # Today's actual count
    today_count = daily_counts.get(today, 0)

    # Historical days excluding today
    past_counts = {d: count for d, count in daily_counts.items() if d < today}
    num_historical_days = len(past_counts)

    # Check for data sufficiency
    if num_historical_days < MIN_HISTORICAL_DAYS_REQUIRED:
        return {
            'has_sufficient_data': False,
            'message': INSUFFICIENT_DATA_TEXT,
            'today_count': today_count,
            'recent_average': 0.0,
            'predicted_tomorrow': 0,
            'trend': 'Insufficient Data',
            'confidence': 'Low',
            'confidence_display': 'Prediction confidence: Low',
            'historical_days_used': num_historical_days,
            'explanation': INSUFFICIENT_DATA_TEXT,
            'forecast_7days': [],
            'chart_data': {
                'historical_labels': [d.strftime('%b %d') for d in sorted(daily_counts.keys())],
                'historical_counts': [daily_counts[d] for d in sorted(daily_counts.keys())],
                'forecast_labels': [],
                'forecast_counts': []
            },
            'specialty_breakdown': [],
            'specialty_message': INSUFFICIENT_SPECIALTY_TEXT,
            'disclaimer': DISCLAIMER_TEXT
        }

    # 1. Calculate 7-day recent average
    recent_7_dates = [today - timedelta(days=i) for i in range(1, 8)]
    recent_7_counts = [daily_counts.get(d, 0) for d in recent_7_dates]
    active_recent_counts = [c for c in recent_7_counts if c > 0]
    
    if active_recent_counts:
        recent_7_avg = sum(recent_7_counts) / 7.0
    else:
        # Fallback to overall historical average
        recent_7_avg = sum(past_counts.values()) / max(1, len(past_counts))

    overall_avg = sum(past_counts.values()) / max(1, len(past_counts))

    # 2. Day of Week Historical Multipliers
    dow_counts = defaultdict(list)
    for past_date, count in past_counts.items():
        dow = past_date.weekday()  # 0=Monday, 6=Sunday
        dow_counts[dow].append(count)

    dow_averages = {}
    for dow, counts in dow_counts.items():
        dow_averages[dow] = sum(counts) / len(counts)

    # 3. Recent Trend Slope (last 3 days vs prior 4 days)
    last_3_days = [daily_counts.get(today - timedelta(days=i), 0) for i in range(1, 4)]
    prior_4_days = [daily_counts.get(today - timedelta(days=i), 0) for i in range(4, 8)]
    avg_last_3 = sum(last_3_days) / 3.0 if last_3_days else recent_7_avg
    avg_prior_4 = sum(prior_4_days) / 4.0 if prior_4_days else recent_7_avg
    trend_delta = avg_last_3 - avg_prior_4

    # 4. Multi-Day 7-Day Forecast (Tomorrow through Day 7)
    forecast_7days = []
    tomorrow = today + timedelta(days=1)
    
    for offset in range(1, 8):
        target_date = today + timedelta(days=offset)
        dow = target_date.weekday()
        
        dow_avg = dow_averages.get(dow, recent_7_avg)
        
        # Weighted formula: 60% recent 7-day MA + 30% day-of-week pattern + 10% trend delta
        raw_pred = (0.60 * recent_7_avg) + (0.30 * dow_avg) + (0.10 * trend_delta)
        predicted_load = max(0, int(round(raw_pred)))

        # Trend determination relative to recent 7-day average
        diff_pct = (predicted_load - recent_7_avg) / max(1.0, recent_7_avg)
        if diff_pct > 0.10:
            day_trend = "Higher than recent average"
            trend_badge = "Higher"
        elif diff_pct < -0.10:
            day_trend = "Lower than recent average"
            trend_badge = "Lower"
        else:
            day_trend = "Consistent with recent average"
            trend_badge = "Consistent"

        # Confidence assessment based on historical depth and forecast horizon
        if num_historical_days >= 14 and offset <= 3:
            day_conf = "High"
        elif num_historical_days >= 7 and offset <= 5:
            day_conf = "Medium"
        else:
            day_conf = "Medium" if num_historical_days >= 7 else "Low"

        forecast_7days.append({
            'date': target_date,
            'date_str': target_date.strftime('%a, %b %d'),
            'day_name': target_date.strftime('%A'),
            'predicted_load': predicted_load,
            'trend': day_trend,
            'trend_badge': trend_badge,
            'confidence': day_conf,
            'confidence_display': f"Prediction confidence: {day_conf}"
        })

    # Tomorrow's forecast summary
    tomorrow_forecast = forecast_7days[0]
    predicted_tomorrow = tomorrow_forecast['predicted_load']
    overall_trend = tomorrow_forecast['trend']
    overall_confidence = tomorrow_forecast['confidence']

    # Explainable rationale
    if trend_delta > 0.5:
        explanation = "Recent appointment activity shows an upward trend compared with the previous period."
    elif trend_delta < -0.5:
        explanation = "Recent appointment activity shows a downward trend compared with the previous period."
    else:
        explanation = "Recent appointment activity remains steady and consistent with normal operational baseline."

    # 5. Chart.js Series Data
    # Sorted last 14 historical days
    sorted_history_dates = sorted([d for d in daily_counts.keys() if d >= today - timedelta(days=14)])
    chart_historical_labels = [d.strftime('%b %d') for d in sorted_history_dates]
    chart_historical_counts = [daily_counts[d] for d in sorted_history_dates]

    chart_forecast_labels = [item['date'].strftime('%b %d') for item in forecast_7days]
    chart_forecast_counts = [item['predicted_load'] for item in forecast_7days]

    # 6. Specialization Breakdown (Secondary Feature)
    total_appointments_count = db.session.query(func.count(Appointment.id)).filter(
        Appointment.hospital_id == hospital_id,
        Appointment.status != Appointment.STATUS_CANCELLED
    ).scalar() or 0

    specialty_breakdown = []
    specialty_message = ""

    if total_appointments_count >= 10:
        # Group by doctor specialization
        spec_records = db.session.query(
            Doctor.specialization,
            func.count(Appointment.id)
        ).join(
            Appointment, Doctor.id == Appointment.doctor_id
        ).filter(
            Appointment.hospital_id == hospital_id,
            Appointment.status != Appointment.STATUS_CANCELLED
        ).group_by(Doctor.specialization).all()

        total_spec_appts = sum(r[1] for r in spec_records)
        if total_spec_appts > 0:
            for spec, count in sorted(spec_records, key=lambda x: x[1], reverse=True):
                share = count / float(total_spec_appts)
                spec_tomorrow_load = max(0, int(round(predicted_tomorrow * share)))
                specialty_breakdown.append({
                    'specialization': spec,
                    'historical_count': count,
                    'percentage': round(share * 100, 1),
                    'predicted_load': spec_tomorrow_load
                })
    else:
        specialty_message = INSUFFICIENT_SPECIALTY_TEXT

    return {
        'has_sufficient_data': True,
        'message': "",
        'today_count': today_count,
        'recent_average': round(recent_7_avg, 1),
        'overall_average': round(overall_avg, 1),
        'predicted_tomorrow': predicted_tomorrow,
        'trend': overall_trend,
        'trend_badge': tomorrow_forecast['trend_badge'],
        'confidence': overall_confidence,
        'confidence_display': f"Prediction confidence: {overall_confidence}",
        'historical_days_used': num_historical_days,
        'explanation': explanation,
        'forecast_7days': forecast_7days,
        'chart_data': {
            'historical_labels': chart_historical_labels,
            'historical_counts': chart_historical_counts,
            'forecast_labels': chart_forecast_labels,
            'forecast_counts': chart_forecast_counts
        },
        'specialty_breakdown': specialty_breakdown,
        'specialty_message': specialty_message,
        'disclaimer': DISCLAIMER_TEXT
    }
