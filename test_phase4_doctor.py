from datetime import date, timedelta
import unittest
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment

class CareConnectPhase4DoctorTestCase(unittest.TestCase):
    def setUp(self):
        """Sets up an in-memory testing application context with seeded demo data."""
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        """Cleans up the database and application context."""
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    # 1. Doctor dashboard requires authentication
    def test_doctor_dashboard_requires_auth(self):
        """Verifies unauthenticated request to doctor dashboard redirects to login."""
        response = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    # 2. Non-doctors cannot access doctor dashboard
    def test_non_doctors_cannot_access_doctor_dashboard(self):
        """Verifies Hospital Admin and Patient roles cannot access doctor dashboard."""
        # Hospital Admin access attempt
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)
        r_admin = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertEqual(r_admin.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # Patient access attempt
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)
        r_pat = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertEqual(r_pat.status_code, 302)

    # 3. Doctor can view own profile
    def test_doctor_can_view_own_profile(self):
        """Verifies doctor can view their own profile and dashboard."""
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        # Profile Page
        res_prof = self.client.get('/doctor/profile')
        self.assertEqual(res_prof.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_prof.data)
        self.assertIn(b'Cardiology', res_prof.data)
        self.assertIn(b'dr.smith@careconnect.org', res_prof.data)
        self.assertIn(b'Metro General Hospital', res_prof.data)

        # Dashboard Page
        res_dash = self.client.get('/doctor/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Doctor Dashboard', res_dash.data)
        self.assertIn(b'Practicing Physician', res_dash.data)
        self.assertIn(b'Dr. Sarah Smith', res_dash.data)

    # 4. Doctor cannot view or modify another doctor's profile
    def test_doctor_cannot_view_or_modify_another_doctor_profile(self):
        """Verifies Doctor A cannot access or modify Doctor B's profile."""
        dr_smith_user = User.query.filter_by(email='dr.smith@careconnect.org').first()
        dr_johnson_user = User.query.filter_by(email='dr.johnson@careconnect.org').first()
        dr_johnson = Doctor.query.filter_by(user_id=dr_johnson_user.id).first()

        # Login as Dr. Smith
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        # Attempt to access Dr. Johnson's profile explicitly
        res = self.client.get(f'/doctor/profile/{dr_johnson.id}', follow_redirects=False)
        self.assertEqual(res.status_code, 403)

    # 5. Doctor can update own profile
    def test_doctor_can_update_own_profile(self):
        """Verifies doctor can update their own clinical and contact profile information."""
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        hospital = Hospital.query.first()
        update_payload = {
            'full_name': 'Dr. Sarah Smith MD PhD',
            'email': 'dr.smith.updated@careconnect.org',
            'phone': '+1 (212) 555-8899',
            'specialization': 'Interventional Cardiology',
            'qualification': 'MD, PhD, FACC',
            'experience_years': '14',
            'consultation_fee': '165.00',
            'room_number': 'Cardiac Wing - Room 404',
            'hospital_id': str(hospital.id),
            'bio': 'Specializing in advanced coronary interventions and cardiac care.'
        }

        res = self.client.post('/doctor/profile', data=update_payload, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Doctor profile updated successfully!', res.data)

        # Verify DB persistence
        dr = Doctor.query.filter_by(specialization='Interventional Cardiology').first()
        self.assertIsNotNone(dr)
        self.assertEqual(dr.user.full_name, 'Dr. Sarah Smith MD PhD')
        self.assertEqual(dr.user.email, 'dr.smith.updated@careconnect.org')
        self.assertEqual(dr.consultation_fee, 165.00)
        self.assertEqual(dr.experience_years, 14)
        self.assertEqual(dr.room_number, 'Cardiac Wing - Room 404')

    # 6. Doctor can update own availability
    def test_doctor_can_update_own_availability(self):
        """Verifies doctor can manage on-duty availability, working days, and hours."""
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        # Test Schedule Form Update
        schedule_payload = {
            'is_available': 'true',
            'days': ['Monday', 'Wednesday', 'Friday'],
            'start_time': '08:30 AM',
            'end_time': '04:30 PM'
        }
        res_sched = self.client.post('/doctor/availability', data=schedule_payload, follow_redirects=True)
        self.assertEqual(res_sched.status_code, 200)
        self.assertIn(b'schedule saved successfully', res_sched.data)

        # Check in DB
        dr_user = User.query.filter_by(email='dr.smith@careconnect.org').first()
        dr = Doctor.query.filter_by(user_id=dr_user.id).first()
        self.assertTrue(dr.is_available)
        self.assertIn('Monday', dr.available_days)
        self.assertIn('Wednesday', dr.available_days)
        self.assertEqual(dr.available_time, '08:30 AM - 04:30 PM')
        self.assertEqual(dr.start_time, '08:30 AM')
        self.assertEqual(dr.end_time, '04:30 PM')

        # Test Toggle Availability endpoint
        res_toggle = self.client.post('/doctor/toggle-availability', follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)
        db.session.refresh(dr)
        self.assertFalse(dr.is_available)

    # 7. Doctor cannot update another doctor's availability
    def test_doctor_cannot_update_another_doctor_availability(self):
        """Verifies Doctor A cannot modify Doctor B's availability."""
        dr_johnson_user = User.query.filter_by(email='dr.johnson@careconnect.org').first()
        dr_johnson = Doctor.query.filter_by(user_id=dr_johnson_user.id).first()
        initial_status = dr_johnson.is_available

        # Login as Dr. Smith
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        # Attempt modifying Dr. Johnson's availability
        res = self.client.post(f'/doctor/availability/{dr_johnson.id}', data={'is_available': 'false'}, follow_redirects=False)
        self.assertEqual(res.status_code, 403)

        # Ensure no change occurred in DB
        db.session.refresh(dr_johnson)
        self.assertEqual(dr_johnson.is_available, initial_status)

    # 8. Doctor sees only own appointments
    def test_doctor_sees_only_own_appointments(self):
        """Verifies Doctor A and Doctor B only see appointments assigned to themselves."""
        dr_smith_user = User.query.filter_by(email='dr.smith@careconnect.org').first()
        dr_smith = Doctor.query.filter_by(user_id=dr_smith_user.id).first()
        dr_johnson_user = User.query.filter_by(email='dr.johnson@careconnect.org').first()
        dr_johnson = Doctor.query.filter_by(user_id=dr_johnson_user.id).first()
        patient = Patient.query.first()

        # Create unique appointment for Dr. Johnson
        appt_johnson = Appointment(
            appointment_uid='APPT-TEST-JOHNSON-001',
            patient_id=patient.id,
            doctor_id=dr_johnson.id,
            hospital_id=dr_johnson.hospital_id,
            appointment_date=date.today() + timedelta(days=2),
            time_slot='11:00 AM - 11:30 AM',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Neurology migraine examination'
        )
        db.session.add(appt_johnson)
        db.session.commit()

        # Login as Dr. Smith: should NOT see Dr. Johnson's appointment
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        res_smith = self.client.get('/doctor/appointments')
        self.assertEqual(res_smith.status_code, 200)
        self.assertNotIn(b'APPT-TEST-JOHNSON-001', res_smith.data)
        self.assertNotIn(b'Neurology migraine examination', res_smith.data)

        self.client.get('/logout', follow_redirects=True)

        # Login as Dr. Johnson: SHOULD see their appointment
        self.client.post('/login', data={
            'identifier': 'dr.johnson@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        res_johnson = self.client.get('/doctor/appointments')
        self.assertEqual(res_johnson.status_code, 200)
        self.assertIn(b'APPT-TEST-JOHNSON-001', res_johnson.data)
        self.assertIn(b'Neurology migraine examination', res_johnson.data)

    # 9. Doctor sees only patients associated with their appointments
    def test_doctor_sees_only_patients_associated_with_their_appointments(self):
        """Verifies patient history section displays only patients who had appointments with this doctor."""
        dr_johnson_user = User.query.filter_by(email='dr.johnson@careconnect.org').first()
        dr_johnson = Doctor.query.filter_by(user_id=dr_johnson_user.id).first()

        # Create Patient 2 who has an appointment ONLY with Dr. Johnson
        user_p2 = User(
            username='patient2',
            email='patient2@careconnect.org',
            full_name='Alice Wonderland',
            role=User.ROLE_PATIENT,
            phone='+1 (555) 777-8888'
        )
        user_p2.set_password('patient123')
        db.session.add(user_p2)
        db.session.flush()

        p2 = Patient(user_id=user_p2.id, date_of_birth=date(1995, 5, 15), blood_group='B+')
        db.session.add(p2)
        db.session.flush()

        appt_p2 = Appointment(
            appointment_uid='APPT-TEST-P2-EXCLUSIVE',
            patient_id=p2.id,
            doctor_id=dr_johnson.id,
            hospital_id=dr_johnson.hospital_id,
            appointment_date=date.today(),
            time_slot='02:00 PM - 02:30 PM',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Neurological assessment'
        )
        db.session.add(appt_p2)
        db.session.commit()

        # Login as Dr. Smith: should NOT see Alice Wonderland in patients history
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        res_smith_patients = self.client.get('/doctor/patients')
        self.assertEqual(res_smith_patients.status_code, 200)
        self.assertNotIn(b'Alice Wonderland', res_smith_patients.data)

        self.client.get('/logout', follow_redirects=True)

        # Login as Dr. Johnson: SHOULD see Alice Wonderland
        self.client.post('/login', data={
            'identifier': 'dr.johnson@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        res_johnson_patients = self.client.get('/doctor/patients')
        self.assertEqual(res_johnson_patients.status_code, 200)
        self.assertIn(b'Alice Wonderland', res_johnson_patients.data)
        self.assertIn(b'B+', res_johnson_patients.data)

    # 10. Doctor sees only their associated hospital
    def test_doctor_sees_only_their_associated_hospital(self):
        """Verifies doctor hospital information view shows only the doctor's affiliated facility."""
        # Create a second hospital (Hospital B)
        user_hosp_b = User(
            username='hosp_b_admin',
            email='admin@riverside.org',
            full_name='Riverside Hospital Admin',
            role=User.ROLE_HOSPITAL
        )
        user_hosp_b.set_password('admin123')
        db.session.add(user_hosp_b)
        db.session.flush()

        hosp_b = Hospital(
            user_id=user_hosp_b.id,
            name='Riverside Specialty Hospital',
            registration_number='HOSP-RIVER-9988',
            hospital_type='Specialty Surgery Center',
            address='1200 River Rd',
            city='Boston',
            contact_email='info@riverside.org',
            contact_phone='+1 (617) 555-9988',
            total_beds=90,
            available_beds=25
        )
        db.session.add(hosp_b)
        db.session.commit()

        # Login as Dr. Smith (affiliated with Metro General Hospital)
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        res = self.client.get('/doctor/hospital')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Metro General Hospital', res.data)
        self.assertIn(b'Affiliated Hospital Information', res.data)
        # Must not see Riverside Hospital
        self.assertNotIn(b'Riverside Specialty Hospital', res.data)
        self.assertNotIn(b'HOSP-RIVER-9988', res.data)

    # 11. Invalid profile data is rejected
    def test_invalid_profile_data_rejected(self):
        """Verifies validation rejects empty name, invalid email format, negative fee, and negative experience."""
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        # 1. Empty full name
        res_empty_name = self.client.post('/doctor/profile', data={
            'full_name': '',
            'email': 'dr.smith@careconnect.org',
            'specialization': 'Cardiology',
            'qualification': 'MD',
            'experience_years': '10',
            'consultation_fee': '100.0'
        }, follow_redirects=True)
        self.assertIn(b'Doctor full name cannot be empty', res_empty_name.data)

        # 2. Invalid email format
        res_bad_email = self.client.post('/doctor/profile', data={
            'full_name': 'Dr. Sarah Smith',
            'email': 'not-an-email',
            'specialization': 'Cardiology',
            'qualification': 'MD',
            'experience_years': '10',
            'consultation_fee': '100.0'
        }, follow_redirects=True)
        self.assertIn(b'valid email address', res_bad_email.data)

        # 3. Negative consultation fee
        res_neg_fee = self.client.post('/doctor/profile', data={
            'full_name': 'Dr. Sarah Smith',
            'email': 'dr.smith@careconnect.org',
            'specialization': 'Cardiology',
            'qualification': 'MD',
            'experience_years': '10',
            'consultation_fee': '-50.0'
        }, follow_redirects=True)
        self.assertIn(b'Consultation fee cannot be negative', res_neg_fee.data)

        # 4. Negative experience years
        res_neg_exp = self.client.post('/doctor/profile', data={
            'full_name': 'Dr. Sarah Smith',
            'email': 'dr.smith@careconnect.org',
            'specialization': 'Cardiology',
            'qualification': 'MD',
            'experience_years': '-3',
            'consultation_fee': '100.0'
        }, follow_redirects=True)
        self.assertIn(b'Experience years cannot be negative', res_neg_exp.data)

if __name__ == '__main__':
    unittest.main()
