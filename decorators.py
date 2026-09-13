"""
Reusable route decorators and helpers for authentication.

Keeping these in their own module avoids circular imports: routes in
auth.py, customers.py, invoices.py, etc. can all import from here.
"""
from functools import wraps
from flask import session, jsonify

from models import User


def current_user():
    """
    Return the User for the current session, or None if not logged in.

    Always reads from the database rather than caching values in the
    session, so changes (email update, user deletion) are reflected
    immediately.
    """
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return User.query.get(user_id)


def login_required(view):
    """
    Decorator: reject requests without an authenticated session.

    Usage:
        @auth_bp.route('/me')
        @login_required
        def me():
            ...

    Unauthenticated requests receive 401 with a JSON body — never a
    redirect, since our API clients expect JSON.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get('user_id') is None:
            return jsonify({'errors': ['Authentication required']}), 401
        return view(*args, **kwargs)
    return wrapper