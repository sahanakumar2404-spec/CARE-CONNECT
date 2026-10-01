import unittest
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient

class CareConnectPhase3HospitalTestCase(unittest.TestCase):
    def setUp(self):
        """Sets up an in-memory testing application context."""
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

    def test_hospital_dashboard_requires_login(self):
        """Verifies unauthenticated access to hospital dashboard redirects to login."""
        response = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    def test_non_hospital_users_blocked_from_hospital_dashboard(self):
        """Verifies Doctor and Patient roles are unauthorized on hospital dashboard."""
        # 1. Doctor attempting access
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)
        res_doc = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertEqual(res_doc.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # 2. Patient attempting access
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)
        res_pat = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertEqual(res_pat.status_code, 302)

    def test_hospital_views_own_profile_and_dashboard(self):
        """Verifies authenticated hospital admin can view their own facility dashboard and profile."""
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        # View Dashboard
        dash_res = self.client.get('/hospital/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b'Metro General Hospital', dash_res.data)
        self.assertIn(b'Cardiology', dash_res.data)
        self.assertIn(b'Total Doctors', dash_res.data)

        # View Profile
        prof_res = self.client.get('/hospital/profile')
        self.assertEqual(prof_res.status_code, 200)
        self.assertIn(b'HOSP-NYC-2026-001', prof_res.data)
        self.assertIn(b'Metro General Hospital', prof_res.data)

    def test_hospital_cannot_access_or_modify_another_hospital_profile(self):
        """Verifies that Hospital B cannot access or modify Hospital A's profile."""
        # Register Hospital B
        hosp_b_data = {
            'hospital_name': 'Mercy General Clinic',
            'registration_number': 'HOSP-MERCY-002',
            'hospital_type': 'General Hospital',
            'address': '200 Oak Lane',
            'city': 'Chicago',
            'contact_phone': '+1 (312) 555-0155',
            'email': 'admin@mercy.org',
            'password': 'mercypassword1',
            'confirm_password': 'mercypassword1'
        }
        self.client.post('/register/hospital', data=hosp_b_data, follow_redirects=True)

        # Hospital B is logged in; accesses /hospital/profile
        res = self.client.get('/hospital/profile')
        self.assertEqual(res.status_code, 200)
        # Should strictly see Mercy General Clinic, NOT Metro General Hospital
        self.assertIn(b'Mercy General Clinic', res.data)
        self.assertNotIn(b'Metro General Hospital', res.data)

        # Hospital B submits profile edits
        update_data = {
            'name': 'Mercy Health Medical Center',
            'hospital_type': 'Specialty Clinic',
            'address': '202 Oak Lane Ext',
            'city': 'Chicago',
            'contact_email': 'contact@mercyhealth.org',
            'contact_phone': '+1 (312) 555-0199',
            'total_beds': '120',
            'available_beds': '45',
            'operational_status': 'High Capacity',
            'daily_notice': 'Emergency renovations underway.'
        }
        post_res = self.client.post('/hospital/profile', data=update_data, follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)
        self.assertIn(b'Hospital profile updated successfully', post_res.data)

        # Verify Hospital A is untouched
        hosp_a = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()
        self.assertEqual(hosp_a.name, 'Metro General Hospital & Research Center')
        self.assertNotEqual(hosp_a.city, 'Chicago')

    def test_hospital_sees_only_own_doctors(self):
        """Verifies Hospital A and Hospital B only see their respective affiliated doctors."""
        # 1. Check Hospital A doctors
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        res_a = self.client.get('/hospital/doctors')
        self.assertEqual(res_a.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_a.data)
        self.assertIn(b'Dr. Marcus Johnson', res_a.data)

        self.client.get('/logout', follow_redirects=True)

        # 2. Register Hospital B
        hosp_b_data = {
            'hospital_name': 'Suburban Care Hospital',
            'registration_number': 'HOSP-SUB-003',
            'hospital_type': 'General Hospital',
            'address': '55 County Road',
            'city': 'Austin',
            'contact_phone': '+1 (512) 555-0188',
            'email': 'admin@suburban.org',
            'password': 'suburbanpass1',
            'confirm_password': 'suburbanpass1'
        }
        self.client.post('/register/hospital', data=hosp_b_data, follow_redirects=True)

        # Hospital B doctors roster should be empty
        res_b = self.client.get('/hospital/doctors')
        self.assertEqual(res_b.status_code, 200)
        self.assertIn(b'No doctors currently registered with Suburban Care Hospital', res_b.data)
        self.assertNotIn(b'Dr. Sarah Smith', res_b.data)

    def test_hospital_cannot_access_or_edit_other_hospital_doctors(self):
        """Verifies Hospital B cannot view, edit, or toggle doctors belonging to Hospital A."""
        # Retrieve Doctor belonging to Hospital A (Dr. Sarah Smith)
        dr_a = Doctor.query.first()
        self.assertIsNotNone(dr_a)

        # Register and login as Hospital B
        hosp_b_data = {
            'hospital_name': 'North Shore Hospital',
            'registration_number': 'HOSP-NS-004',
            'hospital_type': 'General Hospital',
            'address': '90 Harbor Dr',
            'city': 'Seattle',
            'contact_phone': '+1 (206) 555-0177',
            'email': 'admin@northshore.org',
            'password': 'northshorepass1',
            'confirm_password': 'northshorepass1'
        }
        self.client.post('/register/hospital', data=hosp_b_data, follow_redirects=True)

        # 1. Hospital B attempts to view edit page of Hospital A's doctor
        res_edit = self.client.get(f'/hospital/doctors/{dr_a.id}/edit', follow_redirects=True)
        self.assertIn(b'Unauthorized: Doctor record does not belong to your hospital facility', res_edit.data)

        # 2. Hospital B attempts to POST edit to Hospital A's doctor
        res_post_edit = self.client.post(f'/hospital/doctors/{dr_a.id}/edit', data={
            'full_name': 'Hacked Name',
            'specialization': 'Hacked Specialization',
            'qualification': 'Hacked',
            'experience_years': '99'
        }, follow_redirects=True)
        self.assertIn(b'Unauthorized', res_post_edit.data)

        # Doctor A must NOT be modified
        db.session.refresh(dr_a)
        self.assertNotEqual(dr_a.specialization, 'Hacked Specialization')

        # 3. Hospital B attempts to toggle availability of Hospital A's doctor
        original_avail = dr_a.is_available
        res_toggle = self.client.post(f'/hospital/doctors/{dr_a.id}/toggle-availability', follow_redirects=True)
        self.assertIn(b'Unauthorized', res_toggle.data)
        db.session.refresh(dr_a)
        self.assertEqual(dr_a.is_available, original_avail)

    def test_doctor_availability_display_and_toggle(self):
        """Verifies hospital management can toggle doctor availability and update schedule."""
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        dr = Doctor.query.first()
        self.assertTrue(dr.is_available)

        # Toggle to off-duty
        res1 = self.client.post(f'/hospital/doctors/{dr.id}/toggle-availability', follow_redirects=True)
        self.assertEqual(res1.status_code, 200)
        db.session.refresh(dr)
        self.assertFalse(dr.is_available)

        # Toggle back to available
        res2 = self.client.post(f'/hospital/doctors/{dr.id}/toggle-availability', follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        db.session.refresh(dr)
        self.assertTrue(dr.is_available)

        # Update schedule
        res_sched = self.client.post(f'/hospital/doctors/{dr.id}/schedule', data={
            'available_days': 'Tuesday, Thursday',
            'available_time': '10:00 AM - 02:00 PM'
        }, follow_redirects=True)
        self.assertEqual(res_sched.status_code, 200)
        db.session.refresh(dr)
        self.assertEqual(dr.available_days, 'Tuesday, Thursday')
        self.assertEqual(dr.available_time, '10:00 AM - 02:00 PM')

    def test_hospital_profile_update_success(self):
        """Verifies hospital profile update persists changes correctly."""
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        payload = {
            'name': 'Metro Health University Medical Center',
            'hospital_type': 'Multispecialty Teaching & Research Hospital',
            'address': '500 Lexington Avenue',
            'city': 'New York',
            'contact_email': 'contact@metrohealth.edu',
            'contact_phone': '+1 (212) 555-9900',
            'total_beds': '400',
            'available_beds': '110',
            'emergency_available': 'on',
            'operational_status': 'Normal Operations',
            'daily_notice': 'Cardiac wing open for consultations.'
        }
        response = self.client.post('/hospital/profile', data=payload, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Hospital profile updated successfully', response.data)

        # Check DB
        hosp = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()
        self.assertEqual(hosp.name, 'Metro Health University Medical Center')
        self.assertEqual(hosp.contact_email, 'contact@metrohealth.edu')
        self.assertEqual(hosp.total_beds, 400)
        self.assertEqual(hosp.available_beds, 110)
        self.assertEqual(hosp.daily_notice, 'Cardiac wing open for consultations.')

    def test_invalid_profile_data_rejected(self):
        """Verifies validation catches empty name, invalid email, and invalid bed counts."""
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        # 1. Empty name
        res_name = self.client.post('/hospital/profile', data={
            'name': '',
            'contact_email': 'valid@metro.org',
            'total_beds': '100',
            'available_beds': '20'
        }, follow_redirects=True)
        self.assertIn(b'Hospital name cannot be empty', res_name.data)

        # 2. Invalid email format
        res_email = self.client.post('/hospital/profile', data={
            'name': 'Valid Name',
            'contact_email': 'not-an-email',
            'total_beds': '100',
            'available_beds': '20'
        }, follow_redirects=True)
        self.assertIn(b'Please provide a valid email format', res_email.data)

        # 3. available_beds > total_beds
        res_beds = self.client.post('/hospital/profile', data={
            'name': 'Valid Name',
            'contact_email': 'valid@metro.org',
            'total_beds': '100',
            'available_beds': '150'
        }, follow_redirects=True)
        self.assertIn(b'Available beds cannot exceed total inpatient beds capacity', res_beds.data)

    def test_daily_updates_endpoint(self):
        """Verifies /hospital/daily-updates endpoint updates bed capacity and notices."""
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        res = self.client.post('/hospital/daily-updates', data={
            'operational_status': 'High Capacity',
            'daily_notice': 'ICU capacity near 90%. Priority triaging in effect.',
            'total_beds': '320',
            'available_beds': '15',
            'emergency_available': 'on'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Daily hospital updates and operational notice saved successfully', res.data)

        hosp = Hospital.query.filter_by(registration_number='HOSP-NYC-2026-001').first()
        self.assertEqual(hosp.operational_status, 'High Capacity')
        self.assertEqual(hosp.available_beds, 15)

if __name__ == '__main__':
    unittest.main()
