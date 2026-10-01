import unittest
from datetime import date, timedelta

from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from services.booking_service import book_appointment, generate_doctor_slots
from utils.pdf_generator import generate_appointment_pdf


class CareConnectPhase8AppointmentManagementTestCase(unittest.TestCase):
    """
    Test suite for Phase 8:
    - Patient Appointment History & Filtering
    - Patient Appointment Cancellation & Lifecycle Validation
    - Slot Re-availability & Concurrency Immunity
    - Doctor Appointment Queue & Status Updates (Confirmed / Completed)
    - Hospital Multi-Tenant Isolation & Appointment Management
    - Existing PDF & QR Code Verification Preservation
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
            username='hosp_admin_a',
            email='admin_a@hospital.org',
            full_name='Admin Hospital A',
            role=User.ROLE_HOSPITAL
        )
        admin_a.set_password('pass123')
        db.session.add(admin_a)
        db.session.flush()

        self.hospital_a = Hospital(
            user_id=admin_a.id,
            name='Mercy General Hospital',
            registration_number='HOSP-P8-001',
            hospital_type='General Hospital',
            address='123 Health Ave',
            city='Boston'
        )
        db.session.add(self.hospital_a)
        db.session.flush()

        # 2. Hospital B & Admin B (for cross-tenant tests)
        admin_b = User(
            username='hosp_admin_b',
            email='admin_b@hospital.org',
            full_name='Admin Hospital B',
            role=User.ROLE_HOSPITAL
        )
        admin_b.set_password('pass123')
        db.session.add(admin_b)
        db.session.flush()

        self.hospital_b = Hospital(
            user_id=admin_b.id,
            name='St. Luke Clinic',
            registration_number='HOSP-P8-002',
            hospital_type='Specialty Clinic',
            address='456 Care Blvd',
            city='Boston'
        )
        db.session.add(self.hospital_b)
        db.session.flush()

        # 3. Doctor 1 (Hospital A)
        doc1_user = User(
            username='dr_house',
            email='house@mercy.org',
            full_name='Gregory House',
            role=User.ROLE_DOCTOR
        )
        doc1_user.set_password('pass123')
        db.session.add(doc1_user)
        db.session.flush()

        self.doctor_1 = Doctor(
            user_id=doc1_user.id,
            hospital_id=self.hospital_a.id,
            specialization='Diagnostic Medicine',
            qualification='MD',
            consultation_fee=180.0,
            is_available=True,
            available_days='Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday',
            available_time='09:00 AM - 05:00 PM',
            room_number='Room 101'
        )
        db.session.add(self.doctor_1)
        db.session.flush()

        # 4. Doctor 2 (Hospital B)
        doc2_user = User(
            username='dr_wilson',
            email='wilson@stluke.org',
            full_name='James Wilson',
            role=User.ROLE_DOCTOR
        )
        doc2_user.set_password('pass123')
        db.session.add(doc2_user)
        db.session.flush()

        self.doctor_2 = Doctor(
            user_id=doc2_user.id,
            hospital_id=self.hospital_b.id,
            specialization='Oncology',
            qualification='MD',
            consultation_fee=200.0,
            is_available=True,
            available_days='Monday, Tuesday, Wednesday, Thursday, Friday',
            available_time='09:00 AM - 05:00 PM',
            room_number='Room 202'
        )
        db.session.add(self.doctor_2)
        db.session.flush()

        # 5. Patient A
        pat_a_user = User(
            username='patient_alice',
            email='alice@example.com',
            full_name='Alice Smith',
            phone='+1 (617) 555-1111',
            role=User.ROLE_PATIENT
        )
        pat_a_user.set_password('patient123')
        db.session.add(pat_a_user)
        db.session.flush()

        self.patient_a = Patient(
            user_id=pat_a_user.id,
            date_of_birth=date(1990, 4, 10),
            gender='Female',
            blood_group='A+',
            address='10 Park Street',
            city='Boston'
        )
        db.session.add(self.patient_a)
        db.session.flush()

        # 6. Patient B
        pat_b_user = User(
            username='patient_bob',
            email='bob@example.com',
            full_name='Bob Jones',
            phone='+1 (617) 555-2222',
            role=User.ROLE_PATIENT
        )
        pat_b_user.set_password('patient123')
        db.session.add(pat_b_user)
        db.session.flush()

        self.patient_b = Patient(
            user_id=pat_b_user.id,
            date_of_birth=date(1988, 7, 19),
            gender='Male',
            blood_group='B+',
            address='20 Elm Street',
            city='Boston'
        )
        db.session.add(self.patient_b)
        db.session.flush()

        # 7. Seed Appointments
        self.future_date = date.today() + timedelta(days=3)
        self.past_date = date.today() - timedelta(days=5)

        # Appointment 1: Patient A with Doctor 1 (Upcoming Confirmed)
        self.appt_a1 = Appointment(
            patient_id=self.patient_a.id,
            doctor_id=self.doctor_1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=self.future_date,
            time_slot='10:00 AM - 10:30 AM',
            appointment_number='CC-2026-800001',
            verification_token='TOKEN-P8-A1',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Chronic leg pain'
        )
        db.session.add(self.appt_a1)

        # Appointment 2: Patient A with Doctor 1 (Past Completed)
        self.appt_a_completed = Appointment(
            patient_id=self.patient_a.id,
            doctor_id=self.doctor_1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=self.past_date,
            time_slot='11:00 AM - 11:30 AM',
            appointment_number='CC-2026-800002',
            verification_token='TOKEN-P8-A2',
            status=Appointment.STATUS_COMPLETED,
            symptoms='Routine diagnostic checkup'
        )
        db.session.add(self.appt_a_completed)

        # Appointment 3: Patient B with Doctor 2 (Upcoming Confirmed)
        self.appt_b1 = Appointment(
            patient_id=self.patient_b.id,
            doctor_id=self.doctor_2.id,
            hospital_id=self.hospital_b.id,
            appointment_date=self.future_date,
            time_slot='02:00 PM - 02:30 PM',
            appointment_number='CC-2026-800003',
            verification_token='TOKEN-P8-B1',
            status=Appointment.STATUS_CONFIRMED,
            symptoms='Oncology follow-up'
        )
        db.session.add(self.appt_b1)

        db.session.commit()

    # 1. Patient can view own appointment history
    def test_patient_can_view_own_appointment_history(self):
        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.get('/patient/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('CC-2026-800001', html)
        self.assertIn('Mercy General Hospital', html)
        self.assertIn('Gregory House', html)

    # 2. Patient cannot view another patient's appointments
    def test_patient_cannot_view_another_patient_appointments(self):
        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.get('/patient/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        # Patient B's appointment should NOT appear in Patient A's view
        self.assertNotIn('CC-2026-800003', html)
        self.assertNotIn('St. Luke Clinic', html)
        self.assertNotIn('James Wilson', html)

    # 3. Patient can cancel own upcoming appointment
    def test_patient_can_cancel_own_upcoming_appointment(self):
        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.post(f'/patient/appointments/{self.appt_a1.id}/cancel', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify in database
        refreshed = db.session.get(Appointment, self.appt_a1.id)
        self.assertEqual(refreshed.status, Appointment.STATUS_CANCELLED)
        
        html = response.get_data(as_text=True)
        self.assertIn('cancelled successfully', html.lower())

    # 4. Patient cannot cancel another patient's appointment (HTTP 403)
    def test_patient_cannot_cancel_another_patient_appointment(self):
        self.client.post('/login', data={'identifier': 'bob@example.com', 'password': 'patient123'}, follow_redirects=True)
        # Bob tries to cancel Alice's appointment (appt_a1)
        response = self.client.post(f'/patient/appointments/{self.appt_a1.id}/cancel')
        self.assertEqual(response.status_code, 403)
        
        # Verify appointment was NOT cancelled
        refreshed = db.session.get(Appointment, self.appt_a1.id)
        self.assertEqual(refreshed.status, Appointment.STATUS_CONFIRMED)

    # 5. Completed appointment cannot be cancelled
    def test_completed_appointment_cannot_be_cancelled(self):
        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.post(f'/patient/appointments/{self.appt_a_completed.id}/cancel', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        refreshed = db.session.get(Appointment, self.appt_a_completed.id)
        self.assertEqual(refreshed.status, Appointment.STATUS_COMPLETED)
        html = response.get_data(as_text=True)
        self.assertIn('cannot be cancelled', html.lower())

    # 6. Cancelled appointment cannot be cancelled again
    def test_cancelled_appointment_cannot_be_cancelled_again(self):
        self.appt_a1.status = Appointment.STATUS_CANCELLED
        db.session.commit()

        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.post(f'/patient/appointments/{self.appt_a1.id}/cancel', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        html = response.get_data(as_text=True)
        self.assertIn('already been cancelled', html.lower())

    # 7. Past appointment cannot be cancelled
    def test_past_appointment_cannot_be_cancelled(self):
        # Create a confirmed appointment in the past
        past_appt = Appointment(
            patient_id=self.patient_a.id,
            doctor_id=self.doctor_1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=self.past_date,
            time_slot='03:00 PM - 03:30 PM',
            appointment_number='CC-2026-800099',
            status=Appointment.STATUS_CONFIRMED
        )
        db.session.add(past_appt)
        db.session.commit()

        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        response = self.client.post(f'/patient/appointments/{past_appt.id}/cancel', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        refreshed = db.session.get(Appointment, past_appt.id)
        self.assertEqual(refreshed.status, Appointment.STATUS_CONFIRMED)
        html = response.get_data(as_text=True)
        self.assertIn('past appointments cannot be cancelled', html.lower())

    # 8. Cancelled appointment remains in database
    def test_cancelled_appointment_remains_in_database(self):
        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        self.client.post(f'/patient/appointments/{self.appt_a1.id}/cancel', follow_redirects=True)
        
        # Row must still exist with status 'cancelled'
        appt = Appointment.query.filter_by(id=self.appt_a1.id).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.status, Appointment.STATUS_CANCELLED)

    # 9. Cancelled slot becomes available again
    def test_cancelled_slot_becomes_available_again(self):
        # Before cancellation, slot '10:00 AM - 10:30 AM' is booked
        slots_before = generate_doctor_slots(self.doctor_1, self.future_date)
        target_slot_before = next((s for s in slots_before if s['time_slot'] == '10:00 AM - 10:30 AM'), None)
        self.assertIsNotNone(target_slot_before)
        self.assertTrue(target_slot_before['is_booked'])

        # Cancel appointment
        self.appt_a1.status = Appointment.STATUS_CANCELLED
        db.session.commit()

        # After cancellation, slot must be available
        slots_after = generate_doctor_slots(self.doctor_1, self.future_date)
        target_slot_after = next((s for s in slots_after if s['time_slot'] == '10:00 AM - 10:30 AM'), None)
        self.assertIsNotNone(target_slot_after)
        self.assertFalse(target_slot_after['is_booked'])
        self.assertEqual(target_slot_after['status'], 'available')

    # 10. Another patient can book the released slot
    def test_another_patient_can_book_released_slot(self):
        # Cancel Alice's appointment
        self.appt_a1.status = Appointment.STATUS_CANCELLED
        db.session.commit()

        # Bob books the newly freed slot
        success, msg, new_appt = book_appointment(
            patient=self.patient_b,
            doctor_id=self.doctor_1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=self.future_date,
            time_slot='10:00 AM - 10:30 AM',
            symptoms='Need medical consult'
        )
        self.assertTrue(success, f"Failed to book released slot: {msg}")
        self.assertIsNotNone(new_appt)
        self.assertEqual(new_appt.patient_id, self.patient_b.id)
        self.assertEqual(new_appt.status, Appointment.STATUS_CONFIRMED)

    # 11. Double booking is still prevented on active slot
    def test_double_booking_still_prevented_on_active_slot(self):
        # Attempt to book already booked slot (appt_a1 is active)
        success, msg, new_appt = book_appointment(
            patient=self.patient_b,
            doctor_id=self.doctor_1.id,
            hospital_id=self.hospital_a.id,
            appointment_date=self.future_date,
            time_slot='10:00 AM - 10:30 AM',
            symptoms='Double booking attempt'
        )
        self.assertFalse(success)
        self.assertIn('no longer available', msg.lower())

    # 12. Doctor can view own appointments
    def test_doctor_can_view_own_appointments(self):
        self.client.post('/login', data={'identifier': 'house@mercy.org', 'password': 'pass123'}, follow_redirects=True)
        response = self.client.get('/doctor/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('CC-2026-800001', html)
        self.assertIn('Alice Smith', html)

    # 13. Doctor cannot view another doctor's appointments
    def test_doctor_cannot_view_another_doctor_appointments(self):
        self.client.post('/login', data={'identifier': 'house@mercy.org', 'password': 'pass123'}, follow_redirects=True)
        response = self.client.get('/doctor/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        # Dr. Wilson's appointment with Bob should NOT appear for Dr. House
        self.assertNotIn('CC-2026-800003', html)
        self.assertNotIn('Bob Jones', html)

    # 14. Doctor can mark own appointment completed
    def test_doctor_can_mark_own_appointment_completed(self):
        self.client.post('/login', data={'identifier': 'house@mercy.org', 'password': 'pass123'}, follow_redirects=True)
        response = self.client.post(
            f'/doctor/appointments/{self.appt_a1.id}/status',
            data={'status': 'completed'},
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        
        refreshed = db.session.get(Appointment, self.appt_a1.id)
        self.assertEqual(refreshed.status, Appointment.STATUS_COMPLETED)

    # 15. Doctor cannot modify another doctor's appointment (HTTP 403)
    def test_doctor_cannot_modify_another_doctor_appointment(self):
        self.client.post('/login', data={'identifier': 'house@mercy.org', 'password': 'pass123'}, follow_redirects=True)
        # Dr. House tries to update Dr. Wilson's appointment (appt_b1)
        response = self.client.post(
            f'/doctor/appointments/{self.appt_b1.id}/status',
            data={'status': 'completed'}
        )
        self.assertEqual(response.status_code, 403)
        
        refreshed = db.session.get(Appointment, self.appt_b1.id)
        self.assertEqual(refreshed.status, Appointment.STATUS_CONFIRMED)

    # 16. Hospital sees only its own hospital appointments
    def test_hospital_sees_only_own_appointments(self):
        self.client.post('/login', data={'identifier': 'admin_a@hospital.org', 'password': 'pass123'}, follow_redirects=True)
        response = self.client.get('/hospital/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('CC-2026-800001', html)
        self.assertIn('Alice Smith', html)
        # Hospital B's appointment should NOT be shown
        self.assertNotIn('CC-2026-800003', html)
        self.assertNotIn('Bob Jones', html)

    # 17. Hospital cannot access another hospital's appointments
    def test_hospital_cannot_access_another_hospital_appointments(self):
        self.client.post('/login', data={'identifier': 'admin_b@hospital.org', 'password': 'pass123'}, follow_redirects=True)
        response = self.client.get('/hospital/appointments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('CC-2026-800003', html)
        self.assertNotIn('CC-2026-800001', html)

    # 18. Invalid appointment status transitions are rejected
    def test_invalid_appointment_status_transitions_rejected(self):
        # 18a. Completed -> Cancelled
        can_transition, msg = self.appt_a_completed.can_transition_to('cancelled')
        self.assertFalse(can_transition)
        self.assertIn('completed', msg.lower())

        # 18b. Cancelled -> Completed
        self.appt_a1.status = Appointment.STATUS_CANCELLED
        db.session.commit()
        can_transition, msg = self.appt_a1.can_transition_to('completed')
        self.assertFalse(can_transition)
        self.assertIn('cancelled', msg.lower())

        # 18c. Cancelled -> Confirmed
        can_transition, msg = self.appt_a1.can_transition_to('confirmed')
        self.assertFalse(can_transition)
        self.assertIn('cancelled', msg.lower())

    # 19. Appointment filters work correctly
    def test_appointment_filters_work_correctly(self):
        # Patient filter by status=completed
        self.client.post('/login', data={'identifier': 'alice@example.com', 'password': 'patient123'}, follow_redirects=True)
        res_completed = self.client.get('/patient/appointments?status=completed')
        self.assertEqual(res_completed.status_code, 200)
        html = res_completed.get_data(as_text=True)
        self.assertIn('CC-2026-800002', html)

        # Patient search by doctor name
        res_search = self.client.get('/patient/appointments?q=Gregory')
        self.assertEqual(res_search.status_code, 200)
        self.assertIn('CC-2026-800001', res_search.get_data(as_text=True))

        self.client.get('/logout', follow_redirects=True)

        # Doctor filter by status
        self.client.post('/login', data={'identifier': 'house@mercy.org', 'password': 'pass123'}, follow_redirects=True)
        res_doc_filter = self.client.get('/doctor/appointments?status=upcoming')
        self.assertEqual(res_doc_filter.status_code, 200)

        self.client.get('/logout', follow_redirects=True)

        # Hospital filter by doctor
        self.client.post('/login', data={'identifier': 'admin_a@hospital.org', 'password': 'pass123'}, follow_redirects=True)
        res_hosp_filter = self.client.get(f'/hospital/appointments?doctor_id={self.doctor_1.id}')
        self.assertEqual(res_hosp_filter.status_code, 200)
        self.assertIn('CC-2026-800001', res_hosp_filter.get_data(as_text=True))

    # 20. Existing PDF confirmation still works
    def test_existing_pdf_confirmation_still_works(self):
        pdf_bytes = generate_appointment_pdf(self.appt_a1)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertIn(b'CC-2026-800001', pdf_bytes)

    # 21. Existing QR verification still works
    def test_existing_qr_verification_still_works(self):
        response = self.client.get(f'/verify/appointment/{self.appt_a1.verification_token}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Appointment Verified', html)
        self.assertIn('CC-2026-800001', html)


if __name__ == '__main__':
    unittest.main()
