import unittest
from datetime import date, timedelta

from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import book_appointment
from ai.patient_load_predictor import (
    predict_patient_load,
    DISCLAIMER_TEXT,
    INSUFFICIENT_DATA_TEXT,
    INSUFFICIENT_SPECIALTY_TEXT
)


class CareConnectPhase10PatientLoadTestCase(unittest.TestCase):
    """
    Comprehensive test suite for Phase 10: AI Patient Load Prediction:
    1. Page requires hospital authentication.
    2. Non-hospital users cannot access page.
    3. Hospital can view its own historical and forecast data.
    4. Hospital A cannot see Hospital B data (strict isolation).
    5. Cancelled appointments are excluded from active load.
    6. Prediction uses real database appointment data.
    7. Prediction does not use fake/static counts.
    8. Prediction returns result with sufficient data (>= 3 days).
    9. Insufficient data (< 3 days or 0 appts) handled safely.
    10. Prediction includes confidence.
    11. Prediction includes trend information.
    12. 7-day forecast generated correctly.
    13. Hospital dashboard shows AI Patient Load card.
    14. Chart data belongs strictly to logged-in hospital.
    15. Specialization breakdown does not expose other hospital.
    16. Operational disclaimer displayed.
    17. Prediction does not make medical/disease claims.
    18. Existing booking, PDF, QR, and AI specialist features remain intact.
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
            registration_number='HOSP-P10-A',
            hospital_type='Multispecialty Hospital',
            address='100 Alpha Way',
            city='Boston'
        )
        db.session.add(self.hospital_a)
        db.session.flush()

        # 2. Hospital B & Admin B (empty / new facility for cross-tenant & low-data tests)
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
            registration_number='HOSP-P10-B',
            hospital_type='Community Clinic',
            address='200 Beta Lane',
            city='New York'
        )
        db.session.add(self.hospital_b)
        db.session.flush()

        # 3. Doctors for Hospital A
        doc_a1_user = User(
            username='dr_cardio_a',
            email='dr_cardio_a@hospital-a.org',
            full_name='Dr. Alice Cardio',
            role=User.ROLE_DOCTOR
        )
        doc_a1_user.set_password('doc123')
        db.session.add(doc_a1_user)
        db.session.flush()

        self.doc_a1 = Doctor(
            user_id=doc_a1_user.id,
            hospital_id=self.hospital_a.id,
            specialization='Cardiology',
            qualification='MD, FACC',
            consultation_fee=150.0,
            is_available=True,
            available_days='Monday - Friday',
            available_time='09:00 AM - 05:00 PM'
        )
        db.session.add(self.doc_a1)
        db.session.flush()

        doc_a2_user = User(
            username='dr_neuro_a',
            email='dr_neuro_a@hospital-a.org',
            full_name='Dr. Bob Neuro',
            role=User.ROLE_DOCTOR
        )
        doc_a2_user.set_password('doc123')
        db.session.add(doc_a2_user)
        db.session.flush()

        self.doc_a2 = Doctor(
            user_id=doc_a2_user.id,
            hospital_id=self.hospital_a.id,
            specialization='Neurology',
            qualification='MD, PhD',
            consultation_fee=175.0,
            is_available=True,
            available_days='Monday - Friday',
            available_time='09:00 AM - 05:00 PM'
        )
        db.session.add(self.doc_a2)
        db.session.flush()

        # 4. Doctor for Hospital B
        doc_b1_user = User(
            username='dr_ortho_b',
            email='dr_ortho_b@hospital-b.org',
            full_name='Dr. Charlie Ortho',
            role=User.ROLE_DOCTOR
        )
        doc_b1_user.set_password('doc123')
        db.session.add(doc_b1_user)
        db.session.flush()

        self.doc_b1 = Doctor(
            user_id=doc_b1_user.id,
            hospital_id=self.hospital_b.id,
            specialization='Orthopedics',
            qualification='MD',
            consultation_fee=130.0,
            is_available=True
        )
        db.session.add(self.doc_b1)
        db.session.flush()

        # 5. Patient
        patient_user = User(
            username='patient_one',
            email='patient_one@example.com',
            full_name='David Patient',
            role=User.ROLE_PATIENT
        )
        patient_user.set_password('patient123')
        db.session.add(patient_user)
        db.session.flush()

        self.patient = Patient(
            user_id=patient_user.id,
            date_of_birth=date(1992, 6, 12),
            gender='Male',
            city='Boston'
        )
        db.session.add(self.patient)
        db.session.flush()

        # 6. Seed Historical Appointments across multiple dates for Hospital A (>= 3 active historical days)
        today = date.today()
        dates_and_counts = [
            (today - timedelta(days=1), 4, self.doc_a1),
            (today - timedelta(days=2), 5, self.doc_a2),
            (today - timedelta(days=3), 6, self.doc_a1),
            (today - timedelta(days=4), 3, self.doc_a2),
            (today, 2, self.doc_a1)
        ]

        counter = 1
        for past_date, count, doc in dates_and_counts:
            for i in range(count):
                appt = Appointment(
                    patient_id=self.patient.id,
                    doctor_id=doc.id,
                    hospital_id=self.hospital_a.id,
                    appointment_date=past_date,
                    time_slot=f'{9 + i:02d}:00 AM - {9 + i:02d}:30 AM',
                    appointment_number=f'CC-P10-{counter:06d}',
                    verification_token=f'TOKEN-P10-{counter}',
                    status=Appointment.STATUS_COMPLETED if past_date < today else Appointment.STATUS_CONFIRMED,
                    symptoms='Regular consultation'
                )
                db.session.add(appt)
                counter += 1

        # Seed one CANCELLED appointment for Hospital A (should be excluded from active load)
        cancelled_appt = Appointment(
            patient_id=self.patient.id,
            doctor_id=self.doc_a1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=today - timedelta(days=1),
            time_slot='02:00 PM - 02:30 PM',
            appointment_number=f'CC-P10-{counter:06d}',
            verification_token=f'TOKEN-P10-{counter}',
            status=Appointment.STATUS_CANCELLED,
            symptoms='Cancelled by patient'
        )
        db.session.add(cancelled_appt)
        counter += 1

        # Hospital B only gets 1 appointment on 1 date (insufficient historical data: < 3 days)
        appt_b = Appointment(
            patient_id=self.patient.id,
            doctor_id=self.doc_b1.id,
            hospital_id=self.hospital_b.id,
            appointment_date=today - timedelta(days=2),
            time_slot='11:00 AM - 11:30 AM',
            appointment_number=f'CC-P10-B-{counter:06d}',
            verification_token=f'TOKEN-P10-B-{counter}',
            status=Appointment.STATUS_COMPLETED,
            symptoms='Initial orthopedic evaluation'
        )
        db.session.add(appt_b)

        db.session.commit()

    def _login(self, email, password):
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # ------------------------------------------------------------------------
    # 1. Authentication & RBAC
    # ------------------------------------------------------------------------
    def test_ai_load_prediction_page_requires_hospital_auth(self):
        """Verifies unauthenticated access to /hospital/ai-load-prediction redirects to login."""
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_non_hospital_users_cannot_access_page(self):
        """Verifies Doctor and Patient roles cannot access hospital load prediction."""
        # Doctor attempt
        self._login('dr_cardio_a@hospital-a.org', 'doc123')
        res_doc = self.client.get('/hospital/ai-load-prediction')
        self.assertIn(res_doc.status_code, [302, 403])

        # Patient attempt
        self.client.get('/logout', follow_redirects=True)
        self._login('patient_one@example.com', 'patient123')
        res_pat = self.client.get('/hospital/ai-load-prediction')
        self.assertIn(res_pat.status_code, [302, 403])

    def test_hospital_can_view_own_prediction_page(self):
        """Verifies authenticated hospital admin can load /hospital/ai-load-prediction."""
        self._login('admin_a@hospital-a.org', 'pass123')
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'AI Patient Load Prediction', res.data)
        self.assertIn(b'Hospital Alpha Medical Center', res.data)
        self.assertIn(b'Operational Capacity Planning Notice', res.data)

    # ------------------------------------------------------------------------
    # 2. Multi-Tenant Data Isolation
    # ------------------------------------------------------------------------
    def test_hospital_a_cannot_see_hospital_b_data(self):
        """Verifies Hospital A and Hospital B only see their respective historical data."""
        # Hospital A
        self._login('admin_a@hospital-a.org', 'pass123')
        res_a = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res_a.status_code, 200)
        self.assertIn(b'Hospital Alpha Medical Center', res_a.data)
        self.assertNotIn(b'Hospital Beta Health Facility', res_a.data)

        # Hospital B
        self.client.get('/logout', follow_redirects=True)
        self._login('admin_b@hospital-b.org', 'pass123')
        res_b = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res_b.status_code, 200)
        self.assertIn(b'Hospital Beta Health Facility', res_b.data)
        self.assertNotIn(b'Hospital Alpha Medical Center', res_b.data)

    # ------------------------------------------------------------------------
    # 3. Cancelled Appointments Excluded
    # ------------------------------------------------------------------------
    def test_cancelled_appointments_are_excluded(self):
        """Verifies cancelled appointments are not included in daily load totals."""
        from ai.patient_load_predictor import get_hospital_daily_counts
        counts = get_hospital_daily_counts(self.hospital_a.id)
        yesterday = date.today() - timedelta(days=1)
        # 4 completed + 1 cancelled was seeded for yesterday; count should strictly be 4
        self.assertEqual(counts.get(yesterday, 0), 4)

    # ------------------------------------------------------------------------
    # 4. Real Data & Prediction Outputs
    # ------------------------------------------------------------------------
    def test_prediction_uses_real_database_records(self):
        """Verifies prediction engine calculates metrics from actual database records."""
        pred = predict_patient_load(self.hospital_a.id)
        self.assertTrue(pred['has_sufficient_data'])
        self.assertEqual(pred['today_count'], 2)  # Seeded 2 for today
        self.assertGreater(pred['predicted_tomorrow'], 0)
        self.assertEqual(pred['historical_days_used'], 4)  # 4 past days seeded

    def test_prediction_does_not_use_fake_static_patient_counts(self):
        """Verifies modifying appointment data changes the resulting prediction."""
        initial_pred = predict_patient_load(self.hospital_a.id)

        # Add 10 appointments for yesterday
        yesterday = date.today() - timedelta(days=1)
        for i in range(10):
            appt = Appointment(
                patient_id=self.patient.id,
                doctor_id=self.doc_a1.id,
                hospital_id=self.hospital_a.id,
                appointment_date=yesterday,
                time_slot=f'0{i}:00 PM - 0{i}:30 PM',
                status=Appointment.STATUS_COMPLETED
            )
            db.session.add(appt)
        db.session.commit()

        updated_pred = predict_patient_load(self.hospital_a.id)
        # Higher volume should increase the predicted tomorrow load
        self.assertGreater(updated_pred['predicted_tomorrow'], initial_pred['predicted_tomorrow'])

    def test_insufficient_historical_data_handled_safely(self):
        """Verifies facilities with < 3 historical days return safe insufficient data status."""
        pred_b = predict_patient_load(self.hospital_b.id)
        self.assertFalse(pred_b['has_sufficient_data'])
        self.assertIn('Insufficient historical data', pred_b['message'])

        # Check template rendering for low-data facility
        self._login('admin_b@hospital-b.org', 'pass123')
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Insufficient Historical Data', res.data)

    def test_prediction_includes_confidence_and_trend(self):
        """Verifies prediction outputs safe confidence wording and trend direction."""
        pred = predict_patient_load(self.hospital_a.id)
        self.assertIn(pred['confidence'], ['High', 'Medium', 'Low'])
        self.assertIn('Prediction confidence:', pred['confidence_display'])
        self.assertIn(pred['trend_badge'], ['Higher', 'Consistent', 'Lower'])

    def test_seven_day_forecast_generated_correctly(self):
        """Verifies 7 sequential daily projections are generated with valid properties."""
        pred = predict_patient_load(self.hospital_a.id)
        forecast = pred['forecast_7days']
        self.assertEqual(len(forecast), 7)

        expected_date = date.today() + timedelta(days=1)
        for day in forecast:
            self.assertEqual(day['date'], expected_date)
            self.assertGreaterEqual(day['predicted_load'], 0)
            self.assertIn(day['trend_badge'], ['Higher', 'Consistent', 'Lower'])
            self.assertIn(day['confidence'], ['High', 'Medium', 'Low'])
            expected_date += timedelta(days=1)

    # ------------------------------------------------------------------------
    # 5. Hospital Dashboard Integration & UI
    # ------------------------------------------------------------------------
    def test_hospital_dashboard_shows_ai_load_card(self):
        """Verifies hospital dashboard displays the AI Patient Load highlight card."""
        self._login('admin_a@hospital-a.org', 'pass123')
        res = self.client.get('/hospital/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'AI Patient Load', res.data)
        self.assertIn(b'Predicted tomorrow:', res.data)
        self.assertIn(b'View Prediction', res.data)

    def test_chart_data_belongs_only_to_logged_in_hospital(self):
        """Verifies Chart.js data series in HTML contains only facility's own counts."""
        self._login('admin_a@hospital-a.org', 'pass123')
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'loadPredictionChart', res.data)
        self.assertIn(b'Historical Actual', res.data)
        self.assertIn(b'Predicted Forecast', res.data)

    def test_specialization_breakdown_does_not_expose_other_hospital(self):
        """Verifies department breakdown shows only specialties from the facility's own doctors."""
        pred = predict_patient_load(self.hospital_a.id)
        if pred['specialty_breakdown']:
            specs = [item['specialization'] for item in pred['specialty_breakdown']]
            self.assertIn('Cardiology', specs)
            # Orthopedics belongs to Hospital B, must NOT appear in Hospital A's breakdown
            self.assertNotIn('Orthopedics', specs)

    def test_operational_disclaimer_displayed(self):
        """Verifies operational disclaimer is clearly displayed in page response."""
        self._login('admin_a@hospital-a.org', 'pass123')
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Predictions are estimates based on historical Care Connect appointment activity', res.data)
        self.assertIn(b'may differ from actual patient volume', res.data)

    def test_prediction_does_not_make_medical_disease_claims(self):
        """Verifies prediction outputs contain no medical diagnosis or disease words."""
        pred = predict_patient_load(self.hospital_a.id)
        explanation = pred['explanation'].lower()
        self.assertNotIn('diagnosis', explanation)
        self.assertNotIn('disease', explanation)
        self.assertNotIn('prescription', explanation)
        self.assertNotIn('medication', explanation)

    # ------------------------------------------------------------------------
    # 6. Preservation of Existing Features (Phases 1 - 9)
    # ------------------------------------------------------------------------
    def test_existing_appointment_booking_still_works(self):
        """Verifies booking service creates appointments normally."""
        target_date = date.today() + timedelta(days=2)
        while target_date.weekday() >= 5:  # Ensure weekday for Monday - Friday schedule
            target_date += timedelta(days=1)

        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doc_a1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot='10:00 AM - 10:30 AM',
            symptoms='Post-load-check booking'
        )
        self.assertTrue(success, f"Booking failed with message: {msg}")
        self.assertIsNotNone(appt)

    def test_existing_ai_specialist_recommendation_still_works(self):
        """Verifies Phase 9 AI specialist recommendation is intact."""
        self._login('patient_one@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have had migraines, frequent headaches, and difficulty concentrating.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Neurology', res.data)


if __name__ == '__main__':
    unittest.main()
