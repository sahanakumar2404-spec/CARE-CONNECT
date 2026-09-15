# Care Connect — Sample Demonstration Data

This directory contains reference demonstration records and seed data schemas for Care Connect.

## 1. Demonstration Accounts & Credentials

| Role | Email | Password | Associated Profile |
| :--- | :--- | :--- | :--- |
| **Hospital Admin** | `admin@careconnect.org` | `admin123` | Metro General Hospital & Research Center |
| **Doctor (Cardiology)** | `dr.smith@careconnect.org` | `doctor123` | Dr. Sarah Smith, MD, FACC |
| **Doctor (Pediatrics)** | `dr.patel@careconnect.org` | `doctor123` | Dr. Rajesh Patel, MBBS, DCH |
| **Doctor (Neurology)** | `dr.chen@careconnect.org` | `doctor123` | Dr. Michael Chen, MD, DM |
| **Patient** | `patient@careconnect.org` | `patient123` | John Doe (Blood Group: O+) |

## 2. Seeded Records Overview

- **Users:** 5 accounts (1 Hospital Administrator, 3 Doctors, 1 Patient)
- **Hospitals:** 1 multispecialty teaching facility (320 beds, 78 available)
- **Specializations Covered:** Cardiology, Pediatrics, Neurology, Dermatology, Orthopedics, Ophthalmology, ENT, General Medicine
- **Appointments:** Active confirmed consultation passes with unique tracking numbers (`CC-2026-000001`), verification tokens, ReportLab PDFs, and digital QR codes.

## 3. Data File

- `sample_dataset.json`: Structured JSON dump of active demonstration records reflecting the production SQLite database state.
