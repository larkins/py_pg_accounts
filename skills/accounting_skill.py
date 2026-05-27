"""
Accounting Skill for AI Agents

This skill provides a structured interface for AI agents to interact with the
accounting database. It wraps the REST API to provide natural language access
to expense and invoice management.

Usage:
    from skills.accounting_skill import AccountingSkill
    skill = AccountingSkill(api_key="your-api-key", base_url="http://192.168.4.44:5061")
    result = skill.create_expense(vendor_name="Office Supplies", ex_gst_amount=100.00)
"""

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

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None):
        url = f"{self.BASE_URL}{endpoint}"

        if files:
            headers = {'X-API-Key': self.api_key}
            response = requests.request(method, url, headers=headers, files=files)
        else:
            response = requests.request(method, url, headers=self.headers, json=data)

        response.raise_for_status()
        return response.json()

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
        result = self._make_request('DELETE', f'/api/expenses/{expense_id}')
        return result

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

    def create_invoice(
        self,
        client_name: str,
        ex_gst_amount: float,
        invoice_date: str,
        gst_type: float = 0.1,
        description: str = "",
        due_date: Optional[str] = None,
        account_category_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new invoice record.

        Args:
            client_name: Name of the client/customer
            ex_gst_amount: Amount excluding GST
            invoice_date: Date of invoice in YYYY-MM-DD format
            gst_type: GST type (0 for no GST, 0.1 for 10% GST)
            description: Optional description
            due_date: Optional payment due date in YYYY-MM-DD format
            account_category_id: Optional UUID of the account category

        Returns:
            Dictionary containing the created invoice data
        """
        data = {
            'client_name': client_name,
            'ex_gst_amount': str(ex_gst_amount),
            'invoice_date': invoice_date,
            'gst_type': str(gst_type),
            'description': description
        }
        if due_date:
            data['due_date'] = due_date
        if account_category_id:
            data['account_category_id'] = account_category_id

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
            **kwargs: Any invoice fields to update

        Returns:
            Dictionary containing the updated invoice data
        """
        data = {}
        for key, value in kwargs.items():
            if key in ['client_name', 'description', 'invoice_date', 'due_date', 'account_category_id']:
                data[key] = value
            elif key in ['ex_gst_amount', 'gst_type']:
                data[key] = str(value)

        result = self._make_request('PUT', f'/api/invoices/{invoice_id}', data)
        return result['invoice']

    def delete_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Delete an invoice by ID."""
        result = self._make_request('DELETE', f'/api/invoices/{invoice_id}')
        return result

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

    def delete_account_category(self, category_id: str) -> Dict[str, Any]:
        """Delete an account category by ID."""
        result = self._make_request('DELETE', f'/api/account-categories/{category_id}')
        return result

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
        result = self._make_request('GET', f'/api/reports/profit-loss?{params}')
        return result

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
        result = self._make_request('GET', f'/api/reports/quarterly-bas{query}')
        return result

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
        result = self._make_request('GET', f'/api/reports/monthly{query}')
        return result

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
        result = self._make_request('GET', f'/api/reports/yearly-finances{query}')
        return result


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


def generate_api_key(api_key: str) -> Dict[str, Any]:
    """
    Generate an API key for a user (requires existing API key).

    Args:
        api_key: Existing API key for authentication

    Returns:
        Dictionary containing the new API key
    """
    url = f"{AccountingSkill.BASE_URL}/api/auth/api-key"
    headers = {'X-API-Key': api_key}
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()
