import secrets
import uuid
from datetime import datetime, timezone
from database import db

from sqlalchemy import text

class Appointment(db.Model):
    """Appointment model linking Patient, Doctor, and Hospital."""
    __tablename__ = 'appointments'

    STATUS_SCHEDULED = 'scheduled'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    id = db.Column(db.Integer, primary_key=True)
    appointment_uid = db.Column(
        db.String(36), 
        unique=True, 
        nullable=False, 
        default=lambda: str(uuid.uuid4())
    )
    appointment_number = db.Column(
        db.String(50),
        unique=True,
        nullable=True,
        index=True
    )
    verification_token = db.Column(
        db.String(64),
        unique=True,
        nullable=True,
        index=True,
        default=lambda: secrets.token_urlsafe(24)
    )
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', ondelete='CASCADE'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True)
    
    appointment_date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default=STATUS_SCHEDULED, nullable=False)
    
    symptoms = db.Column(db.Text, nullable=True)
    diagnosis_notes = db.Column(db.Text, nullable=True)
    qr_code_file = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index(
            'uq_doctor_date_slot',
            'doctor_id',
            'appointment_date',
            'time_slot',
            unique=True,
            sqlite_where=text("status != 'cancelled'")
        ),
    )

    @classmethod
    def generate_appointment_number(cls, target_date=None) -> str:
        """Generates a sequential, guaranteed-unique appointment number like CC-2026-000001."""
        year = target_date.year if target_date else datetime.now().year
        count = cls.query.count() + 1
        candidate = f"CC-{year}-{str(count).zfill(6)}"
        while cls.query.filter_by(appointment_number=candidate).first():
            count += 1
            candidate = f"CC-{year}-{str(count).zfill(6)}"
        return candidate

    def can_transition_to(self, new_status: str) -> tuple[bool, str]:
        """
        Validates whether the appointment can transition to new_status.
        Allowed:
          - confirmed/scheduled -> completed
          - confirmed/scheduled -> cancelled
          - confirmed -> confirmed
        Forbidden:
          - completed -> cancelled / confirmed (completed appointments cannot be altered)
          - cancelled -> completed / confirmed (cancelled appointments cannot be reactivated)
        """
        current = (self.status or "").lower()
        target = (new_status or "").lower()

        if current == target:
            return True, ""

        if current == self.STATUS_COMPLETED:
            return False, "Completed appointments cannot be modified or cancelled."

        if current == self.STATUS_CANCELLED:
            return False, "Cancelled appointments cannot be modified or reactivated."

        if target in [self.STATUS_COMPLETED, self.STATUS_CANCELLED, self.STATUS_CONFIRMED]:
            return True, ""

        return False, f"Invalid appointment status transition from '{current}' to '{target}'."

    def can_cancel(self, by_patient: bool = True) -> tuple[bool, str]:
        """
        Validates if the appointment can be cancelled.
        - Cannot cancel already cancelled appointments.
        - Cannot cancel completed appointments.
        - Cannot cancel past appointments.
        """
        from datetime import date
        current = (self.status or "").lower()

        if current == self.STATUS_CANCELLED:
            return False, "This appointment has already been cancelled."

        if current == self.STATUS_COMPLETED:
            return False, "Completed appointments cannot be cancelled."

        if self.appointment_date and self.appointment_date < date.today():
            return False, "Past appointments cannot be cancelled."

        return True, ""

    def __repr__(self):
        ref = self.appointment_number or self.appointment_uid[:8]
        return f'<Appointment #{self.id} {ref} ({self.status})>'
