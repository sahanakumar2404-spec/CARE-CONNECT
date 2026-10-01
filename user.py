from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from database import db

class User(db.Model):
    """Core User model supporting Hospital Admin, Doctor, and Patient roles."""
    __tablename__ = 'users'

    ROLE_HOSPITAL = 'hospital'
    ROLE_DOCTOR = 'doctor'
    ROLE_PATIENT = 'patient'
    ROLES = [ROLE_HOSPITAL, ROLE_DOCTOR, ROLE_PATIENT]

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Profiles (one-to-one)
    hospital_profile = db.relationship('Hospital', backref='user', uselist=False, cascade='all, delete-orphan')
    doctor_profile = db.relationship('Doctor', backref='user', uselist=False, cascade='all, delete-orphan')
    patient_profile = db.relationship('Patient', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password: str):
        """Hashes and sets the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verifies a plain password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def is_hospital(self) -> bool:
        return self.role == self.ROLE_HOSPITAL

    def is_doctor(self) -> bool:
        return self.role == self.ROLE_DOCTOR

    def is_patient(self) -> bool:
        return self.role == self.ROLE_PATIENT

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
