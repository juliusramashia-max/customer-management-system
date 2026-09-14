from email_validator import validate_email, EmailNotValidError
from decimal import Decimal, InvalidOperation


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