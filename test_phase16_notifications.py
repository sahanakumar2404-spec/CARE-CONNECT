"""
Care Connect - Phase 16: Appointment Notifications & Reminders Test Suite
Comprehensive testing for:
1. Notification model creation and fields
2. Patient booking notification
3. Doctor new appointment notification
4. Hospital facility notification
5. Cancellation notification dispatch
6. Appointment status update notification
7. Upcoming appointment reminder generation
8. Cancelled appointments do not generate reminders
9. Completed appointments do not generate reminders
10. Duplicate reminder prevention (idempotency key)
11. Duplicate event notification prevention
12. Unread notification count
13. Mark individual notification as read
14. Mark all notifications as read
15. Notification ownership enforcement
16. Cross-user access blocked (IDOR defense)
17. Unauthenticated access blocked
18. Role authorization (Patient, Doctor, Hospital)
19. CSRF protection on state-changing endpoints
20. Chronological notification ordering (newest first)
21. Empty notification state rendering
22. Existing appointment booking and lifecycle workflow regression preservation
"""

import unittest
from datetime import date, datetime, timedelta, timezone
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient
from models.appointment import Appointment
from models.notification import Notification
from services.booking_service import book_appointment, doctor_works_on_date
from services.notification_service import (
    create_notification,
    notify_appointment_booked,
    notify_appointment_cancelled,
    notify_appointment_status_updated,
    check_and_generate_reminders_for_user,
    get_user_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_as_read
)


def get_working_date(doctor, offset_days=1):
    """Finds the next valid working day for a doctor from today."""
    target = date.today() + timedelta(days=offset_days)
    for _ in range(14):
        if doctor_works_on_date(doctor, target):
            return target
        target += timedelta(days=1)
    return date.today() + timedelta(days=offset_days)


class CareConnectPhase16NotificationsTestCase(unittest.TestCase):
    """Test case for Phase 16 In-App Notifications and Reminders."""

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        # Seed users, hospital, doctor, and patient for testing
        self.patient_user = User.query.filter_by(email='patient@careconnect.org').first()
        self.doctor_user = User.query.filter_by(email='dr.smith@careconnect.org').first()
        self.hospital_user = User.query.filter_by(email='admin@careconnect.org').first()

        self.hospital = Hospital.query.first()
        self.doctor = Doctor.query.filter_by(user_id=self.doctor_user.id).first()
        self.patient = Patient.query.filter_by(user_id=self.patient_user.id).first()

        # Dynamically seed second patient for cross-user/IDOR tests
        self.patient2_user = User.query.filter_by(email='patient2@careconnect.org').first()
        if not self.patient2_user:
            self.patient2_user = User(
                username='patient2',
                email='patient2@careconnect.org',
                full_name='Jordan Lee',
                phone='+1 (212) 555-0899',
                role=User.ROLE_PATIENT
            )
            self.patient2_user.set_password('patient123')
            db.session.add(self.patient2_user)
            db.session.flush()

            self.patient2 = Patient(
                user_id=self.patient2_user.id,
                date_of_birth=date(1998, 5, 15),
                gender='Female',
                blood_group='A+',
                city='New York'
            )
            db.session.add(self.patient2)
            db.session.commit()
        else:
            self.patient2 = Patient.query.filter_by(user_id=self.patient2_user.id).first()

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


    # 1. Notification Model Creation
    def test_01_notification_model_creation(self):
        """Verifies Notification model fields, defaults, and relationships."""
        notif = Notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Test Notification",
            message="This is a test notification message.",
            is_read=False,
            event_key="test:unique:key:1"
        )
        db.session.add(notif)
        db.session.commit()

        self.assertIsNotNone(notif.id)
        self.assertEqual(notif.recipient_user_id, self.patient_user.id)
        self.assertEqual(notif.notification_type, Notification.TYPE_APPOINTMENT_BOOKED)
        self.assertEqual(notif.title, "Test Notification")
        self.assertFalse(notif.is_read)
        self.assertIsNone(notif.read_at)
        self.assertIsNotNone(notif.created_at)
        self.assertEqual(notif.recipient.email, 'patient@careconnect.org')

        # Test mark_as_read helper
        notif.mark_as_read()
        db.session.commit()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

    # 2. Patient Receives Booking Notification
    def test_02_patient_receives_booking_notification(self):
        """Verifies booking an appointment generates an in-app notification for the patient."""
        booking_date = get_working_date(self.doctor, offset_days=3)
        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=booking_date,
            time_slot="10:00 AM - 10:30 AM",
            symptoms="Persistent seasonal allergies"
        )
        self.assertTrue(success, f"Booking failed: {msg}")

        # Check patient's notifications
        patient_notifs = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED
        ).all()
        self.assertGreaterEqual(len(patient_notifs), 1)

        latest = patient_notifs[-1]
        self.assertEqual(latest.title, "Appointment Booked")
        self.assertIn("confirmed", latest.message.lower())
        self.assertIn(appt.appointment_number, latest.message)
        self.assertEqual(latest.related_appointment_id, appt.id)

    # 3. Doctor Receives New Appointment Notification
    def test_03_doctor_receives_new_appointment_notification(self):
        """Verifies doctor receives an in-app notification upon new booking."""
        booking_date = get_working_date(self.doctor, offset_days=4)
        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=booking_date,
            time_slot="11:00 AM - 11:30 AM",
            symptoms="Follow-up consultation"
        )
        self.assertTrue(success)

        doctor_notifs = Notification.query.filter_by(
            recipient_user_id=self.doctor_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED
        ).all()
        self.assertGreaterEqual(len(doctor_notifs), 1)

        latest = doctor_notifs[-1]
        self.assertEqual(latest.title, "New Appointment Scheduled")
        self.assertIn(appt.appointment_number, latest.message)
        self.assertEqual(latest.related_appointment_id, appt.id)

    # 4. Hospital Receives Facility Notification
    def test_04_hospital_receives_facility_notification(self):
        """Verifies hospital management user receives operational booking notification."""
        booking_date = get_working_date(self.doctor, offset_days=5)
        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=booking_date,
            time_slot="02:00 PM - 02:30 PM",
            symptoms="General checkup"
        )
        self.assertTrue(success)

        hospital_notifs = Notification.query.filter_by(
            recipient_user_id=self.hospital_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED
        ).all()
        self.assertGreaterEqual(len(hospital_notifs), 1)

        latest = hospital_notifs[-1]
        self.assertEqual(latest.title, "Facility Consultation Scheduled")
        self.assertIn(appt.appointment_number, latest.message)

    # 5. Cancellation Notification Sent to All Relevant Parties
    def test_05_cancellation_notification_sent_to_all_parties(self):
        """Verifies cancellation notifies Patient, Doctor, and Hospital."""
        booking_date = get_working_date(self.doctor, offset_days=6)
        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=booking_date,
            time_slot="11:30 AM - 12:00 PM",
            symptoms="Mild headache"
        )
        self.assertTrue(success, f"Booking failed: {msg}")

        # Cancel appointment via patient route
        self._login('patient@careconnect.org')
        resp = self.client.post(f'/patient/appointments/{appt.id}/cancel', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Check patient cancellation notification
        p_notif = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_CANCELLED
        ).first()
        self.assertIsNotNone(p_notif)
        self.assertEqual(p_notif.title, "Appointment Cancelled")

        # Check doctor cancellation notification
        d_notif = Notification.query.filter_by(
            recipient_user_id=self.doctor_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_CANCELLED
        ).first()
        self.assertIsNotNone(d_notif)
        self.assertEqual(d_notif.title, "Appointment Cancelled")

        # Check hospital cancellation notification
        h_notif = Notification.query.filter_by(
            recipient_user_id=self.hospital_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_CANCELLED
        ).first()
        self.assertIsNotNone(h_notif)
        self.assertEqual(h_notif.title, "Appointment Cancelled")

    # 6. Appointment Status Update Notification Sent to Patient
    def test_06_appointment_status_update_notification_sent_to_patient(self):
        """Verifies doctor marking appointment status notifies the patient."""
        booking_date = get_working_date(self.doctor, offset_days=7)
        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=booking_date,
            time_slot="01:00 PM - 01:30 PM"
        )
        self.assertTrue(success, f"Booking failed: {msg}")

        # Doctor updates appointment to Completed
        self._login('dr.smith@careconnect.org')
        resp = self.client.post(
            f'/doctor/appointments/{appt.id}/status',
            data={'status': 'completed'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        # Check patient notification
        status_notif = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_STATUS_UPDATED
        ).first()
        self.assertIsNotNone(status_notif)
        self.assertIn("Completed", status_notif.title)
        self.assertIn("Completed", status_notif.message)

    # 7. Reminder Generation for Upcoming Appointments
    def test_07_reminder_generation_for_upcoming_appointments(self):
        """Verifies that active appointments within the reminder window generate reminders."""
        # Create an upcoming appointment for tomorrow
        target_date = date.today() + timedelta(days=1)
        appt = Appointment(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=target_date,
            time_slot="09:30 AM - 10:00 AM",
            status=Appointment.STATUS_CONFIRMED,
            appointment_number="CC-REMINDER-001"
        )
        db.session.add(appt)
        db.session.commit()

        # Trigger reminder check for patient
        reminders = check_and_generate_reminders_for_user(self.patient_user)
        self.assertGreaterEqual(len(reminders), 1)

        rem_notif = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            related_appointment_id=appt.id,
            notification_type=Notification.TYPE_UPCOMING_APPOINTMENT
        ).first()
        self.assertIsNotNone(rem_notif)
        self.assertEqual(rem_notif.title, "Upcoming Appointment Reminder")
        self.assertIn("CC-REMINDER-001", rem_notif.message)

    # 8. Cancelled Appointments Do NOT Generate Reminders
    def test_08_cancelled_appointments_do_not_generate_reminders(self):
        """Verifies that cancelled appointments are ignored by the reminder generator."""
        target_date = date.today() + timedelta(days=1)
        appt = Appointment(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=target_date,
            time_slot="10:30 AM - 11:00 AM",
            status=Appointment.STATUS_CANCELLED,
            appointment_number="CC-CANCELLED-001"
        )
        db.session.add(appt)
        db.session.commit()

        check_and_generate_reminders_for_user(self.patient_user)

        rem_notif = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_UPCOMING_APPOINTMENT,
            related_appointment_id=appt.id
        ).first()
        self.assertIsNone(rem_notif, "Cancelled appointment must not produce an upcoming reminder.")

    # 9. Completed Appointments Do NOT Generate Reminders
    def test_09_completed_appointments_do_not_generate_reminders(self):
        """Verifies that completed appointments are ignored by the reminder generator."""
        target_date = date.today() + timedelta(days=1)
        appt = Appointment(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=target_date,
            time_slot="11:30 AM - 12:00 PM",
            status=Appointment.STATUS_COMPLETED,
            appointment_number="CC-COMPLETED-001"
        )
        db.session.add(appt)
        db.session.commit()

        check_and_generate_reminders_for_user(self.patient_user)

        rem_notif = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_UPCOMING_APPOINTMENT,
            related_appointment_id=appt.id
        ).first()
        self.assertIsNone(rem_notif, "Completed appointment must not produce an upcoming reminder.")

    # 10. Duplicate Reminder Prevention (Idempotency Key)
    def test_10_duplicate_reminder_prevention(self):
        """Verifies running the reminder check repeatedly never creates duplicate notifications."""
        target_date = date.today() + timedelta(days=1)
        appt = Appointment(
            patient_id=self.patient.id,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=target_date,
            time_slot="01:00 PM - 01:30 PM",
            status=Appointment.STATUS_CONFIRMED,
            appointment_number="CC-DEDUP-001"
        )
        db.session.add(appt)
        db.session.commit()

        # Run check 5 times in succession
        for _ in range(5):
            check_and_generate_reminders_for_user(self.patient_user)

        # Count reminders for this appointment
        count = Notification.query.filter_by(
            recipient_user_id=self.patient_user.id,
            related_appointment_id=appt.id,
            notification_type=Notification.TYPE_UPCOMING_APPOINTMENT
        ).count()
        self.assertEqual(count, 1, "Duplicate reminder prevention must enforce exactly 1 notification.")

    # 11. Duplicate Event Notification Prevention
    def test_11_duplicate_event_notification_prevention(self):
        """Verifies duplicate notification creation for the same event key returns existing record."""
        notif1 = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Booking Test",
            message="Booking confirmation test",
            event_key="unique:event:key:999"
        )
        self.assertIsNotNone(notif1)

        # Attempt to create identical event_key
        notif2 = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Booking Test Duplicate",
            message="Duplicate attempt",
            event_key="unique:event:key:999"
        )
        self.assertEqual(notif1.id, notif2.id)

        # Query total count for this key
        count = Notification.query.filter_by(event_key="unique:event:key:999").count()
        self.assertEqual(count, 1)

    # 12. Unread Count Calculation
    def test_12_unread_count_calculation(self):
        """Verifies unread count helper accurately reflects unread records."""
        initial_unread = get_unread_count(self.patient_user.id)

        n1 = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Unread 1",
            message="Message 1"
        )
        n2 = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Unread 2",
            message="Message 2"
        )

        self.assertEqual(get_unread_count(self.patient_user.id), initial_unread + 2)

        # Mark one as read
        n1.mark_as_read()
        db.session.commit()
        self.assertEqual(get_unread_count(self.patient_user.id), initial_unread + 1)

    # 13. Mark Individual Notification as Read
    def test_13_mark_individual_notification_as_read(self):
        """Verifies user can mark their own notification as read via POST endpoint."""
        notif = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="To Read",
            message="Please read me"
        )
        self.assertFalse(notif.is_read)

        self._login('patient@careconnect.org')
        resp = self.client.post(f'/notifications/{notif.id}/read', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        updated_notif = db.session.get(Notification, notif.id)
        self.assertTrue(updated_notif.is_read)
        self.assertIsNotNone(updated_notif.read_at)

    # 14. Mark All Notifications as Read
    def test_14_mark_all_notifications_as_read(self):
        """Verifies mark-all-read endpoint marks every notification for the user as read."""
        # Ensure any pending reminders are already generated so they are also marked read
        check_and_generate_reminders_for_user(self.patient_user)
        create_notification(self.patient_user.id, Notification.TYPE_APPOINTMENT_BOOKED, "N1", "M1")
        create_notification(self.patient_user.id, Notification.TYPE_UPCOMING_APPOINTMENT, "N2", "M2")
        self.assertGreaterEqual(get_unread_count(self.patient_user.id), 2)

        self._login('patient@careconnect.org')
        resp = self.client.post('/notifications/mark-all-read', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(get_unread_count(self.patient_user.id), 0)

    # 15. Notification Ownership Enforcement
    def test_15_notification_ownership_enforcement(self):
        """Verifies user only sees their own notifications, never another user's."""
        create_notification(self.patient_user.id, Notification.TYPE_APPOINTMENT_BOOKED, "Patient1 Only", "Secret P1")
        create_notification(self.patient2_user.id, Notification.TYPE_APPOINTMENT_BOOKED, "Patient2 Only", "Secret P2")

        p1_notifs = get_user_notifications(self.patient_user.id)
        p2_notifs = get_user_notifications(self.patient2_user.id)

        p1_titles = [n.title for n in p1_notifs]
        p2_titles = [n.title for n in p2_notifs]

        self.assertIn("Patient1 Only", p1_titles)
        self.assertNotIn("Patient2 Only", p1_titles)

        self.assertIn("Patient2 Only", p2_titles)
        self.assertNotIn("Patient1 Only", p2_titles)

    # 16. Cross-User Access Blocked (IDOR Defense)
    def test_16_cross_user_access_blocked_idor(self):
        """Verifies Patient 2 receives HTTP 403 when trying to mark Patient 1's notification as read."""
        notif_p1 = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Private Notif",
            message="Private content"
        )

        # Login as Patient 2
        self._login('patient2@careconnect.org')
        resp = self.client.post(f'/notifications/{notif_p1.id}/read')
        self.assertEqual(resp.status_code, 403, "Attempting to mark another user's notification must return HTTP 403.")

        # Verify notification remains unread
        reloaded = db.session.get(Notification, notif_p1.id)
        self.assertFalse(reloaded.is_read)

    # 17. Unauthenticated Access Blocked
    def test_17_unauthenticated_access_blocked(self):
        """Verifies unauthenticated access to notification center redirects to login."""
        resp = self.client.get('/notifications')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers.get('Location', ''))

        resp2 = self.client.post('/notifications/1/read')
        self.assertEqual(resp2.status_code, 302)
        self.assertIn('/login', resp2.headers.get('Location', ''))

    # 18. Role Authorization (Patient, Doctor, Hospital Access)
    def test_18_role_authorization_across_roles(self):
        """Verifies notification center is accessible to Patients, Doctors, and Hospitals."""
        # Patient
        self._login('patient@careconnect.org')
        resp = self.client.get('/notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Notification Center', resp.data)

        # Doctor
        self._login('dr.smith@careconnect.org')
        resp = self.client.get('/notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Notification Center', resp.data)

        # Hospital
        self._login('admin@careconnect.org')
        resp = self.client.get('/notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Notification Center', resp.data)

    # 19. CSRF Protection on POST Endpoints
    def test_19_csrf_protection_on_post_endpoints(self):
        """Verifies CSRF token is required when WTF_CSRF_ENABLED is active."""
        notif = create_notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="CSRF Test",
            message="CSRF validation"
        )
        self.app.config['WTF_CSRF_ENABLED'] = True

        self._login('patient@careconnect.org')

        # POST without CSRF token must fail with 400
        resp = self.client.post(f'/notifications/{notif.id}/read')
        self.assertEqual(resp.status_code, 400)

        # Mark all read without CSRF must fail with 400
        resp2 = self.client.post('/notifications/mark-all-read')
        self.assertEqual(resp2.status_code, 400)

        self.app.config['WTF_CSRF_ENABLED'] = False

    # 20. Chronological Notification Ordering (Newest First)
    def test_20_chronological_notification_ordering(self):
        """Verifies notifications are returned with the newest first."""
        base_time = datetime.now(timezone.utc) - timedelta(hours=3)
        n_old = Notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_APPOINTMENT_BOOKED,
            title="Old Notification",
            message="Old message",
            created_at=base_time
        )
        n_new = Notification(
            recipient_user_id=self.patient_user.id,
            notification_type=Notification.TYPE_UPCOMING_APPOINTMENT,
            title="New Notification",
            message="New message",
            created_at=base_time + timedelta(hours=2)
        )
        db.session.add_all([n_old, n_new])
        db.session.commit()

        results = get_user_notifications(self.patient_user.id)
        self.assertEqual(results[0].title, "New Notification")

    # 21. Empty Notification State Rendering
    def test_21_empty_notification_state_rendering(self):
        """Verifies empty state banner renders cleanly when user has zero notifications."""
        # Ensure patient2 has no notifications
        Notification.query.filter_by(recipient_user_id=self.patient2_user.id).delete()
        db.session.commit()

        self._login('patient2@careconnect.org')
        resp = self.client.get('/notifications')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'No Notifications Found', resp.data)
        self.assertIn(b'emptyNotificationsState', resp.data)

    # 22. Existing Appointment Workflow Still Works
    def test_22_existing_appointment_workflow_preserved(self):
        """Verifies existing appointment booking, confirmation, and status management work without regressions."""
        booking_date = get_working_date(self.doctor, offset_days=8)
        success, msg, appt = book_appointment(
            patient=self.patient,
            doctor_id=self.doctor.id,
            hospital_id=self.hospital.id,
            appointment_date=booking_date,
            time_slot="02:30 PM - 03:00 PM",
            symptoms="Full regression check"
        )
        self.assertTrue(success)
        self.assertIsNotNone(appt.appointment_number)
        self.assertTrue(appt.appointment_number.startswith("CC-"))

        # Doctor completes appointment
        self._login('dr.smith@careconnect.org')
        resp = self.client.post(
            f'/doctor/appointments/{appt.id}/status',
            data={'status': 'completed'},
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)

        reloaded = db.session.get(Appointment, appt.id)
        self.assertEqual(reloaded.status, Appointment.STATUS_COMPLETED)


if __name__ == '__main__':
    unittest.main()
