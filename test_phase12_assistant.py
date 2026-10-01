import unittest
from datetime import date, datetime, timedelta

from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import book_appointment
from ai.care_connect_assistant import (
    process_assistant_message,
    ASSISTANT_DIAGNOSIS_BOUNDARY,
    ASSISTANT_MEDICATION_BOUNDARY,
    ASSISTANT_UNKNOWN_FALLBACK,
    ASSISTANT_NO_RECORD_FOUND
)


class CareConnectPhase12AssistantTestCase(unittest.TestCase):
    """
    Comprehensive test suite for Phase 12: Care Connect AI Assistant:
    1. Patient authentication required
    2. Doctor authentication
    3. Hospital authentication
    4. Patient role isolation
    5. Doctor role isolation
    6. Hospital role isolation
    7. Patient appointment lookup
    8. Doctor appointment lookup
    9. Hospital appointment lookup
    10. Upcoming appointment query
    11. Appointment history query
    12. Hospital search
    13. Doctor search
    14. Specialist search
    15. No fake database records
    16. Unauthorized data access blocked
    17. Phase 9 integration (AI Specialist guidance)
    18. Phase 10 integration (AI Patient Load Prediction summary)
    19. Phase 11 integration (Smart Appointment guidance)
    20. Medical diagnosis safety boundary
    21. Medication safety boundary
    22. Empty input handling
    23. Unknown question handling
    24. Database error handling
    25. Authentication regression
    26. Existing Phase 6 booking regression
    27. PDF/QR verification regression
    28. Appointment history regression
    29. Assistant web interface and AJAX endpoint
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
            registration_number='HOSP-P12-A',
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
            registration_number='HOSP-P12-B',
            hospital_type='Community Clinic',
            address='200 Beta Lane',
            city='New York'
        )
        db.session.add(self.hospital_b)
        db.session.flush()

        # 3. Doctor 1 (Hospital A, Cardiology)
        u_doc1 = User(
            username='dr_marcus',
            email='marcus@hospital-a.org',
            full_name='Marcus Johnson',
            role=User.ROLE_DOCTOR
        )
        u_doc1.set_password('pass123')
        db.session.add(u_doc1)
        db.session.flush()

        self.doc1 = Doctor(
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
        db.session.add(self.doc1)
        db.session.flush()

        # 4. Doctor 2 (Hospital A, Neurology)
        u_doc2 = User(
            username='dr_emily',
            email='emily@hospital-a.org',
            full_name='Emily Watson',
            role=User.ROLE_DOCTOR
        )
        u_doc2.set_password('pass123')
        db.session.add(u_doc2)
        db.session.flush()

        self.doc2 = Doctor(
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
        db.session.add(self.doc2)
        db.session.flush()

        # 5. Doctor 3 (Hospital B, Orthopedics)
        u_doc3 = User(
            username='dr_david',
            email='david@hospital-b.org',
            full_name='David Lee',
            role=User.ROLE_DOCTOR
        )
        u_doc3.set_password('pass123')
        db.session.add(u_doc3)
        db.session.flush()

        self.doc3 = Doctor(
            user_id=u_doc3.id,
            hospital_id=self.hospital_b.id,
            specialization='Orthopedics',
            qualification='MD',
            experience_years=8,
            consultation_fee=140.0,
            available_days='Daily',
            available_time='09:00 AM - 05:00 PM',
            is_available=True
        )
        db.session.add(self.doc3)
        db.session.flush()

        # 6. Patient 1 & User
        self.u_patient1 = User(
            username='alice_patient',
            email='alice@test.com',
            full_name='Alice Patient',
            role=User.ROLE_PATIENT
        )
        self.u_patient1.set_password('pass123')
        db.session.add(self.u_patient1)
        db.session.flush()

        self.patient1 = Patient(
            user_id=self.u_patient1.id,
            date_of_birth=date(1992, 4, 15),
            gender='Female',
            blood_group='A+',
            address='123 Maple St',
            city='Boston',
            emergency_contact='555-0101'
        )
        db.session.add(self.patient1)
        db.session.flush()

        # 7. Patient 2 (Bob)
        self.u_patient2 = User(
            username='bob_patient',
            email='bob@test.com',
            full_name='Bob Patient',
            role=User.ROLE_PATIENT
        )
        self.u_patient2.set_password('pass123')
        db.session.add(self.u_patient2)
        db.session.flush()

        self.patient2 = Patient(
            user_id=self.u_patient2.id,
            date_of_birth=date(1988, 8, 20),
            gender='Male',
            blood_group='O+',
            address='456 Oak Ave',
            city='New York',
            emergency_contact='555-0202'
        )
        db.session.add(self.patient2)
        db.session.flush()

        # 8. Seed Appointments for Patient 1
        today = date.today()
        # Appointment Today for Patient 1
        self.appt1_today = Appointment(
            patient_id=self.patient1.id,
            doctor_id=self.doc1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=today,
            time_slot='09:00 AM - 09:30 AM',
            appointment_number='CC-P12-000001',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Routine cardiac checkup'
        )
        db.session.add(self.appt1_today)

        # Upcoming Appointment for Patient 1 (in 2 days)
        self.appt1_upcoming = Appointment(
            patient_id=self.patient1.id,
            doctor_id=self.doc1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=today + timedelta(days=2),
            time_slot='10:00 AM - 10:30 AM',
            appointment_number='CC-P12-000002',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Follow-up cardiology consultation'
        )
        db.session.add(self.appt1_upcoming)

        # Past Completed Appointment for Patient 1
        self.appt1_past = Appointment(
            patient_id=self.patient1.id,
            doctor_id=self.doc2.id,
            hospital_id=self.hospital_a.id,
            appointment_date=today - timedelta(days=7),
            time_slot='11:00 AM - 11:30 AM',
            appointment_number='CC-P12-000003',
            status=Appointment.STATUS_COMPLETED,
            symptoms='Initial migraine consultation'
        )
        db.session.add(self.appt1_past)

        # Appointment for Patient 2 with Doctor 3 at Hospital B
        self.appt2 = Appointment(
            patient_id=self.patient2.id,
            doctor_id=self.doc3.id,
            hospital_id=self.hospital_b.id,
            appointment_date=today,
            time_slot='02:00 PM - 02:30 PM',
            appointment_number='CC-P12-000004',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Orthopedic knee evaluation'
        )
        db.session.add(self.appt2)

        db.session.commit()

        self.u_admin_a = admin_a
        self.u_admin_b = admin_b
        self.u_doc1 = u_doc1
        self.u_doc2 = u_doc2

    def _login_as(self, email, password='pass123'):
        self.client.get('/logout')
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # 1. Patient authentication required
    def test_patient_authentication_required(self):
        """Verifies unauthenticated access to /assistant redirects to login."""
        res = self.client.get('/assistant')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.location)

    # 2. Doctor authentication
    def test_doctor_authentication(self):
        """Verifies authenticated doctor can access /assistant."""
        self._login_as('marcus@hospital-a.org')
        res = self.client.get('/assistant')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Doctor Role', res.data)

    # 3. Hospital authentication
    def test_hospital_authentication(self):
        """Verifies authenticated hospital admin can access /assistant."""
        self._login_as('admin_a@hospital-a.org')
        res = self.client.get('/assistant')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Hospital Admin Role', res.data)

    # 4. Patient role isolation
    def test_patient_role_isolation(self):
        """Verifies Patient A receives only their own appointments, never Patient B's."""
        res_a = process_assistant_message(self.u_patient1, "Show my upcoming appointments")
        self.assertEqual(res_a['status'], 'success')
        self.assertIn('CC-P12-000002', res_a['response'])
        self.assertNotIn('CC-P12-000004', res_a['response'])

        # Explicit inquiry about Patient B's data is blocked
        res_cross = process_assistant_message(self.u_patient1, "Show other patient appointments")
        self.assertEqual(res_cross['status'], 'unauthorized')
        self.assertIn('Access Denied', res_cross['response'])

    # 5. Doctor role isolation
    def test_doctor_role_isolation(self):
        """Verifies Doctor A cannot query Doctor B's consultation queue."""
        res_cross = process_assistant_message(self.u_doc1, "Show other doctor's appointments")
        self.assertEqual(res_cross['status'], 'unauthorized')
        self.assertIn('Access Denied', res_cross['response'])

    # 6. Hospital role isolation
    def test_hospital_role_isolation(self):
        """Verifies Hospital A cannot access Hospital B's administrative data."""
        res_cross = process_assistant_message(self.u_admin_a, "Show other hospital data")
        self.assertEqual(res_cross['status'], 'unauthorized')
        self.assertIn('Access Denied', res_cross['response'])

    # 7. Patient appointment lookup
    def test_patient_appointment_lookup(self):
        """Verifies patient can retrieve their appointments scheduled for today."""
        res = process_assistant_message(self.u_patient1, "What appointments do I have today?")
        self.assertEqual(res['status'], 'success')
        self.assertIn('CC-P12-000001', res['response'])
        self.assertIn('Marcus Johnson', res['response'])

    # 8. Doctor appointment lookup
    def test_doctor_appointment_lookup(self):
        """Verifies doctor can query their consultations for today."""
        res = process_assistant_message(self.u_doc1, "Show my appointments today")
        self.assertEqual(res['status'], 'success')
        self.assertIn('Alice Patient', res['response'])
        self.assertIn('09:00 AM - 09:30 AM', res['response'])

    # 9. Hospital appointment lookup
    def test_hospital_appointment_lookup(self):
        """Verifies hospital admin receives their facility's appointment metrics."""
        res = process_assistant_message(self.u_admin_a, "Show today's appointment count")
        self.assertEqual(res['status'], 'success')
        self.assertIn('active appointment(s) scheduled for today', res['response'])

    # 10. Upcoming appointment query
    def test_upcoming_appointment_query(self):
        """Verifies next appointment query correctly identifies the earliest upcoming booking."""
        res = process_assistant_message(self.u_patient1, "What is my next appointment?")
        self.assertEqual(res['status'], 'success')
        self.assertIn('CC-P12-000001', res['response'])
        self.assertIn('Marcus Johnson', res['response'])

    # 11. Appointment history query
    def test_appointment_history_query(self):
        """Verifies query returns past and completed consultations."""
        res = process_assistant_message(self.u_patient1, "Show my appointment history")
        self.assertEqual(res['status'], 'success')
        self.assertIn('CC-P12-000003', res['response'])
        self.assertIn('Emily Watson', res['response'])

    # 12. Hospital search
    def test_hospital_search(self):
        """Verifies querying registered hospitals returns real database facilities."""
        res = process_assistant_message(self.u_patient1, "Which hospitals are registered?")
        self.assertEqual(res['status'], 'success')
        self.assertIn('Hospital Alpha Medical Center', res['response'])
        self.assertIn('Hospital Beta Health Facility', res['response'])

    # 13. Doctor search
    def test_doctor_search(self):
        """Verifies searching available doctors returns registered physicians."""
        res = process_assistant_message(self.u_patient1, "Which doctors are available?")
        self.assertEqual(res['status'], 'success')
        self.assertIn('Marcus Johnson', res['response'])
        self.assertIn('Emily Watson', res['response'])

    # 14. Specialist search
    def test_specialist_search(self):
        """Verifies filtering by medical specialization returns matching physicians."""
        res = process_assistant_message(self.u_patient1, "Show cardiologists")
        self.assertEqual(res['status'], 'success')
        self.assertIn('Marcus Johnson', res['response'])
        self.assertNotIn('Emily Watson', res['response'])

    # 15. No fake database records
    def test_no_fake_database_records(self):
        """Verifies querying non-existent specialty or facility returns no matching record."""
        res = process_assistant_message(self.u_patient1, "Show dermatologists at NonExistent Clinic")
        self.assertEqual(res['status'], 'success')
        self.assertIn(ASSISTANT_NO_RECORD_FOUND, res['response'])

    # 16. Unauthorized data access blocked
    def test_unauthorized_data_access_blocked(self):
        """Verifies patient requesting hospital administrative metrics is rejected."""
        res = process_assistant_message(self.u_patient1, "Show patient load prediction")
        self.assertEqual(res['status'], 'unauthorized')
        self.assertIn('Access Denied', res['response'])

    # 17. Phase 9 integration
    def test_phase9_integration(self):
        """Verifies assistant guides patients to AI Specialist Recommendation."""
        res = process_assistant_message(self.u_patient1, "I don't know which specialist to choose")
        self.assertEqual(res['status'], 'success')
        self.assertIn('AI Specialist Recommendation', res['response'])

    # 18. Phase 10 integration
    def test_phase10_integration(self):
        """Verifies hospital admin receives operational forecast summary with disclaimer."""
        res = process_assistant_message(self.u_admin_a, "Show patient-load prediction")
        self.assertEqual(res['status'], 'success')
        self.assertIn('Patient Load', res['response'])
        self.assertIn('operational forecast', res['response'].lower())
        self.assertIn('not a medical prediction', res['response'].lower())

    # 19. Phase 11 integration
    def test_phase11_integration(self):
        """Verifies assistant guides patients to Smart Appointment feature."""
        res = process_assistant_message(self.u_patient1, "How does smart appointment recommendation work?")
        self.assertEqual(res['status'], 'success')
        self.assertIn('Smart Appointment', res['response'])

    # 20. Medical diagnosis safety boundary
    def test_medical_diagnosis_safety_boundary(self):
        """Verifies medical diagnosis queries receive standardized safety boundary."""
        res = process_assistant_message(self.u_patient1, "Can you diagnose my chest pain?")
        self.assertEqual(res['status'], 'safety_boundary')
        self.assertEqual(res['response'], ASSISTANT_DIAGNOSIS_BOUNDARY)

    # 21. Medication safety boundary
    def test_medication_safety_boundary(self):
        """Verifies medication and prescription queries receive standardized safety boundary."""
        res = process_assistant_message(self.u_patient1, "What medicine or dosage should I take?")
        self.assertEqual(res['status'], 'safety_boundary')
        self.assertEqual(res['response'], ASSISTANT_MEDICATION_BOUNDARY)

    # 22. Empty input handling
    def test_empty_input_handling(self):
        """Verifies empty and whitespace queries return clear prompt."""
        res = process_assistant_message(self.u_patient1, "   ")
        self.assertEqual(res['status'], 'empty')
        self.assertIn('Please enter a question', res['response'])

    # 23. Unknown question handling
    def test_unknown_question_handling(self):
        """Verifies unknown queries receive standard fallback response."""
        res = process_assistant_message(self.u_patient1, "What is the capital of Mars?")
        self.assertEqual(res['status'], 'fallback')
        self.assertEqual(res['response'], ASSISTANT_UNKNOWN_FALLBACK)

    # 24. Database error handling
    def test_database_error_handling(self):
        """Verifies unexpected errors return clean user-facing error response."""
        # Query with an invalid user object
        res = process_assistant_message(None, "Show my appointments")
        self.assertEqual(res['status'], 'error')
        self.assertIn('Authentication required', res['response'])

    # 25. Authentication regression
    def test_authentication_regression(self):
        """Verifies existing login and logout flows remain intact."""
        res_ok = self._login_as('alice@test.com', 'pass123')
        self.assertEqual(res_ok.status_code, 200)

        res_logout = self.client.get('/logout', follow_redirects=True)
        self.assertIn(b'logged out', res_logout.data.lower())

    # 26. Existing Phase 6 booking regression
    def test_existing_phase6_booking_regression(self):
        """Verifies Phase 6 appointment booking flow remains functional."""
        target_date = date.today() + timedelta(days=5)
        success, msg, appt = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot='03:00 PM - 03:30 PM',
            symptoms='Phase 12 booking regression check'
        )
        self.assertTrue(success)
        self.assertIsNotNone(appt)
        self.assertIsNotNone(appt.appointment_number)

    # 27. PDF/QR verification regression
    def test_phase7_regression_pdf_qr(self):
        """Verifies Phase 7 PDF download and QR code creation remain operational."""
        target_date = date.today() + timedelta(days=4)
        _, _, appt = book_appointment(
            patient=self.patient1,
            doctor_id=self.doc1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=target_date,
            time_slot='04:00 PM - 04:30 PM'
        )
        self.assertIsNotNone(appt.qr_code_file)
        self._login_as('alice@test.com')
        res_pdf = self.client.get(f'/patient/appointments/{appt.id}/pdf')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.mimetype, 'application/pdf')

    # 28. Appointment history regression
    def test_phase8_appointment_history_regression(self):
        """Verifies Phase 8 appointment history page renders for patient."""
        self._login_as('alice@test.com')
        res = self.client.get('/patient/appointments')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'My Appointments', res.data)

    # 29. Assistant web interface and AJAX endpoint
    def test_assistant_web_interface_and_ajax_endpoint(self):
        """Verifies GET /assistant and POST /assistant/chat work end-to-end."""
        self._login_as('alice@test.com')

        # GET page
        res_get = self.client.get('/assistant')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b'Care Connect AI Assistant', res_get.data)
        self.assertIn(b'What is my next appointment?', res_get.data)

        # POST AJAX chat
        res_post = self.client.post('/assistant/chat', json={
            'message': 'What is my next appointment?'
        })
        self.assertEqual(res_post.status_code, 200)
        data = res_post.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('CC-P12-000001', data['response'])


if __name__ == '__main__':
    unittest.main()
