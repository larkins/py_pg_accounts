from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
import os
import io

from app.models import db
from app.models.user import User
from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.account_category import AccountCategory
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.shared.decorators import api_key_required, log_activity
from app.shared.validators import validate_decimal, validate_date_string, validate_gst_type, validate_uuid

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    country = data.get('country', 'AU')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(email=email, country=country)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'User registered successfully', 'user': user.to_dict()}), 201


@api_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401

    return jsonify({'message': 'Login successful', 'user': user.to_dict()}), 200


@api_bp.route('/auth/api-key', methods=['POST'])
@api_key_required
def generate_api_key():
    user = request.current_user
    api_key = user.generate_api_key()
    db.session.commit()

    return jsonify({'message': 'API key generated', 'api_key': api_key}), 200


@api_bp.route('/account-categories', methods=['GET'])
@api_key_required
def list_account_categories():
    categories = AccountCategory.query.order_by(AccountCategory.name).all()
    return jsonify({'account_categories': [c.to_dict() for c in categories]}), 200


@api_bp.route('/account-categories', methods=['POST'])
@api_key_required
def create_account_category():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    category = AccountCategory(name=name, description=data.get('description', ''))
    db.session.add(category)
    db.session.commit()

    log_activity(
        user_id=request.current_user.id,
        action='CREATE',
        table_name='account_categories',
        record_id=category.id,
        new_values=category.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Account category created', 'account_category': category.to_dict()}), 201


@api_bp.route('/account-categories/<category_id>', methods=['PUT'])
@api_key_required
def update_account_category(category_id):
    if not validate_uuid(category_id):
        return jsonify({'error': 'Invalid category ID'}), 400

    category = AccountCategory.query.get(category_id)
    if not category:
        return jsonify({'error': 'Account category not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    old_values = category.to_dict()

    if 'name' in data:
        category.name = data['name'].strip()
    if 'description' in data:
        category.description = data['description']

    log_activity(
        user_id=request.current_user.id,
        action='UPDATE',
        table_name='account_categories',
        record_id=category.id,
        old_values=old_values,
        new_values=category.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Account category updated', 'account_category': category.to_dict()}), 200


@api_bp.route('/account-categories/<category_id>', methods=['DELETE'])
@api_key_required
def delete_account_category(category_id):
    if not validate_uuid(category_id):
        return jsonify({'error': 'Invalid category ID'}), 400

    category = AccountCategory.query.get(category_id)
    if not category:
        return jsonify({'error': 'Account category not found'}), 404

    old_values = category.to_dict()

    log_activity(
        user_id=request.current_user.id,
        action='DELETE',
        table_name='account_categories',
        record_id=category.id,
        old_values=old_values,
        ip_address=request.remote_addr
    )

    db.session.delete(category)
    db.session.commit()

    return jsonify({'message': 'Account category deleted'}), 200


@api_bp.route('/customers', methods=['GET'])
@api_key_required
def list_customers():
    customers = Customer.query.order_by(Customer.name).all()
    return jsonify({'customers': [c.to_dict() for c in customers]}), 200


@api_bp.route('/customers/<customer_id>', methods=['GET'])
@api_key_required
def get_customer(customer_id):
    if not validate_uuid(customer_id):
        return jsonify({'error': 'Invalid customer ID'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    return jsonify({'customer': customer.to_dict()}), 200


@api_bp.route('/customers', methods=['POST'])
@api_key_required
def create_customer():
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    customer = Customer(
        name=name,
        contact_name=data.get('contact_name'),
        address=data.get('address'),
        contact_email=data.get('contact_email'),
        abn=data.get('abn'),
        contact_number=data.get('contact_number'),
        gst=data.get('gst', True)
    )
    db.session.add(customer)
    db.session.commit()

    log_activity(
        user_id=request.current_user.id,
        action='CREATE',
        table_name='customers',
        record_id=customer.id,
        new_values=customer.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Customer created', 'customer': customer.to_dict()}), 201


@api_bp.route('/customers/<customer_id>', methods=['PUT'])
@api_key_required
def update_customer(customer_id):
    if not validate_uuid(customer_id):
        return jsonify({'error': 'Invalid customer ID'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    old_values = customer.to_dict()

    if 'name' in data:
        new_name = data['name'].strip()
        if not new_name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        customer.name = new_name
    if 'contact_name' in data:
        customer.contact_name = data['contact_name']
    if 'address' in data:
        customer.address = data['address']
    if 'contact_email' in data:
        customer.contact_email = data['contact_email']
    if 'abn' in data:
        customer.abn = data['abn']
    if 'contact_number' in data:
        customer.contact_number = data['contact_number']
    if 'gst' in data:
        customer.gst = data['gst']

    log_activity(
        user_id=request.current_user.id,
        action='UPDATE',
        table_name='customers',
        record_id=customer.id,
        old_values=old_values,
        new_values=customer.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Customer updated', 'customer': customer.to_dict()}), 200


@api_bp.route('/customers/<customer_id>', methods=['DELETE'])
@api_key_required
def delete_customer(customer_id):
    if not validate_uuid(customer_id):
        return jsonify({'error': 'Invalid customer ID'}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    if customer.invoices.first():
        return jsonify({'error': 'Cannot delete customer with existing invoices'}), 400

    old_values = customer.to_dict()

    log_activity(
        user_id=request.current_user.id,
        action='DELETE',
        table_name='customers',
        record_id=customer.id,
        old_values=old_values,
        ip_address=request.remote_addr
    )

    db.session.delete(customer)
    db.session.commit()

    return jsonify({'message': 'Customer deleted'}), 200


@api_bp.route('/expenses', methods=['GET'])
@api_key_required
def list_expenses():
    user = request.current_user

    query = Expense.query.filter_by(user_id=user.id)

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date:
        try:
            start = validate_date_string(start_date)
            query = query.filter(Expense.expense_date >= start)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    if end_date:
        try:
            end = validate_date_string(end_date)
            query = query.filter(Expense.expense_date <= end)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    expenses = query.order_by(Expense.expense_date.desc()).all()
    return jsonify({'expenses': [e.to_dict() for e in expenses]}), 200


@api_bp.route('/expenses', methods=['POST'])
@api_key_required
def create_expense():
    user = request.current_user
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        vendor_name = data.get('vendor_name', '').strip()
        if not vendor_name:
            return jsonify({'error': 'Vendor name is required'}), 400

        amount = data.get('amount') or data.get('ex_gst_amount')
        if amount is None:
            return jsonify({'error': 'Amount is required'}), 400

        input_amount = validate_decimal(amount, required=True, min_value=0)
        amount_type = data.get('amount_type', 'excludes')
        gst_type = validate_gst_type(data.get('gst_type', 0))
        currency = data.get('currency', 'AUD')
        expense_date = validate_date_string(data.get('expense_date'), required=True)
        account_category_id = data.get('account_category_id')

        if account_category_id and not validate_uuid(account_category_id):
            return jsonify({'error': 'Invalid account category ID'}), 400

        original_currency_amount = None
        exchange_rate = None

        if currency == 'USD':
            from app.shared.currency import get_usd_to_aud_rate, convert_usd_to_aud
            exchange_rate = get_usd_to_aud_rate(data.get('expense_date'))
            if exchange_rate:
                original_currency_amount = input_amount
                input_amount = convert_usd_to_aud(input_amount, exchange_rate)

        if amount_type == 'includes':
            ex_gst_amount = (input_amount / (Decimal('1') + gst_type)).quantize(Decimal('0.01'))
        else:
            ex_gst_amount = input_amount

        gst_amount = Expense.calculate_gst(ex_gst_amount, gst_type)
        total_amount = Expense.calculate_total(ex_gst_amount, gst_amount)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    expense = Expense(
        user_id=user.id,
        source='api',
        vendor_name=vendor_name,
        description=data.get('description', ''),
        currency=currency,
        original_currency_amount=original_currency_amount,
        exchange_rate=exchange_rate,
        ex_gst_amount=ex_gst_amount,
        gst_amount=gst_amount,
        gst_type=gst_type,
        total_amount=total_amount,
        expense_date=expense_date,
        account_category_id=account_category_id
    )

    db.session.add(expense)
    db.session.flush()

    log_activity(
        user_id=user.id,
        action='CREATE',
        table_name='expenses',
        record_id=expense.id,
        new_values=expense.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Expense created', 'expense': expense.to_dict()}), 201


@api_bp.route('/expenses/<expense_id>', methods=['GET'])
@api_key_required
def get_expense(expense_id):
    if not validate_uuid(expense_id):
        return jsonify({'error': 'Invalid expense ID'}), 400

    expense = Expense.query.filter_by(id=expense_id, user_id=request.current_user.id).first()
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404

    return jsonify({'expense': expense.to_dict()}), 200


@api_bp.route('/expenses/<expense_id>', methods=['PUT'])
@api_key_required
def update_expense(expense_id):
    if not validate_uuid(expense_id):
        return jsonify({'error': 'Invalid expense ID'}), 400

    expense = Expense.query.filter_by(id=expense_id, user_id=request.current_user.id).first()
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    old_values = expense.to_dict()

    try:
        if 'vendor_name' in data:
            vendor_name = data['vendor_name'].strip()
            if not vendor_name:
                return jsonify({'error': 'Vendor name cannot be empty'}), 400
            expense.vendor_name = vendor_name

        if 'description' in data:
            expense.description = data['description']

        amount_type = data.get('amount_type', 'excludes')

        if 'amount' in data or 'ex_gst_amount' in data:
            input_amount = validate_decimal(data.get('amount') or data.get('ex_gst_amount'), required=True, min_value=0)
            currency = data.get('currency', expense.currency or 'AUD')

            original_currency_amount = None
            exchange_rate = None

            if currency == 'USD':
                from app.shared.currency import get_usd_to_aud_rate, convert_usd_to_aud
                expense_date_str = data.get('expense_date') or expense.expense_date.isoformat()
                exchange_rate = get_usd_to_aud_rate(expense_date_str)
                if exchange_rate:
                    original_currency_amount = input_amount
                    input_amount = convert_usd_to_aud(input_amount, exchange_rate)

            if amount_type == 'includes':
                expense.ex_gst_amount = (input_amount / (Decimal('1') + expense.gst_type)).quantize(Decimal('0.01'))
            else:
                expense.ex_gst_amount = input_amount

            expense.currency = currency
            expense.original_currency_amount = original_currency_amount
            expense.exchange_rate = exchange_rate

        if 'gst_type' in data:
            expense.gst_type = validate_gst_type(data['gst_type'])

        if 'expense_date' in data:
            expense.expense_date = validate_date_string(data['expense_date'], required=True)

        if 'account_category_id' in data:
            if data['account_category_id'] and not validate_uuid(data['account_category_id']):
                return jsonify({'error': 'Invalid account category ID'}), 400
            expense.account_category_id = data['account_category_id']

        if 'currency' in data:
            expense.currency = data['currency']

        expense.gst_amount = Expense.calculate_gst(expense.ex_gst_amount, expense.gst_type)
        expense.total_amount = Expense.calculate_total(expense.ex_gst_amount, expense.gst_amount)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    log_activity(
        user_id=request.current_user.id,
        action='UPDATE',
        table_name='expenses',
        record_id=expense.id,
        old_values=old_values,
        new_values=expense.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Expense updated', 'expense': expense.to_dict()}), 200


@api_bp.route('/expenses/<expense_id>', methods=['DELETE'])
@api_key_required
def delete_expense(expense_id):
    if not validate_uuid(expense_id):
        return jsonify({'error': 'Invalid expense ID'}), 400

    expense = Expense.query.filter_by(id=expense_id, user_id=request.current_user.id).first()
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404

    old_values = expense.to_dict()

    log_activity(
        user_id=request.current_user.id,
        action='DELETE',
        table_name='expenses',
        record_id=expense.id,
        old_values=old_values,
        ip_address=request.remote_addr
    )

    db.session.delete(expense)
    db.session.commit()

    return jsonify({'message': 'Expense deleted'}), 200


@api_bp.route('/expenses/<expense_id>/upload', methods=['POST'])
@api_key_required
def upload_expense_attachment(expense_id):
    if not validate_uuid(expense_id):
        return jsonify({'error': 'Invalid expense ID'}), 400

    expense = Expense.query.filter_by(id=expense_id, user_id=request.current_user.id).first()
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg'}
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'error': 'Invalid file type. Allowed: PDF, PNG, JPG'}), 400

    upload_folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'expenses')
    os.makedirs(upload_folder, exist_ok=True)

    filepath = os.path.join(upload_folder, f'{expense_id}_{filename}')
    file.save(filepath)

    old_values = expense.to_dict()
    expense.attachment_path = filepath

    log_activity(
        user_id=request.current_user.id,
        action='UPDATE',
        table_name='expenses',
        record_id=expense.id,
        old_values=old_values,
        new_values=expense.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'File uploaded', 'expense': expense.to_dict()}), 200


@api_bp.route('/invoices', methods=['GET'])
@api_key_required
def list_invoices():
    user = request.current_user

    query = Invoice.query.filter_by(user_id=user.id)

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date:
        try:
            start = validate_date_string(start_date)
            query = query.filter(Invoice.invoice_date >= start)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    if end_date:
        try:
            end = validate_date_string(end_date)
            query = query.filter(Invoice.invoice_date <= end)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

    invoices = query.order_by(Invoice.invoice_date.desc()).all()
    return jsonify({'invoices': [i.to_dict() for i in invoices]}), 200


@api_bp.route('/invoices', methods=['POST'])
@api_key_required
def create_invoice():
    user = request.current_user
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        client_name = data.get('client_name', '').strip()
        if not client_name:
            return jsonify({'error': 'Client name is required'}), 400

        customer_id = data.get('customer_id', '').strip()
        if not customer_id:
            return jsonify({'error': 'Customer ID is required'}), 400
        if not validate_uuid(customer_id):
            return jsonify({'error': 'Invalid customer ID'}), 400
        customer = Customer.query.get(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        ex_gst_amount = validate_decimal(data.get('ex_gst_amount'), required=True, min_value=0)
        gst_type = validate_gst_type(data.get('gst_type', 0))
        invoice_date = validate_date_string(data.get('invoice_date'), required=True)
        due_date = validate_date_string(data.get('due_date'))
        account_category_id = data.get('account_category_id')

        if account_category_id and not validate_uuid(account_category_id):
            return jsonify({'error': 'Invalid account category ID'}), 400

        gst_amount = Invoice.calculate_gst(ex_gst_amount, gst_type)
        total_amount = Invoice.calculate_total(ex_gst_amount, gst_amount)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    invoice = Invoice(
        user_id=user.id,
        customer_id=customer_id,
        client_name=client_name,
        description=data.get('description', ''),
        ex_gst_amount=ex_gst_amount,
        gst_amount=gst_amount,
        gst_type=gst_type,
        total_amount=total_amount,
        invoice_date=invoice_date,
        due_date=due_date,
        account_category_id=account_category_id
    )

    db.session.add(invoice)
    db.session.flush()

    log_activity(
        user_id=user.id,
        action='CREATE',
        table_name='invoices',
        record_id=invoice.id,
        new_values=invoice.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Invoice created', 'invoice': invoice.to_dict()}), 201


@api_bp.route('/invoices/<invoice_id>', methods=['GET'])
@api_key_required
def get_invoice(invoice_id):
    if not validate_uuid(invoice_id):
        return jsonify({'error': 'Invalid invoice ID'}), 400

    invoice = Invoice.query.filter_by(id=invoice_id, user_id=request.current_user.id).first()
    if not invoice:
        return jsonify({'error': 'Invoice not found'}), 404

    return jsonify({'invoice': invoice.to_dict()}), 200


@api_bp.route('/invoices/<invoice_id>', methods=['PUT'])
@api_key_required
def update_invoice(invoice_id):
    if not validate_uuid(invoice_id):
        return jsonify({'error': 'Invalid invoice ID'}), 400

    invoice = Invoice.query.filter_by(id=invoice_id, user_id=request.current_user.id).first()
    if not invoice:
        return jsonify({'error': 'Invoice not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    old_values = invoice.to_dict()

    try:
        if 'client_name' in data:
            client_name = data['client_name'].strip()
            if not client_name:
                return jsonify({'error': 'Client name cannot be empty'}), 400
            invoice.client_name = client_name

        if 'description' in data:
            invoice.description = data['description']

        if 'ex_gst_amount' in data:
            invoice.ex_gst_amount = validate_decimal(data['ex_gst_amount'], required=True, min_value=0)

        if 'gst_type' in data:
            invoice.gst_type = validate_gst_type(data['gst_type'])

        if 'invoice_date' in data:
            invoice.invoice_date = validate_date_string(data['invoice_date'], required=True)

        if 'due_date' in data:
            invoice.due_date = validate_date_string(data['due_date'])

        if 'account_category_id' in data:
            if data['account_category_id'] and not validate_uuid(data['account_category_id']):
                return jsonify({'error': 'Invalid account category ID'}), 400
            invoice.account_category_id = data['account_category_id']

        if 'customer_id' in data:
            new_customer_id = data['customer_id']
            if not new_customer_id:
                return jsonify({'error': 'Customer ID cannot be empty'}), 400
            if not validate_uuid(new_customer_id):
                return jsonify({'error': 'Invalid customer ID'}), 400
            customer = Customer.query.get(new_customer_id)
            if not customer:
                return jsonify({'error': 'Customer not found'}), 404
            invoice.customer_id = new_customer_id

        invoice.gst_amount = Invoice.calculate_gst(invoice.ex_gst_amount, invoice.gst_type)
        invoice.total_amount = Invoice.calculate_total(invoice.ex_gst_amount, invoice.gst_amount)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    log_activity(
        user_id=request.current_user.id,
        action='UPDATE',
        table_name='invoices',
        record_id=invoice.id,
        old_values=old_values,
        new_values=invoice.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Invoice updated', 'invoice': invoice.to_dict()}), 200


@api_bp.route('/invoices/<invoice_id>', methods=['DELETE'])
@api_key_required
def delete_invoice(invoice_id):
    if not validate_uuid(invoice_id):
        return jsonify({'error': 'Invalid invoice ID'}), 400

    invoice = Invoice.query.filter_by(id=invoice_id, user_id=request.current_user.id).first()
    if not invoice:
        return jsonify({'error': 'Invoice not found'}), 404

    old_values = invoice.to_dict()

    log_activity(
        user_id=request.current_user.id,
        action='DELETE',
        table_name='invoices',
        record_id=invoice.id,
        old_values=old_values,
        ip_address=request.remote_addr
    )

    db.session.delete(invoice)
    db.session.commit()

    return jsonify({'message': 'Invoice deleted'}), 200


@api_bp.route('/invoices/<invoice_id>/upload', methods=['POST'])
@api_key_required
def upload_invoice_attachment(invoice_id):
    if not validate_uuid(invoice_id):
        return jsonify({'error': 'Invalid invoice ID'}), 400

    invoice = Invoice.query.filter_by(id=invoice_id, user_id=request.current_user.id).first()
    if not invoice:
        return jsonify({'error': 'Invoice not found'}), 404

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg'}
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'error': 'Invalid file type. Allowed: PDF, PNG, JPG'}), 400

    upload_folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'invoices')
    os.makedirs(upload_folder, exist_ok=True)

    filepath = os.path.join(upload_folder, f'{invoice_id}_{filename}')
    file.save(filepath)

    old_values = invoice.to_dict()
    invoice.attachment_path = filepath

    log_activity(
        user_id=request.current_user.id,
        action='UPDATE',
        table_name='invoices',
        record_id=invoice.id,
        old_values=old_values,
        new_values=invoice.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'File uploaded', 'invoice': invoice.to_dict()}), 200


@api_bp.route('/invoices/<invoice_id>/pdf', methods=['GET'])
@api_key_required
def generate_invoice_pdf(invoice_id):
    if not validate_uuid(invoice_id):
        return jsonify({'error': 'Invalid invoice ID'}), 400

    invoice = Invoice.query.filter_by(id=invoice_id, user_id=request.current_user.id).first()
    if not invoice:
        return jsonify({'error': 'Invoice not found'}), 404

    user = request.current_user

    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

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

    business_style = ParagraphStyle('Business', parent=styles['Normal'], fontSize=9, alignment=2, leading=12)
    business_cell = [Paragraph('<br/>'.join(business_paragraphs), business_style)] if business_paragraphs else ['']

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=28, spaceAfter=0, alignment=0, textColor=colors.HexColor('#2c3e50'))
    title_cell = Paragraph('INVOICE', title_style)

    header_data = [[logo_cell, business_cell]]
    header_table = Table(header_data, colWidths=[8*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*cm))

    invoice_title_row = Table([[title_cell, '']], colWidths=[12*cm, 4*cm])
    invoice_title_row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
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
        elements.append(Paragraph(
            f'<i>Payment terms: Net 30 days. Please include invoice number {invoice.id[:8].upper()} on payment.</i>',
            styles['Normal']
        ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'invoice_{invoice.id[:8]}_{invoice.invoice_date}.pdf'
    )


@api_bp.route('/auth/business', methods=['GET'])
@api_key_required
def get_business_details():
    user = request.current_user
    return jsonify({'user': user.to_dict()}), 200


@api_bp.route('/auth/business', methods=['PUT'])
@api_key_required
def update_business_details():
    user = request.current_user
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    old_values = user.to_dict()

    if 'business_name' in data:
        user.business_name = data['business_name']
    if 'abn' in data:
        user.abn = data['abn']
    if 'address' in data:
        user.address = data['address']
    if 'contact_email' in data:
        user.contact_email = data['contact_email']
    if 'contact_number' in data:
        user.contact_number = data['contact_number']

    log_activity(
        user_id=user.id,
        action='UPDATE',
        table_name='users',
        record_id=user.id,
        old_values=old_values,
        new_values=user.to_dict(),
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Business details updated', 'user': user.to_dict()}), 200


@api_bp.route('/auth/logo', methods=['POST'])
@api_key_required
def upload_logo():
    user = request.current_user

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename)
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP, SVG'}), 400

    upload_folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'logos')
    os.makedirs(upload_folder, exist_ok=True)

    ext = filename.rsplit('.', 1)[1].lower()
    unique_filename = f'{user.id}.{ext}'
    filepath = os.path.join(upload_folder, unique_filename)
    file.save(filepath)

    old_values = {'logo_path': user.logo_path}
    user.logo_path = filepath

    log_activity(
        user_id=user.id,
        action='UPDATE',
        table_name='users',
        record_id=user.id,
        old_values=old_values,
        new_values={'logo_path': user.logo_path},
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Logo uploaded', 'user': user.to_dict()}), 200


@api_bp.route('/auth/logo', methods=['DELETE'])
@api_key_required
def delete_logo():
    user = request.current_user

    if not user.logo_path:
        return jsonify({'error': 'No logo to delete'}), 404

    try:
        if os.path.exists(user.logo_path):
            os.remove(user.logo_path)
    except OSError:
        pass

    old_values = {'logo_path': user.logo_path}
    user.logo_path = None

    log_activity(
        user_id=user.id,
        action='UPDATE',
        table_name='users',
        record_id=user.id,
        old_values=old_values,
        new_values={'logo_path': None},
        ip_address=request.remote_addr
    )
    db.session.commit()

    return jsonify({'message': 'Logo deleted'}), 200
