"""
PDF generation utilities.

Provides reusable PDF generation for invoices.
"""

import io
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image


def generate_invoice_pdf(user, invoice):
    """
    Generate a PDF for an invoice and return as bytes buffer.

    Args:
        user: User object (with business details and logo)
        invoice: Invoice object (with customer)

    Returns:
        BytesIO buffer positioned at the start of the PDF data
    """
    from reportlab.lib.enums import TA_RIGHT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()

    logo_cell = []
    if user.logo_path and os.path.exists(user.logo_path):
        try:
            logo_img = Image(user.logo_path, width=4*cm, height=2*cm, kind='proportional')
            logo_cell.append(logo_img)
        except Exception:
            pass

    business_paragraphs = []
    if user.business_name:
        business_paragraphs.append(f'<b>{user.business_name}</b>')
    if user.abn:
        business_paragraphs.append(f'ABN: {user.abn}')
    if user.address:
        business_paragraphs.append(user.address.replace(chr(10), '<br/>'))
    if user.contact_email:
        business_paragraphs.append(f'Email: {user.contact_email}')
    if user.contact_number:
        business_paragraphs.append(f'Phone: {user.contact_number}')

    business_style = ParagraphStyle('Business', parent=styles['Normal'], fontSize=9, alignment=TA_RIGHT, leading=12)
    business_cell = [Paragraph('<br/>'.join(business_paragraphs), business_style)] if business_paragraphs else ['']

    business_name_style = ParagraphStyle(
        'BusinessName', parent=styles['Heading2'],
        fontSize=20, alignment=0, leading=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=0, spaceBefore=0
    )
    business_name_cell = [Paragraph(user.business_name, business_name_style)] if user.business_name else ['']

    header_data = [
        [logo_cell, business_cell],
        [business_name_cell, '']
    ]
    header_table = Table(header_data, colWidths=[8*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING', (0, 1), (0, 1), 6),
        ('BOTTOMPADDING', (0, 1), (0, 1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*cm))

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=28, spaceAfter=0, alignment=0, textColor=colors.HexColor('#2c3e50'))
    title_cell = Paragraph('INVOICE', title_style)

    invoice_title_row = Table([[title_cell, '']], colWidths=[12*cm, 4*cm])
    invoice_title_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, colors.HexColor('#2c3e50')),
    ]))
    elements.append(invoice_title_row)
    elements.append(Spacer(1, 0.5*cm))

    info_data = [
        ['Invoice Date:', str(invoice.invoice_date), 'Invoice #:', invoice.id[:8].upper()],
        ['Due Date:', str(invoice.due_date) if invoice.due_date else 'N/A', '', '']
    ]
    info_table = Table(info_data, colWidths=[3*cm, 5*cm, 3*cm, 5*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*cm))

    elements.append(Paragraph('<b>Bill To:</b>', styles['Heading3']))
    customer_info = f"<b>{invoice.customer.name}</b><br/>"
    if invoice.customer.contact_name:
        customer_info += f"Attn: {invoice.customer.contact_name}<br/>"
    if invoice.customer.address:
        customer_info += f"{invoice.customer.address.replace(chr(10), '<br/>')}<br/>"
    if invoice.customer.contact_email:
        customer_info += f"Email: {invoice.customer.contact_email}<br/>"
    if invoice.customer.contact_number:
        customer_info += f"Phone: {invoice.customer.contact_number}<br/>"
    if invoice.customer.abn:
        customer_info += f"ABN: {invoice.customer.abn}<br/>"
    elements.append(Paragraph(customer_info, styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))

    if invoice.description:
        elements.append(Paragraph('<b>Description:</b>', styles['Heading3']))
        elements.append(Paragraph(invoice.description, styles['Normal']))
        elements.append(Spacer(1, 0.5*cm))

    items_data = [
        ['Description', 'Amount'],
        [invoice.description or 'Services', f"${invoice.ex_gst_amount:.2f}"]
    ]
    items_table = Table(items_data, colWidths=[12*cm, 4*cm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.3*cm))

    totals_data = [
        ['Subtotal (ex GST):', f"${invoice.ex_gst_amount:.2f}"],
        [f'GST ({float(invoice.gst_type)*100:.0f}%):', f"${invoice.gst_amount:.2f}"],
        ['TOTAL:', f"${invoice.total_amount:.2f}"]
    ]
    totals_table = Table(totals_data, colWidths=[12*cm, 4*cm])
    totals_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
    ]))
    elements.append(totals_table)

    if invoice.customer.gst and user.abn:
        elements.append(Spacer(1, 1*cm))
        payment_terms = user.payment_terms if user.payment_terms else 14
        elements.append(Paragraph(
            f'<i>Payment terms: Net {payment_terms} days. Please include invoice number {invoice.id[:8].upper()} on payment.</i>',
            styles['Normal']
        ))

    if user.bank_name or user.account_name or user.account_number or user.bsb:
        elements.append(Spacer(1, 0.7*cm))
        elements.append(Paragraph('<b>Bank Details:</b>', styles['Heading3']))
        bank_details = []
        if user.bank_name:
            bank_details.append(f'Bank: {user.bank_name}')
        if user.account_name:
            bank_details.append(f'Account Name: {user.account_name}')
        if user.bsb:
            bank_details.append(f'BSB: {user.bsb}')
        if user.account_number:
            bank_details.append(f'Account Number: {user.account_number}')
        elements.append(Paragraph('<br/>'.join(bank_details), styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_payslip_pdf(user, employee, pay_event, lines=None, business_name=None, abn=None, address=None):
    """
    Generate a payslip PDF (server-side replacement for the fpdf2 scripts in
    ~/evie/payroll/jessica-paul/). Uses ReportLab (already a dep) rather than
    fpdf2 because ReportLab is already loaded in the app process.

    Layout mirrors the manual payslips Jessica has been receiving:
      - PAY SLIP title
      - employer header (business name / ABN / address / phone / email)
      - employee/pay block (name, position, TFN, pay period, payment date, pay frequency)
      - Earnings & deductions table (Gross / PAYG / Net)
      - Superannuation (paid separately)
      - Payment details (bank ref, payment method)

    Args:
        user:        User row (for context — currently unused beyond defaults)
        employee:    Employee row. The TFN is decrypted here (server-side).
        pay_event:   PayEvent row.
        lines:       Optional list of PayEventLine rows. If None, builds a
                     3-row breakdown from the headline gross/payg/net.
        business_name/abn/address: optional overrides (default to user.business_name etc.)

    Returns:
        BytesIO buffer at position 0.
    """
    from reportlab.lib.enums import TA_RIGHT

    biz = business_name or (user.business_name if user else None) or 'Employer'
    biz_abn = abn or (user.abn if user else None) or ''
    biz_addr = address or (user.address if user else None) or ''
    biz_email = (user.contact_email if user else None) or ''
    biz_phone = (user.contact_number if user else None) or ''

    tfn_plain = employee.tfn_plain if employee is not None else None
    position = pay_event.position_snapshot or (employee.position if employee else None) or ''
    legal_name = employee.legal_name if employee else ''
    preferred_name = employee.preferred_name if employee else ''
    name_for_payslip = preferred_name or legal_name

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # ----- Header -----
    title_style = ParagraphStyle(
        'PayslipTitle', parent=styles['Heading1'],
        fontSize=24, alignment=0, leading=28,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=4,
    )
    elements.append(Paragraph('PAY SLIP', title_style))

    header_style = ParagraphStyle(
        'HeaderMeta', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#7f8c8d'), leading=12,
    )
    header_bits = [biz]
    if biz_abn:
        header_bits.append(f'ABN {biz_abn}')
    if biz_addr:
        header_bits.append(biz_addr.replace(chr(10), ', '))
    header_line = ' \u00b7 '.join([b for b in header_bits if b])
    elements.append(Paragraph(header_line, header_style))
    if biz_phone or biz_email:
        contact_bits = []
        if biz_phone:
            contact_bits.append(f'Phone {biz_phone}')
        if biz_email:
            contact_bits.append(biz_email)
        elements.append(Paragraph(' \u00b7 '.join(contact_bits), header_style))
    elements.append(Spacer(1, 0.4*cm))

    # ----- Employee / pay block -----
    label_w = 4*cm
    val_w = 5*cm
    def row(left_label, left_val, right_label, right_val):
        cell_style_l = ParagraphStyle('LblL', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#7f8c8d'))
        cell_style_v = ParagraphStyle('ValV', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold')
        return [Paragraph(left_label, cell_style_l), Paragraph(str(left_val), cell_style_v),
                Paragraph(right_label, cell_style_l), Paragraph(str(right_val), cell_style_v)]

    info_rows = [
        row('Employee',    name_for_payslip, 'Pay period',   f"{pay_event.pay_period_start} \u2013 {pay_event.pay_period_end}"),
        row('Position',    position,        'Payment date', str(pay_event.payment_date)),
        row('TFN',         tfn_plain or '', 'Pay frequency', pay_event.pay_frequency),
    ]
    info_table = Table(info_rows, colWidths=[label_w, val_w, label_w, val_w])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*cm))

    # ----- Earnings & deductions -----
    section_style = ParagraphStyle(
        'Section', parent=styles['Heading3'], fontSize=11,
        textColor=colors.HexColor('#2c3e50'), spaceBefore=4, spaceAfter=4,
    )
    elements.append(Paragraph('Earnings &amp; deductions', section_style))

    # Use provided lines if any, else build a 3-row breakdown.
    if lines:
        rendered_lines = []
        for ln in lines:
            rendered_lines.append([ln.description or ln.line_type, f"${float(ln.amount):,.2f}"])
    else:
        rendered_lines = [
            ['Gross wages', f"${float(pay_event.gross_amount):,.2f}"],
            ['PAYG tax withheld', f"-${float(pay_event.payg_tax_amount):,.2f}"],
            ['Net pay deposited', f"${float(pay_event.net_amount):,.2f}"],
        ]

    items_data = [['Description', 'Amount (AUD)']] + rendered_lines
    items_table = Table(items_data, colWidths=[12*cm, 4*cm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#34495e')),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#2c3e50')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.3*cm))

    # ----- Superannuation (paid separately) -----
    super_pct = float(employee.super_rate_pct) if employee and employee.super_rate_pct is not None else 12.0
    elements.append(Paragraph('Superannuation (paid separately)', section_style))
    super_data = [
        ['Description', 'Amount (AUD)'],
        [f"Superannuation contribution @ {super_pct:.2f}% OTE", f"${float(pay_event.super_payable_amount):,.2f}"],
    ]
    super_table = Table(super_data, colWidths=[12*cm, 4*cm])
    super_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(super_table)

    fund_name = employee.super_fund_name if employee and employee.super_fund_name else "Employee's nominated super fund"
    paid_to_style = ParagraphStyle('PaidTo', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#7f8c8d'))
    elements.append(Spacer(1, 0.15*cm))
    elements.append(Paragraph(f'Paid to: {fund_name}', paid_to_style))
    elements.append(Spacer(1, 0.4*cm))

    # ----- Payment details -----
    elements.append(Paragraph('Payment details', section_style))
    pay_rows = [
        ['Bank reference', pay_event.bank_reference or '—'],
        ['Payment method', 'Direct deposit'],
    ]
    pay_table = Table(pay_rows, colWidths=[4*cm, 12*cm])
    pay_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(pay_table)
    elements.append(Spacer(1, 0.6*cm))

    # ----- Footer -----
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontSize=8,
        textColor=colors.HexColor('#7f8c8d'), leading=10,
    )
    elements.append(Paragraph(
        'This pay slip has been issued in accordance with the Fair Work Act 2009 '
        'and complies with the requirements of section 536. Payslip details are '
        'kept private and stored for 7 years as required by the Fair Work Regulations 2009.',
        footer_style,
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer
