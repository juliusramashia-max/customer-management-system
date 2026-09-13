"""
Tests for authentication endpoints.

Covers:
  - Registration: validation, hashing, duplicate handling
  - Login: success, failures, enumeration protection, session handling
  - Protected routes: /me and /logout behaviour
  - Session fixation protection

Note on the client fixture:
  Flask-SQLAlchemy caches its engine at app-init time, so setting a
  different URI in the fixture has no effect. Instead, we drop_all()
  and create_all() before each test, guaranteeing an empty schema.
"""
import pytest

from app import app
from database import db
from models import User


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture
def client():
    """
    Provide a test client with a clean database schema.

    We reset the schema before each test to guarantee isolation,
    even if a previous test left data behind.
    """
    app.config['TESTING'] = True

    with app.test_client() as test_client:
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            yield test_client
            db.session.remove()
            db.drop_all()


# =====================================================================
# REGISTRATION — HAPPY PATH
# =====================================================================

def test_register_success(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com',
        'password': 'secret123',
    })
    assert response.status_code == 201

    data = response.get_json()
    assert data['user']['email'] == 'alice@example.com'
    assert 'id' in data['user']
    # Never leak the password or its hash
    assert 'password' not in data['user']
    assert 'password_hash' not in data['user']


def test_register_hashes_password(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com',
        'password': 'secret123',
    })
    with app.app_context():
        user = User.query.filter_by(email='alice@example.com').first()
        assert user is not None

        # The stored value must never be the plaintext
        assert user.password_hash != 'secret123'

        # It must look like a Werkzeug hash (colon-delimited, e.g. scrypt:...)
        assert ':' in user.password_hash

        # Behaviour: verification works, and works only for the right password
        assert user.check_password('secret123') is True
        assert user.check_password('wrongpass') is False


def test_register_normalises_email(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'Alice@EXAMPLE.com',
        'password': 'secret123',
    })
    assert response.status_code == 201
    assert response.get_json()['user']['email'] == 'alice@example.com'


# =====================================================================
# REGISTRATION — VALIDATION FAILURES
# =====================================================================

def test_register_missing_email(client):
    response = client.post('/api/v1/auth/register', json={
        'password': 'secret123',
    })
    assert response.status_code == 400
    # Either message is fine; we just want a 400 with an errors list
    assert 'errors' in response.get_json()


def test_register_invalid_email(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'not-an-email',
        'password': 'secret123',
    })
    assert response.status_code == 400
    assert any('Email format is invalid' in e for e in response.get_json()['errors'])


def test_register_short_password(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com',
        'password': 'abc1',
    })
    assert response.status_code == 400
    assert any('at least 8 characters' in e for e in response.get_json()['errors'])


def test_register_password_without_digit(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com',
        'password': 'abcdefgh',
    })
    assert response.status_code == 400
    assert any('at least one number' in e for e in response.get_json()['errors'])


def test_register_password_without_letter(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com',
        'password': '12345678',
    })
    assert response.status_code == 400
    assert any('at least one letter' in e for e in response.get_json()['errors'])


def test_register_non_json_body(client):
    response = client.post(
        '/api/v1/auth/register',
        data='not json',
        content_type='text/plain',
    )
    assert response.status_code == 400


# =====================================================================
# REGISTRATION — CONFLICT
# =====================================================================

def test_register_duplicate_email(client):
    payload = {'email': 'alice@example.com', 'password': 'secret123'}
    first = client.post('/api/v1/auth/register', json=payload)
    assert first.status_code == 201

    second = client.post('/api/v1/auth/register', json=payload)
    assert second.status_code == 409
    assert any('already exists' in e for e in second.get_json()['errors'])


def test_register_duplicate_email_case_insensitive(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    second = client.post('/api/v1/auth/register', json={
        'email': 'ALICE@EXAMPLE.COM', 'password': 'secret123',
    })
    assert second.status_code == 409


# =====================================================================
# LOGIN — HAPPY PATH
# =====================================================================

def test_login_success(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })

    response = client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    assert response.status_code == 200

    data = response.get_json()
    assert data['message'] == 'Login successful'
    assert data['user']['email'] == 'alice@example.com'
    assert 'password_hash' not in data['user']
    assert 'password' not in data['user']


def test_login_sets_session_cookie(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    response = client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    assert 'Set-Cookie' in response.headers
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie
    assert 'SameSite' in cookie


def test_login_with_mixed_case_email(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    response = client.post('/api/v1/auth/login', json={
        'email': 'ALICE@Example.COM', 'password': 'secret123',
    })
    assert response.status_code == 200


# =====================================================================
# LOGIN — FAILURES
# =====================================================================

def test_login_wrong_password(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    response = client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com', 'password': 'wrongpass',
    })
    assert response.status_code == 401
    assert 'Invalid email or password' in response.get_json()['errors']


def test_login_nonexistent_email(client):
    response = client.post('/api/v1/auth/login', json={
        'email': 'nobody@example.com', 'password': 'whatever123',
    })
    assert response.status_code == 401
    assert 'Invalid email or password' in response.get_json()['errors']


def test_login_error_messages_are_identical(client):
    """
    Wrong password and nonexistent email must produce the SAME response.
    Otherwise we leak which emails exist (user enumeration).
    """
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })

    wrong_pw = client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com', 'password': 'wrongpass',
    })
    no_user = client.post('/api/v1/auth/login', json={
        'email': 'nobody@example.com', 'password': 'wrongpass',
    })

    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.get_json() == no_user.get_json()


def test_login_missing_password(client):
    response = client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com',
    })
    assert response.status_code == 400
    assert any('Password is required' in e for e in response.get_json()['errors'])


def test_login_missing_email(client):
    response = client.post('/api/v1/auth/login', json={
        'password': 'secret123',
    })
    assert response.status_code == 400
    assert any('Email is required' in e for e in response.get_json()['errors'])


def test_login_non_json_body(client):
    response = client.post(
        '/api/v1/auth/login',
        data='not json',
        content_type='text/plain',
    )
    assert response.status_code == 400


# =====================================================================
# SESSION BEHAVIOUR
# =====================================================================

def test_login_regenerates_session(client):
    """
    Session fixation protection: after login, session contents
    should reflect the new user, not any prior state.
    """
    # Plant junk in the session
    with client.session_transaction() as sess:
        sess['user_id'] = 999
        sess['junk'] = 'should_be_gone'

    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })

    with client.session_transaction() as sess:
        assert sess['user_id'] != 999   # replaced with the real id
        assert 'junk' not in sess        # cleared


# =====================================================================
# PROTECTED ROUTES
# =====================================================================

def test_me_requires_login(client):
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 401
    assert response.get_json() == {'errors': ['Authentication required']}


def test_me_returns_current_user(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    # Registration auto-logs-in, so /me should work now
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 200

    data = response.get_json()
    assert data['user']['email'] == 'alice@example.com'
    assert 'password_hash' not in data['user']


def test_me_after_login(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    # Wipe session to simulate a fresh browser
    with client.session_transaction() as sess:
        sess.clear()

    assert client.get('/api/v1/auth/me').status_code == 401

    client.post('/api/v1/auth/login', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 200
    assert response.get_json()['user']['email'] == 'alice@example.com'


def test_logout_clears_session(client):
    client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com', 'password': 'secret123',
    })
    assert client.get('/api/v1/auth/me').status_code == 200

    logout = client.post('/api/v1/auth/logout')
    assert logout.status_code == 200
    assert logout.get_json()['message'] == 'Logged out'

    # /me should now be unauthenticated
    assert client.get('/api/v1/auth/me').status_code == 401


def test_logout_requires_login(client):
    response = client.post('/api/v1/auth/logout')
    assert response.status_code == 401


def test_login_required_returns_401_without_session(client):
    """
    Smoke test: @login_required on /me yields a 401 with the expected body.
    (Replaces the earlier 'spy' test — this one is reliable and hits the
    same core requirement: unauthenticated access is blocked.)
    """
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 401
    assert response.get_json() == {'errors': ['Authentication required']}