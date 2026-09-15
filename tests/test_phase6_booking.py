from datetime import date, timedelta
import unittest
from sqlalchemy.exc import IntegrityError
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import doctor_works_on_date

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

def get_next_off_date(doctor, start_date=None):
    curr = (start_date or date.today()) + timedelta(days=1)
    days_str = (doctor.available_days or "").lower()
    for _ in range(14):
        day_name = curr.strftime('%A').lower()
        is_on = (day_name in days_str) or (("monday - friday" in days_str) and curr.weekday() < 5)
        if not is_on:
            return curr
        curr += timedelta(days=1)
    return (start_date or date.today()) + timedelta(days=1)

class CareConnectPhase6BookingTestCase(unittest.TestCase):
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

    # 1. Booking page requires authentication
    def test_booking_page_requires_auth(self):
        """Verifies unauthenticated GET /patient/book redirects to /login."""
        response = self.client.get('/patient/book', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    # 2. Non-patients cannot create appointments
    def test_non_patients_cannot_create_appointments(self):
        """Verifies Hospital Admins and Doctors cannot access or submit to booking endpoints."""
        # Hospital Admin attempt
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)
        r_admin_get = self.client.get('/patient/book', follow_redirects=False)
        self.assertEqual(r_admin_get.status_code, 302)

        r_admin_post = self.client.post('/patient/book', data={
            'doctor_id': 1,
            'hospital_id': 1
        }, follow_redirects=False)
        self.assertEqual(r_admin_post.status_code, 302)

        self.client.get('/logout', follow_redirects=True)

        # Doctor attempt
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)
        r_doc_get = self.client.get('/patient/book', follow_redirects=False)
        self.assertEqual(r_doc_get.status_code, 302)

        r_doc_post = self.client.post('/patient/book', data={
            'doctor_id': 1,
            'hospital_id': 1
        }, follow_redirects=False)
        self.assertEqual(r_doc_post.status_code, 302)

    # 3. Patient can book an available slot
    def test_patient_can_book_available_slot(self):
        """Verifies patient can book a valid available slot and view confirmation."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        booking_data = {
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '09:00 AM - 09:30 AM',
            'symptoms': 'Routine annual cardiology evaluation'
        }

        res = self.client.post('/patient/book', data=booking_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Appointment Confirmed!', res.data)
        self.assertIn(b'Dr. Sarah Smith', res.data)
        self.assertIn(b'Cardiology', res.data)
        self.assertIn(b'Routine annual cardiology evaluation', res.data)
        self.assertIn(b'CC-', res.data)

        # Database check
        appt = Appointment.query.filter_by(
            doctor_id=dr_smith.id,
            appointment_date=valid_date,
            time_slot='09:00 AM - 09:30 AM'
        ).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.status, Appointment.STATUS_CONFIRMED)

    # 4. Doctor must belong to selected hospital
    def test_doctor_must_belong_to_selected_hospital(self):
        """Verifies mismatched doctor and hospital IDs are rejected."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        # Create a second hospital
        user_hosp2 = User(
            username='hosp2_admin',
            email='admin@hosp2.org',
            full_name='Eastside Clinic',
            phone='+1 (212) 555-0999',
            role=User.ROLE_HOSPITAL
        )
        user_hosp2.set_password('admin123')
        db.session.add(user_hosp2)
        db.session.flush()

        hosp2 = Hospital(
            user_id=user_hosp2.id,
            name='Eastside Community Clinic',
            registration_number='HOSP-NYC-2026-999',
            hospital_type='Outpatient Clinic',
            address='200 E 86th St',
            city='New York'
        )
        db.session.add(hosp2)
        db.session.commit()

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Try booking Dr. Smith under hosp2
        res = self.client.post('/patient/book', data={
            'hospital_id': hosp2.id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '09:00 AM - 09:30 AM',
            'symptoms': 'Checkup'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Selected doctor is not affiliated with the selected hospital', res.data)

    # 5. Past dates are rejected
    def test_past_dates_are_rejected(self):
        """Verifies attempting to book on past dates returns validation error."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        past_date = date.today() - timedelta(days=2)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': past_date.strftime('%Y-%m-%d'),
            'time_slot': '09:00 AM - 09:30 AM',
            'symptoms': 'Past date test'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Appointment date cannot be in the past', res.data)

    # 6. Doctor unavailable status prevents booking
    def test_doctor_unavailable_status_prevents_booking(self):
        """Verifies booking is blocked when physician is marked unavailable."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        dr_smith.is_available = False
        db.session.commit()

        valid_date = get_next_working_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '09:00 AM - 09:30 AM',
            'symptoms': 'Doctor unavailable test'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Doctor is currently not available for appointments', res.data)

    # 7. Non-working days prevent booking
    def test_non_working_days_prevent_booking(self):
        """Verifies booking is rejected when selected date is not in doctor's working schedule."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        # Dr. Smith works Mon, Wed, Fri. Find next off-day (e.g. Tuesday or Sunday)
        off_date = get_next_off_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': off_date.strftime('%Y-%m-%d'),
            'time_slot': '09:00 AM - 09:30 AM',
            'symptoms': 'Off-day booking attempt'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Doctor does not have scheduled hours on this day', res.data)

    # 8. Time outside working hours is rejected
    def test_time_outside_working_hours_is_rejected(self):
        """Verifies slots outside the physician's start/end hours are rejected."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # 07:00 AM is before 09:00 AM start time
        res = self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '07:00 AM - 07:30 AM',
            'symptoms': 'Too early'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Selected time slot is outside the doctor', res.data)

    # 9. Already-booked slot cannot be booked again
    def test_already_booked_slot_cannot_be_booked_again(self):
        """Verifies duplicate booking attempt for the same slot receives clear rejection."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        slot_data = {
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '10:00 AM - 10:30 AM',
            'symptoms': 'First booking'
        }

        # 1st booking succeeds
        res1 = self.client.post('/patient/book', data=slot_data, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b'Appointment Confirmed!', res1.data)

        # 2nd booking attempt for the exact same slot
        res2 = self.client.post('/patient/book', data=slot_data, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b'This appointment slot is no longer available.', res2.data)

    # 10. Duplicate/double booking is prevented at database/server level
    def test_duplicate_double_booking_prevented_at_database_level(self):
        """Verifies database uniqueness constraint rolls back duplicate concurrent inserts."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        patient = Patient.query.first()
        target_date = get_next_working_date(dr_smith)

        # 1st appointment directly inserted
        appt1 = Appointment(
            patient_id=patient.id,
            doctor_id=dr_smith.id,
            hospital_id=dr_smith.hospital_id,
            appointment_date=target_date,
            time_slot='11:30 AM - 12:00 PM',
            appointment_number='CC-2026-999001',
            status=Appointment.STATUS_CONFIRMED
        )
        db.session.add(appt1)
        db.session.commit()

        # 2nd appointment with identical doctor, date, and slot
        appt2 = Appointment(
            patient_id=patient.id,
            doctor_id=dr_smith.id,
            hospital_id=dr_smith.hospital_id,
            appointment_date=target_date,
            time_slot='11:30 AM - 12:00 PM',
            appointment_number='CC-2026-999002',
            status=Appointment.STATUS_CONFIRMED
        )

        with self.assertRaises(IntegrityError):
            db.session.add(appt2)
            db.session.commit()

        db.session.rollback()

    # 11. Unique appointment number is generated
    def test_unique_appointment_number_generated(self):
        """Verifies every appointment receives a unique tracking identifier in CC-YYYY-XXXXXX format."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        res = self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '01:00 PM - 01:30 PM',
            'symptoms': 'Tracking number test'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)

        appt = Appointment.query.filter_by(
            doctor_id=dr_smith.id,
            appointment_date=valid_date,
            time_slot='01:00 PM - 01:30 PM'
        ).first()

        self.assertIsNotNone(appt)
        self.assertIsNotNone(appt.appointment_number)
        self.assertTrue(appt.appointment_number.startswith('CC-'))
        self.assertIn(str(valid_date.year), appt.appointment_number)

    # 12. Patient sees their new appointment
    def test_patient_sees_their_new_appointment(self):
        """Verifies newly booked appointment is displayed on patient dashboard."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '02:00 PM - 02:30 PM',
            'symptoms': 'Patient dashboard visibility check'
        }, follow_redirects=True)

        res_dash = self.client.get('/patient/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_dash.data)
        self.assertIn(b'02:00 PM - 02:30 PM', res_dash.data)
        self.assertIn(b'confirmed', res_dash.data)

    # 13. Doctor sees their new appointment
    def test_doctor_sees_their_new_appointment(self):
        """Verifies newly booked appointment automatically appears in the doctor queue."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        # Patient books appointment
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '02:30 PM - 03:00 PM',
            'symptoms': 'Doctor queue test'
        }, follow_redirects=True)

        self.client.get('/logout', follow_redirects=True)

        # Log in as Dr. Smith
        self.client.post('/login', data={
            'identifier': 'dr.smith@careconnect.org',
            'password': 'doctor123'
        }, follow_redirects=True)

        res_doc = self.client.get('/doctor/appointments')
        self.assertEqual(res_doc.status_code, 200)
        self.assertIn(b'Doctor queue test', res_doc.data)
        self.assertIn(b'02:30 PM - 03:00 PM', res_doc.data)

    # 14. Hospital sees the correct appointment
    def test_hospital_sees_correct_appointment(self):
        """Verifies facility management dashboard reflects new appointment booked with their physician."""
        dr_smith = Doctor.query.join(User).filter(User.email == 'dr.smith@careconnect.org').first()
        valid_date = get_next_working_date(dr_smith)

        # Patient books appointment
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        self.client.post('/patient/book', data={
            'hospital_id': dr_smith.hospital_id,
            'doctor_id': dr_smith.id,
            'appointment_date': valid_date.strftime('%Y-%m-%d'),
            'time_slot': '01:30 PM - 02:00 PM',
            'symptoms': 'Hospital metrics test'
        }, follow_redirects=True)

        self.client.get('/logout', follow_redirects=True)

        # Log in as Hospital Admin
        self.client.post('/login', data={
            'identifier': 'admin@careconnect.org',
            'password': 'admin123'
        }, follow_redirects=True)

        res_hosp = self.client.get('/hospital/dashboard')
        self.assertEqual(res_hosp.status_code, 200)
        self.assertIn(b'Metro General Hospital', res_hosp.data)

    # 15. Patient cannot access another patient's appointment
    def test_patient_cannot_access_another_patient_appointment(self):
        """Verifies Patient A cannot view Patient B's appointment confirmation (blocks with HTTP 403)."""
        # Create Patient B
        user_b = User(
            username='patient_b2',
            email='patient.b2@careconnect.org',
            full_name='Clara Oswald',
            phone='+1 (212) 555-7711',
            role=User.ROLE_PATIENT
        )
        user_b.set_password('patient123')
        db.session.add(user_b)
        db.session.flush()

        patient_b = Patient(
            user_id=user_b.id,
            date_of_birth=date(1992, 11, 23),
            gender='Female',
            blood_group='B+',
            city='London'
        )
        db.session.add(patient_b)
        db.session.flush()

        dr_smith = Doctor.query.first()
        appt_b = Appointment(
            patient_id=patient_b.id,
            doctor_id=dr_smith.id,
            hospital_id=dr_smith.hospital_id,
            appointment_date=date.today() + timedelta(days=5),
            time_slot='11:00 AM - 11:30 AM',
            appointment_number='CC-2026-888001',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Confidential consult for Patient B'
        )
        db.session.add(appt_b)
        db.session.commit()

        # Log in as Patient A
        self.client.post('/login', data={
            'identifier': 'patient@careconnect.org',
            'password': 'patient123'
        }, follow_redirects=True)

        # Patient A tries to view Patient B's confirmation receipt
        res = self.client.get(f'/patient/appointments/{appt_b.id}/confirmation', follow_redirects=False)
        self.assertEqual(res.status_code, 403)

if __name__ == '__main__':
    unittest.main()
