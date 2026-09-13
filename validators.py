from email_validator import validate_email, EmailNotValidError


# Minimum password requirements — documented so tests can reference them
PASSWORD_MIN_LENGTH = 8


def validate_registration_data(data):
    """
    Validate registration input.

    Returns (cleaned_data, errors) where:
      - cleaned_data is a dict with normalised values (lowercased email)
      - errors is a list of human-readable error strings
    """
    errors = []

    if not isinstance(data, dict):
        return {}, ['Request body must be JSON object']

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    # --- Email ---
    if not email:
        errors.append('Email is required')
    else:
        try:
            # check_deliverability=False avoids DNS lookups in tests
            result = validate_email(email, check_deliverability=False)
            email = result.normalized.lower()
        except EmailNotValidError:
            errors.append('Email format is invalid')

    # --- Password ---
    if not password:
        errors.append('Password is required')
    elif len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f'Password must be at least {PASSWORD_MIN_LENGTH} characters')
    elif not any(c.isdigit() for c in password):
        errors.append('Password must contain at least one number')
    elif not any(c.isalpha() for c in password):
        errors.append('Password must contain at least one letter')

    return {'email': email, 'password': password}, errors

def validate_login_data(data):
    """
    Minimal validation for login. We only check that email and password
    are present. We do NOT enforce format/policy here on purpose:
      - Login is not the place to teach the user about password rules.
      - Stricter checks risk leaking information.
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