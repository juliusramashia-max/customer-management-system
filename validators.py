from email_validator import validate_email, EmailNotValidError
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from money import to_decimal
from decimal import Decimal


PASSWORD_MIN_LENGTH = 8


# =====================================================================
# REGISTRATION
# =====================================================================
def validate_registration_data(data):
    """
    Validate registration input.
    Returns (cleaned_data, errors).
    """
    errors = []

    if not isinstance(data, dict):
        return {}, ['Request body must be JSON object']

    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    # Email
    if not email:
        errors.append('Email is required')
    else:
        try:
            result = validate_email(email, check_deliverability=False)
            email = result.normalized.lower()
        except EmailNotValidError:
            errors.append('Email format is invalid')

    # Password
    if not password:
        errors.append('Password is required')
    elif len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f'Password must be at least {PASSWORD_MIN_LENGTH} characters')
    elif not any(c.isdigit() for c in password):
        errors.append('Password must contain at least one number')
    elif not any(c.isalpha() for c in password):
        errors.append('Password must contain at least one letter')

    return {'email': email, 'password': password}, errors


# =====================================================================
# LOGIN
# =====================================================================
def validate_login_data(data):
    """
    Minimal login validation — presence checks only.
    Returns (cleaned_data, errors).
    """
    errors = []

    if not isinstance(data, dict):
        return {}, ['Request body must be a JSON object']

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email:
        errors.append('Email is required')
    if not password:
        errors.append('Password is required')

    return {'email': email, 'password': password}, errors


# =====================================================================
# CUSTOMER
# =====================================================================
def validate_customer_data(data, partial=False):
    """
    Validate a customer payload.
    Returns (cleaned_data, errors).
    """
    errors = []

    if not isinstance(data, dict):
        return {}, ['Request body must be a JSON object']

    cleaned = {}

    # --- name (required) ---
    name = (data.get('name') or '').strip()
    if not name:
        errors.append('Name is required')
    elif len(name) > 100:
        errors.append('Name must be 100 characters or fewer')
    else:
        cleaned['name'] = name

    # --- email (required) ---
    email = (data.get('email') or '').strip()
    if not email:
        errors.append('Email is required')
    else:
        try:
            result = validate_email(email, check_deliverability=False)
            cleaned['email'] = result.normalized.lower()
        except EmailNotValidError:
            errors.append('Email format is invalid')

    # --- phone (optional) ---
    phone = data.get('phone')
    if phone is not None:
        phone = str(phone).strip()
        if len(phone) > 20:
            errors.append('Phone must be 20 characters or fewer')
        else:
            cleaned['phone'] = phone or None

    # --- company (optional) ---
    company = data.get('company')
    if company is not None:
        company = str(company).strip()
        if len(company) > 100:
            errors.append('Company must be 100 characters or fewer')
        else:
            cleaned['company'] = company or None

    # --- address (optional) ---
    address = data.get('address')
    if address is not None:
        address = str(address).strip()
        if len(address) > 200:
            errors.append('Address must be 200 characters or fewer')
        else:
            cleaned['address'] = address or None

    return cleaned, errors

def _parse_decimal(value, field_name, errors, min_value=None, max_value=None):
    """
    Parse a value into Decimal, appending a friendly error to `errors`
    if parsing fails or bounds are violated.

    Returns the Decimal on success, None on failure.
    """
    if value is None or value == '':
        errors.append(f'{field_name} is required')
        return None

    # JSON parses numbers as int/float; we go through str() to preserve
    # the user's exact input (e.g. "10.99" becomes Decimal('10.99'),
    # not the imprecise binary value of float 10.99).
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f'{field_name} must be a number')
        return None

    if min_value is not None and decimal_value < Decimal(min_value):
        errors.append(f'{field_name} cannot be less than {min_value}')
        return None
    if max_value is not None and decimal_value > Decimal(max_value):
        errors.append(f'{field_name} cannot be greater than {max_value}')
        return None

    return decimal_value


def validate_product_data(data):
    """
    Validate a product payload.

    Returns (cleaned_data, errors). cleaned_data contains a Decimal
    for unit_price and tax_rate, or is missing those keys if invalid.
    """
    errors = []

    if not isinstance(data, dict):
        return {}, ['Request body must be a JSON object']

    cleaned = {}

    # --- name (required) ---
    name = (data.get('name') or '').strip()
    if not name:
        errors.append('Name is required')
    elif len(name) > 100:
        errors.append('Name must be 100 characters or fewer')
    else:
        cleaned['name'] = name

    # --- description (optional) ---
    description = data.get('description')
    if description is not None:
        description = str(description).strip()
        cleaned['description'] = description or None

    # --- unit_price (required, >= 0) ---
    unit_price = _parse_decimal(
        data.get('unit_price'),
        'Unit price',
        errors,
        min_value='0',
    )
    if unit_price is not None:
        cleaned['unit_price'] = unit_price

    # --- tax_rate (required, 0 <= x <= 100) ---
    tax_rate = _parse_decimal(
        data.get('tax_rate'),
        'Tax rate',
        errors,
        min_value='0',
        max_value='100',
    )
    if tax_rate is not None:
        cleaned['tax_rate'] = tax_rate

    return cleaned, errors

def _parse_date(value, field_name, errors):
    """Parse YYYY-MM-DD into a datetime, or append an error."""
    if not value:
        errors.append(f'{field_name} is required')
        return None
    try:
        # datetime.fromisoformat handles 'YYYY-MM-DD' and full ISO timestamps
        parsed = datetime.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        errors.append(f'{field_name} must be a valid date (YYYY-MM-DD)')
        return None
    return parsed


def _validate_line_items(items, user_id, errors):
    """
    Validate the line_items array.

    Each entry must be:
      { "product_id": <int>, "quantity": <int > 0> }

    Returns a list of dicts:
      [{ "product": Product, "quantity": int }, ...]

    The products are fetched and ownership-checked against user_id. If
    a product doesn't exist OR isn't owned by user_id, we report the
    same error — no information leak.
    """
    from models import Product

    if not isinstance(items, list) or not items:
        errors.append('Invoice must contain at least one line item')
        return []

    validated = []
    for idx, entry in enumerate(items):
        prefix = f'Line item {idx + 1}'

        if not isinstance(entry, dict):
            errors.append(f'{prefix} must be an object')
            continue

        # --- product_id ---
        product_id = entry.get('product_id')
        if product_id is None:
            errors.append(f'{prefix}: product_id is required')
            continue
        try:
            product_id = int(product_id)
        except (ValueError, TypeError):
            errors.append(f'{prefix}: product_id must be an integer')
            continue

        # Ownership check
        product = Product.query.filter_by(id=product_id, user_id=user_id).first()
        if product is None:
            errors.append(f'{prefix}: product not found')
            continue

        # --- quantity ---
        quantity = entry.get('quantity')
        if quantity is None:
            errors.append(f'{prefix}: quantity is required')
            continue
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            errors.append(f'{prefix}: quantity must be an integer')
            continue
        if quantity <= 0:
            errors.append(f'{prefix}: quantity must be greater than 0')
            continue

        validated.append({'product': product, 'quantity': quantity})

    return validated


def validate_invoice_data(data, user_id):
    """
    Validate the payload for creating or updating an invoice.

    Returns (cleaned, errors) where cleaned contains:
      - customer: Customer instance
      - invoice_number: str
      - issue_date: datetime
      - due_date: datetime
      - discount: Decimal
      - notes: str or None
      - line_items: list of {"product": Product, "quantity": int}
    """
    from models import Customer

    errors = []

    if not isinstance(data, dict):
        return {}, ['Request body must be a JSON object']

    cleaned = {}

    # --- customer_id ---
    customer_id = data.get('customer_id')
    if customer_id is None:
        errors.append('customer_id is required')
    else:
        try:
            customer_id = int(customer_id)
        except (ValueError, TypeError):
            errors.append('customer_id must be an integer')
            customer_id = None
    if customer_id is not None:
        customer = Customer.query.filter_by(id=customer_id, user_id=user_id).first()
        if customer is None:
            errors.append('Customer not found')
        else:
            cleaned['customer'] = customer

    # --- invoice_number ---
    invoice_number = (data.get('invoice_number') or '').strip()
    if not invoice_number:
        errors.append('Invoice number is required')
    elif len(invoice_number) > 50:
        errors.append('Invoice number must be 50 characters or fewer')
    else:
        cleaned['invoice_number'] = invoice_number

    # --- issue_date ---
    issue_date = _parse_date(data.get('issue_date'), 'Issue date', errors)
    if issue_date is not None:
        cleaned['issue_date'] = issue_date

    # --- due_date ---
    due_date = _parse_date(data.get('due_date'), 'Due date', errors)
    if due_date is not None:
        cleaned['due_date'] = due_date

    # Cross-field: due >= issue
    if 'issue_date' in cleaned and 'due_date' in cleaned:
        if cleaned['due_date'] < cleaned['issue_date']:
            errors.append('Due date must be on or after issue date')

    # --- discount (optional, >= 0) ---
    discount_raw = data.get('discount', '0')
    try:
        discount = to_decimal(discount_raw)
    except Exception:
        errors.append('Discount must be a number')
        discount = None
    if discount is not None:
        if discount < Decimal('0'):
            errors.append('Discount cannot be negative')
        else:
            cleaned['discount'] = discount

    # --- notes (optional) ---
    notes = data.get('notes')
    if notes is not None:
        cleaned['notes'] = str(notes).strip() or None

    # --- line_items ---
    line_items = _validate_line_items(data.get('line_items'), user_id, errors)
    if line_items:
        cleaned['line_items'] = line_items

    return cleaned, errors