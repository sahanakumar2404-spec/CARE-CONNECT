import unittest
from datetime import date
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment

class CareConnectPhase2AuthTestCase(unittest.TestCase):
    def setUp(self):
        """Sets up testing application with isolated in-memory database."""
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        """Cleans up testing database context."""
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def test_demo_accounts_seeded_and_passwords_hashed(self):
        """Verifies demo accounts exist, have correct roles, and passwords are not stored in plaintext."""
        demo_specs = [
            ('admin@careconnect.org', 'admin123', User.ROLE_HOSPITAL),
            ('dr.smith@careconnect.org', 'doctor123', User.ROLE_DOCTOR),
            ('patient@careconnect.org', 'patient123', User.ROLE_PATIENT)
        ]
        for email, pwd, expected_role in demo_specs:
            user = User.query.filter_by(email=email).first()
            self.assertIsNotNone(user, f"Demo user {email} should be seeded.")
            self.assertEqual(user.role, expected_role)
            self.assertNotEqual(user.password_hash, pwd, "Passwords must NOT be stored as plain text!")
            self.assertTrue(user.check_password(pwd), f"Password verification failed for {email}.")

    def test_hospital_registration(self):
        """Tests complete hospital registration with all required fields."""
        payload = {
            'hospital_name': 'St. Mary Specialized Hospital',
            'registration_number': 'HOSP-SM-9922',
            'hospital_type': 'Specialty Clinic',
            'address': '770 Broad Street',
            'city': 'Boston',
            'contact_phone': '+1 (617) 555-0199',
            'email': 'admin@stmary.org',
            'password': 'password123',
            'confirm_password': 'password123'
        }
        response = self.client.post('/register/hospital', data=payload, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'St. Mary Specialized Hospital', response.data)

        # Check DB
        user = User.query.filter_by(email='admin@stmary.org').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, User.ROLE_HOSPITAL)
        self.assertTrue(user.check_password('password123'))

        hospital = Hospital.query.filter_by(registration_number='HOSP-SM-9922').first()
        self.assertIsNotNone(hospital)
        self.assertEqual(hospital.name, 'St. Mary Specialized Hospital')
        self.assertEqual(hospital.hospital_type, 'Specialty Clinic')
        self.assertEqual(hospital.city, 'Boston')
        self.assertEqual(hospital.user_id, user.id)

    def test_hospital_login(self):
        """Tests hospital admin login and redirect to hospital dashboard."""
        response = self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Hospital Management Hub', response.data)
        self.assertIn(b'Metro General Hospital', response.data)

    def test_doctor_registration_and_login(self):
        """Tests doctor registration with hospital association and subsequent login."""
        # Retrieve an existing hospital
        hospital = Hospital.query.first()
        self.assertIsNotNone(hospital)

        payload = {
            'full_name': 'Dr. Gregory House',
            'specialization': 'Diagnostic Medicine',
            'qualification': 'MD - Johns Hopkins',
            'hospital_id': str(hospital.id),
            'experience_years': '15',
            'consultation_fee': '150.0',
            'email': 'dr.house@careconnect.org',
            'phone': '+1 (212) 555-4321',
            'password': 'diagnostics123',
            'confirm_password': 'diagnostics123'
        }
        reg_response = self.client.post('/register/doctor', data=payload, follow_redirects=True)
        self.assertEqual(reg_response.status_code, 200)
        self.assertIn(b'Dr. Gregory House', reg_response.data)

        # Verify DB
        doc_user = User.query.filter_by(email='dr.house@careconnect.org').first()
        self.assertIsNotNone(doc_user)
        self.assertEqual(doc_user.role, User.ROLE_DOCTOR)

        doctor = Doctor.query.filter_by(user_id=doc_user.id).first()
        self.assertIsNotNone(doctor)
        self.assertEqual(doctor.specialization, 'Diagnostic Medicine')
        self.assertEqual(doctor.hospital_id, hospital.id)

        # Logout and test explicit login
        self.client.get('/logout', follow_redirects=True)
        login_response = self.client.post('/login', data={
            'identifier': 'dr.house@careconnect.org',
            'password': 'diagnostics123'
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn(b'Doctor Dashboard', login_response.data)
        self.assertIn(b'Dr. Gregory House', login_response.data)

    def test_patient_registration_and_login(self):
        """Tests patient registration with DOB, gender, address, and login."""
        payload = {
            'full_name': 'Emma Watson',
            'email': 'emma@example.com',
            'phone': '+1 (555) 789-0123',
            'date_of_birth': '1998-04-15',
            'gender': 'Female',
            'address': '42 Oxford Lane',
            'city': 'New York',
            'blood_group': 'A+',
            'password': 'patientpass123',
            'confirm_password': 'patientpass123'
        }
        reg_response = self.client.post('/register/patient', data=payload, follow_redirects=True)
        self.assertEqual(reg_response.status_code, 200)
        self.assertIn(b'Patient Portal', reg_response.data)
        self.assertIn(b'Emma Watson', reg_response.data)

        # Verify DB
        user = User.query.filter_by(email='emma@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, User.ROLE_PATIENT)

        patient = Patient.query.filter_by(user_id=user.id).first()
        self.assertIsNotNone(patient)
        self.assertEqual(patient.gender, 'Female')
        self.assertEqual(patient.blood_group, 'A+')
        self.assertEqual(patient.date_of_birth, date(1998, 4, 15))

        # Logout and test explicit patient login
        self.client.get('/logout', follow_redirects=True)
        login_response = self.client.post('/login', data={
            'identifier': 'emma@example.com',
            'password': 'patientpass123'
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn(b'Patient Portal', login_response.data)
        self.assertIn(b'Emma Watson', login_response.data)

    def test_incorrect_password(self):
        """Tests that login with invalid password fails and provides error message."""
        response = self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid credentials', response.data)

    def test_duplicate_email_registration_rejected(self):
        """Tests that registering with an already existing email is rejected."""
        # Attempt to register patient with existing patient email
        patient_payload = {
            'full_name': 'Duplicate User',
            'email': 'patient@careconnect.org',
            'phone': '+1 555-0000',
            'password': 'password123',
            'confirm_password': 'password123'
        }
        res = self.client.post('/register/patient', data=patient_payload, follow_redirects=True)
        self.assertIn(b'already registered', res.data)

        # Attempt to register hospital with existing admin email
        hosp_payload = {
            'hospital_name': 'Duplicate Hospital',
            'registration_number': 'HOSP-DUP-1',
            'hospital_type': 'General Hospital',
            'address': '123 Test St',
            'city': 'New York',
            'contact_phone': '+1 555-1111',
            'email': 'admin@careconnect.org',
            'password': 'password123',
            'confirm_password': 'password123'
        }
        res_hosp = self.client.post('/register/hospital', data=hosp_payload, follow_redirects=True)
        self.assertIn(b'already registered', res_hosp.data)

    def test_invalid_email_format_rejected(self):
        """Tests that an improperly formatted email address is rejected."""
        payload = {
            'full_name': 'Invalid Email User',
            'email': 'not-a-valid-email',
            'phone': '+1 555-0000',
            'password': 'password123',
            'confirm_password': 'password123'
        }
        res = self.client.post('/register/patient', data=payload, follow_redirects=True)
        self.assertIn(b'valid email address', res.data)

    def test_password_mismatch_rejected(self):
        """Tests that mismatching passwords fail registration."""
        payload = {
            'full_name': 'Mismatch Test',
            'email': 'mismatch@example.com',
            'phone': '+1 555-0000',
            'password': 'password123',
            'confirm_password': 'differentpassword'
        }
        res = self.client.post('/register/patient', data=payload, follow_redirects=True)
        self.assertIn(b'Passwords do not match', res.data)

    def test_secure_logout(self):
        """Tests that logout clears session and subsequent protected route calls redirect to login."""
        # Login
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Verify access
        r_access = self.client.get('/patient/dashboard')
        self.assertEqual(r_access.status_code, 200)

        # Logout
        r_logout = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(r_logout.status_code, 200)
        self.assertIn(b'logged out securely', r_logout.data)

        # Attempt access to protected route
        r_blocked = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(r_blocked.status_code, 302)
        self.assertIn('/login', r_blocked.headers.get('Location', ''))

    def test_role_based_authorization(self):
        """Verifies that each role cannot access dashboards meant for other roles."""
        # 1. Login as Patient
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Patient attempting doctor dashboard
        r_doc = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertEqual(r_doc.status_code, 302)
        # Patient attempting hospital dashboard
        r_hosp = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertEqual(r_hosp.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # 2. Login as Doctor
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        # Doctor attempting hospital dashboard
        r_hosp2 = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertEqual(r_hosp2.status_code, 302)
        # Doctor attempting patient dashboard
        r_pat = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(r_pat.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # 3. Login as Hospital Admin
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        # Hospital Admin attempting doctor dashboard
        r_doc2 = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertEqual(r_doc2.status_code, 302)
        # Hospital Admin attempting patient dashboard
        r_pat2 = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(r_pat2.status_code, 302)

    def test_cross_account_data_isolation(self):
        """Verifies that a user cannot see another user's private dashboard data."""
        # 1. Register Second Hospital (Hospital B)
        hosp_b_payload = {
            'hospital_name': 'Westside Community Clinic',
            'registration_number': 'HOSP-WEST-7711',
            'hospital_type': 'General Hospital',
            'address': '800 West End Ave',
            'city': 'New York',
            'contact_phone': '+1 (212) 555-7711',
            'email': 'admin@westside.org',
            'password': 'westsidepass1',
            'confirm_password': 'westsidepass1'
        }
        self.client.post('/register/hospital', data=hosp_b_payload, follow_redirects=True)
        r_hosp_b = self.client.get('/hospital/dashboard')
        self.assertEqual(r_hosp_b.status_code, 200)
        # Hospital B dashboard should show its own name and 0 doctors
        self.assertIn(b'Westside Community Clinic', r_hosp_b.data)
        self.assertIn(b'0 Specialists', r_hosp_b.data)
        # Must NOT show Metro General Hospital's doctors
        self.assertNotIn(b'Dr. Sarah Smith', r_hosp_b.data)

        self.client.get('/logout', follow_redirects=True)

        # 2. Register Second Patient (Patient B)
        patient_b_payload = {
            'full_name': 'Patient Two',
            'email': 'patient2@example.com',
            'phone': '+1 555-2222',
            'date_of_birth': '2000-01-01',
            'gender': 'Female',
            'address': '10 Pine St',
            'city': 'New York',
            'password': 'patientpass2',
            'confirm_password': 'patientpass2'
        }
        self.client.post('/register/patient', data=patient_b_payload, follow_redirects=True)
        r_pat_b = self.client.get('/patient/dashboard')
        self.assertEqual(r_pat_b.status_code, 200)
        # Patient B has no appointments yet
        self.assertIn(b'No scheduled appointments yet', r_pat_b.data)
        # Must NOT see Patient A (Alex Rivera)'s appointments or symptoms
        self.assertNotIn(b'Routine annual cardiovascular evaluation', r_pat_b.data)

        self.client.get('/logout', follow_redirects=True)

        # 3. Register Second Doctor (Doctor B)
        hosp = Hospital.query.filter_by(registration_number='HOSP-WEST-7711').first()
        doc_b_payload = {
            'full_name': 'Dr. Robert Chase',
            'specialization': 'Intensive Care',
            'qualification': 'MD - Oxford University',
            'hospital_id': str(hosp.id),
            'experience_years': '6',
            'consultation_fee': '95.0',
            'email': 'dr.chase@careconnect.org',
            'phone': '+1 555-3333',
            'password': 'doctorpass2',
            'confirm_password': 'doctorpass2'
        }
        self.client.post('/register/doctor', data=doc_b_payload, follow_redirects=True)
        r_doc_b = self.client.get('/doctor/dashboard')
        self.assertEqual(r_doc_b.status_code, 200)
        # Doctor B has no appointments yet
        self.assertIn(b'0 Bookings', r_doc_b.data)
        # Must NOT see Dr. Smith's appointment queue
        self.assertNotIn(b'Alex Rivera', r_doc_b.data)

if __name__ == '__main__':
    unittest.main()
