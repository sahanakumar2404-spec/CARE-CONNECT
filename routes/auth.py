import re
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from services.auth_service import login_user, logout_user
from utils.helpers import validate_email_format

auth_bp = Blueprint('auth', __name__)

def generate_unique_username(base_name: str) -> str:
    """Generates a unique database username based on a name or email prefix."""
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '', base_name.lower().replace(' ', '_'))
    if not cleaned:
        cleaned = "user"
    candidate = cleaned
    counter = 1
    while User.query.filter_by(username=candidate).first():
        candidate = f"{cleaned}_{counter}"
        counter += 1
    return candidate

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticates users and routes them to their role-specific dashboard."""
    # Check if user is already logged in
    if 'user_id' in session:
        role = session.get('user_role')
        if role == User.ROLE_HOSPITAL:
            return redirect(url_for('hospital.dashboard'))
        elif role == User.ROLE_DOCTOR:
            return redirect(url_for('doctor.dashboard'))
        elif role == User.ROLE_PATIENT:
            return redirect(url_for('patient.dashboard'))
        return redirect(url_for('main.index'))

    target_role = request.args.get('role', '').strip().lower()

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()
        expected_role = request.form.get('role', target_role).strip().lower()

        if not identifier or not password:
            flash('Please enter both your email/username and password.', 'danger')
            return render_template('auth/login.html', target_role=target_role)

        # Find user by email (case-insensitive) or username (case-insensitive)
        user = User.query.filter(
            (User.email.ilike(identifier)) | (User.username.ilike(identifier))
        ).first()

        if not user or not user.check_password(password):
            flash('Invalid credentials. Please verify your email/username and password.', 'danger')
            return render_template('auth/login.html', target_role=target_role)

        if not user.is_active:
            flash('This account is currently deactivated. Please contact support.', 'warning')
            return render_template('auth/login.html', target_role=target_role)

        # Optional check if login was requested for a specific role
        if expected_role and user.role != expected_role:
            flash(f'Account found, but it is registered as a {user.role.capitalize()}, not {expected_role.capitalize()}.', 'warning')
            return render_template('auth/login.html', target_role=target_role)

        # Establish secure user session
        login_user(user)
        flash(f'Welcome back, {user.full_name}!', 'success')

        next_url = request.args.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)

        if user.is_hospital():
            return redirect(url_for('hospital.dashboard'))
        elif user.is_doctor():
            return redirect(url_for('doctor.dashboard'))
        elif user.is_patient():
            return redirect(url_for('patient.dashboard'))

        return redirect(url_for('main.index'))

    return render_template('auth/login.html', target_role=target_role)

# Registration endpoints handled below with @auth_bp.route('/register') and @auth_bp.route('/register/patient')

@auth_bp.route('/register/hospital', methods=['GET', 'POST'])
def register_hospital():
    """Registers a new Hospital Facility and Hospital Admin account."""
    if 'user_id' in session:
        flash('You are already signed in. Please log out first to register a new account.', 'info')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        hospital_name = request.form.get('hospital_name', '').strip()
        registration_number = request.form.get('registration_number', '').strip().upper()
        hospital_type = request.form.get('hospital_type', 'General Hospital').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not hospital_name or not registration_number or not address or not city or not contact_phone or not email or not password:
            flash('All required fields must be completed.', 'danger')
            return render_template('auth/register_hospital.html', form_data=request.form)

        if not validate_email_format(email):
            flash('Please enter a valid email address (e.g., admin@hospital.org).', 'danger')
            return render_template('auth/register_hospital.html', form_data=request.form)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/register_hospital.html', form_data=request.form)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('auth/register_hospital.html', form_data=request.form)

        # Check duplicate email
        if User.query.filter(User.email.ilike(email)).first():
            flash('An account with this email address is already registered.', 'danger')
            return render_template('auth/register_hospital.html', form_data=request.form)

        # Check duplicate registration number
        if Hospital.query.filter_by(registration_number=registration_number).first():
            flash('A hospital with this registration number is already registered.', 'danger')
            return render_template('auth/register_hospital.html', form_data=request.form)

        # Create user account for Hospital Admin
        username = generate_unique_username(hospital_name)
        user = User(
            username=username,
            email=email,
            full_name=f"{hospital_name} Admin",
            phone=contact_phone,
            role=User.ROLE_HOSPITAL
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Create Hospital facility profile
        hospital = Hospital(
            user_id=user.id,
            name=hospital_name,
            registration_number=registration_number,
            hospital_type=hospital_type,
            address=address,
            city=city,
            contact_email=email,
            contact_phone=contact_phone,
            total_beds=100,
            available_beds=30,
            emergency_available=True
        )
        db.session.add(hospital)
        db.session.commit()

        login_user(user)
        flash(f'Hospital "{hospital_name}" registered successfully! Welcome to your management dashboard.', 'success')
        return redirect(url_for('hospital.dashboard'))

    return render_template('auth/register_hospital.html', form_data={})

@auth_bp.route('/register/doctor', methods=['GET', 'POST'])
def register_doctor():
    """Registers a new practicing Doctor account."""
    if 'user_id' in session:
        flash('You are already signed in. Please log out first to register a new account.', 'info')
        return redirect(url_for('main.index'))

    hospitals = Hospital.query.order_by(Hospital.name.asc()).all()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        specialization = request.form.get('specialization', '').strip()
        qualification = request.form.get('qualification', '').strip()
        hospital_id = request.form.get('hospital_id', '').strip()
        experience_years = request.form.get('experience_years', '0').strip()
        consultation_fee = request.form.get('consultation_fee', '50.0').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not full_name or not specialization or not qualification or not email or not password or not phone:
            flash('All required fields must be completed.', 'danger')
            return render_template('auth/register_doctor.html', hospitals=hospitals, form_data=request.form)

        if not validate_email_format(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('auth/register_doctor.html', hospitals=hospitals, form_data=request.form)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/register_doctor.html', hospitals=hospitals, form_data=request.form)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('auth/register_doctor.html', hospitals=hospitals, form_data=request.form)

        # Check duplicate email
        if User.query.filter(User.email.ilike(email)).first():
            flash('An account with this email address is already registered.', 'danger')
            return render_template('auth/register_doctor.html', hospitals=hospitals, form_data=request.form)

        # Parse numeric fields safely
        try:
            exp_int = max(0, int(experience_years))
        except ValueError:
            exp_int = 0

        try:
            fee_float = max(0.0, float(consultation_fee))
        except ValueError:
            fee_float = 50.0

        hosp_id_int = None
        if hospital_id and hospital_id.isdigit():
            hosp_id_int = int(hospital_id)

        # Create doctor User
        username = generate_unique_username(full_name)
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            phone=phone,
            role=User.ROLE_DOCTOR
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Create Doctor profile
        doctor = Doctor(
            user_id=user.id,
            hospital_id=hosp_id_int,
            specialization=specialization,
            qualification=qualification,
            experience_years=exp_int,
            consultation_fee=fee_float,
            is_available=True,
            available_days="Monday - Friday",
            available_time="09:00 AM - 05:00 PM",
            room_number="Room 101"
        )
        db.session.add(doctor)
        db.session.commit()

        login_user(user)
        flash(f'Welcome, {full_name}! Your doctor profile has been created.', 'success')
        return redirect(url_for('doctor.dashboard'))

    return render_template('auth/register_doctor.html', hospitals=hospitals, form_data={})

@auth_bp.route('/register', methods=['GET', 'POST'], endpoint='register')
@auth_bp.route('/register/patient', methods=['GET', 'POST'], endpoint='register_patient')
def register_patient():
    """Registers a new Patient user account or routes to role-specific registration."""
    if 'user_id' in session:
        flash('You are already signed in. Please log out first to register a new account.', 'info')
        return redirect(url_for('main.index'))

    if request.method == 'GET':
        role = request.args.get('role', '').strip().lower()
        if role == 'hospital':
            return redirect(url_for('auth.register_hospital'))
        elif role == 'doctor':
            return redirect(url_for('auth.register_doctor'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        dob_str = request.form.get('date_of_birth', '').strip()
        gender = request.form.get('gender', 'Not Specified').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', 'New York').strip()
        blood_group = request.form.get('blood_group', 'O+').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not full_name or not email or not password or not phone:
            flash('All required fields must be completed.', 'danger')
            return render_template('auth/register_patient.html', form_data=request.form)

        if not validate_email_format(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('auth/register_patient.html', form_data=request.form)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter.', 'danger')
            return render_template('auth/register_patient.html', form_data=request.form)

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('auth/register_patient.html', form_data=request.form)

        # Check duplicate email
        if User.query.filter(User.email.ilike(email)).first():
            flash('An account with this email address is already registered.', 'danger')
            return render_template('auth/register_patient.html', form_data=request.form)

        # Parse date of birth
        dob = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                dob = None

        # Create Patient User
        username = generate_unique_username(full_name)
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            phone=phone,
            role=User.ROLE_PATIENT
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Create Patient Profile
        patient = Patient(
            user_id=user.id,
            date_of_birth=dob,
            gender=gender,
            blood_group=blood_group,
            address=address,
            city=city
        )
        db.session.add(patient)
        db.session.commit()

        login_user(user)
        flash('Patient registration successful! Welcome to your health portal.', 'success')
        return redirect(url_for('patient.dashboard'))

    return render_template('auth/register_patient.html', form_data={})

@auth_bp.route('/logout')
def logout():
    """Logs out the active user and securely clears the session."""
    logout_user()
    flash('You have been logged out securely.', 'info')
    return redirect(url_for('main.index'))
