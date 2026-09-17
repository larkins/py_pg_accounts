#!/usr/bin/env python3
"""
One-shot historical backfill: split the legacy `address` TEXT column on
customers and users into the new structured columns.

This script is INTENDED FOR ONE-TIME USE on a pre-2026-09-17 install. After
that refactor:
  - The legacy `address` column has been dropped from both tables.
  - All new customers must be written with structured fields.

If you run this against a current install, it will fail because the
`address` column no longer exists. That's expected — keep this script in
the repo for archaeological reference and for fresh historical migrations
of archived data, but new installs should skip it entirely.

Why it exists (2026-09-17): addresses used to be a single free-text string.
The Xero CSV export work showed how lossy that was, so we added structured
columns and a backfill to populate them from existing data. The backfill was
run on the original install: 2 customers + 1
user successfully split. Evie's user address (`5 Fisher St Collingwood Park
QLD 4301`) was fixed by hand because the splitter couldn't disambiguate
without a comma separator.

Usage (legacy installs only):
    cd /home/mal/py_pg_accounts && ./venv/bin/python3 scripts/backfill_addresses.py

    # Dry-run mode (no writes; prints what would change):
    ./venv/bin/python3 scripts/backfill_addresses.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

# Bootstrap the app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ENV = Path(__file__).resolve().parent.parent / '.env'
if ENV.exists():
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

from app import create_app
from app.models import db
from app.models.customer import Customer
from app.models.user import User
from app.shared.address import split_address


def backfill_table(model, table_name, dry_run=False):
    """Backfill one table. Returns (split_count, skipped_count, skipped_examples).

    `skipped_examples` is a list of strings (sample addresses) that couldn't
    be split into a postcode + state — useful for follow-up manual cleanup.
    """
    split_count = 0
    skipped = 0
    skipped_examples = []

    # Guard: the legacy `address` column must exist (only on pre-refactor installs).
    if not hasattr(model, 'address'):
        print(f'  {table_name}: legacy `address` column not present — skipping '
              f'(this script is a no-op on post-2026-09-17 installs).')
        return 0, 0, []

    query = model.query.filter(
        db.or_(
            model.address_line1.is_(None),
            model.city.is_(None),
            model.state.is_(None),
            model.postcode.is_(None),
        ),
        model.address.isnot(None),
        model.address != '',
    )

    for row in query.all():
        line1, line2, city, region, postcode, country = split_address(row.address)

        # If we couldn't extract BOTH a postcode AND a state, the legacy
        # address probably doesn't have enough structure to backfill
        # meaningfully. Skip those — the summary lists them for manual
        # follow-up.
        if not postcode or not region:
            skipped += 1
            if len(skipped_examples) < 5:
                skipped_examples.append(
                    f'{table_name} {row.id[:8]} '
                    f'({getattr(row, "name", getattr(row, "email", "?"))}): '
                    f'{row.address!r}'
                )
            continue

        row.address_line1 = line1
        row.address_line2 = line2
        row.city = city
        row.state = region
        row.postcode = postcode
        # User model uses `address_country`; Customer uses `country`.
        if hasattr(row, 'address_country'):
            row.address_country = country
        else:
            row.country = country
        split_count += 1

    if not dry_run and split_count:
        db.session.commit()

    return split_count, skipped, skipped_examples


def main():
    parser = argparse.ArgumentParser(description='Backfill structured address columns.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would change without writing.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print(f'Mode: {"DRY RUN" if args.dry_run else "WRITE"}')
        print()

        cust_split, cust_skipped, cust_examples = backfill_table(
            Customer, 'customers', dry_run=args.dry_run,
        )
        print(f'Customers:')
        print(f'  split:   {cust_split}')
        print(f'  skipped: {cust_skipped} (no postcode/state extracted)')
        if cust_examples:
            print(f'  examples needing manual review:')
            for ex in cust_examples:
                print(f'    - {ex}')

        user_split, user_skipped, user_examples = backfill_table(
            User, 'users', dry_run=args.dry_run,
        )
        print(f'Users:')
        print(f'  split:   {user_split}')
        print(f'  skipped: {user_skipped} (no postcode/state extracted)')
        if user_examples:
            print(f'  examples needing manual review:')
            for ex in user_examples:
                print(f'    - {ex}')


if __name__ == '__main__':
    main()
