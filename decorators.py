"""
Reusable route decorators and helpers for authentication.
"""
from functools import wraps
from flask import session, jsonify

from database import db
from models import User


def current_user():
    """
    Return the User for the current session, or None if not logged in
    or if the user no longer exists.
    """
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    """
    Decorator: reject requests without a valid, existing authenticated user.

    This is stricter than just checking that 'user_id' is in the session.
    If the session references a user that has since been deleted
    (e.g., after wiping the dev database), we clear the stale session
    and return 401 — the same as if no session existed at all.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            # Clear any stale session so the client gets a clean state
            session.clear()
            return jsonify({'errors': ['Authentication required']}), 401
        return view(*args, **kwargs)
    return wrapper