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
import base64
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.models import db
from app.models.expense import Expense
from app.models.ocr_queue import OcrQueue


PROMPT = """You are an OCR system for Australian receipts. Extract the following information from this receipt image and return ONLY valid JSON with these exact keys:
- vendor_name: the business name (string)
- expense_date: the date on the receipt in YYYY-MM-DD format (string)
- ex_gst_amount: the amount before GST as a number (number)
- gst_amount: the GST amount as a number (number)
- gst_type: the GST rate as a decimal (e.g., 0.1 for 10%) (number)
- description: any notes or description from the receipt (string, can be empty)

If information is not available or illegible, use null for that field.
Do not include any text other than the JSON object.
Example output: {"vendor_name": "Bunnings", "expense_date": "2024-03-15", "ex_gst_amount": 45.50, "gst_amount": 4.55, "gst_type": 0.1, "description": "Hardware supplies"}"""


def encode_image(image_path):
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_vision_model(image_path, ollama_host, model, timeout):
    image_b64 = encode_image(image_path)

    payload = {
        'model': model,
        'prompt': PROMPT,
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

            raw_response = call_vision_model(job.image_path, ollama_host, model, timeout)

            data = json.loads(raw_response)

            if data.get('vendor_name'):
                expense.vendor_name = data['vendor_name']
            if data.get('description'):
                expense.description = data['description']
            if data.get('expense_date'):
                try:
                    expense.expense_date = datetime.strptime(data['expense_date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            if data.get('ex_gst_amount') is not None:
                try:
                    expense.ex_gst_amount = Decimal(str(data['ex_gst_amount']))
                except (ValueError, TypeError):
                    pass
            if data.get('gst_amount') is not None:
                try:
                    expense.gst_amount = Decimal(str(data['gst_amount']))
                except (ValueError, TypeError):
                    pass
            if data.get('gst_type') is not None:
                try:
                    expense.gst_type = Decimal(str(data['gst_type']))
                except (ValueError, TypeError):
                    pass

            if expense.ex_gst_amount and expense.gst_amount:
                expense.total_amount = expense.ex_gst_amount + expense.gst_amount

            job.status = 'completed'
            job.extracted_data = data
            job.processed_at = datetime.now(timezone.utc)
            db.session.commit()

        except json.JSONDecodeError as e:
            job.status = 'failed'
            job.error_message = f'JSON parse error: {str(e)} - Response: {raw_response[:500] if raw_response else "empty"}'
            job.processed_at = datetime.now(timezone.utc)
            db.session.commit()

        except Exception as e:
            job.status = 'pending'
            job.error_message = str(e)
            db.session.commit()


def run_processor(ollama_host, model, timeout, poll_interval=5, max_attempts=3):
    app = create_app()

    print(f'OCR Processor starting...')
    print(f'Vision model: {model} at {ollama_host}')
    print(f'Poll interval: {poll_interval}s')

    while True:
        with app.app_context():
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
