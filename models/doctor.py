from database import db

class Doctor(db.Model):
    """Doctor profile model."""
    __tablename__ = 'doctors'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id', ondelete='SET NULL'), nullable=True)
    specialization = db.Column(db.String(100), nullable=False, index=True)
    qualification = db.Column(db.String(120), nullable=False)
    experience_years = db.Column(db.Integer, default=5)
    consultation_fee = db.Column(db.Float, default=50.0)
    is_available = db.Column(db.Boolean, default=True)
    available_days = db.Column(db.String(100), default="Monday - Friday")
    available_time = db.Column(db.String(60), default="09:00 AM - 05:00 PM")
    room_number = db.Column(db.String(20), default="Room 101")
    bio = db.Column(db.Text, nullable=True)

    # Relationships
    appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic')

    @property
    def start_time(self):
        """Extracts starting consultation time from available_time."""
        if self.available_time and '-' in self.available_time:
            return self.available_time.split('-')[0].strip()
        return "09:00 AM"

    @property
    def end_time(self):
        """Extracts ending consultation time from available_time."""
        if self.available_time and '-' in self.available_time:
            return self.available_time.split('-')[1].strip()
        return "05:00 PM"

    def is_available_today(self) -> bool:
        """Checks if doctor is active and today's weekday is in their schedule."""
        from datetime import date
        if not self.is_available:
            return False
        if not self.available_days:
            return True
        today_name = date.today().strftime('%A')
        days_str = self.available_days.lower()
        if today_name.lower() in days_str:
            return True
        if "monday - friday" in days_str or "mon - fri" in days_str:
            return date.today().weekday() < 5
        if "monday - saturday" in days_str or "mon - sat" in days_str:
            return date.today().weekday() < 6
        if "all days" in days_str or "daily" in days_str or "everyday" in days_str:
            return True
        return False

    def __repr__(self):
        return f'<Doctor Dr. {self.user.full_name if self.user else self.id} - {self.specialization}>'
