"""
Payment endpoints.

Payments are nested resources of invoices. Ownership flows through the
parent invoice: a payment is accessible iff its invoice belongs to the
current user.

Overpayment policy:
  Overpayments are ACCEPTED. When a payment exceeds the invoice's
  outstanding balance, the payment is recorded in full and a CreditNote
  is issued to the customer for the excess. The invoice becomes PAID.
  The customer's credit balance (reported as "Due to you") increases.

  Example: outstanding = 100.00, payment = 130.00
    → invoice marked PAID
    → CreditNote of 30.00 issued to the customer
    → Customer.credit_balance() == 30.00
"""
from decimal import Decimal
from flask import Blueprint, request, jsonify

from database import db
from models import Invoice, Payment, CreditNote
from validators import validate_payment_data
from decorators import login_required, current_user
from money import money

payments_bp = Blueprint('payments', __name__, url_prefix='/api/v1')


def _get_owned_invoice(invoice_id):
    """Fetch an invoice owned by the current user, or None."""
    return Invoice.query.filter_by(
        id=invoice_id,
        user_id=current_user().id,
    ).first()


def _get_owned_payment(payment_id):
    """
    Fetch a payment whose parent invoice is owned by the current user.

    Ownership propagates through the invoice — we never trust a raw
    payment_id alone.
    """
    return (
        Payment.query
        .join(Invoice)
        .filter(
            Payment.id == payment_id,
            Invoice.user_id == current_user().id,
        )
        .first()
    )


# =====================================================================
# LIST  (payments for an invoice)
# =====================================================================
@payments_bp.route('/invoices/<int:invoice_id>/payments', methods=['GET'])
@login_required
def list_payments(invoice_id):
    invoice = _get_owned_invoice(invoice_id)
    if invoice is None:
        return jsonify({'errors': ['Invoice not found']}), 404

    customer = invoice.customer
    return jsonify({
        'items': [p.to_dict() for p in invoice.payments],
        'total': len(invoice.payments),
        'outstanding_balance': str(invoice.outstanding_balance()),
        'total_paid': str(invoice.total_paid()),
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'credit_balance': str(customer.credit_balance()),
            'credit_balance_display': customer.credit_balance_display(),
        },
    }), 200


# =====================================================================
# CREATE  (record a payment; may generate a credit note on overpayment)
# =====================================================================
@payments_bp.route('/invoices/<int:invoice_id>/payments', methods=['POST'])
@login_required
def create_payment(invoice_id):
    """
    Record a payment against an invoice.

    Overpayment policy:
      - amount <= outstanding: record payment, update status
      - amount >  outstanding: record payment in full, mark invoice
        PAID, and issue a CreditNote for the excess
    """
    invoice = _get_owned_invoice(invoice_id)
    if invoice is None:
        return jsonify({'errors': ['Invoice not found']}), 404

    if invoice.status == 'DRAFT':
        return jsonify({
            'errors': ['Cannot record payments against a DRAFT invoice']
        }), 409

    if invoice.status == 'PAID':
        return jsonify({
            'errors': [
                'Invoice is already fully paid. '
                'Issue a standalone credit note for additional credit.'
            ]
        }), 409

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    cleaned, errors = validate_payment_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    amount = cleaned['amount']
    outstanding = invoice.outstanding_balance()

    # 1. Record the payment in full
    payment = Payment(
        invoice=invoice,
        amount=amount,
        payment_method=cleaned['payment_method'],
        reference=cleaned.get('reference'),
        notes=cleaned.get('notes'),
    )
    if 'payment_date' in cleaned:
        payment.payment_date = cleaned['payment_date']

    db.session.add(payment)
    db.session.flush()

    # 2. Overpayment? Issue a credit note for the excess
    overpayment = amount - outstanding
    credit_note = None

    if overpayment > Decimal('0.00'):
        overpayment = money(overpayment)
        credit_note = CreditNote(
            user_id=current_user().id,
            customer_id=invoice.customer_id,
            invoice=invoice,
            amount=overpayment,
            reason=(
                f"Overpayment on {invoice.invoice_number}: "
                f"paid {amount}, outstanding was {outstanding}"
            ),
        )
        db.session.add(credit_note)
        db.session.flush()

    # 3. Recompute invoice status (PAID if fully covered)
    invoice.recalculate_status()
    db.session.commit()

    # 4. Build response
    customer = invoice.customer
    response = {
        'payment': payment.to_dict(),
        'invoice': invoice.to_dict(),
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'credit_balance': str(customer.credit_balance()),
            'credit_balance_display': customer.credit_balance_display(),
        },
    }
    if credit_note is not None:
        response['credit_note'] = credit_note.to_dict()

    return jsonify(response), 201


# =====================================================================
# READ ONE
# =====================================================================
@payments_bp.route('/payments/<int:payment_id>', methods=['GET'])
@login_required
def get_payment(payment_id):
    payment = _get_owned_payment(payment_id)
    if payment is None:
        return jsonify({'errors': ['Payment not found']}), 404
    return jsonify({'payment': payment.to_dict()}), 200


# =====================================================================
# DELETE  (void a payment)
# =====================================================================
@payments_bp.route('/payments/<int:payment_id>', methods=['DELETE'])
@login_required
def delete_payment(payment_id):
    """
    Void a payment. Refuses if the invoice has an associated credit
    note from an overpayment — the credit must be reversed first.
    """
    payment = _get_owned_payment(payment_id)
    if payment is None:
        return jsonify({'errors': ['Payment not found']}), 404

    invoice = payment.invoice

    if invoice.status == 'DRAFT':
        return jsonify({
            'errors': ['Cannot modify payments on a DRAFT invoice']
        }), 409

    # Block deletion if a credit note exists for this invoice
    linked_credits = CreditNote.query.filter_by(invoice=invoice).count()
    if linked_credits > 0:
        return jsonify({
            'errors': [
                'This invoice has an associated credit note from an '
                'overpayment. Reverse the credit note first.'
            ]
        }), 409

    db.session.delete(payment)
    db.session.flush()

    invoice.recalculate_status()
    db.session.commit()

    return '', 204