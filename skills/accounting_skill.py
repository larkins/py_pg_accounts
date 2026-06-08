"""
Accounting Skill for AI Agents

This skill provides a structured interface for AI agents to interact with the
accounting database. It wraps the REST API to provide natural language access
to expense, invoice, customer, and business profile management.

Usage:
    from skills.accounting_skill import AccountingSkill
    skill = AccountingSkill(api_key="your-api-key", base_url="http://192.168.4.44:5061")
    result = skill.create_expense(vendor_name="Office Supplies", ex_gst_amount=100.00)
"""

import os
import requests
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from decimal import Decimal


class AccountingSkill:
    BASE_URL = "http://192.168.4.44:5061"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        if base_url:
            self.BASE_URL = base_url
        self.headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        }

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None, stream: bool = False):
        url = f"{self.BASE_URL}{endpoint}"

        if files:
            headers = {'X-API-Key': self.api_key}
            response = requests.request(method, url, headers=headers, files=files)
        else:
            response = requests.request(method, url, headers=self.headers, json=data)

        response.raise_for_status()

        if stream:
            return response
        return response.json()

    def download_file(self, endpoint: str, save_path: str) -> str:
        """
        Download a file from the API.

        Args:
            endpoint: API endpoint that returns a file
            save_path: Local path to save the file

        Returns:
            Path to the saved file
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = {'X-API-Key': self.api_key}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return save_path

    # =========================================================================
    # Business Profile Management
    # =========================================================================

    def get_business_details(self) -> Dict[str, Any]:
        """
        Get the current business profile (user details).

        Returns:
            Dictionary containing the user/business profile
        """
        result = self._make_request('GET', '/api/auth/business')
        return result['user']

    def update_business_details(
        self,
        business_name: Optional[str] = None,
        abn: Optional[str] = None,
        address: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_number: Optional[str] = None,
        bank_name: Optional[str] = None,
        account_name: Optional[str] = None,
        account_number: Optional[str] = None,
        bsb: Optional[str] = None,
        payment_terms: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create or update business profile details. These appear on invoice PDFs.

        Bank details can be set/updated using the bank_name, account_name,
        account_number, and bsb parameters. To clear a field, pass an empty
        string ("").

        Args:
            business_name: Business name
            abn: Australian Business Number
            address: Business address (can include newlines)
            contact_email: Business contact email
            contact_number: Business contact phone number
            bank_name: Bank name
            account_name: Account holder name
            account_number: Bank account number
            bsb: Bank State Branch (BSB) number
            payment_terms: Number of days for payment (default 14). This is
                used in the "Payment terms: Net X days" line on invoice PDFs
                and should be consistent with the invoice due date.

        Returns:
            Dictionary containing the updated user/business profile
        """
        data = {}
        if business_name is not None:
            data['business_name'] = business_name
        if abn is not None:
            data['abn'] = abn
        if address is not None:
            data['address'] = address
        if contact_email is not None:
            data['contact_email'] = contact_email
        if contact_number is not None:
            data['contact_number'] = contact_number
        if bank_name is not None:
            data['bank_name'] = bank_name
        if account_name is not None:
            data['account_name'] = account_name
        if account_number is not None:
            data['account_number'] = account_number
        if bsb is not None:
            data['bsb'] = bsb
        if payment_terms is not None:
            data['payment_terms'] = payment_terms

        result = self._make_request('PUT', '/api/auth/business', data)
        return result['user']

    def upload_logo(self, file_path: str) -> Dict[str, Any]:
        """
        Upload a business logo. The logo appears on the top-left of invoice PDFs.

        Args:
            file_path: Local path to the logo file (PNG, JPG, JPEG, GIF, WEBP, SVG)

        Returns:
            Dictionary containing the updated user profile with logo path
        """
        with open(file_path, 'rb') as f:
            files = {'file': f}
            result = self._make_request('POST', '/api/auth/logo', files=files)
        return result['user']

    def delete_logo(self) -> Dict[str, Any]:
        """
        Delete the business logo.

        Returns:
            Dictionary with confirmation message
        """
        return self._make_request('DELETE', '/api/auth/logo')

    # =========================================================================
    # Expense Management
    # =========================================================================

    def create_expense(
        self,
        vendor_name: str,
        amount: float,
        expense_date: str,
        gst_type: float = 0.1,
        amount_type: str = "excludes",
        currency: str = "AUD",
        description: str = "",
        account_category_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new expense record.

        Args:
            vendor_name: Name of the vendor/supplier
            amount: Amount (excludes or includes GST depending on amount_type)
            expense_date: Date of expense in YYYY-MM-DD format
            gst_type: GST type (0 for no GST, 0.1 for 10% GST)
            amount_type: 'excludes' (default) or 'includes' GST
            currency: 'AUD' (default) or 'USD'
            description: Optional description of the expense
            account_category_id: Optional UUID of the account category

        Returns:
            Dictionary containing the created expense data
        """
        data = {
            'vendor_name': vendor_name,
            'amount': str(amount),
            'amount_type': amount_type,
            'currency': currency,
            'expense_date': expense_date,
            'gst_type': str(gst_type),
            'description': description
        }
        if account_category_id:
            data['account_category_id'] = account_category_id

        result = self._make_request('POST', '/api/expenses', data)
        return result['expense']

    def get_expense(self, expense_id: str) -> Dict[str, Any]:
        """Get a single expense by ID."""
        result = self._make_request('GET', f'/api/expenses/{expense_id}')
        return result['expense']

    def list_expenses(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all expenses, optionally filtered by date range.

        Args:
            start_date: Start date filter in YYYY-MM-DD format
            end_date: End date filter in YYYY-MM-DD format

        Returns:
            List of expense dictionaries
        """
        params = []
        if start_date:
            params.append(f'start_date={start_date}')
        if end_date:
            params.append(f'end_date={end_date}')

        query = '?' + '&'.join(params) if params else ''
        result = self._make_request('GET', f'/api/expenses{query}')
        return result['expenses']

    def update_expense(
        self,
        expense_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update an existing expense.

        Args:
            expense_id: UUID of the expense to update
            **kwargs: Any expense fields to update (vendor_name, amount, amount_type, currency, gst_type, etc.)

        Returns:
            Dictionary containing the updated expense data
        """
        data = {}
        for key, value in kwargs.items():
            if key in ['vendor_name', 'description', 'expense_date', 'account_category_id', 'amount_type', 'currency']:
                data[key] = value
            elif key in ['amount', 'ex_gst_amount', 'gst_type']:
                data[key] = str(value)

        result = self._make_request('PUT', f'/api/expenses/{expense_id}', data)
        return result['expense']

    def delete_expense(self, expense_id: str) -> Dict[str, Any]:
        """Delete an expense by ID."""
        return self._make_request('DELETE', f'/api/expenses/{expense_id}')

    def upload_expense_attachment(self, expense_id: str, file_path: str) -> Dict[str, Any]:
        """
        Upload an attachment (image or PDF) to an expense.

        Args:
            expense_id: UUID of the expense
            file_path: Local path to the file to upload

        Returns:
            Dictionary containing the updated expense with attachment path
        """
        with open(file_path, 'rb') as f:
            files = {'file': f}
            result = self._make_request('POST', f'/api/expenses/{expense_id}/upload', files=files)
        return result['expense']

    # =========================================================================
    # Customer Management
    # =========================================================================

    def create_customer(
        self,
        name: str,
        contact_name: Optional[str] = None,
        address: Optional[str] = None,
        contact_email: Optional[str] = None,
        abn: Optional[str] = None,
        contact_number: Optional[str] = None,
        gst: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new customer.

        Args:
            name: Customer/business name (required)
            contact_name: Contact person name
            address: Customer address
            contact_email: Contact email
            abn: Australian Business Number
            contact_number: Phone number
            gst: Whether customer is GST registered (default True)

        Returns:
            Dictionary containing the created customer
        """
        data = {
            'name': name,
            'gst': gst
        }
        if contact_name is not None:
            data['contact_name'] = contact_name
        if address is not None:
            data['address'] = address
        if contact_email is not None:
            data['contact_email'] = contact_email
        if abn is not None:
            data['abn'] = abn
        if contact_number is not None:
            data['contact_number'] = contact_number

        result = self._make_request('POST', '/api/customers', data)
        return result['customer']

    def get_customer(self, customer_id: str) -> Dict[str, Any]:
        """Get a single customer by ID."""
        result = self._make_request('GET', f'/api/customers/{customer_id}')
        return result['customer']

    def list_customers(self) -> List[Dict[str, Any]]:
        """List all customers, sorted by name."""
        result = self._make_request('GET', '/api/customers')
        return result['customers']

    def update_customer(self, customer_id: str, **kwargs) -> Dict[str, Any]:
        """
        Update an existing customer.

        Args:
            customer_id: UUID of the customer
            **kwargs: Customer fields to update (name, contact_name, address, etc.)

        Returns:
            Dictionary containing the updated customer
        """
        result = self._make_request('PUT', f'/api/customers/{customer_id}', kwargs)
        return result['customer']

    def delete_customer(self, customer_id: str) -> Dict[str, Any]:
        """
        Delete a customer. Fails if the customer has any invoices.

        Args:
            customer_id: UUID of the customer

        Returns:
            Dictionary with confirmation message
        """
        return self._make_request('DELETE', f'/api/customers/{customer_id}')

    # =========================================================================
    # Invoice Management (requires customer_id)
    # =========================================================================

    def create_invoice(
        self,
        customer_id: str,
        client_name: str,
        ex_gst_amount: float,
        invoice_date: str,
        gst_type: float = 0.1,
        description: str = "",
        due_date: Optional[str] = None,
        account_category_id: Optional[str] = None,
        status: str = "draft",
        payment_date: Optional[str] = None,
        amount_paid: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Create a new invoice. Requires an existing customer_id.

        Args:
            customer_id: UUID of the customer (REQUIRED)
            client_name: Display name for the client on the invoice
            ex_gst_amount: Amount excluding GST
            invoice_date: Date of invoice in YYYY-MM-DD format
            gst_type: GST type (0 for no GST, 0.1 for 10% GST)
            description: Optional description
            due_date: Optional payment due date in YYYY-MM-DD format
            account_category_id: Optional UUID of the account category
            status: Invoice status (default 'draft'). One of: draft, sent, paid, overdue, cancelled
            payment_date: Date payment was received (YYYY-MM-DD)
            amount_paid: Amount that was paid (for partial payments)

        Returns:
            Dictionary containing the created invoice data
        """
        data = {
            'customer_id': customer_id,
            'client_name': client_name,
            'ex_gst_amount': str(ex_gst_amount),
            'invoice_date': invoice_date,
            'gst_type': str(gst_type),
            'description': description,
            'status': status
        }
        if due_date:
            data['due_date'] = due_date
        if account_category_id:
            data['account_category_id'] = account_category_id
        if payment_date:
            data['payment_date'] = payment_date
        if amount_paid is not None:
            data['amount_paid'] = str(amount_paid)

        result = self._make_request('POST', '/api/invoices', data)
        return result['invoice']

    def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Get a single invoice by ID."""
        result = self._make_request('GET', f'/api/invoices/{invoice_id}')
        return result['invoice']

    def list_invoices(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all invoices, optionally filtered by date range.

        Args:
            start_date: Start date filter in YYYY-MM-DD format
            end_date: End date filter in YYYY-MM-DD format

        Returns:
            List of invoice dictionaries
        """
        params = []
        if start_date:
            params.append(f'start_date={start_date}')
        if end_date:
            params.append(f'end_date={end_date}')

        query = '?' + '&'.join(params) if params else ''
        result = self._make_request('GET', f'/api/invoices{query}')
        return result['invoices']

    def update_invoice(
        self,
        invoice_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update an existing invoice.

        Args:
            invoice_id: UUID of the invoice to update
            **kwargs: Any invoice fields to update. Supported fields:
                customer_id, client_name, description, invoice_date, due_date,
                account_category_id, status, payment_date, amount_paid,
                ex_gst_amount, gst_type

        Returns:
            Dictionary containing the updated invoice data
        """
        data = {}
        for key, value in kwargs.items():
            if key in ['customer_id', 'client_name', 'description', 'invoice_date', 'due_date', 'account_category_id', 'status', 'payment_date']:
                data[key] = value
            elif key in ['ex_gst_amount', 'gst_type', 'amount_paid']:
                data[key] = str(value)

        result = self._make_request('PUT', f'/api/invoices/{invoice_id}', data)
        return result['invoice']

    def mark_invoice_paid(
        self,
        invoice_id: str,
        payment_date: Optional[str] = None,
        amount_paid: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Mark an invoice as paid. Sets status='paid' and records payment details.

        Args:
            invoice_id: UUID of the invoice
            payment_date: Date payment was received (YYYY-MM-DD). Defaults to today.
            amount_paid: Amount paid. Defaults to invoice total_amount (full payment).

        Returns:
            Dictionary containing the updated invoice data
        """
        data = {}
        if payment_date:
            data['payment_date'] = payment_date
        if amount_paid is not None:
            data['amount_paid'] = str(amount_paid)

        result = self._make_request('POST', f'/api/invoices/{invoice_id}/mark-paid', data)
        return result['invoice']

    def delete_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Delete an invoice by ID."""
        return self._make_request('DELETE', f'/api/invoices/{invoice_id}')

    def upload_invoice_attachment(self, invoice_id: str, file_path: str) -> Dict[str, Any]:
        """
        Upload an attachment (image or PDF) to an invoice.

        Args:
            invoice_id: UUID of the invoice
            file_path: Local path to the file to upload

        Returns:
            Dictionary containing the updated invoice with attachment path
        """
        with open(file_path, 'rb') as f:
            files = {'file': f}
            result = self._make_request('POST', f'/api/invoices/{invoice_id}/upload', files=files)
        return result['invoice']

    def download_invoice_pdf(self, invoice_id: str, save_path: str) -> str:
        """
        Download a generated PDF of an invoice.

        The PDF includes:
        - The user's business logo (top-left, if uploaded)
        - The user's business details (top-right)
        - Customer information (Bill To)
        - Invoice details, line items, totals
        - Payment terms footer

        Args:
            invoice_id: UUID of the invoice
            save_path: Local path to save the PDF (e.g. './invoice.pdf')

        Returns:
            Path to the saved PDF file
        """
        return self.download_file(f'/api/invoices/{invoice_id}/pdf', save_path)

    # =========================================================================
    # Account Categories
    # =========================================================================

    def create_account_category(
        self,
        name: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Create a new account category.

        Args:
            name: Name of the category
            description: Optional description

        Returns:
            Dictionary containing the created category data
        """
        data = {
            'name': name,
            'description': description
        }
        result = self._make_request('POST', '/api/account-categories', data)
        return result['account_category']

    def list_account_categories(self) -> List[Dict[str, Any]]:
        """List all account categories."""
        result = self._make_request('GET', '/api/account-categories')
        return result['account_categories']

    def update_account_category(self, category_id: str, **kwargs) -> Dict[str, Any]:
        """
        Update an existing account category.

        Args:
            category_id: UUID of the category
            **kwargs: Category fields to update (name, description)

        Returns:
            Dictionary containing the updated category
        """
        result = self._make_request('PUT', f'/api/account-categories/{category_id}', kwargs)
        return result['account_category']

    def delete_account_category(self, category_id: str) -> Dict[str, Any]:
        """Delete an account category by ID."""
        return self._make_request('DELETE', f'/api/account-categories/{category_id}')

    # =========================================================================
    # Reports
    # =========================================================================

    def get_profit_loss_report(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Generate a Profit & Loss report for a date range.

        Args:
            start_date: Report start date in YYYY-MM-DD format
            end_date: Report end date in YYYY-MM-DD format

        Returns:
            Dictionary containing P&L data with income, expenses, GST, and category breakdown
        """
        params = f'start_date={start_date}&end_date={end_date}'
        return self._make_request('GET', f'/api/reports/profit-loss?{params}')

    def get_quarterly_bas_report(
        self,
        year: Optional[int] = None,
        quarter: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a Quarterly BAS (Business Activity Statement) report.

        For Australian GST reporting.
        If year/quarter not provided, uses current period.

        Args:
            year: Financial year (e.g., 2024 for FY 2024-25)
            quarter: Quarter number (1-4)

        Returns:
            Dictionary containing GST collected, GST paid, and GST owing
        """
        params = []
        if year:
            params.append(f'year={year}')
        if quarter:
            params.append(f'quarter={quarter}')

        query = '?' + '&'.join(params) if params else ''
        return self._make_request('GET', f'/api/reports/quarterly-bas{query}')

    def get_monthly_report(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a Monthly P&L report.

        Args:
            year: Year (e.g., 2024)
            month: Month number (1-12)

        Returns:
            Dictionary containing monthly P&L data with income, expenses, GST, and category breakdown
        """
        params = []
        if year:
            params.append(f'year={year}')
        if month:
            params.append(f'month={month}')

        query = '?' + '&'.join(params) if params else ''
        return self._make_request('GET', f'/api/reports/monthly{query}')

    def get_yearly_finances_report(self, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate a yearly financial report for the Australian financial year.

        Australian financial year runs July 1 to June 30.
        If year not provided, uses current financial year.

        Args:
            year: Start year of the financial year (e.g., 2024 for FY 2024-25)

        Returns:
            Dictionary containing yearly totals and quarterly breakdowns
        """
        query = f'?year={year}' if year else ''
        return self._make_request('GET', f'/api/reports/yearly-finances{query}')


def register_user(email: str, password: str, country: str = "AU") -> Dict[str, Any]:
    """
    Register a new user (no API key required).

    Args:
        email: User's email address
        password: User's password
        country: Country code (default: AU for Australia)

    Returns:
        Dictionary containing the created user data
    """
    url = f"{AccountingSkill.BASE_URL}/api/auth/register"
    data = {
        'email': email,
        'password': password,
        'country': country
    }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()
