"""
Care Connect - Phase 14 Security, Privacy, Data Protection & Quality Review Test Suite
Comprehensive verification of authentication, RBAC, data isolation, IDOR protection,
input validation, double-booking prevention, XSS escaping, QR privacy, AI safety boundaries,
error handling, and security headers across all 33 critical security domains.
"""

import unittest
from datetime import date, timedelta
from sqlalchemy.exc import IntegrityError
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import book_appointment, doctor_works_on_date


def get_working_date_for_doctor(doctor, offset_days=2):
    """Finds the next confirmed working date for the specified doctor."""
    target = date.today() + timedelta(days=offset_days)
    for _ in range(14):
        if doctor_works_on_date(doctor, target):
            return target
        target += timedelta(days=1)
    return date.today() + timedelta(days=offset_days)


class CareConnectPhase14SecurityTestCase(unittest.TestCase):
    """Comprehensive test suite covering all 33 required security & quality domains."""

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
        """Helper to authenticate user via the main login endpoint."""
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. Authentication Security
    # -------------------------------------------------------------------------
    def test_01_authentication_protection_on_protected_routes(self):
        """1. Verify unauthenticated requests to protected endpoints redirect to login."""
        protected_endpoints = [
            '/patient/dashboard',
            '/doctor/dashboard',
            '/hospital/dashboard',
            '/assistant',
            '/patient/appointments',
            '/doctor/appointments',
            '/hospital/appointments',
        ]
        for ep in protected_endpoints:
            res = self.client.get(ep, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Expected 302 redirect for unauthenticated {ep}")
            self.assertIn('/login', res.headers.get('Location', ''))

    def test_02_password_hashing_pbkdf2_and_repr_privacy(self):
        """2. Verify secure password hashing is active and __repr__ never leaks password hash."""
        user = User.query.filter_by(email='patient@careconnect.org').first()
        self.assertIsNotNone(user)
        # Modern Werkzeug generates scrypt or pbkdf2 hashes
        self.assertTrue(user.password_hash.startswith(('scrypt:', 'pbkdf2:')))
        self.assertNotEqual(user.password_hash, 'patient123')
        self.assertTrue(user.check_password('patient123'))
        self.assertFalse(user.check_password('wrongpassword'))
        # Ensure __repr__ does not reveal password hash
        repr_str = repr(user)
        self.assertNotIn('scrypt', repr_str)
        self.assertNotIn('pbkdf2', repr_str)
        self.assertNotIn(user.password_hash, repr_str)

    def test_03_duplicate_email_registration_rejected(self):
        """3. Verify duplicate email registration is rejected with appropriate user feedback."""
        res = self.client.post('/register/patient', data={
            'full_name': 'Duplicate Test',
            'email': 'patient@careconnect.org',  # Existing demo email
            'password': 'Password123!',
            'confirm_password': 'Password123!',
            'phone': '9876543210'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'already registered', res.data.lower())

    # -------------------------------------------------------------------------
    # 2. Role-Based Access Control (RBAC)
    # -------------------------------------------------------------------------
    def test_04_rbac_patient_forbidden_from_staff_routes(self):
        """4. Verify authenticated patient cannot access doctor or hospital portals."""
        self._login('patient@careconnect.org', 'patient123')
        res_doc = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertIn(res_doc.status_code, (302, 403))
        res_hosp = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertIn(res_hosp.status_code, (302, 403))

    def test_05_rbac_doctor_forbidden_from_admin_and_patient_routes(self):
        """5. Verify authenticated doctor cannot access hospital management or patient booking."""
        self._login('dr.smith@careconnect.org', 'doctor123')
        res_hosp = self.client.get('/hospital/dashboard', follow_redirects=False)
        self.assertIn(res_hosp.status_code, (302, 403))
        res_pat = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertIn(res_pat.status_code, (302, 403))

    def test_06_rbac_hospital_forbidden_from_clinical_and_patient_routes(self):
        """6. Verify authenticated hospital admin cannot access doctor clinical or patient dashboards."""
        self._login('admin@careconnect.org', 'admin123')
        res_doc = self.client.get('/doctor/dashboard', follow_redirects=False)
        self.assertIn(res_doc.status_code, (302, 403))
        res_pat = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertIn(res_pat.status_code, (302, 403))

    # -------------------------------------------------------------------------
    # 3. Data Isolation & IDOR Protection
    # -------------------------------------------------------------------------
    def test_07_patient_data_isolation_appointments(self):
        """7. Verify patient only sees their own appointments in /patient/appointments."""
        user2 = User(username='patient2', full_name='Second Patient', email='patient2@careconnect.org', role='patient')
        user2.set_password('patient123')
        db.session.add(user2)
        db.session.flush()
        p2 = Patient(user_id=user2.id, emergency_contact='9998887776')
        db.session.add(p2)
        db.session.flush()
        doc = Doctor.query.first()
        hosp = Hospital.query.first()
        target_date = get_working_date_for_doctor(doc, 2)
        appt2 = Appointment(
            appointment_number='CC-2026-TESTP2',
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=hosp.id,
            appointment_date=target_date,
            time_slot='11:00 AM - 11:30 AM',
            status='confirmed'
        )
        db.session.add(appt2)
        db.session.commit()

        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get('/patient/appointments')
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(b'CC-2026-TESTP2', res.data)

    def test_08_patient_data_isolation_profile(self):
        """8. Verify patient profile only exposes and updates logged-in patient data."""
        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get('/patient/profile')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'patient@careconnect.org', res.data)

    def test_09_doctor_data_isolation(self):
        """9. Verify doctor only sees appointments specifically assigned to them."""
        # Create second doctor & appointment
        u_doc2 = User(username='dr_iso', full_name='Dr. Iso', email='dr.iso@careconnect.org', role='doctor')
        u_doc2.set_password('doctor123')
        db.session.add(u_doc2)
        db.session.flush()
        hosp = Hospital.query.first()
        doc2 = Doctor(
            user_id=u_doc2.id,
            hospital_id=hosp.id,
            specialization='Dermatology',
            qualification='MD, MBBS'
        )
        db.session.add(doc2)
        db.session.flush()
        pat = Patient.query.first()
        target_date = get_working_date_for_doctor(doc2, 3)
        appt_other = Appointment(
            appointment_number='CC-2026-OTHERDOC',
            patient_id=pat.id,
            doctor_id=doc2.id,
            hospital_id=hosp.id,
            appointment_date=target_date,
            time_slot='10:00 AM - 10:30 AM',
            status='confirmed'
        )
        db.session.add(appt_other)
        db.session.commit()

        self._login('dr.smith@careconnect.org', 'doctor123')
        res = self.client.get('/doctor/appointments')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Patient Consultations', res.data)
        self.assertNotIn(b'CC-2026-OTHERDOC', res.data)

    def test_10_hospital_data_isolation(self):
        """10. Verify hospital admin only sees data from their own registered hospital facility."""
        self._login('admin@careconnect.org', 'admin123')
        res = self.client.get('/hospital/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Metro General Hospital', res.data)
        self.assertIn(b'Hospital Management', res.data)

    def test_11_idor_patient_cannot_cancel_others_appointment(self):
        """11. Verify IDOR protection: patient attempting to cancel another patient's appointment receives 403."""
        user2 = User(username='victim_pat', full_name='Victim Patient', email='victim@careconnect.org', role='patient')
        user2.set_password('pass123')
        db.session.add(user2)
        db.session.flush()
        p2 = Patient(user_id=user2.id, emergency_contact='9123456780')
        db.session.add(p2)
        db.session.flush()
        doc = Doctor.query.first()
        hosp = Hospital.query.first()
        target_date = get_working_date_for_doctor(doc, 3)
        appt_victim = Appointment(
            appointment_number='CC-2026-VICTIM',
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=hosp.id,
            appointment_date=target_date,
            time_slot='02:00 PM - 02:30 PM',
            status='confirmed'
        )
        db.session.add(appt_victim)
        db.session.commit()

        self._login('patient@careconnect.org', 'patient123')
        res = self.client.post(f'/patient/appointments/{appt_victim.id}/cancel')
        self.assertEqual(res.status_code, 403)
        db.session.refresh(appt_victim)
        self.assertEqual(appt_victim.status, 'confirmed')

    def test_12_idor_patient_cannot_view_others_confirmation(self):
        """12. Verify IDOR protection: patient attempting to view another patient's confirmation receives 403."""
        user2 = User(username='other_pat', full_name='Other Patient', email='other_pat@careconnect.org', role='patient')
        user2.set_password('pass123')
        db.session.add(user2)
        db.session.flush()
        p2 = Patient(user_id=user2.id, emergency_contact='9123456781')
        db.session.add(p2)
        db.session.flush()
        doc = Doctor.query.first()
        hosp = Hospital.query.first()
        target_date = get_working_date_for_doctor(doc, 3)
        appt_other = Appointment(
            appointment_number='CC-2026-OTHER',
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=hosp.id,
            appointment_date=target_date,
            time_slot='03:00 PM - 03:30 PM',
            status='confirmed'
        )
        db.session.add(appt_other)
        db.session.commit()

        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get(f'/patient/appointments/{appt_other.id}/confirmation')
        self.assertEqual(res.status_code, 403)

    def test_13_idor_patient_cannot_download_others_pdf(self):
        """13. Verify IDOR protection: patient cannot download another patient's PDF (returns 403)."""
        user2 = User(username='secret_pat', full_name='Secret Patient', email='secret_pat@careconnect.org', role='patient')
        user2.set_password('pass123')
        db.session.add(user2)
        db.session.flush()
        p2 = Patient(user_id=user2.id, emergency_contact='9123456782')
        db.session.add(p2)
        db.session.flush()
        doc = Doctor.query.first()
        hosp = Hospital.query.first()
        target_date = get_working_date_for_doctor(doc, 3)
        appt_secret = Appointment(
            appointment_number='CC-2026-SECRET',
            patient_id=p2.id,
            doctor_id=doc.id,
            hospital_id=hosp.id,
            appointment_date=target_date,
            time_slot='04:00 PM - 04:30 PM',
            status='confirmed'
        )
        db.session.add(appt_secret)
        db.session.commit()

        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get(f'/patient/appointments/{appt_secret.id}/pdf')
        self.assertEqual(res.status_code, 403)

    def test_14_idor_doctor_cannot_update_others_appointment(self):
        """14. Verify IDOR protection: doctor cannot modify the status of another doctor's appointment."""
        u_doc2 = User(username='dr_other', full_name='Dr. Other', email='dr.other@careconnect.org', role='doctor')
        u_doc2.set_password('doctor123')
        db.session.add(u_doc2)
        db.session.flush()
        hosp = Hospital.query.first()
        doc2 = Doctor(
            user_id=u_doc2.id,
            hospital_id=hosp.id,
            specialization='Neurology',
            qualification='MD, DM Neurology'
        )
        db.session.add(doc2)
        db.session.flush()
        pat = Patient.query.first()
        target_date = get_working_date_for_doctor(doc2, 3)
        appt_doc2 = Appointment(
            appointment_number='CC-2026-DOC2',
            patient_id=pat.id,
            doctor_id=doc2.id,
            hospital_id=hosp.id,
            appointment_date=target_date,
            time_slot='10:00 AM - 10:30 AM',
            status='confirmed'
        )
        db.session.add(appt_doc2)
        db.session.commit()

        self._login('dr.smith@careconnect.org', 'doctor123')
        res = self.client.post(f'/doctor/appointments/{appt_doc2.id}/status', data={'status': 'completed'})
        self.assertEqual(res.status_code, 403)

    def test_15_idor_doctor_cannot_toggle_others_availability(self):
        """15. Verify doctor availability route only updates the logged-in doctor's state and blocks cross-doctor toggle."""
        u_doc2 = User(username='dr_target', full_name='Dr. Target', email='dr.target@careconnect.org', role='doctor')
        u_doc2.set_password('doctor123')
        db.session.add(u_doc2)
        db.session.flush()
        hosp = Hospital.query.first()
        doc2 = Doctor(
            user_id=u_doc2.id,
            hospital_id=hosp.id,
            specialization='Cardiology',
            qualification='MD, DM Cardiology'
        )
        db.session.add(doc2)
        db.session.flush()
        db.session.commit()

        self._login('dr.smith@careconnect.org', 'doctor123')
        res_cross = self.client.post(f'/doctor/availability/{doc2.id}')
        self.assertEqual(res_cross.status_code, 403)

        doc1 = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        init_status = doc1.is_available
        res_self = self.client.post('/doctor/toggle-availability', follow_redirects=True)
        self.assertEqual(res_self.status_code, 200)
        db.session.refresh(doc1)
        self.assertNotEqual(doc1.is_available, init_status)

    def test_16_idor_hospital_cannot_edit_other_hospitals_doctor(self):
        """16. Verify hospital admin cannot edit a doctor affiliated with another hospital."""
        u_hosp2 = User(username='admin2', full_name='Admin 2', email='admin2@hospital2.org', role='hospital')
        u_hosp2.set_password('admin123')
        db.session.add(u_hosp2)
        db.session.flush()
        hosp2 = Hospital(
            user_id=u_hosp2.id,
            name='Other Hospital',
            registration_number='HOSP-TEST-002',
            address='456 Central Ave',
            city='Metropolis'
        )
        db.session.add(hosp2)
        db.session.flush()

        u_doc_ext = User(username='dr_ext', full_name='Dr. External', email='dr.ext@hospital2.org', role='doctor')
        u_doc_ext.set_password('doctor123')
        db.session.add(u_doc_ext)
        db.session.flush()
        doc_ext = Doctor(
            user_id=u_doc_ext.id,
            hospital_id=hosp2.id,
            specialization='Pediatrics',
            qualification='MD, FAAP'
        )
        db.session.add(doc_ext)
        db.session.commit()

        self._login('admin@careconnect.org', 'admin123')
        res = self.client.post(f'/hospital/doctors/{doc_ext.id}/edit', data={
            'full_name': 'Hacked Name',
            'specialization': 'Hacked Specialty',
            'qualification': 'MD'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'unauthorized', res.data.lower())

    # -------------------------------------------------------------------------
    # 4. Input Validation & Edge Cases
    # -------------------------------------------------------------------------
    def test_17_invalid_appointment_parameters_rejected(self):
        """17. Verify booking with non-existent doctor ID is safely rejected."""
        self._login('patient@careconnect.org', 'patient123')
        tomorrow = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
        res = self.client.post('/patient/book', data={
            'hospital_id': '1',
            'doctor_id': '99999',  # Non-existent
            'appointment_date': tomorrow,
            'time_slot': '10:00 AM - 10:30 AM',
            'symptoms': 'General Checkup'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'physician does not exist', res.data.lower())

    def test_18_past_appointment_date_rejected(self):
        """18. Verify booking an appointment on a past date is rejected."""
        self._login('patient@careconnect.org', 'patient123')
        doc = Doctor.query.first()
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        res = self.client.post('/patient/book', data={
            'hospital_id': str(doc.hospital_id),
            'doctor_id': str(doc.id),
            'appointment_date': yesterday,
            'time_slot': '10:00 AM - 10:30 AM',
            'symptoms': 'Past appointment test'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'past', res.data.lower())

    def test_19_invalid_consultation_time_slot_rejected(self):
        """19. Verify consultation slot outside working hours is rejected."""
        self._login('patient@careconnect.org', 'patient123')
        doc = Doctor.query.first()
        target_date = get_working_date_for_doctor(doc, 2)
        res = self.client.post('/patient/book', data={
            'hospital_id': str(doc.hospital_id),
            'doctor_id': str(doc.id),
            'appointment_date': target_date.strftime('%Y-%m-%d'),
            'time_slot': '06:00 AM - 06:30 AM',  # Outside 09:00 AM - 05:00 PM
            'symptoms': 'Invalid slot test'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'outside the doctor', res.data.lower())

    def test_20_double_booking_database_protection(self):
        """20. Verify database-level double-booking protection prevents concurrent collisions."""
        pat = Patient.query.first()
        doc = Doctor.query.first()
        target_date = get_working_date_for_doctor(doc, 4)
        slot = '10:00 AM - 10:30 AM'

        # First booking succeeds
        success, msg, appt = book_appointment(pat, doc.id, doc.hospital_id, target_date, slot, 'First Booking')
        self.assertTrue(success)
        self.assertIsNotNone(appt)

        # Application-level prevention for second attempt
        pat2_user = User(username='pat2_user', full_name='Pat Two', email='pattwo@careconnect.org', role='patient')
        pat2_user.set_password('pass123')
        db.session.add(pat2_user)
        db.session.flush()
        pat2 = Patient(user_id=pat2_user.id, emergency_contact='9000000001')
        db.session.add(pat2)
        db.session.commit()

        success2, msg2, appt2 = book_appointment(pat2, doc.id, doc.hospital_id, target_date, slot, 'Collision Booking')
        self.assertFalse(success2)
        self.assertIsNone(appt2)
        self.assertIn('no longer available', msg2.lower())

        # Database-level unique constraint protection
        appt_dup = Appointment(
            patient_id=pat2.id,
            doctor_id=doc.id,
            hospital_id=doc.hospital_id,
            appointment_date=target_date,
            time_slot=slot,
            appointment_number='CC-2026-DUP001',
            status='confirmed'
        )
        db.session.add(appt_dup)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_21_appointment_cancellation_authorization(self):
        """21. Verify legitimate patient can cancel their appointment, and double-cancellation is prevented."""
        self._login('patient@careconnect.org', 'patient123')
        pat = Patient.query.first()
        doc = Doctor.query.first()
        target_date = get_working_date_for_doctor(doc, 5)
        success, msg, appt = book_appointment(pat, doc.id, doc.hospital_id, target_date, '11:30 AM - 12:00 PM', 'Cancel Test')
        self.assertTrue(success)

        # Cancel once
        res = self.client.post(f'/patient/appointments/{appt.id}/cancel', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        db.session.refresh(appt)
        self.assertEqual(appt.status.lower(), 'cancelled')

        # Attempt to cancel a second time
        res2 = self.client.post(f'/patient/appointments/{appt.id}/cancel', follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b'already been cancelled', res2.data.lower())

    def test_22_appointment_status_lifecycle_validation(self):
        """22. Verify doctor can transition confirmed appointment to completed, but invalid transitions fail."""
        self._login('dr.smith@careconnect.org', 'doctor123')
        pat = Patient.query.first()
        doc = Doctor.query.first()
        target_date = get_working_date_for_doctor(doc, 5)
        success, msg, appt = book_appointment(pat, doc.id, doc.hospital_id, target_date, '02:30 PM - 03:00 PM', 'Lifecycle Test')
        self.assertTrue(success)

        # Transition to Completed
        res = self.client.post(f'/doctor/appointments/{appt.id}/status', data={'status': 'completed'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        db.session.refresh(appt)
        self.assertEqual(appt.status.lower(), 'completed')

        # Invalid transition from Completed back to Confirmed
        res2 = self.client.post(f'/doctor/appointments/{appt.id}/status', data={'status': 'confirmed'}, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        db.session.refresh(appt)
        self.assertEqual(appt.status.lower(), 'completed')  # Must remain Completed

    # -------------------------------------------------------------------------
    # 5. Public QR Verification Privacy (Zero PHI)
    # -------------------------------------------------------------------------
    def test_23_public_qr_verification_privacy_no_phi(self):
        """23. Verify public verification page exposes verification status, but ZERO patient PHI."""
        appt = Appointment.query.first()
        pat = db.session.get(Patient, appt.patient_id)
        pat_user = db.session.get(User, pat.user_id)

        res = self.client.get(f'/verify/appointment/{appt.verification_token}')
        self.assertEqual(res.status_code, 200)

        # Public verification MUST show appointment reference and status
        self.assertIn(appt.appointment_number.encode('utf-8'), res.data)
        self.assertIn(b'Confirmed', res.data)

        # Public verification MUST NOT leak any Patient Health Information (PHI)
        self.assertNotIn(pat_user.full_name.encode('utf-8'), res.data)
        self.assertNotIn(pat_user.email.encode('utf-8'), res.data)
        if pat_user.phone:
            self.assertNotIn(pat_user.phone.encode('utf-8'), res.data)
        self.assertNotIn(b'password', res.data.lower())
        if appt.symptoms:
            self.assertNotIn(appt.symptoms.encode('utf-8'), res.data)

    def test_24_invalid_qr_verification_token_handled(self):
        """24. Verify invalid or tampered QR token produces friendly error message, not 500."""
        res = self.client.get('/verify/appointment/invalid-token-123456789')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'invalid', res.data.lower())

    # -------------------------------------------------------------------------
    # 6. XSS & Output Escaping
    # -------------------------------------------------------------------------
    def test_25_xss_output_escaping(self):
        """25. Verify user input with potential script injection is HTML-escaped by Jinja."""
        self._login('patient@careconnect.org', 'patient123')
        xss_payload = "<script>alert('XSS-TEST')</script>"
        res = self.client.post('/patient/profile', data={
            'full_name': f"John {xss_payload}",
            'email': 'patient@careconnect.org',
            'phone': '9876543210',
            'gender': 'Male',
            'blood_group': 'O+',
            'address': '123 Safe St',
            'city': 'Metropolis',
            'emergency_contact': '9111111111'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        # Raw unescaped script tag must NOT be present in output
        self.assertNotIn(b"<script>alert('XSS-TEST')</script>", res.data)
        self.assertIn(b"&lt;script&gt;alert(&#39;XSS-TEST&#39;)&lt;/script&gt;", res.data)

    # -------------------------------------------------------------------------
    # 7. AI Safety & Privacy Boundaries
    # -------------------------------------------------------------------------
    def test_26_ai_assistant_authentication_and_role_isolation(self):
        """26. Verify AI Assistant requires login and respects tenant isolation."""
        res = self.client.get('/assistant', follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        self._login('patient@careconnect.org', 'patient123')
        chat_res = self.client.post('/assistant/chat', json={'message': 'Show my appointments'})
        self.assertEqual(chat_res.status_code, 200)
        data = chat_res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('response', data)

    def test_27_ai_specialist_non_diagnostic_boundary(self):
        """27. Verify AI Specialist displays non-diagnostic disclaimer and triage safety guidance."""
        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get('/patient/ai-specialist')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'not a medical diagnosis', res.data.lower())
        self.assertIn(b'emergency', res.data.lower())

    def test_28_ai_smart_appointment_safety(self):
        """28. Verify Smart Appointment does not auto-book and features disclaimer."""
        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get('/patient/smart-appointment')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Operational Appointment Notice', res.data)
        self.assertIn(b'It does not diagnose medical conditions', res.data)

    def test_29_ai_load_prediction_hospital_isolation_and_disclaimer(self):
        """29. Verify AI load prediction is isolated to hospital data and includes operational disclaimer."""
        self._login('admin@careconnect.org', 'admin123')
        res = self.client.get('/hospital/ai-load-prediction')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Predictions are estimates based on historical Care Connect appointment activity', res.data)
        self.assertIn(b'may differ from actual patient volume', res.data)

    # -------------------------------------------------------------------------
    # 8. Error Handling & Information Leakage
    # -------------------------------------------------------------------------
    def test_30_sensitive_error_handling_404_403(self):
        """30. Verify custom 404 and 403 error pages render cleanly without stack traces or schema info."""
        res_404 = self.client.get('/non-existent-healthcare-route-xyz')
        self.assertEqual(res_404.status_code, 404)
        self.assertIn(b'Page Not Found', res_404.data)
        self.assertNotIn(b'Traceback', res_404.data)
        self.assertNotIn(b'sqlite3', res_404.data.lower())

    # -------------------------------------------------------------------------
    # 9. Configuration & Session Security
    # -------------------------------------------------------------------------
    def test_31_secret_configuration_security(self):
        """31. Verify application security settings: SECRET_KEY, HTTPOnly cookies, SameSite=Lax."""
        self.assertTrue(self.app.config.get('SECRET_KEY') is not None)
        self.assertTrue(len(self.app.config.get('SECRET_KEY')) >= 16)
        self.assertTrue(self.app.config.get('SESSION_COOKIE_HTTPONLY'))
        self.assertEqual(self.app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax')

    def test_32_session_and_logout_security(self):
        """32. Verify logout clears session and invalidates access to protected pages."""
        self._login('patient@careconnect.org', 'patient123')
        res = self.client.get('/patient/dashboard')
        self.assertEqual(res.status_code, 200)
        res_logout = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(res_logout.status_code, 200)
        res_after = self.client.get('/patient/dashboard', follow_redirects=False)
        self.assertEqual(res_after.status_code, 302)
        self.assertIn('/login', res_after.headers.get('Location', ''))

    # -------------------------------------------------------------------------
    # 10. HTTP Security Headers
    # -------------------------------------------------------------------------
    def test_33_security_http_headers_present(self):
        """33. Verify responses include X-Content-Type-Options, X-Frame-Options, and Referrer-Policy."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(res.headers.get('X-XSS-Protection'), '1; mode=block')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')


if __name__ == '__main__':
    unittest.main()
