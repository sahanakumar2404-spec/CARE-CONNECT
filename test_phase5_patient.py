from datetime import date, timedelta
import unittest
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment

class CareConnectPhase5PatientTestCase(unittest.TestCase):
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

    # 1. Patient dashboard requires authentication
    def test_patient_dashboard_requires_auth(self):
        """Verifies unauthenticated request to patient dashboard redirects to login."""
        response = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    # 2. Non-patients cannot access patient dashboard
    def test_non_patients_cannot_access_patient_dashboard(self):
        """Verifies Hospital Admin and Doctor roles cannot access patient dashboard."""
        # Hospital Admin access attempt
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)
        r_admin = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(r_admin.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # Doctor access attempt
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)
        r_doc = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(r_doc.status_code, 302)

    # 3. Patient can view own profile and dashboard
    def test_patient_can_view_own_profile(self):
        """Verifies authenticated patient can view their own profile and dashboard metrics."""
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Profile Page
        res_prof = self.client.get('/patient/profile')
        self.assertEqual(res_prof.status_code, 200)
        self.assertIn(b'Alex Rivera', res_prof.data)
        self.assertIn(b'patient@careconnect.org', res_prof.data)
        self.assertIn(b'O+', res_prof.data)
        self.assertIn(b'New York', res_prof.data)

        # Dashboard Page
        res_dash = self.client.get('/patient/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Alex Rivera', res_dash.data)
        self.assertIn(b'Patient Portal', res_dash.data)
        self.assertIn(b'AI Specialist Discovery', res_dash.data)

    # 4. Patient cannot view or modify another patient's profile
    def test_patient_cannot_view_or_modify_another_patient_profile(self):
        """Verifies Patient A cannot access or modify Patient B's private profile."""
        # Create Patient B
        user_b = User(
            username='patient_b',
            email='patient.b@careconnect.org',
            full_name='Taylor Swift',
            phone='+1 (212) 555-8888',
            role=User.ROLE_PATIENT
        )
        user_b.set_password('patient123')
        db.session.add(user_b)
        db.session.flush()

        patient_b = Patient(
            user_id=user_b.id,
            date_of_birth=date(1989, 12, 13),
            gender='Female',
            blood_group='A+',
            address='13 Cornelia Street',
            city='New York',
            emergency_contact='+1 (212) 555-7777'
        )
        db.session.add(patient_b)
        db.session.commit()

        # Login as Patient A
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Attempt to access Patient B's profile directly
        res_get = self.client.get(f'/patient/profile/{patient_b.id}', follow_redirects=False)
        self.assertEqual(res_get.status_code, 403)

        res_post = self.client.post(f'/patient/profile/{patient_b.id}', data={
            'full_name': 'Hacked Name',
            'email': 'hacked@careconnect.org'
        }, follow_redirects=False)
        self.assertEqual(res_post.status_code, 403)

    # 5. Patient can update own profile
    def test_patient_can_update_own_profile(self):
        """Verifies patient can update their own personal, contact, and medical information."""
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        update_data = {
            'full_name': 'Alexander Rivera',
            'email': 'alex.rivera@careconnect.org',
            'phone': '+1 (212) 555-9999',
            'date_of_birth': '1995-08-22',
            'gender': 'Male',
            'blood_group': 'AB+',
            'city': 'Brooklyn',
            'address': '123 Ocean Parkway',
            'emergency_contact': '+1 (212) 555-8888'
        }

        res = self.client.post('/patient/profile', data=update_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Patient profile updated successfully!', res.data)

        # Verify changes persisted in database
        updated_user = User.query.filter_by(email='alex.rivera@careconnect.org').first()
        self.assertIsNotNone(updated_user)
        self.assertEqual(updated_user.full_name, 'Alexander Rivera')
        self.assertEqual(updated_user.phone, '+1 (212) 555-9999')

        updated_patient = Patient.query.filter_by(user_id=updated_user.id).first()
        self.assertEqual(updated_patient.blood_group, 'AB+')
        self.assertEqual(updated_patient.city, 'Brooklyn')
        self.assertEqual(updated_patient.address, '123 Ocean Parkway')

    # 6. Hospital search returns only registered hospitals
    def test_hospital_search_returns_registered_hospitals(self):
        """Verifies hospital directory returns only registered Care Connect facilities."""
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.get('/patient/hospitals')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Metro General Hospital', res.data)
        self.assertIn(b'HOSP-NYC-2026-001', res.data)
        self.assertIn(b'Multispecialty Teaching', res.data)

        # Verify unauthenticated request is blocked
        self.client.get('/logout', follow_redirects=True)
        res_unauth = self.client.get('/patient/hospitals', follow_redirects=False)
        self.assertEqual(res_unauth.status_code, 302)

    # 7. Hospital search by city
    def test_hospital_search_by_city(self):
        """Verifies filtering registered hospitals by city."""
        # Create a second hospital in Boston
        user_boston = User(
            username='boston_admin',
            email='admin@bostonhealth.org',
            full_name='Boston Health Care',
            phone='+1 (617) 555-0100',
            role=User.ROLE_HOSPITAL
        )
        user_boston.set_password('admin123')
        db.session.add(user_boston)
        db.session.flush()

        hospital_boston = Hospital(
            user_id=user_boston.id,
            name='Boston Children & Family Center',
            registration_number='HOSP-BOS-2026-002',
            hospital_type='Pediatric Specialty Center',
            address='300 Longwood Avenue',
            city='Boston',
            contact_email='contact@bostonhealth.org',
            contact_phone='+1 (617) 555-0199',
            total_beds=180,
            available_beds=50,
            emergency_available=True
        )
        db.session.add(hospital_boston)
        db.session.commit()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Search for New York
        res_nyc = self.client.get('/patient/hospitals?city=New York')
        self.assertEqual(res_nyc.status_code, 200)
        self.assertIn(b'Metro General Hospital', res_nyc.data)
        self.assertNotIn(b'Boston Children & Family Center', res_nyc.data)

        # Search for Boston
        res_bos = self.client.get('/patient/hospitals?city=Boston')
        self.assertEqual(res_bos.status_code, 200)
        self.assertIn(b'Boston Children', res_bos.data)
        self.assertNotIn(b'Metro General Hospital', res_bos.data)

    # 8. Hospital search by type
    def test_hospital_search_by_type(self):
        """Verifies filtering registered hospitals by hospital type."""
        # Create a clinic type hospital
        user_clinic = User(
            username='clinic_admin',
            email='admin@expressclinic.org',
            full_name='Express Urgent Clinic',
            phone='+1 (212) 555-0222',
            role=User.ROLE_HOSPITAL
        )
        user_clinic.set_password('admin123')
        db.session.add(user_clinic)
        db.session.flush()

        clinic = Hospital(
            user_id=user_clinic.id,
            name='Midtown Urgent Care Clinic',
            registration_number='HOSP-NYC-2026-003',
            hospital_type='Urgent Care Clinic',
            address='100 5th Avenue',
            city='New York',
            contact_email='contact@expressclinic.org',
            contact_phone='+1 (212) 555-0223',
            total_beds=20,
            available_beds=12,
            emergency_available=False
        )
        db.session.add(clinic)
        db.session.commit()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Filter by Urgent Care Clinic
        res_clinic = self.client.get('/patient/hospitals?type=Urgent Care Clinic')
        self.assertEqual(res_clinic.status_code, 200)
        self.assertIn(b'Midtown Urgent Care Clinic', res_clinic.data)
        self.assertNotIn(b'Metro General Hospital', res_clinic.data)

    # 9. Patient can view registered hospital details
    def test_patient_can_view_hospital_details(self):
        """Verifies viewing registered hospital facility details and practicing specialists."""
        hospital = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.get(f'/patient/hospitals/{hospital.id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Metro General Hospital', res.data)
        self.assertIn(b'HOSP-NYC-2026-001', res.data)
        self.assertIn(b'450 Lexington Avenue', res.data)
        self.assertIn(b'Dr. Sarah Smith', res.data)
        self.assertIn(b'Cardiology', res.data)
        self.assertIn(b'Dr. Marcus Johnson', res.data)
        self.assertIn(b'Dr. Anita Patel', res.data)

    # 10. Doctor roster is scoped strictly to selected hospital
    def test_doctor_roster_scoped_to_hospital(self):
        """Verifies that doctor roster only displays doctors affiliated with the selected hospital."""
        hospital_a = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()

        # Create Hospital B with Dr. Emily
        user_hosp_b = User(
            username='hosp_b_admin',
            email='admin@hospb.org',
            full_name='Westside Community Hospital',
            phone='+1 (212) 555-0300',
            role=User.ROLE_HOSPITAL
        )
        user_hosp_b.set_password('admin123')
        db.session.add(user_hosp_b)
        db.session.flush()

        hospital_b = Hospital(
            user_id=user_hosp_b.id,
            name='Westside Community Hospital',
            registration_number='HOSP-NYC-2026-004',
            hospital_type='Community Hospital',
            address='800 10th Avenue',
            city='New York',
            contact_email='contact@hospb.org',
            contact_phone='+1 (212) 555-0399',
            total_beds=90,
            available_beds=30,
            emergency_available=True
        )
        db.session.add(hospital_b)
        db.session.flush()

        dr_emily_user = User(
            username='dremily',
            email='dr.emily@careconnect.org',
            full_name='Dr. Emily Stone',
            phone='+1 (212) 555-0344',
            role=User.ROLE_DOCTOR
        )
        dr_emily_user.set_password('doctor123')
        db.session.add(dr_emily_user)
        db.session.flush()

        dr_emily = Doctor(
            user_id=dr_emily_user.id,
            hospital_id=hospital_b.id,
            specialization='Dermatology',
            qualification='MD - NYU Grossman School of Medicine',
            experience_years=7,
            consultation_fee=110.0,
            is_available=True,
            available_days='Monday - Thursday',
            available_time='10:00 AM - 04:00 PM',
            room_number='Room 102',
            bio='Dermatologist specializing in medical dermatology.'
        )
        db.session.add(dr_emily)
        db.session.commit()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Inspect Hospital A: Dr. Smith present, Dr. Emily NOT present
        res_a = self.client.get(f'/patient/hospitals/{hospital_a.id}')
        self.assertEqual(res_a.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_a.data)
        self.assertNotIn(b'Dr. Emily Stone', res_a.data)

        # Inspect Hospital B: Dr. Emily present, Dr. Smith NOT present
        res_b = self.client.get(f'/patient/hospitals/{hospital_b.id}')
        self.assertEqual(res_b.status_code, 200)
        self.assertIn(b'Dr. Emily Stone', res_b.data)
        self.assertNotIn(b'Dr. Sarah Smith', res_b.data)

    # 11. Specialist filtering on hospital page
    def test_specialist_filtering_on_hospital_page(self):
        """Verifies filtering doctors by specialization on the hospital detail page."""
        hospital = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Filter by Cardiology
        res_cardio = self.client.get(f'/patient/hospitals/{hospital.id}?specialty=Cardiology')
        self.assertEqual(res_cardio.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_cardio.data)
        self.assertNotIn(b'Dr. Marcus Johnson', res_cardio.data)
        self.assertNotIn(b'Dr. Anita Patel', res_cardio.data)

        # Filter by Neurology
        res_neuro = self.client.get(f'/patient/hospitals/{hospital.id}?specialty=Neurology')
        self.assertEqual(res_neuro.status_code, 200)
        self.assertIn(b'Dr. Marcus Johnson', res_neuro.data)
        self.assertNotIn(b'Dr. Sarah Smith', res_neuro.data)

    # 12. Doctor details page renders correctly
    def test_doctor_details_renders_correctly(self):
        """Verifies patient-facing physician profile renders qualifications, fee, bio, and booking button."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.get(f'/patient/doctors/{dr_smith.id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res.data)
        self.assertIn(b'Cardiology', res.data)
        self.assertIn(b'Harvard Medical School', res.data)
        self.assertIn(b'120.00', res.data)
        self.assertIn(b'Book Appointment', res.data)
        self.assertIn(b'Metro General Hospital', res.data)

    # 13. Patient cannot modify hospital data
    def test_patient_cannot_modify_hospital_data(self):
        """Verifies patient cannot send POST requests to hospital endpoints to modify facility data."""
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Attempt to modify hospital profile
        res_edit = self.client.post('/hospital/profile', data={
            'name': 'Hacked Hospital Name',
            'address': 'Hacked Address'
        }, follow_redirects=False)
        self.assertEqual(res_edit.status_code, 302)

        # Attempt to modify a doctor via hospital endpoint
        dr_smith = Doctor.query.first()
        res_edit_doc = self.client.post(f'/hospital/doctors/{dr_smith.id}/edit', data={
            'full_name': 'Unauthorized Doctor',
            'specialization': 'General Medicine'
        }, follow_redirects=False)
        self.assertEqual(res_edit_doc.status_code, 302)

        # Hospital data remains unchanged
        hospital = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()
        self.assertEqual(hospital.name, 'Metro General Hospital & Research Center')

    # 14. Patient cannot modify doctor data
    def test_patient_cannot_modify_doctor_data(self):
        """Verifies patient cannot send POST requests to doctor endpoints to modify physician data."""
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Attempt to modify doctor profile
        res_doc_prof = self.client.post('/doctor/profile', data={
            'full_name': 'Hacked Doctor Name',
            'specialization': 'Hacked Specialty'
        }, follow_redirects=False)
        self.assertEqual(res_doc_prof.status_code, 302)

        # Attempt to modify doctor availability
        res_doc_avail = self.client.post('/doctor/availability', data={
            'is_available': False,
            'available_time': 'Closed'
        }, follow_redirects=False)
        self.assertEqual(res_doc_avail.status_code, 302)

        # Doctor data remains unchanged
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        self.assertEqual(dr_smith.user.full_name, 'Dr. Sarah Smith')
        self.assertEqual(dr_smith.specialization, 'Cardiology')

if __name__ == '__main__':
    unittest.main()
