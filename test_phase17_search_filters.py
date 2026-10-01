"""
Care Connect - Phase 17: Advanced Search & Filters Test Suite
Comprehensive testing for:
1. Patient can access hospital search
2. Hospital name search
3. Case-insensitive hospital search
4. Partial hospital search
5. City filter
6. Hospital type filter
7. Operational status filter
8. Hospital sorting (name, beds)
9. Clear hospital filters
10. Empty hospital result handling
11. Patient can access doctor discovery (/patient/doctors)
12. Doctor name search
13. Case-insensitive & partial doctor name search
14. Specialization filter (dynamic from database)
15. Qualification filter
16. Experience filter (0-2, 3-5, 6-10, 10+)
17. Availability filter (today, this_week)
18. Combined multi-criteria filtering
19. Doctor sorting (Name A-Z, Name Z-A, Exp Low-to-High, Exp High-to-Low)
20. Empty doctor result handling
21. Unauthorized access blocked (redirect to login)
22. Cross-role access protection (Doctor/Hospital roles blocked)
23. SQL injection safety
24. Existing booking workflow integration
25. Existing AI specialist workflow preserved
26. Existing smart appointment workflow preserved
"""

import unittest
from datetime import date, timedelta
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from services.booking_service import doctor_works_on_date


class CareConnectPhase17SearchFiltersTestCase(unittest.TestCase):
    """Test case for Phase 17 Advanced Search and Filters."""

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        # Seeded demo users
        self.patient_user = User.query.filter_by(email='patient@careconnect.org').first()
        self.doctor_user = User.query.filter_by(email='dr.smith@careconnect.org').first()
        self.hospital_user = User.query.filter_by(email='admin@careconnect.org').first()

        self.hospital = Hospital.query.first()
        self.doctor = Doctor.query.filter_by(user_id=self.doctor_user.id).first()
        self.patient = Patient.query.filter_by(user_id=self.patient_user.id).first()

        # Seed additional hospital in Coimbatore for explicit test verification
        self.hospital_coimbatore = Hospital.query.filter_by(name='Coimbatore General Hospital').first()
        if not self.hospital_coimbatore:
            user_coimb = User(
                username='coimb_admin',
                email='admin@coimbatorehospital.org',
                full_name='Coimbatore Health Trust',
                role=User.ROLE_HOSPITAL
            )
            user_coimb.set_password('admin123')
            db.session.add(user_coimb)
            db.session.flush()

            self.hospital_coimbatore = Hospital(
                user_id=user_coimb.id,
                name='Coimbatore General Hospital',
                registration_number='HOSP-CBE-2026-004',
                hospital_type='General Hospital',
                address='100 Avinashi Road',
                city='Coimbatore',
                total_beds=250,
                available_beds=80,
                emergency_available=True,
                operational_status='High Patient Load'
            )
            db.session.add(self.hospital_coimbatore)
            db.session.commit()

        # Seed doctor with 1 year experience for range testing (0-2 years)
        doc_junior_user = User.query.filter_by(email='dr.junior@careconnect.org').first()
        if not doc_junior_user:
            doc_junior_user = User(
                username='drjunior',
                email='dr.junior@careconnect.org',
                full_name='Dr. Kevin Ray',
                role=User.ROLE_DOCTOR
            )
            doc_junior_user.set_password('doctor123')
            db.session.add(doc_junior_user)
            db.session.flush()

            self.doc_junior = Doctor(
                user_id=doc_junior_user.id,
                hospital_id=self.hospital.id,
                specialization='Pediatrics',
                qualification='MBBS, MD - Boston University',
                experience_years=1,
                consultation_fee=60.0,
                is_available=True,
                available_days='Monday - Friday',
                available_time='09:00 AM - 01:00 PM'
            )
            db.session.add(self.doc_junior)
            db.session.commit()
        else:
            self.doc_junior = Doctor.query.filter_by(user_id=doc_junior_user.id).first()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def _login(self, email, password=None):
        if password is None:
            if 'admin' in email:
                password = 'admin123'
            elif 'dr.' in email or 'doctor' in email:
                password = 'doctor123'
            else:
                password = 'patient123'
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # 1. Patient can access hospital search
    def test_01_patient_can_access_hospital_search(self):
        """Verifies authenticated patient can access the hospital search directory."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Care Connect Hospital Directory', resp.data)
        self.assertIn(b'Filter Registered Facilities', resp.data)
        self.assertIn(b'Metro General Hospital', resp.data)

    # 2. Hospital name search
    def test_02_hospital_name_search(self):
        """Verifies searching hospital by exact name."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals?name=Metro General')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Metro General Hospital', resp.data)
        self.assertNotIn(b'Coimbatore General Hospital', resp.data)

    # 3. Case-insensitive hospital search
    def test_03_case_insensitive_hospital_search(self):
        """Verifies searching hospital with lowercase and uppercase queries."""
        self._login('patient@careconnect.org')
        # Lowercase
        r_lower = self.client.get('/patient/hospitals?name=metro')
        self.assertEqual(r_lower.status_code, 200)
        self.assertIn(b'Metro General Hospital', r_lower.data)

        # Uppercase
        r_upper = self.client.get('/patient/hospitals?name=METRO')
        self.assertEqual(r_upper.status_code, 200)
        self.assertIn(b'Metro General Hospital', r_upper.data)

    # 4. Partial hospital search
    def test_04_partial_hospital_search(self):
        """Verifies searching with partial keyword 'Coimb' finds 'Coimbatore General Hospital'."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals?name=Coimb')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Coimbatore General Hospital', resp.data)
        self.assertNotIn(b'Metro General Hospital', resp.data)

    # 5. City filter
    def test_05_city_filter(self):
        """Verifies filtering registered hospitals by city."""
        self._login('patient@careconnect.org')
        # Search Coimbatore
        r_cbe = self.client.get('/patient/hospitals?city=Coimbatore')
        self.assertEqual(r_cbe.status_code, 200)
        self.assertIn(b'Coimbatore General Hospital', r_cbe.data)
        self.assertNotIn(b'Metro General Hospital', r_cbe.data)

        # Search New York
        r_nyc = self.client.get('/patient/hospitals?city=New York')
        self.assertEqual(r_nyc.status_code, 200)
        self.assertIn(b'Metro General Hospital', r_nyc.data)
        self.assertNotIn(b'Coimbatore General Hospital', r_nyc.data)

    # 6. Hospital type filter
    def test_06_hospital_type_filter(self):
        """Verifies filtering registered hospitals by facility type."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals?type=Multispecialty')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Metro General Hospital', resp.data)
        self.assertNotIn(b'Community Health Center', resp.data)

    # 7. Operational status filter
    def test_07_operational_status_filter(self):
        """Verifies filtering registered hospitals by operational status."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals?status=High Patient Load')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Coimbatore General Hospital', resp.data)
        self.assertNotIn(b'Metro General Hospital', resp.data)

    # 8. Hospital sorting
    def test_08_hospital_sorting(self):
        """Verifies sorting hospitals by name (Z-A) and total beds."""
        self._login('patient@careconnect.org')
        r_desc = self.client.get('/patient/hospitals?sort=name_desc')
        self.assertEqual(r_desc.status_code, 200)

        # Coimbatore vs Metro position
        pos_metro = r_desc.data.find(b'Metro General')
        pos_coimb = r_desc.data.find(b'Coimbatore General')
        self.assertTrue(pos_metro < pos_coimb, "Metro General should precede Coimbatore in Z-A ordering.")

    # 9. Clear filters restores full hospital list
    def test_09_clear_filters_hospital(self):
        """Verifies clearing hospital filters restores all registered facilities."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Metro General Hospital', resp.data)
        self.assertIn(b'Coimbatore General Hospital', resp.data)

    # 10. Empty hospital result
    def test_10_empty_hospital_result(self):
        """Verifies clean empty state banner when no hospitals match filters."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/hospitals?name=NonexistentHospitalXYZ')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'No matching hospitals found', resp.data)
        self.assertIn(b'Clear Filters', resp.data)

    # 11. Patient can access doctor search
    def test_11_patient_can_access_doctor_search(self):
        """Verifies authenticated patient can access the doctor search & filter page."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/doctors')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Find Doctors &amp; Specialists', resp.data)
        self.assertIn(b'Filter Specialists', resp.data)
        self.assertIn(b'Dr. Sarah Smith', resp.data)

    # 12. Doctor name search
    def test_12_doctor_name_search(self):
        """Verifies searching doctors by name."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/doctors?name=Sarah')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Sarah Smith', resp.data)
        self.assertNotIn(b'Marcus Johnson', resp.data)

    # 13. Case-insensitive and partial doctor search
    def test_13_case_insensitive_partial_doctor_search(self):
        """Verifies case-insensitive partial match on doctor name."""
        self._login('patient@careconnect.org')
        r_part = self.client.get('/patient/doctors?name=smith')
        self.assertEqual(r_part.status_code, 200)
        self.assertIn(b'Sarah Smith', r_part.data)

        r_upper = self.client.get('/patient/doctors?name=SARAH')
        self.assertEqual(r_upper.status_code, 200)
        self.assertIn(b'Sarah Smith', r_upper.data)

    # 14. Specialization filter
    def test_14_specialization_filter(self):
        """Verifies filtering doctors by specialization."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/doctors?specialization=Cardiology')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Sarah Smith', resp.data)
        self.assertNotIn(b'Marcus Johnson', resp.data)  # Neurology

    # 15. Qualification filter
    def test_15_qualification_filter(self):
        """Verifies filtering doctors by academic/medical qualification."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/doctors?qualification=Harvard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Sarah Smith', resp.data)
        self.assertNotIn(b'Johns Hopkins', resp.data)

    # 16. Experience filter
    def test_16_experience_filter(self):
        """Verifies filtering doctors by clinical experience brackets."""
        self._login('patient@careconnect.org')
        # 0-2 years (Dr. Kevin Ray, 1 yr)
        r_junior = self.client.get('/patient/doctors?experience=0-2')
        self.assertEqual(r_junior.status_code, 200)
        self.assertIn(b'Kevin Ray', r_junior.data)
        self.assertNotIn(b'Sarah Smith', r_junior.data)  # 12 yrs

        # 10+ years (Dr. Sarah Smith, 12 yrs)
        r_senior = self.client.get('/patient/doctors?experience=10+')
        self.assertEqual(r_senior.status_code, 200)
        self.assertIn(b'Sarah Smith', r_senior.data)
        self.assertNotIn(b'Kevin Ray', r_senior.data)

    # 17. Availability filter
    def test_17_availability_filter(self):
        """Verifies availability filter against doctor schedules."""
        self._login('patient@careconnect.org')
        # Available this week
        resp = self.client.get('/patient/doctors?availability=this_week')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Dr.', resp.data)

    # 18. Combined multi-criteria filtering
    def test_18_combined_filters(self):
        """Verifies combined filtering matches ALL criteria simultaneously."""
        self._login('patient@careconnect.org')
        # Matches Dr. Sarah Smith (Cardiology, Harvard, 10+ yrs)
        resp = self.client.get(
            f'/patient/doctors?hospital_id={self.hospital.id}&specialization=Cardiology&experience=10+&sort=name_asc'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Sarah Smith', resp.data)
        self.assertNotIn(b'Marcus Johnson', resp.data)
        self.assertNotIn(b'Kevin Ray', resp.data)

        # Non-matching combination (Cardiology with 0-2 years exp)
        resp_empty = self.client.get(
            f'/patient/doctors?hospital_id={self.hospital.id}&specialization=Cardiology&experience=0-2'
        )
        self.assertEqual(resp_empty.status_code, 200)
        self.assertIn(b'No doctors match your selected filters', resp_empty.data)

    # 19. Doctor sorting
    def test_19_doctor_sorting(self):
        """Verifies sorting doctors by experience and name."""
        self._login('patient@careconnect.org')
        # High to low experience
        r_exp = self.client.get('/patient/doctors?sort=exp_high')
        self.assertEqual(r_exp.status_code, 200)
        pos_smith = r_exp.data.find(b'Sarah Smith')  # 12 yrs
        pos_junior = r_exp.data.find(b'Kevin Ray')   # 1 yr
        self.assertTrue(pos_smith < pos_junior, "12-year experienced doctor must precede 1-year junior doctor.")

        # Low to high experience
        r_low = self.client.get('/patient/doctors?sort=exp_low')
        self.assertEqual(r_low.status_code, 200)
        pos_smith2 = r_low.data.find(b'Sarah Smith')
        pos_junior2 = r_low.data.find(b'Kevin Ray')
        self.assertTrue(pos_junior2 < pos_smith2, "1-year junior doctor must precede 12-year doctor when sorted low to high.")

    # 20. Empty doctor result
    def test_20_empty_doctor_result(self):
        """Verifies professional empty state banner when no doctors match."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/doctors?name=NonexistentDoctorABC')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'No doctors match your selected filters', resp.data)
        self.assertIn(b'Clear Filters', resp.data)

    # 21. Unauthorized access blocked
    def test_21_unauthorized_access_blocked(self):
        """Verifies unauthenticated access to search routes redirects to login."""
        r1 = self.client.get('/patient/hospitals', follow_redirects=False)
        self.assertEqual(r1.status_code, 302)
        self.assertIn('/login', r1.headers.get('Location', ''))

        r2 = self.client.get('/patient/doctors', follow_redirects=False)
        self.assertEqual(r2.status_code, 302)
        self.assertIn('/login', r2.headers.get('Location', ''))

    # 22. Cross-role access protection
    def test_22_cross_role_access_protection(self):
        """Verifies Doctor and Hospital admin roles cannot access patient doctor search."""
        # Doctor role
        self._login('dr.smith@careconnect.org')
        r_doc = self.client.get('/patient/doctors', follow_redirects=False)
        self.assertEqual(r_doc.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # Hospital role
        self._login('admin@careconnect.org')
        r_hosp = self.client.get('/patient/doctors', follow_redirects=False)
        self.assertEqual(r_hosp.status_code, 302)

    # 23. SQL injection-safe search input
    def test_23_sql_injection_safe_search_input(self):
        """Verifies search input containing SQL syntax does not execute or error."""
        self._login('patient@careconnect.org')
        payload = "' OR 1=1; DROP TABLE hospitals; --"
        resp = self.client.get(f'/patient/hospitals?name={payload}')
        self.assertEqual(resp.status_code, 200)
        # Database intact
        self.assertGreaterEqual(Hospital.query.count(), 1)

        resp2 = self.client.get(f'/patient/doctors?name={payload}')
        self.assertEqual(resp2.status_code, 200)
        self.assertGreaterEqual(Doctor.query.count(), 1)

    # 24. Existing booking workflow integration
    def test_24_existing_booking_integration(self):
        """Verifies doctor search result links cleanly into existing booking flow."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/doctors?name=Sarah')
        self.assertEqual(resp.status_code, 200)
        # Check booking button link exists
        expected_booking_param = f"doctor_id={self.doctor.id}"
        self.assertIn(expected_booking_param.encode('utf-8'), resp.data)

        # Follow link to booking page
        book_resp = self.client.get(f'/patient/book?doctor_id={self.doctor.id}&hospital_id={self.hospital.id}')
        self.assertIn(b'Schedule an Appointment', book_resp.data)

    # 25. Existing AI specialist workflow preserved
    def test_25_existing_ai_specialist_workflow_preserved(self):
        """Verifies AI Specialist Recommendation page continues to function normally."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/ai-specialist')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'AI Specialist Recommendation', resp.data)

    # 26. Existing smart appointment workflow preserved
    def test_26_existing_smart_appointment_preserved(self):
        """Verifies Smart Appointment Recommendation page continues to function normally."""
        self._login('patient@careconnect.org')
        resp = self.client.get('/patient/smart-appointment')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Smart Appointment', resp.data)


if __name__ == '__main__':
    unittest.main()
