import unittest
from datetime import date, datetime, timedelta

from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import book_appointment, generate_doctor_slots
from ai.smart_appointment import (
    recommend_smart_slots,
    SMART_APPOINTMENT_DISCLAIMER,
    classify_time_period,
    get_candidate_dates
)


class CareConnectPhase11SmartAppointmentTestCase(unittest.TestCase):
    """
    Comprehensive test suite for Phase 11: AI-Assisted Smart Appointment Recommendation:
    1. Patient-only access (unauthenticated / doctor / hospital redirected or 403)
    2. Hospital filtering
    3. Specialization filtering
    4. Doctor filtering
    5. Preferred date matching
    6. Morning preference matching
    7. Afternoon preference matching
    8. Evening preference matching
    9. Any-time preference matching
    10. Flexibility handling (Exact, Somewhat Flexible, Flexible)
    11. Real available slots only
    12. Booked slots excluded
    13. Cancelled slots handled correctly (available again)
    14. Doctor working day respected
    15. Doctor working hours respected
    16. Hospital-doctor relationship validated
    17. Recommendations are explainable
    18. No medical diagnosis logic
    19. Recommendation does NOT create an appointment
    20. Existing Phase 6 booking still works
    21. Double-booking protection still works
    22. Patient data isolation
    23. Phase 9 regression tests
    24. Phase 10 regression tests
    25. PDF/QR regression
    26. Appointment history regression
    27. Authentication regression
    28. Role-based access regression
    29. Page renders cleanly with form controls
    """

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        self._seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def _seed_test_data(self):
        # 1. Hospital A & Admin A
        admin_a = User(
            username='admin_a',
            email='admin_a@hospital-a.org',
            full_name='Admin Hospital A',
            role=User.ROLE_HOSPITAL
        )
        admin_a.set_password('pass123')
        db.session.add(admin_a)
        db.session.flush()

        self.hospital_a = Hospital(
            user_id=admin_a.id,
            name='Hospital Alpha Medical Center',
            registration_number='HOSP-P11-A',
            hospital_type='Multispecialty Hospital',
            address='100 Alpha Way',
            city='Boston'
        )
        db.session.add(self.hospital_a)
        db.session.flush()

        # 2. Hospital B & Admin B
        admin_b = User(
            username='admin_b',
            email='admin_b@hospital-b.org',
            full_name='Admin Hospital B',
            role=User.ROLE_HOSPITAL
        )
        admin_b.set_password('pass123')
        db.session.add(admin_b)
        db.session.flush()

        self.hospital_b = Hospital(
            user_id=admin_b.id,
            name='Hospital Beta Health Facility',
            registration_number='HOSP-P11-B',
            hospital_type='Community Clinic',
            address='200 Beta Lane',
            city='New York'
        )
        db.session.add(self.hospital_b)
        db.session.flush()

        # 3. Doctor 1 (Hospital A, Cardiology, Daily)
        u_doc1 = User(
            username='dr_cardiologist',
            email='cardio@hospital-a.org',
            full_name='Marcus Johnson',
            role=User.ROLE_DOCTOR
        )
        u_doc1.set_password('pass123')
        db.session.add(u_doc1)
        db.session.flush()

        self.doc1_cardio = Doctor(
            user_id=u_doc1.id,
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            qualification='MD, FACC',
            experience_years=12,
            consultation_fee=150.0,
            available_days='Daily',
            available_time='09:00 AM - 05:00 PM',
            is_available=True
        )
        db.session.add(self.doc1_cardio)
        db.session.flush()

        # 4. Doctor 2 (Hospital A, Neurology, Weekdays Only: Monday - Friday)
        u_doc2 = User(
            username='dr_neurologist',
            email='neuro@hospital-a.org',
            full_name='Sarah Smith',
            role=User.ROLE_DOCTOR
        )
        u_doc2.set_password('pass123')
        db.session.add(u_doc2)
        db.session.flush()

        self.doc2_neuro = Doctor(
            user_id=u_doc2.id,
            hospital_id=self.hospital_a.id,
            specialization='Neurology',
            qualification='MD, FAAN',
            experience_years=10,
            consultation_fee=180.0,
            available_days='Monday - Friday',
            available_time='08:00 AM - 04:00 PM',
            is_available=True
        )
        db.session.add(self.doc2_neuro)
        db.session.flush()

        # 5. Doctor 3 (Hospital B, Cardiology, Daily)
        u_doc3 = User(
            username='dr_cardio_b',
            email='cardio@hospital-b.org',
            full_name='David Lee',
            role=User.ROLE_DOCTOR
        )
        u_doc3.set_password('pass123')
        db.session.add(u_doc3)
        db.session.flush()

        self.doc3_cardio_b = Doctor(
            user_id=u_doc3.id,
            hospital_id=self.hospital_b.id,
            specialization='Cardiology',
            qualification='MD',
            experience_years=8,
            consultation_fee=130.0,
            available_days='Daily',
            available_time='09:00 AM - 05:00 PM',
            is_available=True
        )
        db.session.add(self.doc3_cardio_b)
        db.session.flush()

        # 6. Patient 1 & User
        u_patient1 = User(
            username='patient1',
            email='patient1@test.com',
            full_name='Alice Patient',
            role=User.ROLE_PATIENT
        )
        u_patient1.set_password('pass123')
        db.session.add(u_patient1)
        db.session.flush()

        self.patient1 = Patient(
            user_id=u_patient1.id,
            date_of_birth=date(1992, 4, 15),
            gender='Female',
            blood_group='A+',
            address='123 Maple Street',
            city='Boston',
            emergency_contact='555-0101'
        )
        db.session.add(self.patient1)
        db.session.flush()

        # 7. Patient 2 (for isolation tests)
        u_patient2 = User(
            username='patient2',
            email='patient2@test.com',
            full_name='Bob Patient',
            role=User.ROLE_PATIENT
        )
        u_patient2.set_password('pass123')
        db.session.add(u_patient2)
        db.session.flush()

        self.patient2 = Patient(
            user_id=u_patient2.id,
            date_of_birth=date(1988, 8, 20),
            gender='Male',
            blood_group='O+',
            address='456 Oak Avenue',
            city='New York',
            emergency_contact='555-0202'
        )
        db.session.add(self.patient2)
        db.session.commit()

    def _login_as(self, email, password='pass123'):
        self.client.get('/logout')
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # 1. Patient-only access
    def test_patient_only_access(self):
        """Verifies only authenticated patients can access /patient/smart-appointment."""
        # Unauthenticated access -> redirect to login
        res = self.client.get('/patient/smart-appointment')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.location)

        # Doctor access -> redirected with unauthorized notice
        self._login_as('cardio@hospital-a.org')
        res_doc = self.client.get('/patient/smart-appointment', follow_redirects=True)
        self.assertIn(b'not authorized', res_doc.data.lower())

        # Hospital access -> redirected with unauthorized notice
        self._login_as('admin_a@hospital-a.org')
        res_hosp = self.client.get('/patient/smart-appointment', follow_redirects=True)
        self.assertIn(b'not authorized', res_hosp.data.lower())

        # Patient access -> 200 OK
        self._login_as('patient1@test.com')
        res_pat = self.client.get('/patient/smart-appointment')
        self.assertEqual(res_pat.status_code, 200)

    # 2. Hospital filtering
    def test_hospital_filtering(self):
        """Verifies recommendations only include doctors from the selected hospital."""
        target_date = date.today() + timedelta(days=2)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        self.assertGreater(len(res['recommendations']), 0)
        for r in res['recommendations']:
            self.assertEqual(r['hospital_id'], self.hospital_a.id)
            self.assertNotEqual(r['hospital_id'], self.hospital_b.id)

    # 3. Specialization filtering
    def test_specialization_filtering(self):
        """Verifies recommendations only match the requested specialization."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Neurology',
            preferred_date=target_date,
            flexibility='flexible'
        )
        if res['status'] == 'success':
            for r in res['recommendations']:
                self.assertEqual(r['specialization'], 'Neurology')
                self.assertEqual(r['doctor_id'], self.doc2_neuro.id)

    # 4. Doctor filtering
    def test_doctor_filtering(self):
        """Verifies selecting a specific doctor filters strictly for that physician."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            doctor_id=self.doc1_cardio.id,
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        for r in res['recommendations']:
            self.assertEqual(r['doctor_id'], self.doc1_cardio.id)

    # 5. Preferred date matching
    def test_preferred_date_matching(self):
        """Verifies slots on the preferred date receive +2 exact date bonus points."""
        pref_date = date.today() + timedelta(days=2)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=pref_date,
            flexibility='somewhat_flexible'
        )
        self.assertEqual(res['status'], 'success')
        # Check that preferred date slots have the +2 date bonus in their breakdown
        exact_slots = [r for r in res['recommendations'] if r['date'] == pref_date.strftime('%Y-%m-%d')]
        self.assertGreater(len(exact_slots), 0)
        for s in exact_slots:
            has_date_bonus = any('+2 pts' in b for b in s['score_breakdown'])
            self.assertTrue(has_date_bonus)

    # 6. Morning preference matching
    def test_morning_preference_matching(self):
        """Verifies morning preference gives morning slots highest priority."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            preferred_time_period='morning',
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        top_rec = res['recommendations'][0]
        self.assertEqual(top_rec['time_period'], 'Morning')
        self.assertIn('+3 pts', ' '.join(top_rec['score_breakdown']))

    # 7. Afternoon preference matching
    def test_afternoon_preference_matching(self):
        """Verifies afternoon preference gives afternoon slots highest priority."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            preferred_time_period='afternoon',
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        top_rec = res['recommendations'][0]
        self.assertEqual(top_rec['time_period'], 'Afternoon')

    # 8. Evening preference matching
    def test_evening_preference_matching(self):
        """Verifies evening preference handles evening classification or fallback safely."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            preferred_time_period='evening',
            flexibility='somewhat_flexible'
        )
        # Even if doctor's hours end at 5pm, somewhat_flexible allows alternative slots
        self.assertIn(res['status'], ['success', 'no_slots'])

    # 9. Any-time preference matching
    def test_any_time_preference_matching(self):
        """Verifies any_time preference awards time points across available slots."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            preferred_time_period='any_time',
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        self.assertGreater(len(res['recommendations']), 0)
        self.assertIn('any-time', res['recommendations'][0]['score_breakdown'][0].lower())

    # 10. Flexibility handling
    def test_flexibility_handling(self):
        """Verifies exact, somewhat_flexible, and flexible candidate date sets."""
        today = date.today()
        base_date = today + timedelta(days=3)

        exact_dates = get_candidate_dates(base_date, 'exact')
        self.assertEqual(len(exact_dates), 1)
        self.assertEqual(exact_dates[0], base_date)

        somewhat_dates = get_candidate_dates(base_date, 'somewhat_flexible')
        self.assertGreaterEqual(len(somewhat_dates), 3)

        flexible_dates = get_candidate_dates(base_date, 'flexible')
        self.assertGreaterEqual(len(flexible_dates), 5)

    # 11. Real available slots only
    def test_real_available_slots_only(self):
        """Verifies all recommended slots actually exist in doctor's scheduled hours."""
        target_date = date.today() + timedelta(days=2)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        all_slots = generate_doctor_slots(self.doc1_cardio, target_date)
        valid_time_slots = {s['time_slot'] for s in all_slots}

        for r in res['recommendations']:
            self.assertIn(r['time_slot'], valid_time_slots)

    # 12. Booked slots excluded
    def test_booked_slots_excluded(self):
        """Verifies already booked slots are excluded from recommendations."""
        target_date = date.today() + timedelta(days=2)
        all_slots = generate_doctor_slots(self.doc1_cardio, target_date)
        first_slot = all_slots[0]['time_slot']

        # Book this first slot
        success, _, _ = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot=first_slot,
            symptoms='Test Booking'
        )
        self.assertTrue(success)

        # Get recommendations
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        recommended_slots = [r['time_slot'] for r in res['recommendations']]
        self.assertNotIn(first_slot, recommended_slots)

    # 13. Cancelled slots handled correctly
    def test_cancelled_slots_handled_correctly(self):
        """Verifies cancelled appointments release their slot back for recommendation."""
        target_date = date.today() + timedelta(days=2)
        all_slots = generate_doctor_slots(self.doc1_cardio, target_date)
        test_slot = all_slots[0]['time_slot']

        # Book the slot
        _, _, appt = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot=test_slot,
            symptoms='Test Booking for Cancellation'
        )

        # Cancel the appointment
        appt.status = Appointment.STATUS_CANCELLED
        db.session.commit()

        # Recommendation should include the released slot again
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        recommended_slots = [r['time_slot'] for r in res['recommendations']]
        self.assertIn(test_slot, recommended_slots)

    # 14. Doctor working day respected
    def test_doctor_working_day_respected(self):
        """Verifies doctors are never recommended on non-working days."""
        # Find next Sunday
        target_date = date.today() + timedelta(days=1)
        while target_date.weekday() != 6:  # 6 = Sunday
            target_date += timedelta(days=1)

        # Doctor 2 works Monday - Friday only
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Neurology',
            doctor_id=self.doc2_neuro.id,
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'no_slots')

    # 15. Doctor working hours respected
    def test_doctor_working_hours_respected(self):
        """Verifies slots adhere strictly to the doctor's start and end times."""
        target_date = date.today() + timedelta(days=1)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            doctor_id=self.doc1_cardio.id,
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        for r in res['recommendations']:
            # Doctor 1 is 09:00 AM - 05:00 PM
            self.assertGreaterEqual(r['start_time'], '09:00 AM')

    # 16. Hospital-doctor relationship validated
    def test_hospital_doctor_relationship_validated(self):
        """Verifies that attempting to book a doctor at the wrong hospital yields no slots."""
        target_date = date.today() + timedelta(days=1)
        # Doctor 1 belongs to Hospital A, not Hospital B
        res = recommend_smart_slots(
            hospital_id=self.hospital_b.id,
            specialization='Cardiology',
            doctor_id=self.doc1_cardio.id,
            preferred_date=target_date,
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'no_slots')

    # 17. Recommendations are explainable
    def test_recommendations_are_explainable(self):
        """Verifies recommendation results provide a clear human-readable explanation and score."""
        target_date = date.today() + timedelta(days=2)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date,
            preferred_time_period='morning',
            flexibility='exact'
        )
        self.assertEqual(res['status'], 'success')
        rec = res['recommendations'][0]
        self.assertIn('score', rec)
        self.assertGreater(rec['score'], 0)
        self.assertIn('explanation', rec)
        self.assertIn('score_breakdown', rec)
        self.assertTrue(len(rec['explanation']) > 10)

    # 18. No medical diagnosis logic
    def test_no_medical_diagnosis_logic(self):
        """Verifies recommendation engine and disclaimers do not make diagnostic or treatment claims."""
        target_date = date.today() + timedelta(days=2)
        res = recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date
        )
        self.assertIn('disclaimer', res)
        disclaimer = res['disclaimer'].lower()
        self.assertIn('not a medical diagnosis', disclaimer)
        # Ensure no medical diagnostic statements in results
        for r in res.get('recommendations', []):
            exp = r['explanation'].lower()
            self.assertNotIn('diagnosed with', exp)
            self.assertNotIn('treatment', exp)
            self.assertNotIn('prescription', exp)

    # 19. Recommendation does NOT create an appointment
    def test_recommendation_does_not_create_appointment(self):
        """Verifies generating recommendations does not persist any appointment record."""
        initial_count = Appointment.query.count()
        target_date = date.today() + timedelta(days=2)
        recommend_smart_slots(
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            preferred_date=target_date
        )
        post_count = Appointment.query.count()
        self.assertEqual(initial_count, post_count)

    # 20. Existing Phase 6 booking still works
    def test_existing_phase6_booking_still_works(self):
        """Verifies Phase 6 booking flow remains fully operational."""
        target_date = date.today() + timedelta(days=3)
        success, message, appt = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot='10:00 AM - 10:30 AM',
            symptoms='Phase 11 booking regression check'
        )
        self.assertTrue(success)
        self.assertIsNotNone(appt)
        self.assertIsNotNone(appt.appointment_number)

    # 21. Double-booking protection still works
    def test_double_booking_protection_still_works(self):
        """Verifies Phase 6 concurrency protection rejects duplicate bookings for same slot."""
        target_date = date.today() + timedelta(days=3)
        slot = '11:00 AM - 11:30 AM'
        success1, _, _ = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot=slot
        )
        self.assertTrue(success1)

        success2, msg, _ = book_appointment(
            patient=self.patient2,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot=slot
        )
        self.assertFalse(success2)
        self.assertIn('no longer available', msg)

    # 22. Patient data isolation
    def test_patient_data_isolation(self):
        """Verifies Patient A cannot access Patient B's appointment cancellation or private records."""
        target_date = date.today() + timedelta(days=4)
        _, _, appt_a = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot='02:00 PM - 02:30 PM'
        )

        # Login as Patient 2 and attempt to cancel Patient 1's appointment
        self._login_as('patient2@test.com')
        res = self.client.post(f'/patient/appointments/{appt_a.id}/cancel')
        self.assertEqual(res.status_code, 403)

    # 23. Phase 9 regression tests
    def test_phase9_regression(self):
        """Verifies Phase 9 AI Specialist Recommendation still functions."""
        self._login_as('patient1@test.com')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have severe headaches and dizziness'
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Neurology', res.data)

    # 24. Phase 10 regression tests
    def test_phase10_regression(self):
        """Verifies Phase 10 Hospital AI Load Prediction still functions."""
        self._login_as('admin_a@hospital-a.org')
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'AI Patient Load Prediction', res.data)

    # 25. PDF/QR regression
    def test_phase7_regression_pdf_qr(self):
        """Verifies Phase 7 PDF and QR code generation still work."""
        target_date = date.today() + timedelta(days=2)
        _, _, appt = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1_cardio.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot='03:00 PM - 03:30 PM'
        )
        self.assertIsNotNone(appt.qr_code_file)
        self.assertIsNotNone(appt.verification_token)

        self._login_as('patient1@test.com')
        res_pdf = self.client.get(f'/patient/appointments/{appt.id}/pdf')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.mimetype, 'application/pdf')

    # 26. Appointment history regression
    def test_phase8_regression_history(self):
        """Verifies Phase 8 appointment history page loads correctly."""
        self._login_as('patient1@test.com')
        res = self.client.get('/patient/appointments')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'My Appointments', res.data)

    # 27. Authentication regression
    def test_phase2_auth_regression(self):
        """Verifies login, logout, and password hashing work correctly."""
        res_fail = self._login_as('patient1@test.com', 'wrongpassword')
        self.assertIn(b'Invalid', res_fail.data)

        res_ok = self._login_as('patient1@test.com', 'pass123')
        self.assertEqual(res_ok.status_code, 200)

        res_logout = self.client.get('/logout', follow_redirects=True)
        self.assertIn(b'logged out', res_logout.data.lower())

    # 28. Role-based access regression
    def test_role_based_access_regression(self):
        """Verifies doctor and hospital portals reject unauthorized cross-role access."""
        self._login_as('patient1@test.com')
        res_hosp = self.client.get('/hospital/dashboard', follow_redirects=True)
        self.assertIn(b'not authorized', res_hosp.data.lower())

        res_doc = self.client.get('/doctor/dashboard', follow_redirects=True)
        self.assertIn(b'not authorized', res_doc.data.lower())

    # 29. Smart appointment page renders cleanly
    def test_smart_appointment_page_renders_cleanly(self):
        """Verifies GET /patient/smart-appointment renders form and dropdowns."""
        self._login_as('patient1@test.com')
        res = self.client.get('/patient/smart-appointment')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Smart Appointment Recommendation', res.data)
        self.assertIn(b'Hospital Facility', res.data)
        self.assertIn(b'Medical Specialty', res.data)
        self.assertIn(b'Schedule Flexibility', res.data)

        # Submit search via query args
        target_date = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
        res_search = self.client.get(f'/patient/smart-appointment?hospital_id={self.hospital_a.id}&specialization=Cardiology&preferred_date={target_date}&preferred_time_period=morning&flexibility=exact')
        self.assertEqual(res_search.status_code, 200)
        self.assertIn(b'Top Recommended Consultation Slots', res_search.data)
        self.assertIn(b'Book This Slot', res_search.data)


if __name__ == '__main__':
    unittest.main()
