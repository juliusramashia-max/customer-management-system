"""
Tests for dashboard and reporting endpoints.

The response shapes we assert against:

  GET /api/v1/dashboard
    {
      "counts": { "customers": n, "products": n, "invoices": n },
      "totals": { "invoiced": "x.xx", "paid": "x.xx",
                  "outstanding": "x.xx", "credits_issued": "x.xx" },
      "invoices_by_status": { "DRAFT": n, ... },
      "overdue": { "count": n, "total_outstanding": "x.xx" },
      "recent_invoices": [ {...}, ... ],
      "recent_payments": [ {...}, ... ]
    }

  GET /api/v1/reports/outstanding
    { "items": [...], "count": n, "total_outstanding": "x.xx" }

  GET /api/v1/reports/overdue
    { "items": [...], "count": n, "total_outstanding": "x.xx" }

  GET /api/v1/reports/customer-balances
    { "items": [...], "count": n }
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from app import app
from database import db


# =====================================================================
# FIXTURES
# =====================================================================

@pytest.fixture
def client():
    """Reset the schema and yield a base client."""
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


# =====================================================================
# HELPERS
# =====================================================================

def _customer(c, name='Acme', email='acme@example.com'):
    return c.post('/api/v1/customers', json={
        'name': name, 'email': email,
    }).get_json()['customer']['id']


def _product(c, unit_price='100.00', tax_rate='0'):
    return c.post('/api/v1/products', json={
        'name': 'Consulting', 'unit_price': unit_price, 'tax_rate': tax_rate,
    }).get_json()['product']['id']


def _invoice(c, customer_id, product_id, qty=1,
             invoice_number='INV-1',
             issue_date='2026-09-01',
             due_date='2026-09-30',
             send=True):
    inv = c.post('/api/v1/invoices', json={
        'customer_id': customer_id,
        'invoice_number': invoice_number,
        'issue_date': issue_date,
        'due_date': due_date,
        'line_items': [{'product_id': product_id, 'quantity': qty}],
    }).get_json()['invoice']
    if send:
        c.post(f'/api/v1/invoices/{inv["id"]}/send')
    return inv['id']


def _pay(c, invoice_id, amount, method='CASH'):
    c.post(f'/api/v1/invoices/{invoice_id}/payments', json={
        'amount': amount, 'payment_method': method,
    })


# =====================================================================
# AUTH
# =====================================================================

def test_dashboard_requires_login(client):
    assert client.get('/api/v1/dashboard').status_code == 401


def test_outstanding_report_requires_login(client):
    assert client.get('/api/v1/reports/outstanding').status_code == 401


def test_overdue_report_requires_login(client):
    assert client.get('/api/v1/reports/overdue').status_code == 401


def test_customer_balances_requires_login(client):
    assert client.get('/api/v1/reports/customer-balances').status_code == 401


# =====================================================================
# DASHBOARD — EMPTY
# =====================================================================

def test_dashboard_empty(alice):
    r = alice.get('/api/v1/dashboard')
    assert r.status_code == 200
    data = r.get_json()

    assert data['counts'] == {'customers': 0, 'products': 0, 'invoices': 0}
    assert data['totals']['invoiced'] == '0.00'
    assert data['totals']['paid'] == '0.00'
    assert data['totals']['outstanding'] == '0.00'
    assert data['totals']['credits_issued'] == '0.00'
    assert data['invoices_by_status'] == {}
    assert data['overdue'] == {'count': 0, 'total_outstanding': '0.00'}
    assert data['recent_invoices'] == []
    assert data['recent_payments'] == []


# =====================================================================
# DASHBOARD — COUNTS
# =====================================================================

def test_dashboard_counts(alice):
    c1 = _customer(alice, 'Acme', 'a@a.com')
    c2 = _customer(alice, 'Globex', 'g@g.com')
    p = _product(alice)

    _invoice(alice, c1, p, invoice_number='INV-1', send=True)
    _invoice(alice, c2, p, invoice_number='INV-2', send=True)
    _invoice(alice, c1, p, invoice_number='INV-3', send=False)   # DRAFT

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['counts']['customers'] == 2
    assert data['counts']['products'] == 1
    assert data['counts']['invoices'] == 3
    assert data['invoices_by_status'].get('DRAFT') == 1
    assert data['invoices_by_status'].get('SENT') == 2


# =====================================================================
# DASHBOARD — TOTALS
# =====================================================================

def test_dashboard_totals(alice):
    """
    Invoice 1: 100.00 → paid in full
    Invoice 2: 200.00 → partial 50.00
    Invoice 3: 300.00 → DRAFT (excluded from totals)

    Expected:
      invoiced    = 300.00  (100 + 200, drafts excluded)
      paid        = 150.00
      outstanding = 150.00
    """
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    i1 = _invoice(alice, c, p, qty=1, invoice_number='INV-1')      # 100
    i2 = _invoice(alice, c, p, qty=2, invoice_number='INV-2')      # 200
    _invoice(alice, c, p, qty=3, invoice_number='INV-3', send=False)  # 300 draft

    _pay(alice, i1, '100.00')
    _pay(alice, i2, '50.00')

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['totals']['invoiced'] == '300.00'
    assert data['totals']['paid'] == '150.00'
    assert data['totals']['outstanding'] == '150.00'


def test_dashboard_paid_full_invoice_contributes_zero_outstanding(alice):
    c = _customer(alice)
    p = _product(alice, unit_price='500.00', tax_rate='0')
    inv = _invoice(alice, c, p, qty=1)   # 500.00
    _pay(alice, inv, '500.00')

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['totals']['invoiced'] == '500.00'
    assert data['totals']['paid'] == '500.00'
    assert data['totals']['outstanding'] == '0.00'


# =====================================================================
# DASHBOARD — CREDITS ISSUED
# =====================================================================

def test_dashboard_credits_issued(alice):
    """An overpayment should appear in the credits_issued total."""
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')
    inv = _invoice(alice, c, p, qty=1)   # total 100.00

    # Pay 130.00 → 30.00 credit note
    _pay(alice, inv, '130.00')

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['totals']['credits_issued'] == '30.00'
    assert data['totals']['paid'] == '130.00'
    assert data['totals']['outstanding'] == '0.00'


# =====================================================================
# DASHBOARD — OVERDUE
# =====================================================================

def test_dashboard_overdue_count(alice):
    """One past-due unpaid invoice should be counted as overdue."""
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    # Past-due, unpaid
    _invoice(alice, c, p, invoice_number='INV-PASTDUE',
             issue_date='2020-01-01', due_date='2020-01-31')

    # Future due date, unpaid
    future = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
    _invoice(alice, c, p, invoice_number='INV-FUTURE',
             issue_date='2026-09-01', due_date=future)

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['overdue']['count'] == 1
    assert data['overdue']['total_outstanding'] == '100.00'


def test_dashboard_overdue_excludes_paid(alice):
    """A paid past-due invoice is not overdue — nothing is owed."""
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    inv = _invoice(alice, c, p,
                   issue_date='2020-01-01', due_date='2020-01-31')
    _pay(alice, inv, '100.00')

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['overdue']['count'] == 0
    assert data['overdue']['total_outstanding'] == '0.00'


def test_dashboard_overdue_excludes_draft(alice):
    """Draft invoices aren't overdue — they haven't been issued."""
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    _invoice(alice, c, p, send=False,
             issue_date='2020-01-01', due_date='2020-01-31')

    data = alice.get('/api/v1/dashboard').get_json()
    assert data['overdue']['count'] == 0


# =====================================================================
# DASHBOARD — RECENT ACTIVITY
# =====================================================================

def test_dashboard_recent_invoices(alice):
    c = _customer(alice)
    p = _product(alice, unit_price='10.00', tax_rate='0')
    for i in range(7):
        _invoice(alice, c, p, invoice_number=f'INV-{i}', send=False)

    data = alice.get('/api/v1/dashboard').get_json()
    assert len(data['recent_invoices']) == 5


def test_dashboard_recent_payments(alice):
    c = _customer(alice)
    p = _product(alice, unit_price='10.00', tax_rate='0')
    inv = _invoice(alice, c, p, qty=10, invoice_number='INV-1')  # 100.00
    for _ in range(6):
        _pay(alice, inv, '10.00')

    data = alice.get('/api/v1/dashboard').get_json()
    assert len(data['recent_payments']) == 5


# =====================================================================
# IDOR — DASHBOARD
# =====================================================================

def test_dashboard_isolation(alice, bob):
    """Bob's dashboard shouldn't see Alice's data."""
    ca = _customer(alice, 'AliceCo', 'alice-co@example.com')
    pa = _product(alice, unit_price='999.00', tax_rate='0')
    _invoice(alice, ca, pa, invoice_number='INV-ALICE')

    data = bob.get('/api/v1/dashboard').get_json()
    assert data['counts']['customers'] == 0
    assert data['counts']['products'] == 0
    assert data['counts']['invoices'] == 0
    assert data['totals']['invoiced'] == '0.00'


# =====================================================================
# REPORT: OUTSTANDING
# =====================================================================

def test_outstanding_report_empty(alice):
    data = alice.get('/api/v1/reports/outstanding').get_json()
    assert data['items'] == []
    assert data['count'] == 0
    assert data['total_outstanding'] == '0.00'


def test_outstanding_report_includes_partial_and_sent(alice):
    """
    Invoice A: sent, unpaid         → outstanding 100.00
    Invoice B: partial payment 40   → outstanding 60.00
    Invoice C: draft                → excluded
    Invoice D: paid                 → excluded (nothing owed)
    """
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    _invoice(alice, c, p, invoice_number='INV-A')                     # 100 unpaid
    b = _invoice(alice, c, p, invoice_number='INV-B')                 # 100 partial
    _pay(alice, b, '40.00')
    _invoice(alice, c, p, invoice_number='INV-C', send=False)         # draft
    d = _invoice(alice, c, p, invoice_number='INV-D')                 # paid
    _pay(alice, d, '100.00')

    data = alice.get('/api/v1/reports/outstanding').get_json()
    assert data['count'] == 2
    nums = sorted(item['invoice_number'] for item in data['items'])
    assert nums == ['INV-A', 'INV-B']
    assert data['total_outstanding'] == '160.00'   # 100 + 60


def test_outstanding_report_sorted_by_due_date(alice):
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    _invoice(alice, c, p, invoice_number='INV-LATE',
             issue_date='2026-09-01', due_date='2026-12-01')
    _invoice(alice, c, p, invoice_number='INV-SOON',
             issue_date='2026-09-01', due_date='2026-09-15')

    data = alice.get('/api/v1/reports/outstanding').get_json()
    assert [item['invoice_number'] for item in data['items']] == ['INV-SOON', 'INV-LATE']


def test_outstanding_report_isolation(alice, bob):
    ca = _customer(alice)
    pa = _product(alice, unit_price='100.00', tax_rate='0')
    _invoice(alice, ca, pa, invoice_number='INV-ALICE')

    data = bob.get('/api/v1/reports/outstanding').get_json()
    assert data['count'] == 0


# =====================================================================
# REPORT: OVERDUE
# =====================================================================

def test_overdue_report_empty(alice):
    data = alice.get('/api/v1/reports/overdue').get_json()
    assert data['items'] == []
    assert data['count'] == 0
    assert data['total_outstanding'] == '0.00'


def test_overdue_report_includes_only_past_due(alice):
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')

    _invoice(alice, c, p, invoice_number='INV-PASTDUE',
             issue_date='2020-01-01', due_date='2020-01-31')

    future = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
    _invoice(alice, c, p, invoice_number='INV-FUTURE',
             issue_date='2026-09-01', due_date=future)

    data = alice.get('/api/v1/reports/overdue').get_json()
    assert data['count'] == 1
    assert data['items'][0]['invoice_number'] == 'INV-PASTDUE'
    assert data['total_outstanding'] == '100.00'


def test_overdue_report_excludes_paid(alice):
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')
    inv = _invoice(alice, c, p, invoice_number='INV-PAID-OLD',
                   issue_date='2020-01-01', due_date='2020-01-31')
    _pay(alice, inv, '100.00')

    data = alice.get('/api/v1/reports/overdue').get_json()
    assert data['count'] == 0


def test_overdue_report_isolation(alice, bob):
    ca = _customer(alice)
    pa = _product(alice, unit_price='100.00', tax_rate='0')
    _invoice(alice, ca, pa, invoice_number='INV-ALICE-PAST',
             issue_date='2020-01-01', due_date='2020-01-31')

    data = bob.get('/api/v1/reports/overdue').get_json()
    assert data['count'] == 0


# =====================================================================
# REPORT: CUSTOMER BALANCES
# =====================================================================

def test_customer_balances_empty(alice):
    data = alice.get('/api/v1/reports/customer-balances').get_json()
    assert data['items'] == []
    assert data['count'] == 0


def test_customer_balances_per_customer(alice):
    """
    Customer A: 2 invoices (100 + 200), one paid in full, one unpaid
      → invoiced 300, paid 100, outstanding 200, credit 0
    Customer B: 1 invoice (50), fully paid
      → invoiced 50, paid 50, outstanding 0, credit 0
    """
    c_a = _customer(alice, 'Alpha', 'a@a.com')
    c_b = _customer(alice, 'Beta', 'b@b.com')
    p = _product(alice, unit_price='100.00', tax_rate='0')

    # Alpha
    inv_a1 = _invoice(alice, c_a, p, qty=1, invoice_number='INV-A1')   # 100
    _pay(alice, inv_a1, '100.00')
    _invoice(alice, c_a, p, qty=2, invoice_number='INV-A2')             # 200

    # Beta — use a separate product of 50.00 for cleanliness
    p50 = _product(alice, unit_price='50.00', tax_rate='0')
    inv_b1 = _invoice(alice, c_b, p50, qty=1, invoice_number='INV-B1')  # 50
    _pay(alice, inv_b1, '50.00')

    data = alice.get('/api/v1/reports/customer-balances').get_json()
    by_name = {item['customer_name']: item for item in data['items']}

    assert by_name['Alpha']['invoiced'] == '300.00'
    assert by_name['Alpha']['paid'] == '100.00'
    assert by_name['Alpha']['outstanding'] == '200.00'
    assert by_name['Alpha']['credit_balance'] == '0.00'

    assert by_name['Beta']['invoiced'] == '50.00'
    assert by_name['Beta']['paid'] == '50.00'
    assert by_name['Beta']['outstanding'] == '0.00'


def test_customer_balances_credit_balance(alice):
    """Overpayment appears as a credit balance on the customer row."""
    c = _customer(alice)
    p = _product(alice, unit_price='100.00', tax_rate='0')
    inv = _invoice(alice, c, p, qty=1)   # 100.00
    _pay(alice, inv, '150.00')            # 50.00 over

    data = alice.get('/api/v1/reports/customer-balances').get_json()
    row = data['items'][0]
    assert row['credit_balance'] == '50.00'
    assert row['credit_balance_display'] == 'Due to you: 50.00'


def test_customer_balances_isolation(alice, bob):
    ca = _customer(alice)
    _customer(bob, 'BobsOwn', 'bob-cust@example.com')

    data = alice.get('/api/v1/reports/customer-balances').get_json()
    # Alice sees only her customers
    names = [item['customer_name'] for item in data['items']]
    assert 'BobsOwn' not in names