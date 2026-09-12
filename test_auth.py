import pytest
from app import app
from database import db
from models import User


@pytest.fixture
def client():
    """Provide a test client with a fresh in-memory database."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False  # not using CSRF yet, but harmless

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()


# ---------- Happy path ----------

def test_register_success(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'alice@example.com',
        'password': 'secret123',
    })
    assert response.status_code == 201

    data = response.get_json()
    assert data['user']['email'] == 'alice@example.com'
    assert 'id' in data['user']
    # Critical: password must never appear in the response
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
        # Hash is stored, not the plaintext
        assert user.password_hash != 'secret123'
        assert ':' in user.password_hash  # bcrypt hash format
        # And the hash verifies the original password
        assert user.check_password('secret123') is True
        assert user.check_password('wrongpass') is False


def test_register_normalises_email(client):
    response = client.post('/api/v1/auth/register', json={
        'email': 'Alice@EXAMPLE.com',
        'password': 'secret123',
    })
    assert response.status_code == 201
    assert response.get_json()['user']['email'] == 'alice@example.com'


# ---------- Validation failures ----------

def test_register_missing_email(client):
    response = client.post('/api/v1/auth/register', json={
        'password': 'secret123',
    })
    assert response.status_code == 400
    assert any('Email is required' in e for e in response.get_json()['errors'])


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


# ---------- Conflict ----------

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


# ---------- Bad requests ----------

def test_register_non_json_body(client):
    response = client.post(
        '/api/v1/auth/register',
        data='not json',
        content_type='text/plain',
    )
    assert response.status_code == 400