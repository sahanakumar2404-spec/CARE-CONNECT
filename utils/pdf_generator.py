import io
import os
from datetime import datetime, timezone

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable
)
from utils.qr_generator import get_or_create_appointment_qr

# Primary Brand Colors
COLOR_PRIMARY = colors.HexColor("#0f766e")       # Deep Teal
COLOR_PRIMARY_DARK = colors.HexColor("#115e59")  # Dark Teal
COLOR_SECONDARY = colors.HexColor("#0284c7")     # Sky Blue
COLOR_TEXT_MAIN = colors.HexColor("#1e293b")     # Slate 800
COLOR_TEXT_MUTED = colors.HexColor("#64748b")    # Slate 500
COLOR_BG_LIGHT = colors.HexColor("#f8fafc")      # Slate 50
COLOR_BORDER = colors.HexColor("#e2e8f0")        # Slate 200
COLOR_SUCCESS_BG = colors.HexColor("#dcfce7")    # Green 100
COLOR_SUCCESS_TEXT = colors.HexColor("#166534")  # Green 800


def generate_appointment_pdf(appointment, output_path: str = None, base_url: str = None) -> bytes:
    """
    Generates a professional healthcare appointment confirmation PDF using ReportLab.
    Returns the generated PDF as bytes, and optionally saves it to output_path.
    Uses pageCompression=0 so generated streams remain directly verifiable.
    """
    buffer = io.BytesIO()
    
    # Configure document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        pageCompression=0  # Direct uncompressed streams for speed and testability
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=COLOR_PRIMARY
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=COLOR_TEXT_MUTED
    )

    header_right_style = ParagraphStyle(
        'HeaderRight',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        alignment=2, # Right
        textColor=COLOR_PRIMARY_DARK
    )

    badge_style = ParagraphStyle(
        'StatusBadge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=2,
        textColor=COLOR_SUCCESS_TEXT
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=COLOR_PRIMARY
    )

    label_style = ParagraphStyle(
        'FieldLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=COLOR_TEXT_MUTED
    )

    value_style = ParagraphStyle(
        'FieldValue',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=COLOR_TEXT_MAIN
    )

    bold_value_style = ParagraphStyle(
        'FieldBoldValue',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=COLOR_TEXT_MAIN
    )

    instruction_title_style = ParagraphStyle(
        'InstructionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=COLOR_PRIMARY_DARK
    )

    instruction_text_style = ParagraphStyle(
        'InstructionText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=COLOR_TEXT_MAIN
    )

    footer_style = ParagraphStyle(
        'FooterNotice',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        alignment=1, # Center
        textColor=COLOR_TEXT_MUTED
    )

    # Safe extraction of entity fields
    patient_obj = appointment.patient
    patient_user = patient_obj.user if patient_obj else None
    patient_name = patient_user.full_name if patient_user else "Patient"
    patient_phone = (patient_user.phone if patient_user and patient_user.phone else None) or (patient_obj.emergency_contact if patient_obj else None) or "Not Provided"

    doctor_obj = appointment.doctor
    doctor_user = doctor_obj.user if doctor_obj else None
    raw_doc_name = doctor_user.full_name if doctor_user else "Assigned Physician"
    doctor_name = raw_doc_name if raw_doc_name.startswith("Dr.") else f"Dr. {raw_doc_name}"
    doctor_spec = doctor_obj.specialization if doctor_obj else "Specialist"
    room_number = (doctor_obj.room_number if doctor_obj and doctor_obj.room_number else "Consultation Suite")

    hospital_obj = appointment.hospital
    hospital_name = hospital_obj.name if hospital_obj else "Care Connect Partner Hospital"
    hospital_addr = hospital_obj.address if hospital_obj else "Medical Center"
    hospital_city = hospital_obj.city if hospital_obj else ""
    hospital_loc = f"{hospital_addr}, {hospital_city}" if hospital_city else hospital_addr

    appt_num = appointment.appointment_number or f"CC-{appointment.id:06d}"
    appt_status = (appointment.status or "CONFIRMED").upper()
    
    if appointment.appointment_date:
        appt_date_str = appointment.appointment_date.strftime("%A, %B %d, %Y")
    else:
        appt_date_str = "Scheduled Date"
        
    time_slot_str = appointment.time_slot or "Scheduled Slot"
    
    if appointment.created_at:
        booked_on_str = appointment.created_at.strftime("%Y-%m-%d %H:%M UTC")
    else:
        booked_on_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    symptoms_text = appointment.symptoms or "General Clinical Consultation"

    # Ensure QR Code exists
    _, qr_filepath = get_or_create_appointment_qr(appointment, base_url=base_url)

    story = []

    # 1. Header Bar Table
    header_data = [
        [
            Paragraph("Care Connect", title_style),
            Paragraph(f"Appointment Pass<br/><b>{appt_num}</b>", header_right_style)
        ],
        [
            Paragraph("AI Healthcare Coordination Platform &bull; Digital Verification System", subtitle_style),
            Paragraph(f"<font color='{COLOR_SUCCESS_TEXT.hexval()}'>● {appt_status}</font>", badge_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[3.8 * inch, 3.7 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY, spaceBefore=4, spaceAfter=14))

    # 2. Appointment Summary Box
    summary_data = [
        [
            Paragraph("APPOINTMENT DATE", label_style),
            Paragraph("TIME SLOT", label_style),
            Paragraph("STATUS", label_style),
            Paragraph("BOOKED ON", label_style)
        ],
        [
            Paragraph(appt_date_str, bold_value_style),
            Paragraph(time_slot_str, bold_value_style),
            Paragraph(f"<b>{appt_status}</b>", bold_value_style),
            Paragraph(booked_on_str, value_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[2.2 * inch, 1.8 * inch, 1.5 * inch, 2.0 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # 3. Two-column details: Patient Info & Doctor/Facility Info
    details_col1 = [
        [Paragraph("PATIENT DETAILS", section_heading), ""],
        [Paragraph("Full Name:", label_style), Paragraph(patient_name, bold_value_style)],
        [Paragraph("Mobile / Phone:", label_style), Paragraph(patient_phone, value_style)],
        [Paragraph("Emergency Contact:", label_style), Paragraph(getattr(patient_obj, 'emergency_contact', None) or "On File", value_style)],
        [Paragraph("Blood Group:", label_style), Paragraph(getattr(patient_obj, 'blood_group', None) or "Not recorded", value_style)],
    ]

    details_col2 = [
        [Paragraph("HOSPITAL & PHYSICIAN", section_heading), ""],
        [Paragraph("Doctor:", label_style), Paragraph(doctor_name, bold_value_style)],
        [Paragraph("Specialization:", label_style), Paragraph(doctor_spec, value_style)],
        [Paragraph("Hospital:", label_style), Paragraph(hospital_name, bold_value_style)],
        [Paragraph("Location:", label_style), Paragraph(hospital_loc, value_style)],
        [Paragraph("Room / Wing:", label_style), Paragraph(room_number, value_style)],
    ]

    t_col1 = Table(details_col1, colWidths=[1.3 * inch, 2.3 * inch])
    t_col1.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('LINEBELOW', (0, 0), (1, 0), 1, COLOR_PRIMARY),
        ('BOTTOMPADDING', (0, 0), (1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))

    t_col2 = Table(details_col2, colWidths=[1.2 * inch, 2.5 * inch])
    t_col2.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('LINEBELOW', (0, 0), (1, 0), 1, COLOR_PRIMARY),
        ('BOTTOMPADDING', (0, 0), (1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))

    two_col_table = Table([[t_col1, t_col2]], colWidths=[3.7 * inch, 3.8 * inch])
    two_col_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(two_col_table)
    story.append(Spacer(1, 14))

    # 4. Reason for Visit / Symptoms Box
    symptoms_data = [
        [Paragraph("REASON FOR VISIT / CLINICAL NOTES", section_heading)],
        [Paragraph(symptoms_text, value_style)]
    ]
    symptoms_table = Table(symptoms_data, colWidths=[7.5 * inch])
    symptoms_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(symptoms_table)
    story.append(Spacer(1, 14))

    # 5. Verification QR Code + Arrival Instructions Side-by-Side
    qr_img = Image(qr_filepath, width=1.5 * inch, height=1.5 * inch)
    
    instructions_content = [
        Paragraph("Important Arrival Instructions & Hospital Check-in", instruction_title_style),
        Spacer(1, 4),
        Paragraph("&bull; <b>Arrive Early:</b> Please arrive at the hospital reception 15 minutes before your scheduled slot.", instruction_text_style),
        Paragraph("&bull; <b>Identification:</b> Present a valid government-issued photo ID and this digital appointment slip.", instruction_text_style),
        Paragraph("&bull; <b>Medical Records:</b> Bring any previous medical prescriptions, lab reports, and medication lists.", instruction_text_style),
        Paragraph("&bull; <b>QR Verification:</b> Hospital staff will scan the verification QR code at the reception desk to confirm eligibility.", instruction_text_style),
        Paragraph("&bull; <b>Cancellation:</b> If you cannot attend, please reschedule or cancel through your portal at least 2 hours in advance.", instruction_text_style),
    ]

    qr_caption = Paragraph("<b>Digital Verification QR</b><br/><font size=7.5 color='#64748b'>Scan at hospital desk</font>", ParagraphStyle('QRCaption', parent=styles['Normal'], alignment=1, fontSize=8, leading=10))

    qr_cell = [
        qr_img,
        Spacer(1, 4),
        qr_caption
    ]

    verification_table = Table(
        [[qr_cell, instructions_content]],
        colWidths=[1.8 * inch, 5.7 * inch]
    )
    verification_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(KeepTogether([verification_table]))
    story.append(Spacer(1, 18))

    # 6. Footer Disclaimer & Barcode-style rule
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceBefore=4, spaceAfter=8))
    footer_text = (
        "This is an official digital appointment confirmation issued by Care Connect AI Healthcare Coordination Platform. "
        "Secure verification token is embedded in the digital QR code. For emergency care, proceed directly to the nearest hospital Emergency Room."
    )
    story.append(Paragraph(footer_text, footer_style))

    # Build PDF document
    doc.build(story)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

    return pdf_bytes
