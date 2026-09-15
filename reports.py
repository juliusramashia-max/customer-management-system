"""
Dashboard and reporting endpoints.

All endpoints are GET-only and scoped to the current user. They
aggregate across customers, invoices, payments, and credit notes.

We compute aggregates on demand via SQL (func.sum, func.count,
group_by) rather than caching. For a small business CMS this is
fast and always correct.
"""
from datetime import datetime
from decimal import Decimal
from flask import Blueprint, jsonify

from database import db
from models import Customer, Product, Invoice, Payment, CreditNote
from decorators import login_required, current_user
from money import money

reports_bp = Blueprint('reports', __name__, url_prefix='/api/v1')


def _sum_or_zero(query):
    """Run a scalar SUM query, returning Decimal('0.00') when result is None."""
    value = query.scalar()
    if value is None:
        return Decimal('0.00')
    return money(value)


# =====================================================================
# DASHBOARD
# =====================================================================
@reports_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """
    Return a one-page summary of the user's business.

    Fields:
      - counts: customers, products, invoices
      - totals: invoiced, paid, outstanding, credits_issued
      - invoices_by_status: { DRAFT: n, SENT: n, PARTIALLY_PAID: n, PAID: n }
      - overdue: { count, total_outstanding }
      - recent_invoices: last 5 by issue_date
      - recent_payments: last 5 by payment_date
    """
    user_id = current_user().id

    # --- Counts ---------------------------------------------------
    customer_count = Customer.query.filter_by(user_id=user_id).count()
    product_count = Product.query.filter_by(user_id=user_id).count()
    invoice_count = Invoice.query.filter_by(user_id=user_id).count()

    # --- Invoiced total (all non-draft? or all?) ------------------
    # We report two numbers: invoiced_total (all non-draft) and
    # invoiced_total_all (including drafts) so the user can see both.
    invoiced_non_draft = _sum_or_zero(
        db.session.query(db.func.sum(Invoice.total))
        .filter(Invoice.user_id == user_id)
        .filter(~Invoice.status.in_(['DRAFT']))
    )

    paid_total = _sum_or_zero(
        db.session.query(db.func.sum(Payment.amount))
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .filter(Invoice.user_id == user_id)
    )

    credits_issued = _sum_or_zero(
        db.session.query(db.func.sum(CreditNote.amount))
        .filter(CreditNote.user_id == user_id)
    )

    # --- Outstanding across invoices ----------------------------
    # Sum outstanding_balance() for non-draft, non-archived invoices.
    # outstanding_balance() is a Python method, so we can't sum it in SQL
    # directly. Iterate over non-draft invoices — acceptable because
    # the set is bounded and typically small.
    outstanding = Decimal('0.00')
    overdue_count = 0
    overdue_total = Decimal('0.00')

    non_draft_invoices = Invoice.query.filter(
        Invoice.user_id == user_id,
        ~Invoice.status.in_(['DRAFT', 'ARCHIVED']),
    ).all()

    for inv in non_draft_invoices:
        bal = inv.outstanding_balance()
        outstanding += bal
        if inv.is_overdue():
            overdue_count += 1
            overdue_total += bal

    outstanding = money(outstanding)
    overdue_total = money(overdue_total)

    # --- Invoices by status -------------------------------------
    status_rows = (
        db.session.query(Invoice.status, db.func.count(Invoice.id))
        .filter(Invoice.user_id == user_id)
        .group_by(Invoice.status)
        .all()
    )
    invoices_by_status = {status: count for status, count in status_rows}

    # --- Recent invoices ----------------------------------------
    recent_invoices = (
        Invoice.query
        .filter_by(user_id=user_id)
        .order_by(Invoice.created_at.desc())
        .limit(5)
        .all()
    )

    # --- Recent payments ----------------------------------------
    recent_payments = (
        Payment.query
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .filter(Invoice.user_id == user_id)
        .order_by(Payment.payment_date.desc())
        .limit(5)
        .all()
    )

    return jsonify({
        'counts': {
            'customers': customer_count,
            'products': product_count,
            'invoices': invoice_count,
        },
        'totals': {
            'invoiced': str(invoiced_non_draft),
            'paid': str(paid_total),
            'outstanding': str(outstanding),
            'credits_issued': str(credits_issued),
        },
        'invoices_by_status': invoices_by_status,
        'overdue': {
            'count': overdue_count,
            'total_outstanding': str(overdue_total),
        },
        'recent_invoices': [inv.to_dict() for inv in recent_invoices],
        'recent_payments': [p.to_dict() for p in recent_payments],
    }), 200


# =====================================================================
# REPORT: OUTSTANDING INVOICES
# =====================================================================
@reports_bp.route('/reports/outstanding', methods=['GET'])
@login_required
def report_outstanding():
    """
    List non-draft invoices with an outstanding balance > 0.

    Sorted by due_date ascending (most urgent first).
    """
    user_id = current_user().id

    invoices = (
        Invoice.query
        .filter(
            Invoice.user_id == user_id,
            ~Invoice.status.in_(['DRAFT', 'ARCHIVED']),
        )
        .order_by(Invoice.due_date.asc())
        .all()
    )

    items = []
    total = Decimal('0.00')
    for inv in invoices:
        bal = inv.outstanding_balance()
        if bal > Decimal('0.00'):
            items.append({
                'invoice_id': inv.id,
                'invoice_number': inv.invoice_number,
                'customer_id': inv.customer_id,
                'customer_name': inv.customer.name if inv.customer else None,
                'due_date': inv.due_date.isoformat() if inv.due_date else None,
                'total': str(inv.total),
                'total_paid': str(inv.total_paid()),
                'outstanding_balance': str(bal),
                'is_overdue': inv.is_overdue(),
                'status': inv.status,
            })
            total += bal

    return jsonify({
        'items': items,
        'count': len(items),
        'total_outstanding': str(money(total)),
    }), 200


# =====================================================================
# REPORT: OVERDUE INVOICES
# =====================================================================
@reports_bp.route('/reports/overdue', methods=['GET'])
@login_required
def report_overdue():
    """
    List invoices past their due date with an outstanding balance > 0.
    """
    user_id = current_user().id

    invoices = (
        Invoice.query
        .filter(
            Invoice.user_id == user_id,
            ~Invoice.status.in_(['DRAFT', 'ARCHIVED', 'PAID']),
        )
        .order_by(Invoice.due_date.asc())
        .all()
    )

    items = []
    total = Decimal('0.00')
    for inv in invoices:
        if inv.is_overdue():
            bal = inv.outstanding_balance()
            items.append({
                'invoice_id': inv.id,
                'invoice_number': inv.invoice_number,
                'customer_id': inv.customer_id,
                'customer_name': inv.customer.name if inv.customer else None,
                'due_date': inv.due_date.isoformat() if inv.due_date else None,
                'total': str(inv.total),
                'total_paid': str(inv.total_paid()),
                'outstanding_balance': str(bal),
                'status': inv.status,
            })
            total += bal

    return jsonify({
        'items': items,
        'count': len(items),
        'total_outstanding': str(money(total)),
    }), 200


# =====================================================================
# REPORT: CUSTOMER BALANCES
# =====================================================================
@reports_bp.route('/reports/customer-balances', methods=['GET'])
@login_required
def report_customer_balances():
    """
    Per-customer summary: invoiced, paid, outstanding, credit balance.
    """
    user_id = current_user().id

    customers = Customer.query.filter_by(user_id=user_id).order_by(Customer.name).all()

    items = []
    for cust in customers:
        # Sum invoice totals (non-draft) for this customer
        invoiced = _sum_or_zero(
            db.session.query(db.func.sum(Invoice.total))
            .filter(
                Invoice.customer_id == cust.id,
                ~Invoice.status.in_(['DRAFT', 'ARCHIVED']),
            )
        )

        # Sum payments for invoices belonging to this customer
        paid = _sum_or_zero(
            db.session.query(db.func.sum(Payment.amount))
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .filter(Invoice.customer_id == cust.id)
        )

        # Outstanding across this customer's non-draft invoices
        outstanding = Decimal('0.00')
        for inv in cust.invoices:
            if inv.status not in ('DRAFT', 'ARCHIVED'):
                outstanding += inv.outstanding_balance()
        outstanding = money(outstanding)

        credit = cust.credit_balance()

        items.append({
            'customer_id': cust.id,
            'customer_name': cust.name,
            'email': cust.email,
            'invoiced': str(invoiced),
            'paid': str(paid),
            'outstanding': str(outstanding),
            'credit_balance': str(credit),
            'credit_balance_display': cust.credit_balance_display(),
        })

    return jsonify({
        'items': items,
        'count': len(items),
    }), 200