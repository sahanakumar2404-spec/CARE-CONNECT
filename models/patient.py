from database import db

class Patient(db.Model):
    """Patient profile model."""
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), default='Not Specified')
    blood_group = db.Column(db.String(10), default='O+')
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), default='New York')
    emergency_contact = db.Column(db.String(30), nullable=True)
    allergies = db.Column(db.String(255), default='None reported')
    chronic_conditions = db.Column(db.String(255), default='None reported')

    # Relationships
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic')

    def __repr__(self):
        return f'<Patient {self.user.full_name if self.user else self.id}>'
