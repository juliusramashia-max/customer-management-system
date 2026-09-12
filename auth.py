from flask import Blueprint, request, jsonify, session
from sqlalchemy.exc import IntegrityError

from database import db
from models import User
from validators import validate_registration_data

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user.

    Request JSON:  { "email": "...", "password": "..." }
    Response 201:  { "user": {...}, "message": "..." }
    Response 400:  { "errors": [...] }
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    cleaned, errors = validate_registration_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    # Check for existing user (case-insensitive thanks to normalisation)
    existing = User.query.filter_by(email=cleaned['email']).first()
    if existing:
        # Same generic message we'd give anywhere — don't leak which emails exist
        return jsonify({'errors': ['An account with this email already exists']}), 409

    user = User(email=cleaned['email'])
    user.set_password(cleaned['password'])  # hashes internally

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Race condition: someone else registered the same email between
        # our SELECT above and this INSERT. The unique constraint saves us.
        db.session.rollback()
        return jsonify({'errors': ['An account with this email already exists']}), 409

    # Optional: log the user in immediately
    session['user_id'] = user.id

    return jsonify({
        'message': 'Registration successful',
        'user': user.to_dict(),
    }), 201