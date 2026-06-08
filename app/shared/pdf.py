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
        [invoice.client_name, f"${invoice.ex_gst_amount:.2f}"]
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
