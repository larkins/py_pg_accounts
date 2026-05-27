#!/usr/bin/env python3
"""
Entry point for the Accounting System application.

This script initializes the Flask applications for both the API server
and the HMI (Human-Machine Interface) server.
"""

import os
import sys
import argparse
from threading import Thread

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import db


def init_database(app):
    """Initialize the database tables."""
    with app.app_context():
        db.create_all()
        print("Database tables created successfully.")


def run_api_server(app, host, port):
    """Run the API server."""
    print(f"Starting API server on {host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)


def run_hmi_server(app, host, port):
    """Run the HMI (Browser Interface) server."""
    print(f"Starting HMI server on {host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)


def main():
    parser = argparse.ArgumentParser(description='Accounting System')
    parser.add_argument('--config', '-c', default='config.yaml',
                        help='Path to configuration file')
    parser.add_argument('--init-db', action='store_true',
                        help='Initialize database tables only')
    parser.add_argument('--api-only', action='store_true',
                        help='Run API server only')
    parser.add_argument('--hmi-only', action='store_true',
                        help='Run HMI server only')
    parser.add_argument('--api-port', type=int, default=5061,
                        help='API server port (default: 5061)')
    parser.add_argument('--hmi-port', type=int, default=5062,
                        help='HMI server port (default: 5062)')
    parser.add_argument('--host', default='192.168.4.44',
                        help='Host address (default: 192.168.4.44)')

    args = parser.parse_args()

    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Warning: Config file '{config_path}' not found. Using defaults.")

    app = create_app(config_path if os.path.exists(config_path) else None)

    init_database(app)

    if args.init_db:
        print("Database initialization complete.")
        return

    host = args.host

    if args.api_only:
        run_api_server(app, host, args.api_port)
    elif args.hmi_only:
        run_hmi_server(app, host, args.hmi_port)
    else:
        api_thread = Thread(target=run_api_server, args=(app, host, args.api_port), daemon=True)
        hmi_thread = Thread(target=run_hmi_server, args=(app, host, args.hmi_port), daemon=True)

        api_thread.start()
        hmi_thread.start()

        print("Both servers started. Press Ctrl+C to stop.")

        try:
            api_thread.join()
            hmi_thread.join()
        except KeyboardInterrupt:
            print("\nShutting down servers...")
            sys.exit(0)


if __name__ == '__main__':
    main()
