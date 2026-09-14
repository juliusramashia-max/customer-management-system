"""
Tests for customer CRUD endpoints.

Focus areas:
  - CRUD works end-to-end for the owning user
  - IDOR: user B cannot see/modify user A's customers
  - Validation: bad payloads produce 400
  - Conflict: duplicate email per user
  - Pagination and search
  - Unauthenticated access → 401

Important fixture design:
  Each actor (alice, bob) gets its OWN test client with its OWN cookie
  jar. If they shared a client, logging in as one would overwrite the
  other's session and every IDOR test would silently test the wrong thing.
"""
import pytest

from app import app
from database import db
from models import User, Customer


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture
def client():
    """
    Reset the schema before each test, then yield a base client.

    Other fixtures depend on this, so the schema reset happens exactly
    once per test, before any per-actor clients are built.
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


def _make_logged_in_client(email, password):
    """
    Create an independent test client logged in as the given user.

    Because it creates a fresh app.test_client(), this client has its
    own cookie jar — independent of any other actor's client.
    """
    c = app.test_client()
    r = c.post('/api/v1/auth/register', json={'email': email, 'password': password})
    if r.status_code == 409:
        c.post('/api/v1/auth/login', json={'email': email, 'password': password})
    return c


@pytest.fixture
def alice(client):
    """Independent client logged in as alice@example.com."""
    return _make_logged_in_client('alice@example.com', 'secret123')


@pytest.fixture
def bob(client):
    """Independent client logged in as bob@example.com."""
    return _make_logged_in_client('bob@example.com', 'secret456')


def _sample_customer(**overrides):
    """Helper: build a customer payload, with optional field overrides."""
    data = {
        'name': 'Acme Corp',
        'email': 'billing@acme.com',
        'phone': '+1 555-0101',
        'company': 'Acme Corporation',
        'address': '123 Main St',
    }
    data.update(overrides)
    return data


# =====================================================================
# AUTHENTICATION
# =====================================================================

def test_list_requires_login(client):
    assert client.get('/api/v1/customers').status_code == 401


def test_create_requires_login(client):
    assert client.post('/api/v1/customers', json=_sample_customer()).status_code == 401


def test_get_requires_login(client):
    assert client.get('/api/v1/customers/1').status_code == 401


def test_update_requires_login(client):
    assert client.put('/api/v1/customers/1', json=_sample_customer()).status_code == 401


def test_delete_requires_login(client):
    assert client.delete('/api/v1/customers/1').status_code == 401


# =====================================================================
# CREATE
# =====================================================================

def test_create_customer(alice):
    response = alice.post('/api/v1/customers', json=_sample_customer())
    assert response.status_code == 201
    data = response.get_json()['customer']
    assert data['name'] == 'Acme Corp'
    assert data['email'] == 'billing@acme.com'
    assert data['id'] > 0
    # Never leak user_id
    assert 'user_id' not in data


def test_create_customer_normalises_email(alice):
    response = alice.post('/api/v1/customers', json=_sample_customer(email='ACME@Example.COM'))
    assert response.status_code == 201
    assert response.get_json()['customer']['email'] == 'acme@example.com'


def test_create_customer_minimal_fields(alice):
    response = alice.post('/api/v1/customers', json={
        'name': 'Bare Minimum',
        'email': 'min@example.com',
    })
    assert response.status_code == 201
    data = response.get_json()['customer']
    assert data['phone'] is None
    assert data['company'] is None
    assert data['address'] is None


def test_create_customer_missing_name(alice):
    payload = _sample_customer()
    del payload['name']
    response = alice.post('/api/v1/customers', json=payload)
    assert response.status_code == 400
    assert any('Name is required' in e for e in response.get_json()['errors'])


def test_create_customer_missing_email(alice):
    payload = _sample_customer()
    del payload['email']
    response = alice.post('/api/v1/customers', json=payload)
    assert response.status_code == 400


def test_create_customer_invalid_email(alice):
    response = alice.post('/api/v1/customers', json=_sample_customer(email='not-email'))
    assert response.status_code == 400
    assert any('Email format is invalid' in e for e in response.get_json()['errors'])


def test_create_customer_duplicate_email_same_user(alice):
    alice.post('/api/v1/customers', json=_sample_customer())
    response = alice.post('/api/v1/customers', json=_sample_customer(name='Other'))
    assert response.status_code == 409


def test_create_customer_same_email_different_user(alice, bob):
    """Alice's customer email does not conflict with Bob's."""
    alice.post('/api/v1/customers', json=_sample_customer())
    response = bob.post('/api/v1/customers', json=_sample_customer())
    assert response.status_code == 201


# =====================================================================
# LIST + PAGINATION + SEARCH
# =====================================================================

def test_list_empty(alice):
    response = alice.get('/api/v1/customers')
    assert response.status_code == 200
    data = response.get_json()
    assert data['items'] == []
    assert data['total'] == 0


def test_list_returns_only_own_customers(alice, bob):
    alice.post('/api/v1/customers', json=_sample_customer(name='AliceCo', email='a@a.com'))
    bob.post('/api/v1/customers', json=_sample_customer(name='BobCo', email='b@b.com'))

    r = alice.get('/api/v1/customers')
    data = r.get_json()
    assert data['total'] == 1
    assert data['items'][0]['name'] == 'AliceCo'


def test_list_pagination(alice):
    for i in range(25):
        alice.post('/api/v1/customers', json=_sample_customer(
            name=f'Customer {i:02d}',
            email=f'c{i}@example.com',
        ))

    r = alice.get('/api/v1/customers?page=1&per_page=10')
    data = r.get_json()
    assert data['total'] == 25
    assert data['pages'] == 3
    assert len(data['items']) == 10

    r = alice.get('/api/v1/customers?page=3&per_page=10')
    assert len(r.get_json()['items']) == 5


def test_list_pagination_invalid_params(alice):
    assert alice.get('/api/v1/customers?page=0').status_code == 400
    assert alice.get('/api/v1/customers?page=abc').status_code == 400
    assert alice.get('/api/v1/customers?per_page=0').status_code == 400
    assert alice.get('/api/v1/customers?per_page=1000').status_code == 400


def test_list_search(alice):
    alice.post('/api/v1/customers', json=_sample_customer(
        name='Acme Corp', email='a@a.com', company='Acme Corporation',
    ))
    alice.post('/api/v1/customers', json=_sample_customer(
        name='Globex', email='g@g.com', company='Globex Industries',
    ))
    alice.post('/api/v1/customers', json=_sample_customer(
        name='Initech', email='i@i.com', company='Acme Subsidiary',
    ))

    r = alice.get('/api/v1/customers?q=acme')
    data = r.get_json()
    # "Acme Corp" (name match) and "Initech" (company="Acme Subsidiary")
    assert data['total'] == 2
    names = sorted(item['name'] for item in data['items'])
    assert names == ['Acme Corp', 'Initech']


# =====================================================================
# GET ONE
# =====================================================================

def test_get_customer(alice):
    created = alice.post('/api/v1/customers', json=_sample_customer()).get_json()['customer']
    r = alice.get(f'/api/v1/customers/{created["id"]}')
    assert r.status_code == 200
    assert r.get_json()['customer']['id'] == created['id']


def test_get_nonexistent(alice):
    assert alice.get('/api/v1/customers/99999').status_code == 404


# =====================================================================
# IDOR PROTECTION
# =====================================================================

def test_user_cannot_read_other_users_customer(alice, bob):
    created = alice.post('/api/v1/customers', json=_sample_customer()).get_json()['customer']
    r = bob.get(f'/api/v1/customers/{created["id"]}')
    assert r.status_code == 404
    assert 'not found' in r.get_json()['errors'][0].lower()


def test_user_cannot_update_other_users_customer(alice, bob):
    created = alice.post('/api/v1/customers', json=_sample_customer()).get_json()['customer']
    r = bob.put(f'/api/v1/customers/{created["id"]}', json=_sample_customer(name='HACKED'))
    assert r.status_code == 404

    # Verify Alice's data is untouched
    check = alice.get(f'/api/v1/customers/{created["id"]}').get_json()['customer']
    assert check['name'] == 'Acme Corp'


def test_user_cannot_delete_other_users_customer(alice, bob):
    created = alice.post('/api/v1/customers', json=_sample_customer()).get_json()['customer']
    r = bob.delete(f'/api/v1/customers/{created["id"]}')
    assert r.status_code == 404

    # Verify Alice's data is untouched
    assert alice.get(f'/api/v1/customers/{created["id"]}').status_code == 200


# =====================================================================
# UPDATE
# =====================================================================

def test_update_customer(alice):
    created = alice.post('/api/v1/customers', json=_sample_customer()).get_json()['customer']
    r = alice.put(f'/api/v1/customers/{created["id"]}', json=_sample_customer(
        name='Updated Name', email='updated@example.com',
    ))
    assert r.status_code == 200
    data = r.get_json()['customer']
    assert data['name'] == 'Updated Name'
    assert data['email'] == 'updated@example.com'


def test_update_duplicate_email(alice):
    a = alice.post('/api/v1/customers', json=_sample_customer(name='A', email='a@a.com')).get_json()['customer']
    alice.post('/api/v1/customers', json=_sample_customer(name='B', email='b@b.com'))

    # Try to make A use B's email
    r = alice.put(f'/api/v1/customers/{a["id"]}', json=_sample_customer(name='A', email='b@b.com'))
    assert r.status_code == 409


def test_update_nonexistent(alice):
    r = alice.put('/api/v1/customers/99999', json=_sample_customer())
    assert r.status_code == 404


# =====================================================================
# DELETE
# =====================================================================

def test_delete_customer(alice):
    created = alice.post('/api/v1/customers', json=_sample_customer()).get_json()['customer']
    r = alice.delete(f'/api/v1/customers/{created["id"]}')
    assert r.status_code == 204
    assert alice.get(f'/api/v1/customers/{created["id"]}').status_code == 404


def test_delete_nonexistent(alice):
    assert alice.delete('/api/v1/customers/99999').status_code == 404