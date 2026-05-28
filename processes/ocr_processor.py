#!/usr/bin/env python3
"""
OCR Queue Processor

Processes receipt images through the vision model to extract
vendor name, amount, date, and other details.
"""

import os
import sys
import time
import json
import re
import base64
import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.models import db
from app.models.expense import Expense
from app.models.ocr_queue import OcrQueue


BASE_PROMPT = """You are an OCR system for Australian receipts. Extract the following information from this receipt image and return ONLY valid JSON with these exact keys (no other text):
- vendor_name: the business name (string in quotes)
- expense_date: the date on the receipt in YYYY-MM-DD format (string in quotes)
- ex_gst_amount: the amount before GST as a decimal number, NOT a string (e.g., 45.50)
- gst_amount: the GST amount as a decimal number, NOT a string (e.g., 4.55)
- gst_type: the GST rate as a decimal (0.1 for 10%, 0 for no GST), NOT a string
- description: any notes or description from the receipt (string in quotes, can be empty string "")

IMPORTANT: All numbers must be JSON numbers, NOT strings. Do NOT use quotes around numbers.
Example: {"vendor_name": "Bunnings", "expense_date": "2024-03-15", "ex_gst_amount": 45.50, "gst_amount": 4.55, "gst_type": 0.1, "description": ""}"""

ATTEMPT_PROMPTS = {
    1: BASE_PROMPT,
    2: BASE_PROMPT + "\n\nIf the image is unclear or partially illegible, provide your best guess for each field and set description to 'REQUIRES REVIEW'.",
    3: BASE_PROMPT + "\n\nIMPORTANT: If fields are unclear or illegible, you MUST provide your best guess. Set description to 'REQUIRES REVIEW' and include any partial information you can read. Do not leave fields empty - always provide a value or your best estimate."
}


def get_prompt(attempt):
    return ATTEMPT_PROMPTS.get(attempt, ATTEMPT_PROMPTS[3])


def encode_image(image_path):
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_vision_model(image_path, ollama_host, model, timeout, prompt):
    image_b64 = encode_image(image_path)

    payload = {
        'model': model,
        'prompt': prompt,
        'images': [image_b64],
        'stream': False,
        'format': 'json'
    }

    response = requests.post(
        f'{ollama_host}/api/generate',
        json=payload,
        timeout=timeout
    )
    response.raise_for_status()
    return response.json().get('response', '')


def process_ocr_job(job, app, ollama_host, model, timeout):
    with app.app_context():
        job = OcrQueue.query.get(job.id)
        if not job or job.status != 'pending':
            return

        expense = Expense.query.get(job.expense_id)
        if not expense:
            job.status = 'failed'
            job.error_message = 'Expense not found'
            job.processed_at = datetime.now(timezone.utc)
            db.session.commit()
            return

        try:
            job.status = 'processing'
            job.attempts += 1
            db.session.commit()

            prompt = get_prompt(job.attempts)
            raw_response = call_vision_model(job.image_path, ollama_host, model, timeout, prompt)

            def extract_json(text):
                text = text.strip()
                start = text.find('{')
                if start == -1:
                    return text
                depth = 0
                end = start
                for i, c in enumerate(text[start:], start):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                return text[start:end]

            try:
                data = json.loads(raw_response)
            except json.JSONDecodeError:
                cleaned = extract_json(raw_response)
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError:
                    data = {}

            def get_value(data, *keys):
                for key in keys:
                    if key in data:
                        return data[key]
                return None

            vendor = get_value(data, 'vendor_name', 'vendor', 'business_name', 'supplier')
            if vendor and isinstance(vendor, str):
                expense.vendor_name = vendor

            desc = get_value(data, 'description', 'notes', 'memo')
            if desc and isinstance(desc, str):
                expense.description = desc

            date_str = get_value(data, 'expense_date', 'date', 'transaction_date')
            if date_str and isinstance(date_str, str):
                try:
                    expense.expense_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass

            ex_gst = get_value(data, 'ex_gst_amount', 'amount_ex_gst', 'subtotal', 'amount_before_gst')
            if ex_gst is not None:
                try:
                    expense.ex_gst_amount = Decimal(str(ex_gst))
                except (ValueError, TypeError):
                    pass

            gst_amt = get_value(data, 'gst_amount', 'gst', 'tax_amount')
            if gst_amt is not None:
                try:
                    expense.gst_amount = Decimal(str(gst_amt))
                except (ValueError, TypeError):
                    pass

            gst_t = get_value(data, 'gst_type', 'tax_rate', 'gst_rate')
            if gst_t is not None:
                try:
                    expense.gst_type = Decimal(str(gst_t))
                except (ValueError, TypeError):
                    pass

            if expense.ex_gst_amount and expense.gst_amount:
                expense.total_amount = expense.ex_gst_amount + expense.gst_amount

            if not data or not any(v for v in data.values() if v is not None):
                expense.vendor_name = 'REQUIRES REVIEW'
                expense.requires_review = True
                job.status = 'failed'
                job.error_message = 'No data could be extracted from model response'
                job.processed_at = datetime.now(timezone.utc)
                db.session.commit()
                return

            if desc == 'REQUIRES REVIEW':
                expense.requires_review = True

            job.status = 'completed'
            job.extracted_data = data
            job.processed_at = datetime.now(timezone.utc)
            db.session.commit()

        except json.JSONDecodeError as e:
            expense.vendor_name = 'REQUIRES REVIEW'
            expense.requires_review = True
            job.status = 'failed'
            job.error_message = f'JSON parse error: {str(e)} - Response: {raw_response[:500] if raw_response else "empty"}'
            job.processed_at = datetime.now(timezone.utc)
            db.session.commit()

        except Exception as e:
            expense.vendor_name = 'REQUIRES REVIEW'
            expense.requires_review = True
            job.status = 'failed'
            job.error_message = str(e)
            job.processed_at = datetime.now(timezone.utc)
            db.session.commit()


def run_processor(ollama_host, model, timeout, poll_interval=5, max_attempts=3):
    app = create_app()

    print(f'OCR Processor starting...')
    print(f'Vision model: {model} at {ollama_host}')
    print(f'Poll interval: {poll_interval}s')

    while True:
        with app.app_context():
            stale_timeout = 300
            stale_jobs = OcrQueue.query.filter(
                OcrQueue.status == 'processing',
                OcrQueue.created_at < datetime.now(timezone.utc) - timedelta(seconds=stale_timeout)
            ).all()
            for stale_job in stale_jobs:
                stale_job.status = 'pending'
                stale_job.error_message = 'Stale job reset'
                db.session.commit()
                print(f'Reset stale job {stale_job.id}')

            pending_jobs = OcrQueue.query.filter_by(status='pending').order_by(OcrQueue.created_at).limit(10).all()

            if pending_jobs:
                print(f'Found {len(pending_jobs)} pending jobs')
                for job in pending_jobs:
                    if job.attempts >= max_attempts:
                        job.status = 'failed'
                        job.error_message = f'Max attempts ({max_attempts}) reached'
                        job.processed_at = datetime.now(timezone.utc)
                        db.session.commit()
                        print(f'Job {job.id} failed: max attempts reached')
                    else:
                        print(f'Processing job {job.id}...')
                        try:
                            process_ocr_job(job, app, ollama_host, model, timeout)
                        except Exception as e:
                            print(f'Error processing job {job.id}: {e}')
                            job.status = 'pending'
                            job.error_message = str(e)
                            db.session.commit()

        time.sleep(poll_interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OCR Queue Processor')
    parser.add_argument('--config', '-c', default='config.yaml', help='Path to config file')
    parser.add_argument('--poll-interval', type=int, default=5, help='Poll interval in seconds')
    parser.add_argument('--max-attempts', type=int, default=3, help='Max retry attempts per job')
    args = parser.parse_args()

    import yaml
    config_path = args.config
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        print(f'Config file {config_path} not found')
        sys.exit(1)

    ollama_host = config.get('vision', {}).get('ollama_host', 'http://localhost:11434')
    model = config.get('vision', {}).get('model', 'gemma4:31b')
    timeout = config.get('vision', {}).get('timeout', 2100.0)

    run_processor(ollama_host, model, timeout, args.poll_interval, args.max_attempts)
