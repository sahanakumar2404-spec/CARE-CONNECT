import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()

def apply_schema_migrations():
    """
    Safely checks existing SQLite tables and migrates schema to match updated models.
    Preserves existing data and seed records without destructive recreations.
    """
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    # Migrate 'hospitals' table if missing Phase 2/3 columns
    if 'hospitals' in table_names:
        columns = [col['name'] for col in inspector.get_columns('hospitals')]
        with db.engine.connect() as conn:
            if 'hospital_type' not in columns:
                conn.execute(
                    text("ALTER TABLE hospitals ADD COLUMN hospital_type VARCHAR(100) DEFAULT 'General Hospital' NOT NULL;")
                )
                conn.execute(
                    text("UPDATE hospitals SET hospital_type = 'Multispecialty Teaching & Research Hospital' WHERE registration_number = 'HOSP-NYC-2026-001';")
                )
            if 'operational_status' not in columns:
                conn.execute(
                    text("ALTER TABLE hospitals ADD COLUMN operational_status VARCHAR(60) DEFAULT 'Normal Operations' NOT NULL;")
                )
            if 'daily_notice' not in columns:
                conn.execute(
                    text("ALTER TABLE hospitals ADD COLUMN daily_notice TEXT;")
                )
                conn.execute(
                    text("UPDATE hospitals SET daily_notice = 'All specialty departments operating normally. Outpatient consultations active.' WHERE registration_number = 'HOSP-NYC-2026-001';")
                )
            conn.commit()

    # Migrate 'appointments' table if missing Phase 6 column / index
    if 'appointments' in table_names:
        columns = [col['name'] for col in inspector.get_columns('appointments')]
        indexes = [idx['name'] for idx in inspector.get_indexes('appointments')]
        with db.engine.connect() as conn:
            if 'appointment_number' not in columns:
                conn.execute(
                    text("ALTER TABLE appointments ADD COLUMN appointment_number VARCHAR(50);")
                )
                conn.execute(
                    text("UPDATE appointments SET appointment_number = 'CC-' || strftime('%Y', appointment_date) || '-' || substr('000000' || id, -6) WHERE appointment_number IS NULL;")
                )
            if 'uq_doctor_date_slot' not in indexes:
                conn.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS uq_doctor_date_slot ON appointments(doctor_id, appointment_date, time_slot) WHERE status != 'cancelled';")
                )
            if 'verification_token' not in columns:
                conn.execute(
                    text("ALTER TABLE appointments ADD COLUMN verification_token VARCHAR(64);")
                )
                conn.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS ix_appointments_verification_token ON appointments(verification_token);")
                )
                conn.execute(
                    text("UPDATE appointments SET verification_token = 'CC-VERIFY-2026-' || substr('000000' || id, -6) WHERE verification_token IS NULL;")
                )
            conn.commit()

def init_db(app):
    """Initializes the database with the Flask app context."""
    # Ensure database folder exists
    db_path = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'sqlite:///' in db_path:
        filepath = db_path.replace('sqlite:///', '')
        folder = os.path.dirname(filepath)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            
    # Ensure generated directories exist
    for directory in [app.config.get('GENERATED_DIR'), 
                      app.config.get('QR_CODES_DIR'), 
                      app.config.get('REPORTS_DIR')]:
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    db.init_app(app)
    
    with app.app_context():
        # Import models so SQLAlchemy knows table definitions
        from models import user, hospital, doctor, patient, appointment
        db.create_all()
        
        # Apply non-destructive schema migrations for existing tables
        apply_schema_migrations()

        # Seed initial sample data if the database has not been seeded yet
        from database.seed import seed_initial_data
        seed_initial_data()
