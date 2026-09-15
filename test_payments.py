"""
Tests for payment endpoints, including the credit-note-on-overpayment policy.

Policy under test:
  - amount <= outstanding: record payment, update status, no credit note
  - amount >  outstanding: record payment, mark invoice PAID, issue a
    CreditNote for the excess, increase the customer's credit balance
  - delete_payment refuses when a credit note exists for the invoice
  - IDOR: user B cannot pay or read user A's invoices or credit notes

Fixture note:
  `alice` and `bob` are independent test clients with their own cookie
  jars. This is essential for the IDOR tests — if they shared a client,
  logging in as one would clobber the other's session.
"""
import pytest
from decimal import Decimal

from app import app
from database import db
from models import Invoice, Payment, CreditNote


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture
def client():
    """Reset the schema and yield a base client. Other fixtures depend on this."""
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
    """Return a fresh test client logged in as the given user."""
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


# =====================================================================
# HELPERS
# =====================================================================

def _setup_invoice(client, quantity=1, unit_price='100.00', tax_rate='10.00',
                   invoice_number='INV-TEST-0001'):
    """
    Create customer + product + invoice, move the invoice to SENT.

    With defaults: 1 × 100.00 = 100.00 subtotal, 10% tax = 10.00, total = 110.00.
    Returns (invoice_id, customer_id).
    """
    cust = client.post('/api/v1/customers', json={
        'name': 'Acme', 'email': 'acme@example.com',
    }).get_json()['customer']

    prod = client.post('/api/v1/products', json={
        'name': 'Consulting',
        'unit_price': unit_price,
        'tax_rate': tax_rate,
    }).get_json()['product']

    inv = client.post('/api/v1/invoices', json={
        'customer_id': cust['id'],
        'invoice_number': invoice_number,
        'issue_date': '2026-09-14',
        'due_date': '2026-10-14',
        'line_items': [{'product_id': prod['id'], 'quantity': quantity}],
    }).get_json()['invoice']

    client.post(f'/api/v1/invoices/{inv["id"]}/send')
    return inv['id'], cust['id']


# =====================================================================
# AUTHENTICATION
# =====================================================================

def test_list_requires_login(client):
    assert client.get('/api/v1/invoices/1/payments').status_code == 401


def test_create_requires_login(client):
    assert client.post('/api/v1/invoices/1/payments', json={}).status_code == 401


def test_get_requires_login(client):
    assert client.get('/api/v1/payments/1').status_code == 401


def test_delete_requires_login(client):
    assert client.delete('/api/v1/payments/1').status_code == 401


# =====================================================================
# NORMAL PAYMENTS (no overpayment)
# =====================================================================

def test_partial_payment(alice):
    inv_id, _ = _setup_invoice(alice)   # total 110.00
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00',
        'payment_method': 'CASH',
    })
    assert r.status_code == 201
    data = r.get_json()

    assert data['payment']['amount'] == '50.00'
    assert data['payment']['payment_method'] == 'CASH'
    assert data['invoice']['status'] == 'PARTIALLY_PAID'
    assert data['invoice']['total_paid'] == '50.00'
    assert data['invoice']['outstanding_balance'] == '60.00'
    assert data['customer']['credit_balance'] == '0.00'
    assert 'credit_note' not in data


def test_full_payment_marks_paid(alice):
    inv_id, _ = _setup_invoice(alice)   # total 110.00
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '110.00',
        'payment_method': 'BANK_TRANSFER',
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['invoice']['status'] == 'PAID'
    assert data['invoice']['outstanding_balance'] == '0.00'
    assert data['invoice']['total_paid'] == '110.00'
    assert data['customer']['credit_balance'] == '0.00'
    assert 'credit_note' not in data


def test_multiple_partial_payments(alice):
    inv_id, _ = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    })
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '30.00', 'payment_method': 'CARD',
    })
    data = r.get_json()
    assert data['invoice']['status'] == 'PARTIALLY_PAID'
    assert data['invoice']['total_paid'] == '80.00'
    assert data['invoice']['outstanding_balance'] == '30.00'


def test_second_payment_completes_invoice(alice):
    inv_id, _ = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    })
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '60.00', 'payment_method': 'CARD',
    })
    data = r.get_json()
    assert data['invoice']['status'] == 'PAID'
    assert data['invoice']['outstanding_balance'] == '0.00'


# =====================================================================
# OVERPAYMENT → CREDIT NOTE
# =====================================================================

def test_overpayment_creates_credit_note(alice):
    inv_id, cust_id = _setup_invoice(alice)   # total 110.00
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00',   # 20.00 over
        'payment_method': 'BANK_TRANSFER',
    })
    assert r.status_code == 201
    data = r.get_json()

    # Invoice fully paid
    assert data['invoice']['status'] == 'PAID'
    assert data['invoice']['total_paid'] == '130.00'
    assert data['invoice']['outstanding_balance'] == '0.00'

    # Credit note for the excess
    assert 'credit_note' in data
    assert data['credit_note']['amount'] == '20.00'
    assert data['credit_note']['customer_id'] == cust_id
    assert data['credit_note']['invoice_id'] == inv_id
    assert 'Overpayment' in data['credit_note']['reason']

    # Customer's credit balance
    assert data['customer']['credit_balance'] == '20.00'
    assert data['customer']['credit_balance_display'] == 'Due to you: 20.00'


def test_overpayment_after_partial_payment(alice):
    inv_id, cust_id = _setup_invoice(alice)   # total 110.00
    # First partial: 50
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    })
    # Then overpay the remaining 60 by 15
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '75.00', 'payment_method': 'CARD',
    })
    data = r.get_json()
    assert data['invoice']['status'] == 'PAID'
    assert data['credit_note']['amount'] == '15.00'
    assert data['customer']['credit_balance'] == '15.00'


def test_overpayment_by_one_cent(alice):
    """Even a tiny overpayment generates a credit note."""
    inv_id, _ = _setup_invoice(alice)   # 110.00
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '110.01', 'payment_method': 'CASH',
    })
    data = r.get_json()
    assert data['credit_note']['amount'] == '0.01'
    assert data['customer']['credit_balance'] == '0.01'


def test_credit_balance_accumulates_across_invoices(alice):
    """Two overpayments on two invoices → credit balance is the sum."""
    inv1, cust_id = _setup_invoice(alice, invoice_number='INV-A')
    prod = alice.get('/api/v1/products').get_json()['items'][0]

    inv2 = alice.post('/api/v1/invoices', json={
        'customer_id': cust_id,
        'invoice_number': 'INV-B',
        'issue_date': '2026-09-14',
        'due_date': '2026-10-14',
        'line_items': [{'product_id': prod['id'], 'quantity': 1}],
    }).get_json()['invoice']
    alice.post(f'/api/v1/invoices/{inv2["id"]}/send')

    # Overpay invoice 1 by 10.00, invoice 2 by 5.00
    alice.post(f'/api/v1/invoices/{inv1}/payments', json={
        'amount': '120.00', 'payment_method': 'CASH',
    })
    r = alice.post(f'/api/v1/invoices/{inv2["id"]}/payments', json={
        'amount': '115.00', 'payment_method': 'CASH',
    })

    data = r.get_json()
    assert data['customer']['credit_balance'] == '15.00'
    assert data['customer']['credit_balance_display'] == 'Due to you: 15.00'


def test_customer_read_includes_credit_balance(alice):
    inv_id, cust_id = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '150.00',   # 40.00 over
        'payment_method': 'CASH',
    })
    r = alice.get(f'/api/v1/customers/{cust_id}')
    cust = r.get_json()['customer']
    assert cust['credit_balance'] == '40.00'
    assert cust['credit_balance_display'] == 'Due to you: 40.00'


# =====================================================================
# CREDIT NOTES ENDPOINTS
# =====================================================================

def test_list_credit_notes(alice):
    inv_id, _ = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00', 'payment_method': 'CASH',
    })
    r = alice.get('/api/v1/credit-notes')
    assert r.status_code == 200
    data = r.get_json()
    assert data['total'] == 1
    assert data['items'][0]['amount'] == '20.00'


def test_read_one_credit_note(alice):
    inv_id, _ = _setup_invoice(alice)
    cn_id = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00', 'payment_method': 'CASH',
    }).get_json()['credit_note']['id']

    r = alice.get(f'/api/v1/credit-notes/{cn_id}')
    assert r.status_code == 200
    assert r.get_json()['credit_note']['amount'] == '20.00'


def test_credit_note_not_found(alice):
    r = alice.get('/api/v1/credit-notes/99999')
    assert r.status_code == 404


def test_invoice_read_includes_credit_notes(alice):
    inv_id, _ = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00', 'payment_method': 'CASH',
    })
    r = alice.get(f'/api/v1/invoices/{inv_id}')
    inv = r.get_json()['invoice']
    assert 'credit_notes' in inv
    assert len(inv['credit_notes']) == 1
    assert inv['credit_notes'][0]['amount'] == '20.00'


# =====================================================================
# DELETE GUARD
# =====================================================================

def test_delete_payment_blocked_when_credit_note_exists(alice):
    inv_id, _ = _setup_invoice(alice)
    payment_id = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00', 'payment_method': 'CASH',
    }).get_json()['payment']['id']

    r = alice.delete(f'/api/v1/payments/{payment_id}')
    assert r.status_code == 409
    assert any('credit note' in e.lower() for e in r.get_json()['errors'])


def test_delete_regular_payment_succeeds(alice):
    inv_id, _ = _setup_invoice(alice)   # 110.00
    payment_id = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    }).get_json()['payment']['id']

    r = alice.delete(f'/api/v1/payments/{payment_id}')
    assert r.status_code == 204

    # Invoice back to SENT, outstanding restored
    inv = alice.get(f'/api/v1/invoices/{inv_id}').get_json()['invoice']
    assert inv['status'] == 'SENT'
    assert inv['outstanding_balance'] == '110.00'
    assert inv['total_paid'] == '0.00'


# =====================================================================
# BUSINESS RULES
# =====================================================================

def test_payment_on_draft_invoice_rejected(alice):
    """Invoices start as DRAFT. Payments are not allowed until SENT."""
    cust = alice.post('/api/v1/customers', json={
        'name': 'Acme', 'email': 'acme@example.com',
    }).get_json()['customer']
    prod = alice.post('/api/v1/products', json={
        'name': 'Consulting', 'unit_price': '100.00', 'tax_rate': '10.00',
    }).get_json()['product']
    inv = alice.post('/api/v1/invoices', json={
        'customer_id': cust['id'],
        'invoice_number': 'INV-DRAFT-1',
        'issue_date': '2026-09-14',
        'due_date': '2026-10-14',
        'line_items': [{'product_id': prod['id'], 'quantity': 1}],
    }).get_json()['invoice']

    r = alice.post(f'/api/v1/invoices/{inv["id"]}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    })
    assert r.status_code == 409
    assert any('DRAFT' in e for e in r.get_json()['errors'])


def test_payment_on_paid_invoice_rejected(alice):
    inv_id, _ = _setup_invoice(alice)   # 110.00
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '110.00', 'payment_method': 'CASH',
    })
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '10.00', 'payment_method': 'CASH',
    })
    assert r.status_code == 409
    assert any('already fully paid' in e for e in r.get_json()['errors'])


def test_payment_invoice_not_found(alice):
    r = alice.post('/api/v1/invoices/99999/payments', json={
        'amount': '10.00', 'payment_method': 'CASH',
    })
    assert r.status_code == 404


# =====================================================================
# VALIDATION
# =====================================================================

def test_payment_missing_amount(alice):
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'payment_method': 'CASH',
    })
    assert r.status_code == 400
    assert any('Amount is required' in e for e in r.get_json()['errors'])


def test_payment_zero_amount(alice):
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '0', 'payment_method': 'CASH',
    })
    assert r.status_code == 400
    assert any('greater than 0' in e for e in r.get_json()['errors'])


def test_payment_negative_amount(alice):
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '-5.00', 'payment_method': 'CASH',
    })
    assert r.status_code == 400


def test_payment_non_numeric_amount(alice):
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': 'abc', 'payment_method': 'CASH',
    })
    assert r.status_code == 400
    assert any('must be a number' in e for e in r.get_json()['errors'])


def test_payment_missing_method(alice):
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00',
    })
    assert r.status_code == 400
    assert any('Payment method is required' in e for e in r.get_json()['errors'])


def test_payment_invalid_method(alice):
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'BITCOIN',
    })
    assert r.status_code == 400
    assert any('Payment method must be one of' in e for e in r.get_json()['errors'])


def test_payment_method_case_insensitive(alice):
    """Clients may send 'cash' or 'Cash' — we normalise to CASH."""
    inv_id, _ = _setup_invoice(alice)
    r = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'cash',
    })
    assert r.status_code == 201
    assert r.get_json()['payment']['payment_method'] == 'CASH'


# =====================================================================
# IDOR
# =====================================================================

def test_bob_cannot_pay_alices_invoice(alice, bob):
    inv_id, _ = _setup_invoice(alice)
    r = bob.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    })
    assert r.status_code == 404


def test_bob_cannot_list_alices_payments(alice, bob):
    inv_id, _ = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    })
    r = bob.get(f'/api/v1/invoices/{inv_id}/payments')
    assert r.status_code == 404


def test_bob_cannot_read_alices_payment(alice, bob):
    inv_id, _ = _setup_invoice(alice)
    payment_id = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    }).get_json()['payment']['id']

    r = bob.get(f'/api/v1/payments/{payment_id}')
    assert r.status_code == 404


def test_bob_cannot_delete_alices_payment(alice, bob):
    inv_id, _ = _setup_invoice(alice)
    payment_id = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '50.00', 'payment_method': 'CASH',
    }).get_json()['payment']['id']

    r = bob.delete(f'/api/v1/payments/{payment_id}')
    assert r.status_code == 404


def test_bob_cannot_read_alices_credit_notes(alice, bob):
    inv_id, _ = _setup_invoice(alice)
    cn_id = alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00', 'payment_method': 'CASH',
    }).get_json()['credit_note']['id']

    r = bob.get(f'/api/v1/credit-notes/{cn_id}')
    assert r.status_code == 404


def test_bobs_credit_notes_list_excludes_alices(alice, bob):
    """Bob's credit-notes list should only show his own."""
    inv_id, _ = _setup_invoice(alice)
    alice.post(f'/api/v1/invoices/{inv_id}/payments', json={
        'amount': '130.00', 'payment_method': 'CASH',
    })

    r = bob.get('/api/v1/credit-notes')
    assert r.status_code == 200
    assert r.get_json()['total'] == 0