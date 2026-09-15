from flask import Blueprint

# Package exports for blueprints
from routes.main import main_bp
from routes.auth import auth_bp
from routes.hospital import hospital_bp
from routes.doctor import doctor_bp
from routes.patient import patient_bp
from routes.assistant import assistant_bp

def register_blueprints(app):
    """Registers all application blueprints."""
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(hospital_bp, url_prefix='/hospital')
    app.register_blueprint(doctor_bp, url_prefix='/doctor')
    app.register_blueprint(patient_bp, url_prefix='/patient')
    app.register_blueprint(assistant_bp)
