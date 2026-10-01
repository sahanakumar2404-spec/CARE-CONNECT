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


def get_next_working_date(doctor, start_date=None):
    curr = (start_date or date.today()) + timedelta(days=1)
    days_str = (doctor.available_days or "").lower()
    for _ in range(14):
        day_name = curr.strftime('%A').lower()
        if day_name in days_str:
            return curr
        if ("monday - friday" in days_str or "mon - fri" in days_str) and curr.weekday() < 5:
            return curr
        if ("monday - saturday" in days_str or "mon - sat" in days_str) and curr.weekday() < 6:
            return curr
        if "daily" in days_str or "all days" in days_str:
            return curr
        curr += timedelta(days=1)
    return (start_date or date.today()) + timedelta(days=1)



class CareConnectPhase13UIUXTestCase(unittest.TestCase):
    """
    Comprehensive test suite for Phase 13: UI/UX improvements, responsive design,
    accessibility, light/dark theme toggle, visual progression, and full regression.
    """

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Seed test fixtures from demo seed data
        self.hospital = Hospital.query.first()
        self.doctor = Doctor.query.first()
        self.patient = Patient.query.first()
        self.patient_user = self.patient.user
        self.doctor_user = self.doctor.user
        self.hospital_user = self.hospital.user
        self.appointment = Appointment.query.first()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def _login(self, email=None, password=None):
        if email is None:
            email = self.patient_user.email
        if password is None:
            if 'admin' in email:
                password = 'admin123'
            elif 'dr.' in email or 'dr' in email:
                password = 'doctor123'
            else:
                password = 'patient123'
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. Base Template & Design System Elements
    # -------------------------------------------------------------------------
    def test_theme_toggle_and_anti_flash_script_present(self):
        """Test that base.html includes the theme toggle button and anti-flash script."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Anti-flash immediate script checking localStorage
        self.assertIn("localStorage.getItem('careconnect_theme')", html)
        self.assertIn("document.documentElement.setAttribute('data-bs-theme'", html)

        # Theme toggle button in navbar
        self.assertIn('id="themeToggleBtn"', html)
        self.assertIn('btn-theme-toggle', html)

        # Meta viewport for responsive design
        self.assertIn('name="viewport"', html)
        self.assertIn('content="width=device-width, initial-scale=1.0"', html)

    def test_skip_link_and_main_content_accessibility(self):
        """Test accessibility skip-to-content link and main landmark target."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('href="#main-content"', html)
        self.assertIn('class="skip-link"', html)
        self.assertIn('id="main-content"', html)

    # -------------------------------------------------------------------------
    # 2. Role-Specific Navigation Links
    # -------------------------------------------------------------------------
    def test_role_navigation_patient(self):
        """Verify patient navigation includes all patient-centric pages and AI tools."""
        self._login(self.patient_user.email)
        response = self.client.get('/patient/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('/patient/hospitals', html)
        self.assertIn('/patient/smart-appointment', html)
        self.assertIn('/patient/ai-specialist', html)
        self.assertIn('/patient/appointments', html)
        self.assertIn('/assistant', html)

    def test_role_navigation_doctor(self):
        """Verify doctor navigation includes doctor dashboard, availability, and appointments."""
        self._login(self.doctor_user.email)
        response = self.client.get('/doctor/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('/doctor/availability', html)
        self.assertIn('/doctor/appointments', html)
        self.assertIn('/doctor/patients', html)
        self.assertIn('/assistant', html)

    def test_role_navigation_hospital(self):
        """Verify hospital admin navigation includes hospital management and AI prediction."""
        self._login(self.hospital_user.email)
        response = self.client.get('/hospital/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('/hospital/doctors', html)
        self.assertIn('/hospital/appointments', html)
        self.assertIn('/hospital/ai-load-prediction', html)
        self.assertIn('/assistant', html)

    # -------------------------------------------------------------------------
    # 3. Accessible Status Badges (Icons + Text)
    # -------------------------------------------------------------------------
    def test_patient_appointment_table_status_badges_have_icons(self):
        """Verify appointment status badges do NOT rely solely on color (pair icons + text)."""
        self._login(self.patient_user.email)
        response = self.client.get('/patient/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Confirmed badge should pair icon with text
        self.assertIn('badge-status-confirmed', html)
        self.assertIn('bi-check-circle-fill', html)
        self.assertIn('confirmed', html.lower())

    def test_doctor_appointment_table_status_badges_have_icons(self):
        """Verify doctor appointment queue uses accessible badges with icons."""
        # Set date to today so it displays in doctor's today queue
        self.appointment.appointment_date = date.today()
        db.session.commit()

        self._login(self.doctor_user.email)
        response = self.client.get('/doctor/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('badge-status-confirmed', html)
        self.assertIn('bi-check-circle-fill', html)

    def test_hospital_appointment_table_status_badges_have_icons(self):
        """Verify hospital appointment queue uses accessible badges with icons."""
        self.appointment.appointment_date = date.today()
        db.session.commit()

        self._login(self.hospital_user.email)
        response = self.client.get('/hospital/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('badge-status-confirmed', html)
        self.assertIn('bi-check-circle-fill', html)

    def test_qr_verification_status_badge_has_icon(self):
        """Verify the public appointment verification page renders accessible status badge."""
        response = self.client.get(f'/verify/appointment/{self.appointment.verification_token}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('badge-status-confirmed', html)
        self.assertIn('bi-check-circle-fill', html)
        self.assertIn('Confirmed', html)

    # -------------------------------------------------------------------------
    # 4. Booking Stepper Progression & Legend
    # -------------------------------------------------------------------------
    def test_booking_page_renders_progression_stepper_and_legend(self):
        """Verify the booking page renders 8-step progression stepper and slot legend."""
        self._login()
        response = self.client.get(f'/patient/book?hospital_id={self.hospital.id}&doctor_id={self.doctor.id}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # 8 steps
        self.assertIn('booking-stepper', html)
        self.assertIn('Hospital', html)
        self.assertIn('Specialization', html)
        self.assertIn('Doctor', html)
        self.assertIn('Date', html)
        self.assertIn('Available Slot', html)
        self.assertIn('Patient Details', html)
        self.assertIn('Review', html)
        self.assertIn('Confirm', html)

        # Slot legend
        self.assertIn('Slot Legend:', html)
        self.assertIn('Available', html)
        self.assertIn('Selected', html)
        self.assertIn('Booked', html)

    # -------------------------------------------------------------------------
    # 5. Empty State Cards
    # -------------------------------------------------------------------------
    def test_empty_state_rendered_when_no_appointments(self):
        """Verify empty state component with icon and helper text appears when queue is empty."""
        Appointment.query.delete()
        db.session.commit()

        self._login()
        response = self.client.get('/patient/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('empty-state-card', html)
        self.assertIn('empty-state-icon', html)

    # -------------------------------------------------------------------------
    # 6. AI Disclaimers & Unified Styling
    # -------------------------------------------------------------------------
    def test_ai_specialist_non_diagnostic_disclaimer(self):
        """Verify AI Specialist page features non-diagnostic disclaimer and accessible controls."""
        self._login()
        response = self.client.get('/patient/ai-specialist')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('This recommendation is for appointment guidance only and is not a medical diagnosis.', html)
        self.assertIn('id="concern"', html)
        self.assertIn('for="concern"', html)

    def test_smart_appointment_non_diagnostic_disclaimer(self):
        """Verify Smart Appointment recommendation page features operational disclaimer."""
        self._login()
        response = self.client.get('/patient/smart-appointment')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('Operational Appointment Notice', html)
        self.assertIn('It does not diagnose medical conditions', html)

    def test_assistant_non_diagnostic_disclaimer(self):
        """Verify AI Assistant page features prominent operational notice."""
        self._login()
        response = self.client.get('/assistant')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('Operational &amp; Navigation Notice', html)
        self.assertIn('does not diagnose medical conditions', html)

    # -------------------------------------------------------------------------
    # 7. Form Accessibility & Controls
    # -------------------------------------------------------------------------
    def test_login_and_register_form_labels_match_inputs(self):
        """Verify login and register inputs have associated labels for accessibility."""
        login_resp = self.client.get('/login')
        login_html = login_resp.get_data(as_text=True)
        self.assertIn('for="identifier"', login_html)
        self.assertIn('id="identifier"', login_html)
        self.assertIn('for="password"', login_html)
        self.assertIn('id="password"', login_html)

        reg_resp = self.client.get('/register/patient')
        reg_html = reg_resp.get_data(as_text=True)
        self.assertIn('for="email"', reg_html)
        self.assertIn('id="email"', reg_html)

    # -------------------------------------------------------------------------
    # 8. Regression Verification Across Phases
    # -------------------------------------------------------------------------
    def test_regression_patient_booking_end_to_end(self):
        """Verify end-to-end appointment booking still works without regressions."""
        valid_date = get_next_working_date(self.doctor)
        self._login()
        post_data = {
            'hospital_id': self.hospital.id,
            'doctor_id': self.doctor.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '09:00 AM - 09:30 AM',
            'symptoms': 'Routine annual cardiology evaluation'
        }
        resp = self.client.post('/patient/book', data=post_data, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Appointment Confirmed!', html)

    def test_regression_pdf_download_preserved(self):
        """Verify PDF generation endpoint returns PDF headers correctly."""
        self._login()
        pdf_resp = self.client.get(f'/patient/appointments/{self.appointment.id}/pdf')
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp.content_type, 'application/pdf')
        self.assertTrue(pdf_resp.data.startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
