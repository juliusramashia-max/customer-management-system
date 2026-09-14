from email_validator import validate_email, EmailNotValidError


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