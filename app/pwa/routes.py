from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from datetime import date
from decimal import Decimal
import os
import uuid
import base64
from PIL import Image
from io import BytesIO

from app.models import db
from app.models.user import User
from app.models.expense import Expense
from app.models.activity_log import ActivityLog
from app.models.ocr_queue import OcrQueue

pwa_bp = Blueprint('pwa', __name__, url_prefix='/pwa')


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'pwa_user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('pwa.pwa_login'))
        return f(*args, **kwargs)
    return decorated_function


@pwa_bp.route('/')
@login_required
def index():
    return render_template('pwa/index.html')


@pwa_bp.route('/login', methods=['GET', 'POST'])
def pwa_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('pwa/login.html')

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password', 'error')
            return render_template('pwa/login.html')

        session['pwa_user_id'] = user.id
        session['pwa_user_email'] = user.email
        flash('Logged in successfully', 'success')
        return redirect(url_for('pwa.index'))

    return render_template('pwa/login.html')


@pwa_bp.route('/logout')
def pwa_logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('pwa.pwa_login'))


@pwa_bp.route('/capture')
@login_required
def capture():
    return render_template('pwa/capture.html')


@pwa_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    user_id = session['pwa_user_id']

    image_data = request.form.get('image_data')

    if not image_data:
        flash('No image captured', 'error')
        return redirect(url_for('pwa.capture'))

    try:
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)

        image = Image.open(BytesIO(image_bytes))
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')

        upload_folder = os.path.join('uploads', 'receipts')
        os.makedirs(upload_folder, exist_ok=True)

        filename = f'{uuid.uuid4()}.jpg'
        filepath = os.path.join(upload_folder, filename)
        image.save(filepath, 'JPEG', quality=85)

        expense = Expense(
            user_id=user_id,
            vendor_name='Pending OCR',
            description='',
            ex_gst_amount=Decimal('0'),
            gst_amount=Decimal('0'),
            gst_type=Decimal('0.1'),
            total_amount=Decimal('0'),
            expense_date=date.today(),
            attachment_path=filepath
        )

        db.session.add(expense)
        db.session.flush()

        ocr_job = OcrQueue(
            expense_id=expense.id,
            image_path=filepath,
            status='pending'
        )
        db.session.add(ocr_job)

        log = ActivityLog(
            user_id=user_id,
            action='CREATE',
            table_name='expenses',
            record_id=expense.id,
            new_values=expense.to_dict(),
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        flash('Receipt uploaded. OCR processing will extract details.', 'success')
        return redirect(url_for('pwa.index'))

    except Exception as e:
        flash(f'Error processing image: {str(e)}', 'error')
        return redirect(url_for('pwa.capture'))
