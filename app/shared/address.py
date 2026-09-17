"""Shared address helpers — split + reassemble + validate.

Used by:
- app/api/xero_export.py (Xero CSV export; reads structured fields directly)
- app/api/routes.py (create/update customer + user; accepts structured fields,
  denormalises into the legacy `address` blob for PDF renderers)
- scripts/backfill_addresses.py (one-shot migration of legacy free-text into
  the new structured columns)

History: addresses used to be a single free-text TEXT column on customers
(and users). The Xero CSV export work exposed how lossy that was — the
splitter could guess 80% of cases but not all, and any future export
integration would have to re-implement the same heuristics.

Refactor (2026-09-17): separate structured columns for line1, line2, city,
state, postcode, country. The legacy `address` column is kept as a
denormalised display blob, regenerated on writes, so existing PDF code keeps
working.

AU state abbreviations (used for state validation):
    NSW, VIC, QLD, SA, WA, TAS, ACT, NT
"""

import re


# Australian state/territory abbreviations (uppercase).
AU_STATES = frozenset({'NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'ACT', 'NT'})


def split_address(address):
    """Best-effort crack of free-text address into structured components.

    Recognises both AU-style patterns:
        Line 1\nLine 2\nCity STATE POSTCODE\nCountry
        Street, Suburb STATE POSTCODE

    Returns (line1, line2, city, region, postcode, country).

    Anything that can't be parsed leaves the corresponding field empty —
    callers should fall back to the legacy `address` blob for display.
    """
    if not address:
        return ('', '', '', '', '', 'Australia')

    parts = [p.strip() for p in re.split(r'[\r\n]+|\s*,\s*', address) if p.strip()]
    if not parts:
        return ('', '', '', '', '', 'Australia')

    line1 = parts[0]
    line2 = parts[1] if len(parts) > 1 else ''
    city = ''
    region = ''
    postcode = ''
    country = 'Australia'

    # Find the line containing a 4-digit postcode.
    post_idx = None
    for i, p in enumerate(parts):
        if re.search(r'\b\d{4}\b', p):
            post_idx = i
            break

    if post_idx is None:
        return (line1, line2, '', '', '', country)

    pm = re.search(r'\b(\d{4})\b', parts[post_idx])
    postcode = pm.group(1) if pm else ''

    tokens = parts[post_idx].split()
    state_idx = None
    for j, t in enumerate(tokens):
        cleaned = re.sub(r'[^A-Za-z]', '', t).upper()
        if cleaned in AU_STATES:
            state_idx = j
            region = cleaned
            break

    if state_idx is not None:
        pre_tokens = [
            re.sub(r'[^A-Za-z\-\' ]', '', t).strip()
            for t in tokens[:state_idx]
        ]
        pre_tokens = [t for t in pre_tokens if t]
        if pre_tokens:
            city = ' '.join(pre_tokens)

        if not city and post_idx >= 1 and parts[post_idx - 1] != line1:
            city = parts[post_idx - 1]

    if post_idx >= 2:
        for k in range(1, post_idx):
            if parts[k] != line1 and parts[k] != city:
                line2 = parts[k]
                break

    if post_idx + 1 < len(parts):
        nxt = parts[post_idx + 1].strip()
        if nxt and not re.search(r'\d', nxt) and nxt.upper() not in AU_STATES:
            country = nxt

    return (line1, line2, city, region, postcode, country)


def render_address(obj):
    """Render a printable multi-line address from any model that has the
    structured fields. Works on both Customer (uses `country`) and User
    (uses `address_country`).

    Returns '' if every component is empty. Suitable for PDF rendering,
    plain-text emails, and any consumer that just wants a printable string.
    """
    if obj is None:
        return ''
    # address_country wins over country because on the User model
    # `country` is the 2-letter locale code (e.g. 'AU'), not the
    # address's country name ('Australia'). On Customer there's no
    # `address_country` so this falls through to `country` correctly.
    country = (
        getattr(obj, 'address_country', None)
        or getattr(obj, 'country', None)
        or 'Australia'
    )
    return reassemble_address(
        getattr(obj, 'address_line1', None),
        getattr(obj, 'address_line2', None),
        getattr(obj, 'city', None),
        getattr(obj, 'state', None),
        getattr(obj, 'postcode', None),
        country,
    )


def reassemble_address(line1=None, line2=None, city=None,
                       state=None, postcode=None, country=None):
    """Reassemble structured fields into a multi-line display string.

    Skips empty components AND drops line2 if it duplicates the formatted
    locality (the splitter assigns the suburb/state/postcode line to line2
    when the address is comma-separated, so reassembling naively would
    produce a duplicated line).

    Result is suitable for PDF rendering and any consumer that just wants
    a printable address.

    Example output (when all fields are populated):
        2/26 Argon Street
        Sumner QLD 4074
        Australia
    """
    locality = _format_locality(city, state, postcode)
    parts = []
    for chunk in (line1, line2, locality, country):
        chunk = (chunk or '').strip()
        if not chunk:
            continue
        # Skip duplicates (case-insensitive, whitespace-normalised)
        key = re.sub(r'\s+', ' ', chunk).lower()
        if any(
            re.sub(r'\s+', ' ', existing).lower() == key
            for existing in parts
        ):
            continue
        parts.append(chunk)
    return '\n'.join(parts)


def _format_locality(city, state, postcode):
    """Format city/state/postcode into a single locality line.

    Conventions:
        "Sumner QLD 4074"  (city + state + postcode)
        "QLD 4074"         (no city)
        "Sumner"           (city only — no state/postcode is unusual)
        ""                 (everything empty)
    """
    city = (city or '').strip()
    state = (state or '').strip().upper()
    postcode = (postcode or '').strip()

    if city and state and postcode:
        return f'{city} {state} {postcode}'
    if city and state:
        return f'{city} {state}'
    if city and postcode:
        return f'{city} {postcode}'
    if state and postcode:
        return f'{state} {postcode}'
    return city or state or postcode


def validate_state(state, country='Australia'):
    """Validate that the state is a recognised AU state abbreviation when the
    country is Australia. Returns (ok, normalised_state_or_error_msg).

    For non-AU addresses we accept any state string (no DB CHECK so we don't
    block non-AU customers from countries we don't currently support).
    """
    if state is None or state == '':
        return (True, '')  # empty is OK — address is optional

    normalised = state.strip().upper()
    if country and country.strip().lower() in ('australia', 'au'):
        if normalised not in AU_STATES:
            return (False, f'state must be one of {sorted(AU_STATES)} (got {state!r})')
    return (True, normalised)


def validate_postcode(postcode, country='Australia'):
    """Validate postcode format. AU postcodes are 4 digits. Returns
    (ok, normalised_or_error_msg)."""
    if postcode is None or postcode == '':
        return (True, '')  # empty is OK

    s = str(postcode).strip()
    if country and country.strip().lower() in ('australia', 'au'):
        if not re.match(r'^\d{4}$', s):
            return (False, f'AU postcode must be 4 digits (got {postcode!r})')
    return (True, s)
