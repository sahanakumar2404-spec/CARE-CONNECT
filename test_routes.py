import unittest
from app import create_app
from database import db
from models.user import User
from models.hospital import Hospital
from models.doctor import Doctor
from models.patient import Patient

class CareConnectTestCase(unittest.TestCase):
    def setUp(self):
        """Sets up an in-memory testing application context."""
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        """Cleans up the database and context."""
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def test_database_and_seed_data(self):
        """Verifies database tables exist and initial demo data is seeded."""
        admin = User.query.filter_by(role=User.ROLE_HOSPITAL).first()
        doctor = User.query.filter_by(role=User.ROLE_DOCTOR).first()
        patient = User.query.filter_by(role=User.ROLE_PATIENT).first()

        self.assertIsNotNone(admin, "Hospital admin user should be seeded")
        self.assertIsNotNone(doctor, "Doctor user should be seeded")
        self.assertIsNotNone(patient, "Patient user should be seeded")

        self.assertTrue(admin.check_password('admin123'))
        self.assertTrue(doctor.check_password('doctor123'))
        self.assertTrue(patient.check_password('patient123'))

        hospital = Hospital.query.first()
        self.assertIsNotNone(hospital, "Hospital entity should be seeded")

    def test_landing_page_loads(self):
        """Verifies public landing page returns HTTP 200 with platform branding."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Care', response.data)
        self.assertIn(b'Connect', response.data)
        self.assertIn(b'Intelligent Healthcare Coordination Platform', response.data)

    def test_about_page_loads(self):
        """Verifies about/architecture page loads successfully."""
        response = self.client.get('/about')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Care Connect Platform Architecture', response.data)

    def test_auth_protection_redirects(self):
        """Verifies unauthenticated access to dashboards redirects to login."""
        for path in ['/hospital/dashboard', '/doctor/dashboard', '/patient/dashboard']:
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 302, f"Path {path} should redirect unauthenticated user")
            self.assertIn('/login', response.headers.get('Location', ''))

    def test_hospital_dashboard_authenticated(self):
        """Verifies hospital dashboard loads for authenticated hospital user."""
        admin = User.query.filter_by(role=User.ROLE_HOSPITAL).first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['user_role'] = admin.role
            sess['user_name'] = admin.full_name
            sess['user_email'] = admin.email

        response = self.client.get('/hospital/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Hospital Management Hub', response.data)
        self.assertIn(b'Metro General Hospital', response.data)

    def test_doctor_dashboard_authenticated(self):
        """Verifies doctor dashboard loads for authenticated doctor."""
        doctor = User.query.filter_by(role=User.ROLE_DOCTOR).first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = doctor.id
            sess['user_role'] = doctor.role
            sess['user_name'] = doctor.full_name
            sess['user_email'] = doctor.email

        response = self.client.get('/doctor/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Doctor Dashboard', response.data)
        self.assertIn(b'Practicing Physician', response.data)

    def test_patient_dashboard_authenticated(self):
        """Verifies patient dashboard loads with AI triage and appointments."""
        patient = User.query.filter_by(role=User.ROLE_PATIENT).first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = patient.id
            sess['user_role'] = patient.role
            sess['user_name'] = patient.full_name
            sess['user_email'] = patient.email

        response = self.client.get('/patient/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Patient Portal', response.data)
        self.assertIn(b'AI Specialist Discovery', response.data)

    def test_ai_triage_api(self):
        """Verifies AI triage endpoint predicts specialization from symptoms."""
        patient = User.query.filter_by(role=User.ROLE_PATIENT).first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = patient.id
            sess['user_role'] = patient.role
            sess['user_name'] = patient.full_name
            sess['user_email'] = patient.email

        response = self.client.post(
            '/patient/ai-triage',
            json={'symptoms': 'severe chest pain and rapid palpitations'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['analysis']['recommended_specialty'], 'Cardiology')

if __name__ == '__main__':
    unittest.main()
