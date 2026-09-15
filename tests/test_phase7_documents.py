import io
import os
import unittest
from datetime import date, timedelta

from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from utils.pdf_generator import generate_appointment_pdf
from utils.qr_generator import generate_appointment_qr_code, get_verification_url
from services.booking_service import book_appointment


class CareConnectPhase7DocumentsTestCase(unittest.TestCase):
    """
    Test suite for Phase 7:
    - ReportLab Appointment Confirmation PDF generation
    - Embedded verification QR code generation
    - Patient PDF download endpoint with strict ownership enforcement (HTTP 403)
    - Public digital QR verification endpoint (/verify/appointment/<token>)
    - Patient PHI privacy protection
    """

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Seed minimal test fixtures
        self._seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def _seed_test_data(self):
        # 1. Hospital Admin & Facility
        admin = User(
            username='hosp_admin',
            email='admin@generalhealth.org',
            full_name='General Health Admin',
            role=User.ROLE_HOSPITAL
        )
        admin.set_password('pass123')
        db.session.add(admin)
        db.session.flush()

        self.hospital = Hospital(
            user_id=admin.id,
            name='St. Jude Community Hospital',
            registration_number='HOSP-P7-001',
            hospital_type='Community Hospital',
            address='100 Healthcare Blvd',
            city='Chicago',
            contact_email='contact@stjude.org',
            contact_phone='+1 (312) 555-0100'
        )
        db.session.add(self.hospital)
        db.session.flush()

        # 2. Doctor
        doc_user = User(
            username='dr_watson',
            email='watson@stjude.org',
            full_name='John Watson',
            role=User.ROLE_DOCTOR
        )
        doc_user.set_password('pass123')
        db.session.add(doc_user)
        db.session.flush()

        self.doctor = Doctor(
            user_id=doc_user.id,
            hospital_id=self.hospital.id,
            specialization='Pulmonology',
            qualification='MD, FCCP',
            consultation_fee=150.0,
            is_available=True,
            available_days='Monday, Tuesday, Wednesday, Thursday, Friday',
            available_time='09:00 AM - 05:00 PM',
            room_number='Suite 402'
        )
        db.session.add(self.doctor)
        db.session.flush()

        # 3. Patient A (Primary)
        pat_user_a = User(
            username='patient_a',
            email='patient_a@example.com',
            full_name='Arthur Dent',
            phone='+1 (312) 555-9876',
            role=User.ROLE_PATIENT
        )
        pat_user_a.set_password('patient123')
        db.session.add(pat_user_a)
        db.session.flush()

        self.patient_a = Patient(
            user_id=pat_user_a.id,
            date_of_birth=date(1982, 5, 15),
            gender='Male',
            blood_group='O+',
            address='42 Galaxy Way',
            city='Chicago',
            emergency_contact='+1 (312) 555-4321'
        )
        db.session.add(self.patient_a)
        db.session.flush()

        # 4. Patient B (Secondary for cross-access tests)
        pat_user_b = User(
            username='patient_b',
            email='patient_b@example.com',
            full_name='Ford Prefect',
            phone='+1 (312) 555-7777',
            role=User.ROLE_PATIENT
        )
        pat_user_b.set_password('patient123')
        db.session.add(pat_user_b)
        db.session.flush()

        self.patient_b = Patient(
            user_id=pat_user_b.id,
            date_of_birth=date(1985, 11, 23),
            gender='Male',
            blood_group='AB-',
            address='15 Towel Street',
            city='Chicago'
        )
        db.session.add(self.patient_b)
        db.session.flush()

        # 5. Confirmed Appointment for Patient A
        self.appointment_a = Appointment(
            patient_id=self.patient_a.id,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=date.today() + timedelta(days=2),
            time_slot='10:00 AM - 10:30 AM',
            appointment_number='CC-2026-700001',
            verification_token='TOKEN-TEST-PATIENT-A-CONFIRMED',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Persistent dry cough and mild respiratory discomfort.'
        )
        db.session.add(self.appointment_a)
        db.session.commit()

    def test_generate_pdf_structure_and_signature(self):
        """Verifies generate_appointment_pdf creates a valid, non-empty ReportLab PDF with PDF magic header."""
        pdf_bytes = generate_appointment_pdf(self.appointment_a)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_generate_pdf_embedded_content(self):
        """Verifies uncompressed PDF stream contains key hospital, appointment, and doctor data strings."""
        pdf_bytes = generate_appointment_pdf(self.appointment_a)
        # Because pageCompression=0 is configured, strings are directly searchable in stream
        self.assertIn(b'Care Connect', pdf_bytes)
        self.assertIn(b'CC-2026-700001', pdf_bytes)
        self.assertIn(b'St. Jude Community Hospital', pdf_bytes)
        self.assertIn(b'Pulmonology', pdf_bytes)
        self.assertIn(b'Arthur Dent', pdf_bytes)
        self.assertIn(b'Arrival Instructions', pdf_bytes)

    def test_qr_code_file_creation_on_disk(self):
        """Verifies QR code generator creates a valid image file on disk in QR_CODES_DIR."""
        qr_filename = generate_appointment_qr_code(self.appointment_a)
        self.assertTrue(qr_filename.endswith('.png'))
        
        qr_dir = self.app.config['QR_CODES_DIR']
        filepath = os.path.join(qr_dir, qr_filename)
        self.assertTrue(os.path.exists(filepath))
        self.assertGreater(os.path.getsize(filepath), 100)

    def test_qr_code_verification_url_format_and_privacy(self):
        """Verifies QR code encodes public verification URL without embedding sensitive patient PHI."""
        url = get_verification_url(self.appointment_a, base_url='https://careconnect.org')
        self.assertEqual(url, 'https://careconnect.org/verify/appointment/TOKEN-TEST-PATIENT-A-CONFIRMED')
        # Ensure no sensitive PHI in QR payload
        self.assertNotIn('Arthur', url)
        self.assertNotIn('cough', url)
        self.assertNotIn('312-555-9876', url)

    def test_download_pdf_authorized_patient_success(self):
        """Verifies authorized patient can download their own appointment confirmation PDF with 200 status."""
        self.client.post('/login', data={'identifier': 'patient_a@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.get(f'/patient/appointments/{self.appointment_a.id}/pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/pdf')
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))
        self.assertIn('CC-2026-700001', response.headers.get('Content-Disposition', ''))
        self.assertTrue(response.data.startswith(b'%PDF-'))

    def test_download_pdf_unauthorized_other_patient_forbidden(self):
        """Verifies Patient B receives HTTP 403 Forbidden when attempting to download Patient A's PDF."""
        self.client.post('/login', data={'identifier': 'patient_b@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.get(f'/patient/appointments/{self.appointment_a.id}/pdf')
        self.assertEqual(response.status_code, 403)

    def test_download_pdf_unauthenticated_redirects_login(self):
        """Verifies unauthenticated request to download PDF redirects to login page."""
        response = self.client.get(f'/patient/appointments/{self.appointment_a.id}/pdf')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    def test_download_pdf_nonexistent_appointment_returns_404(self):
        """Verifies requesting PDF for nonexistent appointment ID returns HTTP 404."""
        self.client.post('/login', data={'identifier': 'patient_a@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.get('/patient/appointments/99999/pdf')
        self.assertEqual(response.status_code, 404)

    def test_public_verification_valid_appointment(self):
        """Verifies public verification endpoint verifies active confirmed appointment without login."""
        response = self.client.get(f'/verify/appointment/{self.appointment_a.verification_token}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Appointment Verified', html)
        self.assertIn('CC-2026-700001', html)
        self.assertIn('St. Jude Community Hospital', html)
        self.assertIn('Pulmonology', html)
        self.assertIn('Confirmed', html)

    def test_public_verification_cancelled_appointment(self):
        """Verifies public verification displays clear cancelled status when appointment is cancelled."""
        self.appointment_a.status = Appointment.STATUS_CANCELLED
        db.session.commit()

        response = self.client.get(f'/verify/appointment/{self.appointment_a.verification_token}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Appointment Cancelled', html)
        self.assertIn('Cancelled', html)

    def test_public_verification_invalid_token(self):
        """Verifies public verification handles invalid or unrecognized tokens gracefully."""
        response = self.client.get('/verify/appointment/COMPLETELY-UNKNOWN-TOKEN-999')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Invalid Appointment', html)
        self.assertIn('COMPLETELY-UNKNOWN-TOKEN-999', html)

    def test_public_verification_zero_phi_exposed(self):
        """Verifies public verification page does NOT expose patient name, phone, address, or symptoms."""
        response = self.client.get(f'/verify/appointment/{self.appointment_a.verification_token}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        
        # Zero sensitive PHI should be in the public HTML
        self.assertNotIn('Arthur Dent', html)
        self.assertNotIn('42 Galaxy Way', html)
        self.assertNotIn('312-555-9876', html)
        self.assertNotIn('Persistent dry cough', html)

    def test_booking_service_generates_token_and_qr_code(self):
        """Verifies booking service creates verification token and QR code automatically upon new booking."""
        next_week = date.today() + timedelta(days=3)
        # Choose a day that doctor works
        while next_week.strftime('%A') in ['Saturday', 'Sunday']:
            next_week += timedelta(days=1)

        success, message, appointment = book_appointment(
            patient=self.patient_a,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=next_week,
            time_slot='02:00 PM - 02:30 PM',
            symptoms='Follow-up asthma review'
        )
        self.assertTrue(success, f"Booking failed: {message}")
        self.assertIsNotNone(appointment)
        self.assertIsNotNone(appointment.verification_token)
        self.assertIsNotNone(appointment.qr_code_file)
        self.assertTrue(appointment.qr_code_file.endswith('.png'))

        qr_path = os.path.join(self.app.config['QR_CODES_DIR'], appointment.qr_code_file)
        self.assertTrue(os.path.exists(qr_path))

    def test_booking_confirmation_template_contains_pdf_download_and_qr(self):
        """Verifies patient booking confirmation page displays Download PDF button and QR code."""
        self.client.post('/login', data={'identifier': 'patient_a@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.get(f'/patient/appointments/{self.appointment_a.id}/confirmation')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Download PDF', html)
        self.assertIn(f'/patient/appointments/{self.appointment_a.id}/pdf', html)
        self.assertIn('Digital Verification Pass', html)


if __name__ == '__main__':
    unittest.main()
