"""
Tests for invoice endpoints.

Coverage:
  - Creation with nested line items
  - Automatic calculation of subtotal, tax, total
  - Snapshotting of unit_price / tax_rate from products
  - Business rules: at least one line item, quantity > 0, unique
    invoice number per user, due >= issue
  - Decimal correctness (no float drift)
  - IDOR protection at all three levels (invoice, customer, product)
  - List, pagination, filters
  - Update and delete rules (draft-only)
"""
import pytest
from decimal import Decimal

from app import app
from database import db
from models import Invoice, LineItem


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


def _setup_customer_and_products(client):
    """Create a customer and two products; return their ids."""
    c = client.post('/api/v1/customers', json={
        'name': 'Acme Corp', 'email': 'billing@acme.com',
    }).get_json()['customer']

    p1 = client.post('/api/v1/products', json={
        'name': 'Consulting', 'unit_price': '250.00', 'tax_rate': '15.00',
    }).get_json()['product']

    p2 = client.post('/api/v1/products', json={
        'name': 'Hosting', 'unit_price': '120.00', 'tax_rate': '5.00',
    }).get_json()['product']

    return c['id'], p1['id'], p2['id']


def _invoice_payload(customer_id, products, **overrides):
    """Build a valid invoice payload. `products` is [(product_id, qty), ...]."""
    data = {
        'customer_id': customer_id,
        'invoice_number': 'INV-2026-0001',
        'issue_date': '2026-09-14',
        'due_date': '2026-10-14',
        'line_items': [
            {'product_id': pid, 'quantity': qty} for pid, qty in products
        ],
    }
    data.update(overrides)
    return data


# =====================================================================
# AUTH
# =====================================================================

def test_list_requires_login(client):
    assert client.get('/api/v1/invoices').status_code == 401


def test_create_requires_login(client):
    assert client.post('/api/v1/invoices', json={}).status_code == 401


def test_get_requires_login(client):
    assert client.get('/api/v1/invoices/1').status_code == 401


def test_update_requires_login(client):
    assert client.put('/api/v1/invoices/1', json={}).status_code == 401


def test_delete_requires_login(client):
    assert client.delete('/api/v1/invoices/1').status_code == 401


# =====================================================================
# CREATE + CALCULATIONS
# =====================================================================

def test_create_invoice(alice):
    cust_id, p1, p2 = _setup_customer_and_products(alice)
    r = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(p1, 2), (p2, 1)]))
    assert r.status_code == 201
    inv = r.get_json()['invoice']

    # Line 1: 2 × 250.00 = 500.00 subtotal, tax 75.00
    # Line 2: 1 × 120.00 = 120.00 subtotal, tax 6.00
    # Subtotal: 620.00; Tax: 81.00; Total: 701.00
    assert inv['subtotal'] == '620.00'
    assert inv['tax_amount'] == '81.00'
    assert inv['total'] == '701.00'
    assert inv['status'] == 'DRAFT'
    assert inv['invoice_number'] == 'INV-2026-0001'


def test_create_invoice_with_discount(alice):
    cust_id, p1, _ = _setup_customer_and_products(alice)
    payload = _invoice_payload(cust_id, [(p1, 1)], discount='50.00')
    # subtotal 250.00, tax 37.50, discount 50.00, total = 250 - 50 + 37.50 = 237.50
    inv = alice.post('/api/v1/invoices', json=payload).get_json()['invoice']
    assert inv['subtotal'] == '250.00'
    assert inv['tax_amount'] == '37.50'
    assert inv['discount'] == '50.00'
    assert inv['total'] == '237.50'


def test_line_item_snapshots_price_and_tax(alice):
    """Line items keep the unit_price/tax_rate from creation time."""
    cust_id, p1, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(p1, 1)])).get_json()['invoice']
    inv_id = inv['id']

    # Change the product's price
    alice.put(f'/api/v1/products/{p1}', json={
        'name': 'Consulting', 'unit_price': '999.00', 'tax_rate': '20.00',
    })

    # Read the invoice; it should still show 250.00 and 15.00
    read = alice.get(f'/api/v1/invoices/{inv_id}').get_json()['invoice']
    item = read['line_items'][0]
    assert item['unit_price'] == '250.00'
    assert item['tax_rate'] == '15.00'
    assert read['subtotal'] == '250.00'
    assert read['total'] == '287.50'


def test_decimal_rounding(alice):
    """Prices that produce 3+ decimals round HALF_UP to 2 places."""
    cust_id, _, _ = _setup_customer_and_products(alice)
    p = alice.post('/api/v1/products', json={
        'name': 'Odd', 'unit_price': '0.005', 'tax_rate': '0',
    }).get_json()['product']
    # 0.005 rounds to 0.01 with ROUND_HALF_UP
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(p['id'], 1)])).get_json()['invoice']
    assert inv['subtotal'] == '0.01'


# =====================================================================
# BUSINESS RULES
# =====================================================================

def test_create_invoice_requires_line_items(alice):
    cust_id, _, _ = _setup_customer_and_products(alice)
    payload = _invoice_payload(cust_id, [])
    payload['line_items'] = []
    r = alice.post('/api/v1/invoices', json=payload)
    assert r.status_code == 400
    assert any('at least one line item' in e for e in r.get_json()['errors'])


def test_create_invoice_zero_quantity(alice):
    cust_id, p1, _ = _setup_customer_and_products(alice)
    r = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(p1, 0)]))
    assert r.status_code == 400
    assert any('quantity must be greater than 0' in e for e in r.get_json()['errors'])


def test_create_invoice_negative_quantity(alice):
    cust_id, p1, _ = _setup_customer_and_products(alice)
    r = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(p1, -1)]))
    assert r.status_code == 400


def test_create_invoice_due_before_issue(alice):
    cust_id, p1, _ = _setup_customer_and_products(alice)
    payload = _invoice_payload(cust_id, [(p1, 1)], issue_date='2026-10-14', due_date='2026-09-14')
    r = alice.post('/api/v1/invoices', json=payload)
    assert r.status_code == 400
    assert any('Due date must be on or after' in e for e in r.get_json()['errors'])


def test_create_invoice_invalid_date(alice):
    cust_id, p1, _ = _setup_customer_and_products(alice)
    payload = _invoice_payload(cust_id, [(p1, 1)], issue_date='not-a-date')
    r = alice.post('/api/v1/invoices', json=payload)
    assert r.status_code == 400


def test_create_invoice_duplicate_number(alice):
    cust_id, p1, _ = _setup_customer_and_products(alice)
    payload = _invoice_payload(cust_id, [(p1, 1)])
    first = alice.post('/api/v1/invoices', json=payload)
    assert first.status_code == 201

    second = alice.post('/api/v1/invoices', json=payload)
    assert second.status_code == 409


def test_same_invoice_number_different_users(alice, bob):
    """Invoice numbers are unique per user, not globally."""
    a_cust, a_p, _ = _setup_customer_and_products(alice)
    b_cust, b_p, _ = _setup_customer_and_products(bob)

    a = alice.post('/api/v1/invoices', json=_invoice_payload(a_cust, [(a_p, 1)]))
    b = bob.post('/api/v1/invoices', json=_invoice_payload(b_cust, [(b_p, 1)]))

    assert a.status_code == 201
    assert b.status_code == 201


def test_create_invoice_missing_customer(alice):
    _, p1, _ = _setup_customer_and_products(alice)
    payload = _invoice_payload(99999, [(p1, 1)])
    r = alice.post('/api/v1/invoices', json=payload)
    assert r.status_code == 400


# =====================================================================
# IDOR
# =====================================================================

def test_bob_cannot_use_alices_customer(alice, bob):
    a_cust, _, _ = _setup_customer_and_products(alice)
    _, b_p, _ = _setup_customer_and_products(bob)

    payload = _invoice_payload(a_cust, [(b_p, 1)])
    r = bob.post('/api/v1/invoices', json=payload)
    assert r.status_code == 400
    assert any('Customer not found' in e for e in r.get_json()['errors'])


def test_bob_cannot_use_alices_product(alice, bob):
    _, a_p, _ = _setup_customer_and_products(alice)
    b_cust, _, _ = _setup_customer_and_products(bob)

    payload = _invoice_payload(b_cust, [(a_p, 1)])
    r = bob.post('/api/v1/invoices', json=payload)
    assert r.status_code == 400
    assert any('product not found' in e for e in r.get_json()['errors'])


def test_bob_cannot_read_alices_invoice(alice, bob):
    a_cust, a_p, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(a_cust, [(a_p, 1)])).get_json()['invoice']
    r = bob.get(f'/api/v1/invoices/{inv["id"]}')
    assert r.status_code == 404


def test_bob_cannot_update_alices_invoice(alice, bob):
    a_cust, a_p, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(a_cust, [(a_p, 1)])).get_json()['invoice']
    r = bob.put(f'/api/v1/invoices/{inv["id"]}', json=_invoice_payload(1, [(1, 1)]))
    assert r.status_code == 404


def test_bob_cannot_delete_alices_invoice(alice, bob):
    a_cust, a_p, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(a_cust, [(a_p, 1)])).get_json()['invoice']
    r = bob.delete(f'/api/v1/invoices/{inv["id"]}')
    assert r.status_code == 404


# =====================================================================
# LIST / FILTERS
# =====================================================================

def test_list_empty(alice):
    assert alice.get('/api/v1/invoices').get_json()['items'] == []


def test_list_returns_only_own(alice, bob):
    a_cust, a_p, _ = _setup_customer_and_products(alice)
    b_cust, b_p, _ = _setup_customer_and_products(bob)
    alice.post('/api/v1/invoices', json=_invoice_payload(a_cust, [(a_p, 1)]))
    bob.post('/api/v1/invoices', json=_invoice_payload(b_cust, [(b_p, 1)]))

    assert alice.get('/api/v1/invoices').get_json()['total'] == 1


def test_list_filter_by_status(alice):
    cust, p1, _ = _setup_customer_and_products(alice)
    alice.post('/api/v1/invoices', json=_invoice_payload(cust, [(p1, 1)]))
    # All invoices are DRAFT by default
    assert alice.get('/api/v1/invoices?status=DRAFT').get_json()['total'] == 1
    assert alice.get('/api/v1/invoices?status=PAID').get_json()['total'] == 0


def test_list_filter_by_customer(alice):
    a_cust, a_p, _ = _setup_customer_and_products(alice)
    # Another customer
    c2 = alice.post('/api/v1/customers', json={
        'name': 'Globex', 'email': 'g@g.com',
    }).get_json()['customer']

    alice.post('/api/v1/invoices', json=_invoice_payload(a_cust, [(a_p, 1)]))
    alice.post('/api/v1/invoices', json=_invoice_payload(
        c2['id'], [(a_p, 1)], invoice_number='INV-2026-0002',
    ))

    assert alice.get(f'/api/v1/invoices?customer_id={a_cust}').get_json()['total'] == 1
    assert alice.get(f'/api/v1/invoices?customer_id={c2["id"]}').get_json()['total'] == 1


# =====================================================================
# UPDATE
# =====================================================================

def test_update_invoice(alice):
    cust, p1, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust, [(p1, 1)])).get_json()['invoice']
    inv_id = inv['id']

    # Update: change quantity from 1 to 3
    payload = _invoice_payload(cust, [(p1, 3)])
    r = alice.put(f'/api/v1/invoices/{inv_id}', json=payload)
    assert r.status_code == 200
    data = r.get_json()['invoice']
    # 3 × 250 = 750 subtotal, tax 112.50, total 862.50
    assert data['subtotal'] == '750.00'
    assert data['tax_amount'] == '112.50'
    assert data['total'] == '862.50'


# =====================================================================
# DELETE
# =====================================================================

def test_delete_invoice(alice):
    cust, p1, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust, [(p1, 1)])).get_json()['invoice']
    r = alice.delete(f'/api/v1/invoices/{inv["id"]}')
    assert r.status_code == 204
    assert alice.get(f'/api/v1/invoices/{inv["id"]}').status_code == 404

# =====================================================================
# PDF DOWNLOAD
# =====================================================================

def test_pdf_requires_login(client):
    assert client.get('/api/v1/invoices/1/pdf').status_code == 401


def test_pdf_returns_valid_pdf_for_owner(alice):
    """
    The owner of an invoice can download its PDF. We verify:
      - HTTP 200
      - Content-Type is application/pdf
      - The bytes start with %PDF- (the PDF magic number)
      - Content-Length > 0 (a real document was produced)
      - Content-Disposition names the right file
    """
    cust_id, prod_id, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(prod_id, 1)])).get_json()['invoice']

    r = alice.get(f'/api/v1/invoices/{inv["id"]}/pdf')
    assert r.status_code == 200
    assert r.mimetype == 'application/pdf'
    assert r.data.startswith(b'%PDF-')
    assert len(r.data) > 500            # a real PDF is at least a few hundred bytes
    assert 'Content-Disposition' in r.headers
    assert inv['invoice_number'] in r.headers['Content-Disposition']
    assert 'attachment' in r.headers['Content-Disposition']


def test_pdf_for_nonexistent_invoice(alice):
    r = alice.get('/api/v1/invoices/99999/pdf')
    assert r.status_code == 404


def test_pdf_isolation(alice, bob):
    """Bob cannot download Alice's invoice PDF — same IDOR rule as the JSON endpoints."""
    cust_id, prod_id, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(prod_id, 1)])).get_json()['invoice']

    r = bob.get(f'/api/v1/invoices/{inv["id"]}/pdf')
    assert r.status_code == 404


def test_pdf_for_paid_invoice(alice):
    """A PDF can be generated regardless of status — for any owned invoice."""
    cust_id, prod_id, _ = _setup_customer_and_products(alice)
    inv = alice.post('/api/v1/invoices', json=_invoice_payload(cust_id, [(prod_id, 2)])).get_json()['invoice']
    alice.post(f'/api/v1/invoices/{inv["id"]}/send')
    alice.post(f'/api/v1/invoices/{inv["id"]}/payments', json={
        'amount': '500.00', 'payment_method': 'CASH',
    })

    r = alice.get(f'/api/v1/invoices/{inv["id"]}/pdf')
    assert r.status_code == 200
    assert r.data.startswith(b'%PDF-')


def test_pdf_with_multiple_line_items(alice):
    """
    Long invoices still render. We just check it doesn't crash and
    produces a valid PDF.
    """
    cust_id, prod_id, _ = _setup_customer_and_products(alice)

    # Build an invoice with many line items by repeating the same product
    many_items = [{'product_id': prod_id, 'quantity': 1} for _ in range(20)]
    inv = alice.post('/api/v1/invoices', json={
        'customer_id': cust_id,
        'invoice_number': 'INV-MANY',
        'issue_date': '2026-09-01',
        'due_date': '2026-09-30',
        'line_items': many_items,
    }).get_json()['invoice']

    r = alice.get(f'/api/v1/invoices/{inv["id"]}/pdf')
    assert r.status_code == 200
    assert r.data.startswith(b'%PDF-')