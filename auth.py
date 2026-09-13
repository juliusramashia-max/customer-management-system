from flask import Blueprint, request, jsonify, session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from models import User
from validators import validate_registration_data, validate_login_data
from decorators import login_required, current_user

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

# Used as a target for check_password_hash when a user isn't found.
# This makes the "user not found" path take the same time as the
# "wrong password" path, defeating timing-based user enumeration.
_DUMMY_HASH = generate_password_hash('not-a-real-password-xyz123')


# =====================================================================
# REGISTER
# =====================================================================
@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user.

    Request JSON:  { "email": "...", "password": "..." }
    Response 201:  { "user": {...}, "message": "..." }
    Response 400:  { "errors": [...] }
    Response 409:  { "errors": ["An account with this email already exists"] }
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    # Full validation (format, length, character rules, normalisation)
    cleaned, errors = validate_registration_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    # Duplicate check (also guarded by a UNIQUE DB constraint)
    existing = User.query.filter_by(email=cleaned['email']).first()
    if existing:
        return jsonify({'errors': ['An account with this email already exists']}), 409

    # Create the user with a hashed password
    user = User(email=cleaned['email'])
    user.set_password(cleaned['password'])

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Race condition: another request created the same email
        # between our SELECT and INSERT. The unique constraint catches it.
        db.session.rollback()
        return jsonify({'errors': ['An account with this email already exists']}), 409

    # Auto-login: establish a session for the new user
    session.clear()
    session['user_id'] = user.id

    return jsonify({
        'message': 'Registration successful',
        'user': user.to_dict(),
    }), 201


# =====================================================================
# LOGIN
# =====================================================================
@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate a user and start a session.

    Request JSON:  { "email": "...", "password": "..." }
    Response 200:  { "message": "...", "user": {...} }
    Response 400:  { "errors": [...] }
    Response 401:  { "errors": ["Invalid email or password"] }
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    # Minimal validation (presence only)
    cleaned, errors = validate_login_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    # Look up the user
    user = User.query.filter_by(email=cleaned['email']).first()

    # Constant-time-ish behaviour for enumeration protection.
    # If the user doesn't exist, still run a hash check against the
    # dummy hash so the response time matches the wrong-password case.
    if user is None:
        check_password_hash(_DUMMY_HASH, cleaned['password'])
        return jsonify({'errors': ['Invalid email or password']}), 401

    if not user.check_password(cleaned['password']):
        return jsonify({'errors': ['Invalid email or password']}), 401

    # Session fixation protection
    session.clear()
    session['user_id'] = user.id

    return jsonify({
        'message': 'Login successful',
        'user': user.to_dict(),
    }), 200

# =====================================================================
# CURRENT USER  (protected)
# =====================================================================
@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    """
    Return the currently authenticated user.

    This is the canonical way for a client to check "am I logged in?"
    and "who am I?".
    """
    user = current_user()
    if user is None:
        # Session references a user that no longer exists.
        # Clear the stale session and treat it as unauthenticated.
        session.clear()
        return jsonify({'errors': ['Authentication required']}), 401

    return jsonify({'user': user.to_dict()}), 200


# =====================================================================
# LOGOUT  (protected)
# =====================================================================
@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    End the current session.

    Requires an active session — calling logout while logged out
    returns 401, since there is nothing to log out of.
    """
    session.clear()
    return jsonify({'message': 'Logged out'}), 200