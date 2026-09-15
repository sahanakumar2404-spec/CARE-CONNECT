from database import db

class Hospital(db.Model):
    """Hospital facility management model."""
    __tablename__ = 'hospitals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    registration_number = db.Column(db.String(50), unique=True, nullable=False)
    hospital_type = db.Column(db.String(100), default='General Hospital', nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False, index=True)
    contact_email = db.Column(db.String(120), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    total_beds = db.Column(db.Integer, default=150)
    available_beds = db.Column(db.Integer, default=45)
    emergency_available = db.Column(db.Boolean, default=True)
    operational_status = db.Column(db.String(60), default='Normal Operations', nullable=False)
    daily_notice = db.Column(db.Text, nullable=True)

    # Relationships
    doctors = db.relationship('Doctor', backref='hospital', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='hospital', lazy='dynamic')

    def __repr__(self):
        return f'<Hospital {self.name} ({self.city})>'
