"""Pure-function builder for NAB-compatible ABA (Cemtext / Direct Entry) files.

The ABA format is an APCA standard for bulk electronic payments, accepted by
all major Australian banks including NAB. Files are plain-text with
fixed-width fields (every record is exactly 120 characters + CRLF).

Layout:
- One Type 0 header record (payer info)
- One or more Type 1 detail records (one per payment)
- One Type 7 file total record

Field positions and constraints follow the Cemtex ABA format specification
(see https://www.cemtexaba.com/aba-format/cemtex-aba-file-format-details/).

Why we hand-roll this rather than use a library:
- No good maintained Python ABA library exists
- The spec is small and stable
- We want pure functions for easy testing

History: added 2026-09-17 per Michael's request — replacing his manual
process of entering payments into NAB internet banking one at a time. The
ABAs we produce here are uploaded via NAB Direct Link / NAB Connect.

Future ENP fitouts integration: same format works for any business with a
NAB BSB; just swap the payer info + employee list.
"""

import re
from datetime import date
from decimal import Decimal


# A line is 120 characters, plus CRLF terminator. The CRLF is added by the
# caller (or by us at the end). The 120-char requirement is on the
# record content itself.
RECORD_LENGTH = 120

# Field positions are 1-indexed in the spec but we slice Python strings
# 0-indexed, so the constants below are inclusive start / exclusive end.
def _slice(s, start_1, end_1):
    return s[start_1 - 1:end_1 - 1]


def _pad(text, length, *, right_justify=False, fill=' '):
    """Pad (and truncate) a string to exactly `length` characters."""
    if text is None:
        text = ''
    text = str(text)
    if len(text) > length:
        text = text[:length]
    if right_justify:
        return text.rjust(length, fill)
    return text.ljust(length, fill)


def _bsb_format(bsb):
    """Normalise a BSB to NNN-NNN form (positions 2-8 in Type 0/1 records
    use this format per spec).

    Accepts: '123456', '123-456', '123 456'. Returns '123-456' or '' if
    the input isn't a valid 6-digit BSB.
    """
    if not bsb:
        return ''
    digits = re.sub(r'\D', '', str(bsb))
    if len(digits) != 6:
        return ''
    return f'{digits[:3]}-{digits[3:]}'


def _format_ddmmyy(d):
    """Date field format for ABA: DDMMYY (positions 75-80 in Type 0).
    Per spec: 'Must be numeric in the format DDMMYY'."""
    return d.strftime('%d%m%y')


def _format_amount_cents(amount):
    """Convert a dollar amount to whole cents, right-justified, zero-filled,
    10 characters wide. Per spec for positions 21-30 in Type 1 detail
    records (and the same shape for the totals in Type 7).

    NAB rejects anything > $99,999,999.99 so amount fits in 10 digits of
    cents. We'll cap with a sensible error if exceeded."""
    cents = int((Decimal(str(amount)) * 100).quantize(Decimal('1')))
    if cents < 0:
        raise ValueError(f'Amount must be non-negative (got {amount})')
    if cents >= 10 ** 10:
        raise ValueError(f'Amount too large for ABA format (got ${amount:,.2f})')
    return _pad(cents, 10, right_justify=True, fill='0')


def _clean_text(s, length):
    """Trim and ASCII-fold a free-text field. ABA doesn't allow non-ASCII
    characters and NAB's old systems choke on odd punctuation."""
    if s is None:
        s = ''
    # Strip non-ASCII (keep simple — most payroll data is already ASCII).
    s = s.encode('ascii', 'replace').decode('ascii').replace('?', '')
    return _pad(s, length)


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------

def build_header_record(user, processing_date):
    """Build the Type 0 (header) record for one ABA file.

    Args:
      user: a User row with bank_name / bsb / account_number / account_name.
            NAB uses 'NB' as the financial institution abbreviation (per
            their Direct Link docs); we hard-code that since it's a fixed
            value, not a per-user choice.
      processing_date: the date the bank should release the payments.

    Returns: a 120-character ASCII string.
    """
    fi_abbr = 'NAB'  # NAB. Per APCA Financial Institution abbreviation list (3 chars per spec).

    record = (
        '0'                        # 1: Record Type
        + _pad('', 17)             # 2-18: Blank (per spec)
        + '01'                     # 19-20: Reel Sequence Number (01 = first/only)
        + fi_abbr                  # 21-23: FI abbreviation (NAB)
        + _pad('', 7)              # 24-30: Blank
        + _clean_text(user.account_name or user.business_name or '', 26)  # 31-56: User name
        + _pad('301500', 6, right_justify=True, fill='0')  # 57-62: User ID Number (NAB issued, placeholder)
        + _clean_text('PAYROLL', 12)                        # 63-74: Description of entries
        + _format_ddmmyy(processing_date)                    # 75-80: Date to be processed
        + _pad('', 40)                                       # 81-120: Blank
    )
    assert len(record) == RECORD_LENGTH, f'Header record is {len(record)} chars, expected {RECORD_LENGTH}'
    return record


def build_detail_record(bsb, account_number, account_name, amount, lodgement_ref, payer_bsb=''):
    """Build one Type 1 (detail) record.

    Args:
      bsb: payee BSB. Accepted formats: '123456', '123-456'.
      account_number: payee account number, padded to 9 chars right-justified.
      account_name: 32-char account title (e.g. 'JESSICA PAUL').
      amount: dollar amount as Decimal/string/float. Converted to cents.
      lodgement_ref: 18-char reference that appears on payee's statement.
      payer_bsb: payer's BSB (used in the trace record, positions 81-87).
                 Pass `user.bsb` from the caller. Blank if unavailable —
                 the trace field becomes 7 blanks, which NAB accepts.

    Returns: a 120-character ASCII string.
    """
    bsb_field = _bsb_format(bsb) or _pad('', 7)
    acct_field = _pad(re.sub(r'\D', '', str(account_number or '')), 9, right_justify=True, fill=' ')
    amount_cents = _format_amount_cents(amount)
    name_clean = _clean_text(account_name or '', 32)

    # Lodgement reference: no leading spaces, zeroes, hyphens (per spec).
    # Many banks require alphanumeric only — we apply a permissive ASCII
    # filter but keep the value as the user supplied it (truncated to 18).
    lodgement_clean = re.sub(r'[^A-Za-z0-9 ]+', '', str(lodgement_ref or ''))[:18]

    # Trace BSB (positions 81-87): the payer's BSB. If we don't have it,
    # we leave the field blank — NAB accepts blank trace records.
    trace_bsb = _bsb_format(payer_bsb) or _pad('', 7)

    record = (
        '1'                        # 1: Record Type
        + bsb_field                # 2-8: Payee BSB (NNN-NNN)
        + acct_field               # 9-17: Payee Account Number
        + ' '                      # 18: Indicator (blank = new payment)
        + '53'                     # 19-20: Transaction Code (53 = Pay, payroll)
        + amount_cents             # 21-30: Amount in cents, right-justified zero-filled
        + name_clean               # 31-62: Title of Account (32 chars)
        + _pad(lodgement_clean, 18) # 63-80: Lodgement Reference (18 chars)
        + trace_bsb                # 81-87: Trace BSB (payer's BSB)
        + _pad('', 9)              # 88-96: Trace Account Number
        + _pad('', 16)             # 97-112: Name of Remitter (optional, blank = use file header)
        + _pad('', 8)              # 113-120: Amount of Withholding Tax (n/a for payroll)
    )
    assert len(record) == RECORD_LENGTH, f'Detail record is {len(record)} chars, expected {RECORD_LENGTH}'
    return record


def build_total_record(count, total_amount_cents):
    """Build the Type 7 (file total) record.

    Per Cemtex spec:
      - Positions 2-8: '999-999' (BSB Format Filler — fixed sentinel)
      - Positions 9-20: 12 spaces
      - Positions 21-30: File Net Total Amount (credits - debits)
      - Positions 31-40: File Credit Total Amount
      - Positions 41-50: File Debit Total Amount
      - Positions 51-74: 24 spaces
      - Positions 75-80: Count of Type 1 records (6 digits)
      - Positions 81-120: 40 spaces

    For a pure-credit batch (our use case), Net = Credits, Debits = 0.
    """
    net = _pad(int(total_amount_cents), 10, right_justify=True, fill='0')
    credit = _pad(int(total_amount_cents), 10, right_justify=True, fill='0')
    debit = _pad(0, 10, right_justify=True, fill='0')
    records = _pad(int(count), 6, right_justify=True, fill='0')

    record = (
        '7'                        # 1: Record Type
        + '999-999'                # 2-8: BSB Format Filler
        + _pad('', 12)             # 9-20: Blank
        + net                      # 21-30: Net Total
        + credit                   # 31-40: Credit Total
        + debit                    # 41-50: Debit Total
        + _pad('', 24)             # 51-74: Blank
        + records                  # 75-80: Count of Type 1 records
        + _pad('', 40)             # 81-120: Blank
    )
    assert len(record) == RECORD_LENGTH, f'Total record is {len(record)} chars, expected {RECORD_LENGTH}'
    return record


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build_aba_file(user, payments, processing_date):
    """Build a complete ABA file (as bytes) ready for upload.

    Args:
      user: a User row. Used to populate the file header (payer's bank
            details).
      payments: iterable of dicts with keys:
                - 'bsb':             payee BSB (string)
                - 'account_number':  payee account number (string, may have spaces/dashes)
                - 'account_name':    payee account title (string)
                - 'amount':          dollar amount (Decimal/str/float)
                - 'lodgement_ref':   reference that appears on payee's statement (string)
      processing_date: date the bank should release the payments.

    Returns: bytes (ASCII) terminated with CRLF between records.
    """
    payer_bsb = user.bsb or ''
    lines = [build_header_record(user, processing_date)]

    total_cents = 0
    count = 0
    for p in payments:
        lines.append(build_detail_record(
            bsb=p['bsb'],
            account_number=p['account_number'],
            account_name=p['account_name'],
            amount=p['amount'],
            lodgement_ref=p.get('lodgement_ref', ''),
            payer_bsb=payer_bsb,
        ))
        total_cents += int((Decimal(str(p['amount'])) * 100).quantize(Decimal('1')))
        count += 1

    lines.append(build_total_record(count, total_cents))

    # CRLF terminator per spec. Use \r\n explicitly so it works on all OSes.
    return ('\r\n'.join(lines) + '\r\n').encode('ascii')
