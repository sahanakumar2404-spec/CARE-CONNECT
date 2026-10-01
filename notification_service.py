from datetime import date, datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from database import db
from models.appointment import Appointment
from models.notification import Notification
from models.user import User


def create_notification(
    recipient_user_id: int,
    notification_type: str,
    title: str,
    message: str,
    related_appointment_id: int = None,
    event_key: str = None
) -> Notification:
    """
    Creates an in-app notification with idempotency protection.
    If event_key is provided and already exists, returns the existing record.
    """
    if event_key:
        existing = Notification.query.filter_by(event_key=event_key).first()
        if existing:
            return existing

    notification = Notification(
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        title=title.strip(),
        message=message.strip(),
        related_appointment_id=related_appointment_id,
        event_key=event_key,
        is_read=False,
        created_at=datetime.now(timezone.utc)
    )

    try:
        db.session.add(notification)
        db.session.commit()
        return notification
    except IntegrityError:
        db.session.rollback()
        if event_key:
            return Notification.query.filter_by(event_key=event_key).first()
        return None
    except Exception:
        db.session.rollback()
        return None


def _format_doctor_name(raw_name: str) -> str:
    if not raw_name:
        return "Doctor"
    name = raw_name.strip()
    if name.startswith("Dr.") or name.startswith("Dr "):
        return name
    return f"Dr. {name}"


def notify_appointment_booked(appointment: Appointment):
    """
    Dispatches in-app notifications to Patient, Doctor, and Hospital
    when an appointment is successfully booked.
    """
    if not appointment:
        return

    formatted_date = appointment.appointment_date.strftime('%B %d, %Y')
    doctor_name = _format_doctor_name(
        appointment.doctor.user.full_name 
        if appointment.doctor and appointment.doctor.user 
        else "Physician"
    )
    specialty = appointment.doctor.specialization if appointment.doctor else "General Consultation"
    hospital_name = (
        appointment.hospital.name 
        if appointment.hospital 
        else "Care Connect Partner Facility"
    )
    ref = appointment.appointment_number or appointment.appointment_uid[:8]

    # 1. Patient Notification
    if appointment.patient and appointment.patient.user_id:
        create_notification(
            recipient_user_id=appointment.patient.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Appointment Booked",
            message=(
                f"Your appointment with {doctor_name} ({specialty}) at {hospital_name} "
                f"on {formatted_date} at {appointment.time_slot} is confirmed. "
                f"Appointment Number: {ref}."
            ),
            related_appointment_id=appointment.id,
            event_key=f"booked:{appointment.id}:{appointment.patient.user_id}"
        )

    # 2. Doctor Notification
    if appointment.doctor and appointment.doctor.user_id:
        create_notification(
            recipient_user_id=appointment.doctor.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="New Appointment Scheduled",
            message=(
                f"New consultation scheduled for {formatted_date} at {appointment.time_slot}. "
                f"Reference: {ref}."
            ),
            related_appointment_id=appointment.id,
            event_key=f"booked:{appointment.id}:{appointment.doctor.user_id}"
        )

    # 3. Hospital Facility Notification
    if appointment.hospital and appointment.hospital.user_id:
        create_notification(
            recipient_user_id=appointment.hospital.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Facility Consultation Scheduled",
            message=(
                f"New consultation scheduled with {doctor_name} ({specialty}) "
                f"on {formatted_date} at {appointment.time_slot}. Reference: {ref}."
            ),
            related_appointment_id=appointment.id,
            event_key=f"booked:{appointment.id}:{appointment.hospital.user_id}"
        )


def notify_appointment_cancelled(appointment: Appointment, cancelled_by_user=None):
    """
    Dispatches in-app notifications when an appointment is cancelled.
    Notifies Patient, Doctor, and Hospital.
    """
    if not appointment:
        return

    formatted_date = appointment.appointment_date.strftime('%B %d, %Y')
    doctor_name = _format_doctor_name(
        appointment.doctor.user.full_name 
        if appointment.doctor and appointment.doctor.user 
        else "Physician"
    )
    ref = appointment.appointment_number or appointment.appointment_uid[:8]

    # 1. Patient Notification
    if appointment.patient and appointment.patient.user_id:
        create_notification(
            recipient_user_id=appointment.patient.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_CANCELLED,
            title="Appointment Cancelled",
            message=(
                f"Your appointment {ref} with {doctor_name} "
                f"on {formatted_date} at {appointment.time_slot} has been cancelled."
            ),
            related_appointment_id=appointment.id,
            event_key=f"cancelled:{appointment.id}:{appointment.patient.user_id}"
        )

    # 2. Doctor Notification
    if appointment.doctor and appointment.doctor.user_id:
        create_notification(
            recipient_user_id=appointment.doctor.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_CANCELLED,
            title="Appointment Cancelled",
            message=(
                f"The appointment on {formatted_date} at {appointment.time_slot} "
                f"(Reference: {ref}) has been cancelled."
            ),
            related_appointment_id=appointment.id,
            event_key=f"cancelled:{appointment.id}:{appointment.doctor.user_id}"
        )

    # 3. Hospital Facility Notification
    if appointment.hospital and appointment.hospital.user_id:
        create_notification(
            recipient_user_id=appointment.hospital.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_CANCELLED,
            title="Appointment Cancelled",
            message=(
                f"Consultation with {doctor_name} on {formatted_date} "
                f"at {appointment.time_slot} (Reference: {ref}) has been cancelled."
            ),
            related_appointment_id=appointment.id,
            event_key=f"cancelled:{appointment.id}:{appointment.hospital.user_id}"
        )


def notify_appointment_status_updated(appointment: Appointment, old_status: str, new_status: str):
    """
    Dispatches in-app notification to the patient when appointment status changes
    (e.g., marked Confirmed or Completed by doctor).
    """
    if not appointment or not new_status:
        return

    formatted_date = appointment.appointment_date.strftime('%B %d, %Y')
    doctor_name = _format_doctor_name(
        appointment.doctor.user.full_name 
        if appointment.doctor and appointment.doctor.user 
        else "Physician"
    )
    ref = appointment.appointment_number or appointment.appointment_uid[:8]
    status_label = new_status.capitalize()

    if appointment.patient and appointment.patient.user_id:
        create_notification(
            recipient_user_id=appointment.patient.user_id,
            notification_type=Notification.TYPE_APPOINTMENT_STATUS_UPDATED,
            title=f"Appointment Status: {status_label}",
            message=(
                f"Your appointment {ref} with {doctor_name} on {formatted_date} "
                f"has been updated to '{status_label}'."
            ),
            related_appointment_id=appointment.id,
            event_key=f"status:{appointment.id}:{new_status.lower()}:{appointment.patient.user_id}"
        )


def check_and_generate_reminders_for_user(user: User) -> list:
    """
    Identifies due appointment reminders for the specified user within an upcoming window
    (today through next 2 days), strictly ignoring cancelled and completed records.
    Uses idempotency keys to guarantee duplicate prevention across repeated executions.
    """
    if not user:
        return []

    today = date.today()
    window_end = today + timedelta(days=2)
    generated = []

    # 1. Patient Reminders
    if user.is_patient() and user.patient_profile:
        patient_id = user.patient_profile.id
        appts = Appointment.query.filter(
            Appointment.patient_id == patient_id,
            Appointment.appointment_date >= today,
            Appointment.appointment_date <= window_end,
            Appointment.status.notin_([Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED])
        ).all()

        for appt in appts:
            doctor_name = _format_doctor_name(
                appt.doctor.user.full_name 
                if appt.doctor and appt.doctor.user 
                else "Physician"
            )
            hospital_name = appt.hospital.name if appt.hospital else "Care Connect Facility"
            formatted_date = appt.appointment_date.strftime('%B %d, %Y')
            ref = appt.appointment_number or appt.appointment_uid[:8]
            day_text = "today" if appt.appointment_date == today else f"on {formatted_date}"

            event_key = f"reminder:{appt.id}:{appt.appointment_date}:{user.id}"
            notif = create_notification(
                recipient_user_id=user.id,
                notification_type=Notification.TYPE_UPCOMING_APPOINTMENT,
                title="Upcoming Appointment Reminder",
                message=(
                    f"Reminder: You have an appointment with {doctor_name} "
                    f"at {hospital_name} {day_text} at {appt.time_slot}. "
                    f"Reference: {ref}."
                ),
                related_appointment_id=appt.id,
                event_key=event_key
            )
            if notif:
                generated.append(notif)

    # 2. Doctor Reminders
    elif user.is_doctor() and user.doctor_profile:
        doctor_id = user.doctor_profile.id
        appts = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date >= today,
            Appointment.appointment_date <= window_end,
            Appointment.status.notin_([Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED])
        ).all()

        for appt in appts:
            formatted_date = appt.appointment_date.strftime('%B %d, %Y')
            ref = appt.appointment_number or appt.appointment_uid[:8]
            day_text = "today" if appt.appointment_date == today else f"on {formatted_date}"

            event_key = f"reminder:{appt.id}:{appt.appointment_date}:{user.id}"
            notif = create_notification(
                recipient_user_id=user.id,
                notification_type=Notification.TYPE_UPCOMING_APPOINTMENT,
                title="Upcoming Consultation Reminder",
                message=(
                    f"Reminder: You have a scheduled consultation {day_text} "
                    f"at {appt.time_slot}. Reference: {ref}."
                ),
                related_appointment_id=appt.id,
                event_key=event_key
            )
            if notif:
                generated.append(notif)

    # 3. Hospital Facility Reminders
    elif user.is_hospital() and user.hospital_profile:
        hospital_id = user.hospital_profile.id
        appts = Appointment.query.filter(
            Appointment.hospital_id == hospital_id,
            Appointment.appointment_date >= today,
            Appointment.appointment_date <= window_end,
            Appointment.status.notin_([Appointment.STATUS_CANCELLED, Appointment.STATUS_COMPLETED])
        ).all()

        for appt in appts:
            formatted_date = appt.appointment_date.strftime('%B %d, %Y')
            doctor_name = _format_doctor_name(
                appt.doctor.user.full_name 
                if appt.doctor and appt.doctor.user 
                else "Physician"
            )
            ref = appt.appointment_number or appt.appointment_uid[:8]
            day_text = "today" if appt.appointment_date == today else f"on {formatted_date}"

            event_key = f"reminder:{appt.id}:{appt.appointment_date}:{user.id}"
            notif = create_notification(
                recipient_user_id=user.id,
                notification_type=Notification.TYPE_UPCOMING_APPOINTMENT,
                title="Upcoming Facility Appointment",
                message=(
                    f"Reminder: Scheduled consultation with {doctor_name} "
                    f"{day_text} at {appt.time_slot}. Reference: {ref}."
                ),
                related_appointment_id=appt.id,
                event_key=event_key
            )
            if notif:
                generated.append(notif)

    return generated


def get_user_notifications(user_id: int, limit: int = 50, unread_only: bool = False) -> list:
    """Retrieves notifications for the specified user ordered newest first."""
    query = Notification.query.filter_by(recipient_user_id=user_id)
    if unread_only:
        query = query.filter_by(is_read=False)
    return query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()


def get_unread_count(user_id: int) -> int:
    """Returns the total number of unread notifications for a user."""
    if not user_id:
        return 0
    return db.session.query(func.count(Notification.id)).filter_by(
        recipient_user_id=user_id,
        is_read=False
    ).scalar() or 0


def mark_as_read(notification_id: int, user_id: int) -> tuple[bool, str]:
    """
    Marks a notification as read if it belongs to user_id.
    Returns (True, 'Success') or (False, reason).
    """
    notif = db.session.get(Notification, notification_id)
    if not notif:
        return False, "Notification not found."
    if notif.recipient_user_id != user_id:
        return False, "Access Denied: Notification belongs to another user."

    notif.mark_as_read()
    try:
        db.session.commit()
        return True, "Notification marked as read."
    except Exception as e:
        db.session.rollback()
        return False, f"Failed to mark as read: {str(e)}"


def mark_all_as_read(user_id: int) -> int:
    """
    Marks all unread notifications as read for the user.
    Returns the count of notifications marked as read.
    """
    if not user_id:
        return 0
    unread_notifs = Notification.query.filter_by(recipient_user_id=user_id, is_read=False).all()
    now_utc = datetime.now(timezone.utc)
    count = len(unread_notifs)
    for n in unread_notifs:
        n.is_read = True
        n.read_at = now_utc

    try:
        db.session.commit()
        return count
    except Exception:
        db.session.rollback()
        return 0
