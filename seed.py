from datetime import date, timedelta
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment

def seed_initial_data():
    """Seeds default demonstration accounts, profiles, and an initial appointment."""
    # Check if data already exists
    if User.query.first():
        return

    print("Seeding initial demonstration data for Care Connect...")

    # 1. Hospital Admin & Facility
    admin_user = User(
        username='admin',
        email='admin@careconnect.org',
        full_name='Metro Health Authority',
        phone='+1 (212) 555-0100',
        role=User.ROLE_HOSPITAL
    )
    admin_user.set_password('admin123')
    db.session.add(admin_user)
    db.session.flush()

    hospital = Hospital(
        user_id=admin_user.id,
        name='Metro General Hospital & Research Center',
        registration_number='HOSP-NYC-2026-001',
        hospital_type='Multispecialty Teaching & Research Hospital',
        address='450 Lexington Avenue',
        city='New York',
        contact_email='contact@metrohealth.org',
        contact_phone='+1 (212) 555-0199',
        total_beds=320,
        available_beds=78,
        emergency_available=True
    )
    db.session.add(hospital)
    db.session.flush()

    # 2. Doctors
    dr_smith_user = User(
        username='drsmith',
        email='dr.smith@careconnect.org',
        full_name='Dr. Sarah Smith',
        phone='+1 (212) 555-0141',
        role=User.ROLE_DOCTOR
    )
    dr_smith_user.set_password('doctor123')
    db.session.add(dr_smith_user)
    db.session.flush()

    dr_smith = Doctor(
        user_id=dr_smith_user.id,
        hospital_id=hospital.id,
        specialization='Cardiology',
        qualification='MD, FACC - Harvard Medical School',
        experience_years=12,
        consultation_fee=120.0,
        is_available=True,
        available_days='Monday, Wednesday, Friday',
        available_time='09:00 AM - 03:00 PM',
        room_number='Cardiology Wing - Room 304',
        bio='Board-certified cardiologist specializing in preventative cardiac health and arrhythmia management.'
    )
    db.session.add(dr_smith)

    dr_johnson_user = User(
        username='drjohnson',
        email='dr.johnson@careconnect.org',
        full_name='Dr. Marcus Johnson',
        phone='+1 (212) 555-0142',
        role=User.ROLE_DOCTOR
    )
    dr_johnson_user.set_password('doctor123')
    db.session.add(dr_johnson_user)
    db.session.flush()

    dr_johnson = Doctor(
        user_id=dr_johnson_user.id,
        hospital_id=hospital.id,
        specialization='Neurology',
        qualification='MD, PhD - Johns Hopkins University',
        experience_years=9,
        consultation_fee=140.0,
        is_available=True,
        available_days='Tuesday, Thursday, Saturday',
        available_time='10:00 AM - 04:00 PM',
        room_number='Neuroscience Wing - Room 212',
        bio='Neurologist with specialized focus on chronic migraines, concussion therapy, and neurological assessments.'
    )
    db.session.add(dr_johnson)

    dr_patel_user = User(
        username='drpatel',
        email='dr.patel@careconnect.org',
        full_name='Dr. Anita Patel',
        phone='+1 (212) 555-0143',
        role=User.ROLE_DOCTOR
    )
    dr_patel_user.set_password('doctor123')
    db.session.add(dr_patel_user)
    db.session.flush()

    dr_patel = Doctor(
        user_id=dr_patel_user.id,
        hospital_id=hospital.id,
        specialization='General Medicine',
        qualification='MD - Columbia University',
        experience_years=8,
        consultation_fee=75.0,
        is_available=True,
        available_days='Monday - Friday',
        available_time='08:30 AM - 02:30 PM',
        room_number='Outpatient Clinic - Room 108',
        bio='Experienced primary care physician providing comprehensive diagnostic consultations and wellness care.'
    )
    db.session.add(dr_patel)
    db.session.flush()

    # 3. Patient
    patient_user = User(
        username='patient',
        email='patient@careconnect.org',
        full_name='Alex Rivera',
        phone='+1 (212) 555-0812',
        role=User.ROLE_PATIENT
    )
    patient_user.set_password('patient123')
    db.session.add(patient_user)
    db.session.flush()

    patient = Patient(
        user_id=patient_user.id,
        date_of_birth=date(1995, 8, 22),
        gender='Male',
        blood_group='O+',
        address='742 Evergreen Terrace, Apt 12',
        city='New York',
        emergency_contact='+1 (212) 555-0999',
        allergies='Penicillin',
        chronic_conditions='None'
    )
    db.session.add(patient)
    db.session.flush()

    # 4. Sample Appointment
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=dr_smith.id,
        hospital_id=hospital.id,
        appointment_date=date.today() + timedelta(days=2),
        time_slot='10:30 AM - 11:00 AM',
        appointment_number='CC-2026-000001',
        verification_token='CC-VERIFY-2026-DEMO-001',
        status=Appointment.STATUS_CONFIRMED,
        symptoms='Routine annual cardiovascular evaluation and mild exercise fatigue.',
        diagnosis_notes='Patient scheduled for ECG and consultation.'
    )
    db.session.add(appointment)

    db.session.commit()
    print("Database seeded successfully with demo hospital, doctors, patient, and appointment!")
