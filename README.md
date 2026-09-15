# Care Connect - AI-Enabled Healthcare Coordination Platform

**Care Connect** is a complete, secure, centralized healthcare coordination web application engineered to bridge the operational gap between **Hospital Administrations**, **Practicing Doctors**, and **Patients**.

---

## Key Problems Addressed

* **Fragmented Specialist Discovery**: Patients often struggle to determine the right medical specialist for their symptoms.
* **Manual Timetables & Queues**: Manual booking results in crowded waiting halls and schedule overlaps.
* **Lack of Centralized Records**: Disconnected hospital inventories, bed counts, and clinician registries.
* **Unverified Appointments**: Absence of digital proof or paper slips that get misplaced.
* **Limited Hospital Visibility**: Lack of high-level analytics on patient trends and department utilization.

---

## Core Technologies

- **Frontend**: HTML5, CSS3, JavaScript (ES6+), [Bootstrap 5.3](https://getbootstrap.com/), [Bootstrap Icons](https://icons.getbootstrap.com/), [Chart.js 4](https://www.chartjs.org/)
- **Backend**: Python 3.14, [Flask 3](https://flask.palletsprojects.com/)
- **Database**: SQLite with [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) ORM
- **AI & ML**: Modular Python NLP/ML triage system (`ai/triage.py`) with Scikit-Learn
- **Security & Verification**:
  - `werkzeug.security` (PBKDF2 SHA256 password hashing)
  - Secure session-based authentication with role-based access control (RBAC)
  - Dynamic QR-code generation for appointment verification (`qrcode`, `pillow`)
  - PDF generation foundation with `reportlab`

---

## User Roles & Capabilities

| User Role | Area / Portal | Capabilities |
| :--- | :--- | :--- |
| **Hospital Management** | `/hospital/dashboard` | Monitor hospital beds, view doctor rosters, track department consultation load via Chart.js, inspect recent appointments. |
| **Doctor** | `/doctor/dashboard` | Toggle live availability status ("Available" / "Off-Duty"), view scheduled patient consultation queues, review symptoms and appointment times. |
| **Patient** | `/patient/dashboard` | Run AI symptom triage to get automated specialist recommendations, explore available doctors, view appointments, and present scannable QR verification tokens. |

---

## Project Structure

```
CareConnect/
├── app.py                   # Flask application factory and entry point
├── config.py                # Configuration classes (Dev, Testing, Prod) & SQLite URI
├── requirements.txt         # Project dependencies
├── README.md                # Project documentation and run guide
├── .gitignore               # Git ignore rules
│
├── database/
│   ├── __init__.py          # SQLAlchemy extension and DB initializers
│   ├── seed.py              # Automatic seeding of demonstration accounts
│   └── careconnect.db       # SQLite database (auto-generated on first run)
│
├── models/
│   ├── __init__.py          # Model exports
│   ├── user.py              # User model with role helpers and password hashing
│   ├── hospital.py          # Hospital facility details & bed counts
│   ├── doctor.py            # Doctor specialization, fees, and schedule
│   ├── patient.py           # Patient profile, blood group, emergency contact
│   └── appointment.py       # Appointment tracking with UID and QR links
│
├── routes/
│   ├── __init__.py          # Blueprint registrations
│   ├── main.py              # Public landing page, about, and QR serving
│   ├── auth.py              # Login, patient registration, and logout
│   ├── hospital.py          # Hospital management dashboard routes
│   ├── doctor.py            # Doctor dashboard and availability toggle
│   └── patient.py           # Patient dashboard and AI triage endpoint
│
├── services/
│   ├── __init__.py
│   └── auth_service.py      # Session management and @role_required decorators
│
├── ai/
│   ├── __init__.py
│   └── triage.py            # Modular AI symptom analysis and specialty mapping
│
├── templates/
│   ├── base.html            # Master layout with navbar, alerts, footer
│   ├── index.html           # Modern public landing page with live stats
│   ├── about.html           # Project architecture and evaluation guide
│   ├── 404.html             # 404 error page
│   ├── 500.html             # 500 error page
│   ├── auth/
│   │   ├── login.html       # Login screen with 1-click evaluation fill buttons
│   │   └── register.html    # Patient registration form
│   ├── dashboards/
│   │   ├── hospital.html    # Hospital Management dashboard with Chart.js
│   │   ├── doctor.html      # Doctor dashboard with patient queue
│   │   └── patient.html     # Patient dashboard with AI widget & QR pass
│   └── components/
│       ├── navbar.html      # Role-aware navigation bar
│       └── footer.html      # Professional footer
│
├── static/
│   ├── css/
│   │   └── style.css        # Healthcare theme styling
│   ├── js/
│   │   └── main.js          # Chart init, demo-fill, and AI triage client logic
│   └── images/              # Assets
│
├── utils/
│   ├── __init__.py
│   └── helpers.py           # QR Code generator and date formatters
│
├── generated/
│   ├── qr_codes/            # Auto-generated verification QR code PNGs
│   └── reports/             # Generated PDF appointment slips
│
└── tests/
    ├── __init__.py
    └── test_routes.py       # Automated test suite
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.14)
- Git (optional)

### 2. Environment Setup

Clone or open the project folder in your terminal:
```bash
cd CareConnect
```

Create and activate a virtual environment:
- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

Install the dependencies:
```bash
pip install -r requirements.txt
```

### 3. Run the Application

Start the Flask server:
```bash
python app.py
```

Open your browser and navigate to:
```
http://127.0.0.1:5000/
```

> **Note**: On the very first launch, Care Connect will automatically create `database/careconnect.db` and populate it with sample hospitals, doctors, patients, and scheduled appointments.

---

## Multi-Role Registration & Access Routes

| Role | Registration Route | Login Route | Primary Dashboard |
| :--- | :--- | :--- | :--- |
| **Hospital Facility** | `/register/hospital` | `/login?role=hospital` | `/hospital/dashboard` |
| **Practicing Doctor** | `/register/doctor` | `/login?role=doctor` | `/doctor/dashboard` |
| **Patient** | `/register/patient` (or `/register`) | `/login?role=patient` | `/patient/dashboard` |

---

## Evaluation Credentials (Pre-Seeded)

The login screen (`/login`) includes **1-Click Evaluation Fill buttons** for effortless testing.

| Role | Username / Email | Password | Direct Dashboard Route |
| :--- | :--- | :--- | :--- |
| **Hospital Admin** | `admin@careconnect.org` | `admin123` | `/hospital/dashboard` |
| **Doctor** | `dr.smith@careconnect.org` | `doctor123` | `/doctor/dashboard` |
| **Patient** | `patient@careconnect.org` | `patient123` | `/patient/dashboard` |

---

## Running Automated Tests

Run the complete Phase 1 and Phase 2 test suites:
```bash
# Run all tests across the project (20 tests)
python -m unittest discover -s tests

# Or run individual test suites:
python -m unittest tests/test_routes.py
python -m unittest tests/test_phase2_auth.py
```
Expected output:
```
Ran 20 tests in ...s
OK
```

---

## Academic Verification Checklist

### Phase 1: Foundation & Modular Architecture
- [x] Clean modular project structure matching requirements.
- [x] Flask application factory entry point (`app.py`).
- [x] SQLite database configuration with SQLAlchemy models (`models/`).
- [x] Multi-role architecture: Hospital Management, Doctor, Patient.
- [x] Modern, responsive landing page (`/`) with live platform metrics.
- [x] Role-protected dashboard routes for all three user personas.
- [x] Modular AI triage module (`ai/triage.py`) with interactive UI.
- [x] Digital appointment QR code generator (`utils/helpers.py`).

### Phase 2: Secure Authentication & Multi-Role Registration
- [x] Dedicated Hospital Facility registration (`/register/hospital`) with license, type, contact, and address.
- [x] Dedicated Doctor onboarding (`/register/doctor`) with specialization, qualifications, and hospital affiliation.
- [x] Dedicated Patient registration (`/register/patient`) with DOB, gender, mobile, and address.
- [x] Password hashing using PBKDF2 SHA-256 (`werkzeug.security`).
- [x] Session-based authentication with role-based access control decorators (`@role_required`).
- [x] Strict cross-tenant data isolation preventing unauthorized access across accounts.
- [x] Validation against duplicate emails, registration numbers, and invalid email formats.
- [x] Secure logout clearing session and protecting private routes.
- [x] 100% automated test pass rate across 20 unit and integration tests.
