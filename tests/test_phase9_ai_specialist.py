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
from utils.pdf_generator import generate_appointment_pdf
from ai.specialist_recommender import (
    recommend_specialist,
    DISCLAIMER_TEXT,
    UNCLEAR_RESPONSE_TEXT
)


class CareConnectPhase9AISpecialistTestCase(unittest.TestCase):
    """
    Comprehensive test suite for Phase 9: AI Specialist Recommendation:
    1. Page requires patient authentication (redirects to login).
    2. Non-patient users cannot access it.
    3. Empty input is handled correctly.
    4. Valid headache concern recommends Neurology.
    5. Skin concern recommends Dermatology.
    6. Heart concern recommends Cardiology.
    7. Bone/joint concern recommends Orthopedics.
    8. Eye concern recommends Ophthalmology.
    9. Unknown input returns an uncertainty response.
    10. Recommendation does not claim a diagnosis.
    11. Recommendation does not provide medication.
    12. Recommendation does not provide treatment instructions.
    13. Confidence value is displayed safely ("Recommendation confidence: ...").
    14. Matching doctors come only from existing database.
    15. No matching registered specialist is handled correctly.
    16. Patient privacy and session isolation preserved.
    17. Existing hospital & doctor discovery flow still works.
    18. Existing appointment booking still works.
    19. Existing PDF confirmation still works.
    20. Existing QR verification still works.
    21. Additional specialty mappings (ENT, Dentistry, Gynecology, Pediatrics) work.
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
        # 1. Hospital Admin & Facility
        admin = User(
            username='hosp_admin',
            email='admin@metrohospital.org',
            full_name='Metro Hospital Admin',
            role=User.ROLE_HOSPITAL
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.flush()

        self.hospital = Hospital(
            user_id=admin.id,
            name='Metro General Hospital',
            registration_number='HOSP-P9-001',
            hospital_type='General Hospital',
            address='100 Healthcare Blvd',
            city='New York'
        )
        db.session.add(self.hospital)
        db.session.flush()

        # 2. Doctor 1: Cardiologist
        doc1_user = User(
            username='drcardio',
            email='cardio@metrohospital.org',
            full_name='Dr. Sarah Smith',
            role=User.ROLE_DOCTOR
        )
        doc1_user.set_password('doc123')
        db.session.add(doc1_user)
        db.session.flush()

        self.doc_cardio = Doctor(
            user_id=doc1_user.id,
            hospital_id=self.hospital.id,
            specialization='Cardiology',
            qualification='MD, FACC',
            experience_years=10,
            consultation_fee=120.0,
            is_available=True,
            available_days='Monday, Wednesday, Friday',
            available_time='09:00 AM - 04:00 PM',
            room_number='Room 301'
        )
        db.session.add(self.doc_cardio)

        # 3. Doctor 2: Neurologist
        doc2_user = User(
            username='drneuro',
            email='neuro@metrohospital.org',
            full_name='Dr. Marcus Johnson',
            role=User.ROLE_DOCTOR
        )
        doc2_user.set_password('doc123')
        db.session.add(doc2_user)
        db.session.flush()

        self.doc_neuro = Doctor(
            user_id=doc2_user.id,
            hospital_id=self.hospital.id,
            specialization='Neurology',
            qualification='MD, PhD',
            experience_years=8,
            consultation_fee=150.0,
            is_available=True,
            available_days='Tuesday, Thursday',
            available_time='10:00 AM - 03:00 PM',
            room_number='Room 205'
        )
        db.session.add(self.doc_neuro)

        # 4. Patient A
        patient_a_user = User(
            username='patient_a',
            email='patient_a@example.com',
            full_name='Alice Walker',
            phone='+1 (555) 019-1001',
            role=User.ROLE_PATIENT
        )
        patient_a_user.set_password('patient123')
        db.session.add(patient_a_user)
        db.session.flush()

        self.patient_a = Patient(
            user_id=patient_a_user.id,
            date_of_birth=date(1990, 5, 15),
            gender='Female',
            blood_group='A+',
            city='New York'
        )
        db.session.add(self.patient_a)

        # 5. Patient B
        patient_b_user = User(
            username='patient_b',
            email='patient_b@example.com',
            full_name='Bob Martin',
            phone='+1 (555) 019-1002',
            role=User.ROLE_PATIENT
        )
        patient_b_user.set_password('patient123')
        db.session.add(patient_b_user)
        db.session.flush()

        self.patient_b = Patient(
            user_id=patient_b_user.id,
            date_of_birth=date(1985, 3, 20),
            gender='Male',
            blood_group='O+',
            city='New York'
        )
        db.session.add(self.patient_b)

        db.session.commit()

    def _login(self, email, password):
        return self.client.post('/login', data={
            'identifier': email,
            'password': password
        }, follow_redirects=True)

    # ------------------------------------------------------------------------
    # 1. Authentication & RBAC
    # ------------------------------------------------------------------------
    def test_ai_specialist_page_requires_auth(self):
        """Verifies unauthenticated access to /patient/ai-specialist redirects to login."""
        res = self.client.get('/patient/ai-specialist')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_non_patients_cannot_access_ai_specialist(self):
        """Verifies Hospital Admins and Doctors cannot access patient AI specialist page."""
        # Hospital Admin attempt
        self._login('admin@metrohospital.org', 'admin123')
        res_hosp = self.client.get('/patient/ai-specialist')
        self.assertIn(res_hosp.status_code, [302, 403])

        # Doctor attempt
        self.client.get('/logout', follow_redirects=True)
        self._login('cardio@metrohospital.org', 'doc123')
        res_doc = self.client.get('/patient/ai-specialist')
        self.assertIn(res_doc.status_code, [302, 403])

    def test_patient_can_access_ai_specialist_page(self):
        """Verifies authenticated patient can view AI specialist recommendation page."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.get('/patient/ai-specialist')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'AI Specialist Recommendation', res.data)
        self.assertIn(b'What is your main health concern?', res.data)
        self.assertIn(b'Get Recommendation', res.data)

    # ------------------------------------------------------------------------
    # 2. Input Validation & Edge Cases
    # ------------------------------------------------------------------------
    def test_empty_and_whitespace_input_handled_safely(self):
        """Verifies submitting empty or whitespace concern returns safe guidance message."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={'concern': '   '}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Recommendation Unclear', res.data)

    def test_very_short_input_handled_safely(self):
        """Verifies input shorter than 3 characters returns unclear guidance response."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={'concern': 'hi'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Recommendation Unclear', res.data)

    def test_very_long_input_handled_safely(self):
        """Verifies input exceeding 1000 characters is handled safely without 500 error."""
        self._login('patient_a@example.com', 'patient123')
        long_concern = "I have a headache. " * 70  # > 1000 chars
        res = self.client.post('/patient/ai-specialist', data={'concern': long_concern}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'exceeds the maximum limit', res.data)

    def test_gibberish_and_special_chars_handled_safely(self):
        """Verifies non-alphanumeric and repeating character gibberish returns unclear response."""
        self._login('patient_a@example.com', 'patient123')
        for bad_input in ['!@#$%^&*()_+', '??????????', 'aaaaaaaaaaaa']:
            res = self.client.post('/patient/ai-specialist', data={'concern': bad_input}, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'Recommendation Unclear', res.data)

    # ------------------------------------------------------------------------
    # 3. Core Clinical Mappings
    # ------------------------------------------------------------------------
    def test_valid_headache_concern_recommends_neurology(self):
        """Verifies headache & concentration complaints recommend Neurology."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have been having frequent headaches and difficulty concentrating with dizziness.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Neurology', res.data)
        self.assertIn(b'neurological care', res.data)

    def test_skin_concern_recommends_dermatology(self):
        """Verifies rash, acne, and itching complaints recommend Dermatology."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have a red skin rash and acne with skin irritation and itching.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dermatology', res.data)
        self.assertIn(b'dermatological care', res.data)

    def test_heart_concern_recommends_cardiology(self):
        """Verifies chest pain and heart flutter complaints recommend Cardiology."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I am experiencing chest pain and irregular heartbeat palpitations.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Cardiology', res.data)
        self.assertIn(b'cardiovascular care', res.data)

    def test_bone_joint_concern_recommends_orthopedics(self):
        """Verifies joint pain, knee swelling, and bone complaints recommend Orthopedics."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'Severe joint pain and knee swelling after a bone injury with limited mobility.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Orthopedics', res.data)
        self.assertIn(b'orthopedic', res.data)

    def test_eye_concern_recommends_ophthalmology(self):
        """Verifies vision, cornea, and eye pain complaints recommend Ophthalmology."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have blurry vision and cornea irritation with severe eye pain.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Ophthalmology', res.data)
        self.assertIn(b'eye care', res.data)

    def test_unknown_or_unclear_input_returns_uncertainty_response(self):
        """Verifies vague or unmapped concerns return clear uncertainty response advising GP."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'The weather is very sunny and I walked five miles today.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Unable to confidently recommend a specialty', res.data)
        self.assertIn(b'consult a general physician', res.data)

    # ------------------------------------------------------------------------
    # 4. Clinical Safety Boundaries
    # ------------------------------------------------------------------------
    def test_recommendation_does_not_claim_diagnosis(self):
        """Verifies the AI response NEVER claims a disease diagnosis."""
        result = recommend_specialist('I have a severe headache, dizziness, and migraine.')
        reason = result['reason'].lower()
        self.assertNotIn('you have been diagnosed with', reason)
        self.assertNotIn('your disease is', reason)
        self.assertNotIn('diagnosis:', reason)

    def test_recommendation_does_not_provide_medication(self):
        """Verifies the AI response NEVER provides medication or dosage instructions."""
        result = recommend_specialist('I have chest pain and palpitations.')
        reason = result['reason'].lower()
        self.assertNotIn('take ', reason)
        self.assertNotIn('aspirin', reason)
        self.assertNotIn('mg', reason)
        self.assertNotIn('prescription', reason)

    def test_recommendation_does_not_provide_treatment_instructions(self):
        """Verifies the AI response NEVER gives treatment or emergency surgical instructions."""
        result = recommend_specialist('My knee is swollen and hurts a lot.')
        reason = result['reason'].lower()
        self.assertNotIn('perform surgery', reason)
        self.assertNotIn('inject', reason)

    def test_confidence_value_displayed_safely(self):
        """Verifies confidence value uses non-medical appointment navigation phrasing."""
        self._login('patient_a@example.com', 'patient123')
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have frequent headaches and migraines.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Recommendation confidence:', res.data)
        # Verify mandatory disclaimer is displayed
        self.assertIn(b'This recommendation is for appointment guidance only and is not a medical diagnosis', res.data)

    # ------------------------------------------------------------------------
    # 5. Database Integration & Matching Doctors
    # ------------------------------------------------------------------------
    def test_matching_doctors_come_only_from_existing_database(self):
        """Verifies only real practicing physicians from the database are suggested."""
        self._login('patient_a@example.com', 'patient123')
        # Recommend Neurology -> Dr. Marcus Johnson exists in DB
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have frequent headaches and concentration issues.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dr. Marcus Johnson', res.data)
        self.assertIn(b'Metro General Hospital', res.data)
        self.assertIn(b'$150.00', res.data)
        # Verify doctor not in DB is not invented
        self.assertNotIn(b'Dr. House', res.data)

    def test_no_matching_registered_specialist_handled_correctly(self):
        """Verifies when no doctor in DB matches recommended specialty, fallback notice is shown."""
        self._login('patient_a@example.com', 'patient123')
        # Recommend Dermatology -> No dermatologist seeded in test DB
        res = self.client.post('/patient/ai-specialist', data={
            'concern': 'I have a skin rash and itchy eczema on my arm.'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'No registered specialist currently matches this recommendation', res.data)
        self.assertIn(b'Explore Registered Hospitals', res.data)

    # ------------------------------------------------------------------------
    # 6. Patient Privacy & Existing System Integrity
    # ------------------------------------------------------------------------
    def test_patient_cannot_access_another_patient_recommendation_data(self):
        """Verifies Patient B cannot view Patient A's recommendation session data."""
        # Patient A logs in and submits
        self._login('patient_a@example.com', 'patient123')
        self.client.post('/patient/ai-specialist', data={'concern': 'Alice private migraine description'})

        # Patient B logs in
        self.client.get('/logout', follow_redirects=True)
        self._login('patient_b@example.com', 'patient123')
        res_b = self.client.get('/patient/ai-specialist')
        self.assertEqual(res_b.status_code, 200)
        self.assertNotIn(b'Alice private migraine description', res_b.data)

    def test_existing_hospital_and_doctor_discovery_still_works(self):
        """Verifies Phase 5 hospital discovery and doctor views remain functional."""
        self._login('patient_a@example.com', 'patient123')
        res_hosp = self.client.get('/patient/hospitals')
        self.assertEqual(res_hosp.status_code, 200)
        self.assertIn(b'Metro General Hospital', res_hosp.data)

        res_detail = self.client.get(f'/patient/hospitals/{self.hospital.id}')
        self.assertEqual(res_detail.status_code, 200)

        res_doc = self.client.get(f'/patient/doctors/{self.doc_cardio.id}')
        self.assertEqual(res_doc.status_code, 200)
        self.assertIn(b'Dr. Sarah Smith', res_doc.data)

    def test_existing_appointment_booking_and_pdf_qr_verification_still_works(self):
        """Verifies Phases 6, 7, and 8 booking, PDF download, and QR verification remain intact."""
        self._login('patient_a@example.com', 'patient123')

        # Book appointment
        target_date = date.today() + timedelta(days=5)
        # Ensure it falls on a working day (Mon/Wed/Fri for cardio)
        while target_date.strftime('%A') not in ['Monday', 'Wednesday', 'Friday']:
            target_date += timedelta(days=1)

        success, msg, appt = book_appointment(
            patient=self.patient_a,
            doctor_id=self.doc_cardio.id,
            hospital_id=self.hospital.id,
            appointment_date=target_date,
            time_slot='09:30 AM - 10:00 AM',
            symptoms='Post-recommendation cardiology check'
        )
        self.assertTrue(success)

        # PDF Download check
        pdf_res = self.client.get(f'/patient/appointments/{appt.id}/pdf')
        self.assertEqual(pdf_res.status_code, 200)
        self.assertEqual(pdf_res.headers.get('Content-Type'), 'application/pdf')

        # Public QR Verification check
        verify_res = self.client.get(f'/verify/appointment/{appt.verification_token}')
        self.assertEqual(verify_res.status_code, 200)
        self.assertIn(b'Appointment Verified', verify_res.data)

    def test_additional_specialty_mappings(self):
        """Verifies ENT, Dentistry, Gynecology, and Pediatrics mappings."""
        cases = [
            ('I have an earache, sore throat, and nasal congestion.', 'ENT'),
            ('I have a severe toothache and cavity with bleeding gums.', 'Dentistry'),
            ('Pregnancy checkup and severe menstrual period pain.', 'Gynecology'),
            ('My child has a high fever and pediatric cough.', 'Pediatrics')
        ]
        for text, expected in cases:
            rec = recommend_specialist(text)
            self.assertEqual(rec['status'], 'success')
            self.assertEqual(rec['recommended_specialty'], expected)


if __name__ == '__main__':
    unittest.main()
