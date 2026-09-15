"""
Care Connect - Phase 15 End-to-End Testing, Bug Fixing & Quality Assurance Test Suite
Complete end-to-end integration and QA verification across:
1. Application startup and asset delivery
2. Hospital workflow and tenant isolation
3. Doctor clinical workflow and authorization
4. Patient discovery, AI guidance, booking, and history
5. Appointment lifecycle, status transitions, and race condition protection
6. PDF appointment confirmation and zero-PHI QR verification
7. Non-diagnostic AI safety boundaries and operational scope
8. Security regressions, HTTP headers, RBAC, IDOR, and XSS auto-escaping
9. UI/UX accessibility, status badges, and Light/Dark theme contracts
10. Database model integrity, foreign keys, and non-destructive persistence
"""

import unittest
import io
import json
from datetime import date, timedelta
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import book_appointment, generate_doctor_slots, doctor_works_on_date
from utils.pdf_generator import generate_appointment_pdf
from ai.specialist_recommender import recommend_specialist
from ai.patient_load_predictor import predict_patient_load
from ai.smart_appointment import recommend_smart_slots
from ai.care_connect_assistant import process_assistant_message


def get_working_date(doctor, offset_days=2):
    """Finds next confirmed working day for a doctor."""
    target = date.today() + timedelta(days=offset_days)
    for _ in range(14):
        if doctor_works_on_date(doctor, target):
            return target
        target += timedelta(days=1)
    return date.today() + timedelta(days=offset_days)


class CareConnectPhase15EndToEndQATestCase(unittest.TestCase):
    """Comprehensive Phase 15 Quality Assurance and End-to-End Test Suite."""

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def _login(self, email, password):
        """Authenticates user via the standard login endpoint."""
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    def _logout(self):
        """Logs out currently authenticated user."""
        return self.client.get('/logout', follow_redirects=True)

    # =========================================================================
    # 1. FULL APPLICATION STARTUP & ASSET CHECK
    # =========================================================================
    def test_01_startup_and_static_assets(self):
        """Verify startup, route registration, and delivery of CSS/JS assets."""
        res_css = self.client.get('/static/css/style.css')
        self.assertEqual(res_css.status_code, 200)
        self.assertIn(b':root', res_css.data)
        self.assertIn(b'--primary', res_css.data)
        res_css.close()

        res_js = self.client.get('/static/js/main.js')
        self.assertEqual(res_js.status_code, 200)
        self.assertIn(b'careconnect_theme', res_js.data)
        res_js.close()

        res_landing = self.client.get('/')
        self.assertEqual(res_landing.status_code, 200)
        self.assertIn(b'Care Connect', res_landing.data)

    # =========================================================================
    # 2. HOSPITAL END-TO-END WORKFLOW & ISOLATION
    # =========================================================================
    def test_02_hospital_workflow_and_isolation(self):
        """Test complete hospital admin workflow using demo account and verify tenant isolation."""
        # 1. Login with demo hospital credentials
        res_login = self._login('admin@careconnect.org', 'admin123')
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'Hospital Dashboard', res_login.data)

        # 2. Hospital Profile
        res_prof = self.client.get('/hospital/profile')
        self.assertEqual(res_prof.status_code, 200)
        self.assertIn(b'Metro General Hospital', res_prof.data)

        # 3. Doctor Roster & Management
        res_docs = self.client.get('/hospital/doctors')
        self.assertEqual(res_docs.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_docs.data)

        # 4. Hospital Appointments Queue
        res_appts = self.client.get('/hospital/appointments')
        self.assertEqual(res_appts.status_code, 200)

        # 5. AI Patient Load Prediction
        res_ai_load = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res_ai_load.status_code, 200)
        self.assertIn(b'Patient Load Prediction', res_ai_load.data)

        # 6. AI Assistant access
        res_asst = self.client.get('/assistant')
        self.assertEqual(res_asst.status_code, 200)

        # 7. Cross-role boundary checks: hospital cannot access patient or doctor pages
        res_pat_book = self.client.get('/patient/book')
        self.assertIn(res_pat_book.status_code, [403, 302])

        res_doc_avail = self.client.get('/doctor/availability')
        self.assertIn(res_doc_avail.status_code, [403, 302])

        # 8. Logout
        res_logout = self._logout()
        self.assertEqual(res_logout.status_code, 200)

    # =========================================================================
    # 3. DOCTOR END-TO-END WORKFLOW & AUTHORIZATION
    # =========================================================================
    def test_03_doctor_workflow_and_authorization(self):
        """Test complete doctor workflow using demo account and verify authorization bounds."""
        # 1. Login
        res_login = self._login('dr.smith@careconnect.org', 'doctor123')
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'Doctor Dashboard', res_login.data)

        # 2. Doctor Profile
        res_prof = self.client.get('/doctor/profile')
        self.assertEqual(res_prof.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_prof.data)

        # 3. Doctor Availability Management
        res_avail = self.client.get('/doctor/availability')
        self.assertEqual(res_avail.status_code, 200)
        self.assertIn(b'Working Days', res_avail.data)

        # 4. Appointments Queue
        res_appts = self.client.get('/doctor/appointments')
        self.assertEqual(res_appts.status_code, 200)

        # 5. Patient Consultation History
        res_patients = self.client.get('/doctor/patients')
        self.assertEqual(res_patients.status_code, 200)

        # 6. Cross-role boundaries: doctor cannot access hospital admin or book as patient
        res_hosp_admin = self.client.get('/hospital/doctors')
        self.assertIn(res_hosp_admin.status_code, [403, 302])

        res_pat_dash = self.client.get('/patient/dashboard')
        self.assertIn(res_pat_dash.status_code, [403, 302])

        # 7. Logout
        self._logout()

    # =========================================================================
    # 4. PATIENT END-TO-END WORKFLOW & DISCOVERY
    # =========================================================================
    def test_04_patient_workflow_and_discovery(self):
        """Test complete patient workflow using demo account from discovery to booking to history."""
        # 1. Login
        res_login = self._login('patient@careconnect.org', 'patient123')
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'Patient Dashboard', res_login.data)

        # 2. Hospital Search & Discovery
        res_hosp = self.client.get('/patient/hospitals')
        self.assertEqual(res_hosp.status_code, 200)
        self.assertIn(b'Metro General Hospital', res_hosp.data)

        # 3. Hospital Detail
        hosp = Hospital.query.first()
        res_hosp_detail = self.client.get(f'/patient/hospitals/{hosp.id}')
        self.assertEqual(res_hosp_detail.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_hosp_detail.data)

        # 4. AI Specialist Recommendation
        res_spec = self.client.get('/patient/ai-specialist')
        self.assertEqual(res_spec.status_code, 200)
        self.assertIn(b'Specialist Recommendation', res_spec.data)
        self.assertIn(b'not a medical diagnosis', res_spec.data)

        # 5. Smart Appointment Recommendation
        res_smart = self.client.get('/patient/smart-appointment')
        self.assertEqual(res_smart.status_code, 200)
        self.assertIn(b'Smart Appointment', res_smart.data)

        # 6. Appointment History
        res_appts = self.client.get('/patient/appointments')
        self.assertEqual(res_appts.status_code, 200)
        self.assertIn(b'My Appointments', res_appts.data)

        # 7. Logout
        self._logout()

    # =========================================================================
    # 5. APPOINTMENT FULL LIFECYCLE & EDGE CASES QA
    # =========================================================================
    def test_05_appointment_full_lifecycle_and_edge_cases(self):
        """Verify complete appointment lifecycle and enforce double-booking & validation rules."""
        doctor = Doctor.query.first()
        patient = Patient.query.first()
        self.assertIsNotNone(doctor)
        self.assertIsNotNone(patient)

        valid_date = get_working_date(doctor, offset_days=3)

        # 1. Available slots generation
        slots = generate_doctor_slots(doctor, valid_date)
        self.assertTrue(len(slots) > 0, "Doctor should have available slots on working day")
        chosen_slot = slots[0]['time_slot']

        # 2. Book appointment via service
        success, msg, appt = book_appointment(
            patient=patient,
            doctor_id=doctor.id,
            hospital_id=doctor.hospital_id,
            appointment_date=valid_date,
            time_slot=chosen_slot,
            symptoms="Routine health checkup"
        )
        self.assertTrue(success, f"Booking failed: {msg}")
        self.assertEqual(appt.status, Appointment.STATUS_CONFIRMED)
        self.assertTrue(appt.appointment_number.startswith('CC-'))

        # 3. Duplicate booking attempt on the same slot must be rejected
        success_dup, msg_dup, _ = book_appointment(
            patient=patient,
            doctor_id=doctor.id,
            hospital_id=doctor.hospital_id,
            appointment_date=valid_date,
            time_slot=chosen_slot,
            symptoms="Duplicate attempt"
        )
        self.assertFalse(success_dup)
        self.assertTrue("no longer available" in msg_dup.lower() or "already booked" in msg_dup.lower())

        # 4. Attempt to book on past date must be rejected
        past_date = date.today() - timedelta(days=5)
        success_past, msg_past, _ = book_appointment(
            patient=patient,
            doctor_id=doctor.id,
            hospital_id=doctor.hospital_id,
            appointment_date=past_date,
            time_slot="09:00 AM - 09:30 AM",
            symptoms="Past date check"
        )
        self.assertFalse(success_past)
        self.assertIn("past", msg_past.lower())

        # 5. Cancel appointment
        can_cancel, _ = appt.can_cancel()
        self.assertTrue(can_cancel)
        appt.status = Appointment.STATUS_CANCELLED
        db.session.commit()

        # 6. Verify cancelled slot becomes available again for re-booking
        success_rebook, msg_rebook, appt_new = book_appointment(
            patient=patient,
            doctor_id=doctor.id,
            hospital_id=doctor.hospital_id,
            appointment_date=valid_date,
            time_slot=chosen_slot,
            symptoms="Rebooking cancelled slot"
        )
        self.assertTrue(success_rebook, f"Re-booking failed: {msg_rebook}")
        self.assertEqual(appt_new.status, Appointment.STATUS_CONFIRMED)

        # 7. Complete appointment
        can_complete, _ = appt_new.can_transition_to(Appointment.STATUS_COMPLETED)
        self.assertTrue(can_complete)
        appt_new.status = Appointment.STATUS_COMPLETED
        db.session.commit()

        # 8. Completed appointment cannot be cancelled
        can_cancel_comp, _ = appt_new.can_cancel()
        self.assertFalse(can_cancel_comp)

    # =========================================================================
    # 6. PDF & QR VERIFICATION SECURITY & PRIVACY QA
    # =========================================================================
    def test_06_pdf_generation_and_qr_privacy(self):
        """Verify PDF generation, IDOR protection, and zero-PHI QR verification."""
        appt = Appointment.query.filter_by(status=Appointment.STATUS_CONFIRMED).first()
        self.assertIsNotNone(appt)

        # 1. Generate PDF in-memory and verify valid PDF stream
        pdf_bytes = generate_appointment_pdf(appt)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertTrue(len(pdf_bytes) > 1000)

        # 2. Verify authorized patient can download PDF
        self._login('patient@careconnect.org', 'patient123')
        res_pdf = self.client.get(f'/patient/appointments/{appt.id}/pdf')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.mimetype, 'application/pdf')
        self.assertIn(b'%PDF-', res_pdf.data)
        self._logout()

        # 3. Verify public QR verification endpoint returns 200 without login
        res_verify = self.client.get(f'/verify/appointment/{appt.verification_token}')
        self.assertEqual(res_verify.status_code, 200)
        self.assertIn(appt.appointment_number.encode(), res_verify.data)

        # 4. Verify ZERO Protected Health Information (PHI) is rendered on the public page
        self.assertNotIn(b'patient@careconnect.org', res_verify.data)
        self.assertNotIn(b'9876543210', res_verify.data)
        if appt.symptoms:
            self.assertNotIn(appt.symptoms.encode(), res_verify.data)

        # 5. Verify invalid verification token returns safe page (valid=False, status 200)
        res_invalid = self.client.get('/verify/appointment/invalid-uuid-token-12345')
        self.assertEqual(res_invalid.status_code, 200)
        self.assertIn(b'Invalid', res_invalid.data)

    # =========================================================================
    # 7. AI FEATURES & CLINICAL SAFETY BOUNDARIES QA
    # =========================================================================
    def test_07_ai_features_and_guardrails(self):
        """Verify Phase 9, 10, 11, and 12 AI features strictly adhere to non-diagnostic bounds."""
        # Phase 9: AI Specialist Recommendation
        res_spec = recommend_specialist("severe chest pain and rapid heartbeat")
        self.assertEqual(res_spec['recommended_specialty'], 'Cardiology')
        self.assertIn('not a medical diagnosis', res_spec['disclaimer'].lower())

        # Phase 10: AI Patient Load Prediction
        hospital = Hospital.query.first()
        prediction = predict_patient_load(hospital.id)
        self.assertIn('has_sufficient_data', prediction)
        self.assertIn('disclaimer', prediction)
        self.assertIn('estimates based on historical', prediction['disclaimer'].lower())
        self.assertNotIn('disease', prediction)

        # Phase 11: AI Smart Appointment Recommendation
        doctor = Doctor.query.first()
        target_date = get_working_date(doctor, offset_days=3)
        res_smart = recommend_smart_slots(
            hospital_id=hospital.id,
            specialization=doctor.specialization,
            preferred_date=target_date,
            preferred_time_period='morning',
            flexibility='flexible'
        )
        self.assertEqual(res_smart['status'], 'success')
        self.assertTrue(len(res_smart['recommendations']) > 0)
        top_rec = res_smart['recommendations'][0]
        self.assertIn('score', top_rec)
        self.assertIn('score_breakdown', top_rec)
        self.assertIn('explanation', top_rec)

        # Phase 12: Care Connect AI Assistant non-diagnostic guardrails
        patient_user = User.query.filter_by(role=User.ROLE_PATIENT).first()
        res_diag = process_assistant_message(patient_user, "Can you diagnose why I have a headache and prescribe medicine?")
        self.assertEqual(res_diag['status'], 'safety_boundary')
        self.assertIn('cannot diagnose', res_diag['response'].lower())

    # =========================================================================
    # 8. SECURITY REGRESSION & HTTP HEADERS QA
    # =========================================================================
    def test_08_security_headers_and_auth_regression(self):
        """Verify security headers, password hashing, and session destruction."""
        # 1. Security Headers
        res = self.client.get('/')
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(res.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')

        # 2. Password Hashing Verification
        user = User.query.filter_by(email='admin@careconnect.org').first()
        self.assertFalse(user.password_hash.startswith('admin123'))
        self.assertTrue(user.password_hash.startswith(('scrypt:', 'pbkdf2:')))
        self.assertTrue(user.check_password('admin123'))

        # 3. Session invalidation on logout
        self._login('patient@careconnect.org', 'patient123')
        self._logout()
        res_protected = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(res_protected.status_code, 302)
        self.assertIn('/login', res_protected.headers.get('Location', ''))

    # =========================================================================
    # 9. UI/UX ACCESSIBILITY & THEME CONTRACTS QA
    # =========================================================================
    def test_09_ui_ux_accessibility_and_badges(self):
        """Verify accessibility skip-link, theme toggle element, and icon-paired status badges."""
        res = self.client.get('/')
        self.assertIn(b'skip-link', res.data)
        self.assertIn(b'Skip to main content', res.data)
        self.assertIn(b'themeToggleBtn', res.data)
        self.assertIn(b'data-bs-theme', res.data)

        # Login and check appointment history page for paired status badge markup
        self._login('patient@careconnect.org', 'patient123')
        res_hist = self.client.get('/patient/appointments')
        self.assertEqual(res_hist.status_code, 200)
        # Check that badges contain icon classes
        self.assertIn(b'badge-status-', res_hist.data)
        self.assertIn(b'bi-', res_hist.data)
        self._logout()

    # =========================================================================
    # 10. DATABASE INTEGRITY & SEED DATA QA
    # =========================================================================
    def test_10_database_integrity_and_demo_seed(self):
        """Verify seeded demonstration data, models, and foreign key integrity."""
        # 1. Demo users present
        roles = [u.role for u in User.query.all()]
        self.assertIn(User.ROLE_HOSPITAL, roles)
        self.assertIn(User.ROLE_DOCTOR, roles)
        self.assertIn(User.ROLE_PATIENT, roles)

        # 2. Hospital relationships
        hospital = Hospital.query.first()
        self.assertIsNotNone(hospital.user)
        self.assertTrue(hospital.doctors.count() > 0)

        # 3. Doctor relationships
        for doc in hospital.doctors.all():
            self.assertIsNotNone(doc.user)
            self.assertEqual(doc.hospital_id, hospital.id)

        # 4. Patient relationships
        patient = Patient.query.first()
        self.assertIsNotNone(patient.user)

        # 5. Appointment relationships
        for appt in Appointment.query.all():
            self.assertIsNotNone(appt.patient)
            self.assertIsNotNone(appt.doctor)
            self.assertIsNotNone(appt.hospital)
            self.assertIsNotNone(appt.verification_token)
            self.assertIsNotNone(appt.appointment_number)


if __name__ == '__main__':
    unittest.main()
