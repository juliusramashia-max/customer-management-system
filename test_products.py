"""
Tests for product CRUD endpoints.

Focus areas:
  - CRUD works end-to-end for the owning user
  - IDOR: user B cannot see/modify user A's products
  - Validation: prices, tax rates, decimals handled correctly
  - Decimal correctness: money never loses precision
  - Pagination and search
  - Unauthenticated access → 401
"""
import pytest
from decimal import Decimal

from app import app
from database import db
from models import User, Product


@pytest.fixture
def client():
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
    c = app.test_client()
    r = c.post('/api/v1/auth/register', json={'email': email, 'password': password})
    if r.status_code == 409:
        c.post('/api/v1/auth/login', json={'email': email, 'password': password})
    return c


@pytest.fixture
def alice(client):
    return _make_logged_in_client('alice@example.com', 'secret123')


@pytest.fixture
def bob(client):
    return _make_logged_in_client('bob@example.com', 'secret456')


def _sample_product(**overrides):
    data = {
        'name': 'Consulting',
        'description': 'Business consulting services',
        'unit_price': '250.00',
        'tax_rate': '15.00',
    }
    data.update(overrides)
    return data


# =====================================================================
# AUTHENTICATION
# =====================================================================

def test_list_requires_login(client):
    assert client.get('/api/v1/products').status_code == 401


def test_create_requires_login(client):
    assert client.post('/api/v1/products', json=_sample_product()).status_code == 401


def test_get_requires_login(client):
    assert client.get('/api/v1/products/1').status_code == 401


def test_update_requires_login(client):
    assert client.put('/api/v1/products/1', json=_sample_product()).status_code == 401


def test_delete_requires_login(client):
    assert client.delete('/api/v1/products/1').status_code == 401


# =====================================================================
# CREATE
# =====================================================================

def test_create_product(alice):
    r = alice.post('/api/v1/products', json=_sample_product())
    assert r.status_code == 201
    data = r.get_json()['product']
    assert data['name'] == 'Consulting'
    assert data['description'] == 'Business consulting services'
    # Decimal values come back as strings
    assert data['unit_price'] == '250.00'
    assert data['tax_rate'] == '15.00'
    assert 'user_id' not in data


def test_create_product_with_numeric_json(alice):
    """A client sending 250.0 (float) still gets an exact Decimal('250.0')."""
    r = alice.post('/api/v1/products', json={
        'name': 'Web Dev',
        'unit_price': 1500.50,     # float in JSON
        'tax_rate': 15,             # int in JSON
    })
    assert r.status_code == 201
    data = r.get_json()['product']
    assert data['unit_price'] == '1500.50'
    assert data['tax_rate'] == '15.00'


def test_create_product_minimal(alice):
    """Description is optional."""
    r = alice.post('/api/v1/products', json={
        'name': 'Bare Minimum',
        'unit_price': '1.00',
        'tax_rate': '0',
    })
    assert r.status_code == 201
    assert r.get_json()['product']['description'] is None


def test_create_product_missing_name(alice):
    payload = _sample_product()
    del payload['name']
    r = alice.post('/api/v1/products', json=payload)
    assert r.status_code == 400
    assert any('Name is required' in e for e in r.get_json()['errors'])


def test_create_product_missing_price(alice):
    payload = _sample_product()
    del payload['unit_price']
    r = alice.post('/api/v1/products', json=payload)
    assert r.status_code == 400
    assert any('Unit price is required' in e for e in r.get_json()['errors'])


def test_create_product_missing_tax_rate(alice):
    payload = _sample_product()
    del payload['tax_rate']
    r = alice.post('/api/v1/products', json=payload)
    assert r.status_code == 400
    assert any('Tax rate is required' in e for e in r.get_json()['errors'])


def test_create_product_negative_price(alice):
    r = alice.post('/api/v1/products', json=_sample_product(unit_price='-5.00'))
    assert r.status_code == 400
    assert any('cannot be less than 0' in e for e in r.get_json()['errors'])


def test_create_product_negative_tax_rate(alice):
    r = alice.post('/api/v1/products', json=_sample_product(tax_rate='-1'))
    assert r.status_code == 400
    assert any('cannot be less than 0' in e for e in r.get_json()['errors'])


def test_create_product_tax_rate_too_high(alice):
    r = alice.post('/api/v1/products', json=_sample_product(tax_rate='150'))
    assert r.status_code == 400
    assert any('cannot be greater than 100' in e for e in r.get_json()['errors'])


def test_create_product_non_numeric_price(alice):
    r = alice.post('/api/v1/products', json=_sample_product(unit_price='abc'))
    assert r.status_code == 400
    assert any('must be a number' in e for e in r.get_json()['errors'])


def test_create_product_zero_price_is_valid(alice):
    """A free product is legal; only negative prices are rejected."""
    r = alice.post('/api/v1/products', json=_sample_product(unit_price='0'))
    assert r.status_code == 201


def test_create_product_decimal_precision_preserved(alice):
    """The DB stores exactly what we sent — no float drift."""
    r = alice.post('/api/v1/products', json=_sample_product(unit_price='10.99'))
    assert r.status_code == 201
    product_id = r.get_json()['product']['id']

    with app.app_context():
        product = db.session.get(Product, product_id)
        # Compare Decimals directly, not via string
        assert product.unit_price == Decimal('10.99')
        # Not the float-approximation that would be 10.9900000000000002...
        assert str(product.unit_price) == '10.99'


# =====================================================================
# LIST + PAGINATION + SEARCH
# =====================================================================

def test_list_empty(alice):
    r = alice.get('/api/v1/products')
    assert r.status_code == 200
    assert r.get_json()['items'] == []


def test_list_returns_only_own_products(alice, bob):
    alice.post('/api/v1/products', json=_sample_product(name='AliceWidget'))
    bob.post('/api/v1/products', json=_sample_product(name='BobWidget'))

    r = alice.get('/api/v1/products')
    data = r.get_json()
    assert data['total'] == 1
    assert data['items'][0]['name'] == 'AliceWidget'


def test_list_pagination(alice):
    for i in range(25):
        alice.post('/api/v1/products', json=_sample_product(name=f'Product {i:02d}'))

    r = alice.get('/api/v1/products?page=1&per_page=10')
    data = r.get_json()
    assert data['total'] == 25
    assert data['pages'] == 3
    assert len(data['items']) == 10


def test_list_pagination_invalid(alice):
    assert alice.get('/api/v1/products?page=0').status_code == 400
    assert alice.get('/api/v1/products?page=abc').status_code == 400
    assert alice.get('/api/v1/products?per_page=0').status_code == 400
    assert alice.get('/api/v1/products?per_page=1000').status_code == 400


def test_list_search(alice):
    alice.post('/api/v1/products', json=_sample_product(name='Web Development'))
    alice.post('/api/v1/products', json=_sample_product(name='Consulting'))
    alice.post('/api/v1/products', json=_sample_product(
        name='Hosting', description='Web hosting plans',
    ))

    r = alice.get('/api/v1/products?q=web')
    data = r.get_json()
    # 'Web Development' (name) and 'Hosting' (description contains "Web")
    assert data['total'] == 2
    names = sorted(item['name'] for item in data['items'])
    assert names == ['Hosting', 'Web Development']


# =====================================================================
# GET ONE
# =====================================================================

def test_get_product(alice):
    created = alice.post('/api/v1/products', json=_sample_product()).get_json()['product']
    r = alice.get(f'/api/v1/products/{created["id"]}')
    assert r.status_code == 200
    assert r.get_json()['product']['id'] == created['id']


def test_get_nonexistent(alice):
    assert alice.get('/api/v1/products/99999').status_code == 404


# =====================================================================
# IDOR
# =====================================================================

def test_user_cannot_read_other_users_product(alice, bob):
    created = alice.post('/api/v1/products', json=_sample_product()).get_json()['product']
    r = bob.get(f'/api/v1/products/{created["id"]}')
    assert r.status_code == 404


def test_user_cannot_update_other_users_product(alice, bob):
    created = alice.post('/api/v1/products', json=_sample_product()).get_json()['product']
    r = bob.put(f'/api/v1/products/{created["id"]}', json=_sample_product(name='HACKED'))
    assert r.status_code == 404

    check = alice.get(f'/api/v1/products/{created["id"]}').get_json()['product']
    assert check['name'] == 'Consulting'


def test_user_cannot_delete_other_users_product(alice, bob):
    created = alice.post('/api/v1/products', json=_sample_product()).get_json()['product']
    r = bob.delete(f'/api/v1/products/{created["id"]}')
    assert r.status_code == 404

    assert alice.get(f'/api/v1/products/{created["id"]}').status_code == 200


# =====================================================================
# UPDATE
# =====================================================================

def test_update_product(alice):
    created = alice.post('/api/v1/products', json=_sample_product()).get_json()['product']
    r = alice.put(f'/api/v1/products/{created["id"]}', json=_sample_product(
        name='Updated', unit_price='99.99', tax_rate='20.00',
    ))
    assert r.status_code == 200
    data = r.get_json()['product']
    assert data['name'] == 'Updated'
    assert data['unit_price'] == '99.99'
    assert data['tax_rate'] == '20.00'


def test_update_nonexistent(alice):
    r = alice.put('/api/v1/products/99999', json=_sample_product())
    assert r.status_code == 404


# =====================================================================
# DELETE
# =====================================================================

def test_delete_product(alice):
    created = alice.post('/api/v1/products', json=_sample_product()).get_json()['product']
    r = alice.delete(f'/api/v1/products/{created["id"]}')
    assert r.status_code == 204
    assert alice.get(f'/api/v1/products/{created["id"]}').status_code == 404


def test_delete_nonexistent(alice):
    assert alice.delete('/api/v1/products/99999').status_code == 404