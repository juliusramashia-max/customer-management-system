"""
Invoice CRUD endpoints.

Invoices are created with line items in a single POST. Line items are
nested resources: adding/updating/removing them via the invoice update
recalculates the parent's subtotal, tax, and total.

All routes are scoped to the current user. IDOR is prevented at three
levels: the invoice, the customer, and every referenced product.
"""
from decimal import Decimal
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from database import db
from models import Invoice, LineItem
from validators import validate_invoice_data
from decorators import login_required, current_user
from money import to_decimal, money

invoices_bp = Blueprint('invoices', __name__, url_prefix='/api/v1/invoices')


def _get_owned_invoice(invoice_id):
    """Fetch an invoice owned by the current user, or None."""
    return Invoice.query.filter_by(
        id=invoice_id,
        user_id=current_user().id,
    ).first()


def _build_line_items(invoice, validated_items):
    """
    Build LineItem instances (not yet committed) with price and tax
    snapshot from the product at this moment in time.

    Note: setting invoice= on the LineItem automatically appends it to
    invoice.line_items via the relationship's backref. Do NOT also call
    invoice.line_items.append(...) — that would double the item.
    """
    for entry in validated_items:
        product = entry['product']
        LineItem(
            invoice=invoice,
            product_id=product.id,
            quantity=entry['quantity'],
            unit_price=product.unit_price,   # snapshot
            tax_rate=product.tax_rate,       # snapshot
            subtotal=Decimal('0.00'),        # filled by recalculate
        )


def _serialize_invoice(invoice):
    """Return a dict with the invoice plus its nested collections."""
    payload = invoice.to_dict()
    payload['line_items'] = [item.to_dict() for item in invoice.line_items]
    payload['payments'] = [p.to_dict() for p in invoice.payments]
    payload['credit_notes'] = [cn.to_dict() for cn in invoice.credit_notes]
    return payload


# =====================================================================
# LIST
# =====================================================================
@invoices_bp.route('', methods=['GET'])
@login_required
def list_invoices():
    """
    List the current user's invoices.

    Query params:
      page        (int, default 1)
      per_page    (int, default 20, max 100)
      q           (str) — substring search on invoice_number / notes
      status      (str) — filter by status (DRAFT, SENT, PAID, ...)
      customer_id (int) — filter to a specific customer
    """
    try:
        page = int(request.args.get('page', 1))
    except (TypeError, ValueError):
        return jsonify({'errors': ['page must be an integer']}), 400
    if page < 1:
        return jsonify({'errors': ['page must be >= 1']}), 400

    try:
        per_page = int(request.args.get('per_page', 20))
    except (TypeError, ValueError):
        return jsonify({'errors': ['per_page must be an integer']}), 400
    if per_page < 1 or per_page > 100:
        return jsonify({'errors': ['per_page must be between 1 and 100']}), 400

    q = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or '').strip().upper()
    customer_id_raw = request.args.get('customer_id')

    query = Invoice.query.filter_by(user_id=current_user().id)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Invoice.invoice_number.ilike(like),
                Invoice.notes.ilike(like),
            )
        )

    if status:
        query = query.filter(Invoice.status == status)

    if customer_id_raw:
        try:
            customer_id = int(customer_id_raw)
        except (ValueError, TypeError):
            return jsonify({'errors': ['customer_id must be an integer']}), 400
        query = query.filter(Invoice.customer_id == customer_id)

    pagination = query.order_by(Invoice.issue_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [inv.to_dict() for inv in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }), 200


# =====================================================================
# CREATE
# =====================================================================
@invoices_bp.route('', methods=['POST'])
@login_required
def create_invoice():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    user = current_user()
    cleaned, errors = validate_invoice_data(data, user.id)
    if errors:
        return jsonify({'errors': errors}), 400

    invoice = Invoice(
        user_id=user.id,
        customer_id=cleaned['customer'].id,
        invoice_number=cleaned['invoice_number'],
        issue_date=cleaned['issue_date'],
        due_date=cleaned['due_date'],
        discount=cleaned.get('discount', Decimal('0.00')),
        notes=cleaned.get('notes'),
        status='DRAFT',
        subtotal=Decimal('0.00'),
        tax_amount=Decimal('0.00'),
        total=Decimal('0.00'),
    )

    _build_line_items(invoice, cleaned['line_items'])
    invoice.recalculate_totals()

    db.session.add(invoice)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'errors': ['An invoice with this number already exists']
        }), 409

    return jsonify({'invoice': invoice.to_dict()}), 201


# =====================================================================
# READ ONE
# =====================================================================
@invoices_bp.route('/<int:invoice_id>', methods=['GET'])
@login_required
def get_invoice(invoice_id):
    invoice = _get_owned_invoice(invoice_id)
    if invoice is None:
        return jsonify({'errors': ['Invoice not found']}), 404
    return jsonify({'invoice': _serialize_invoice(invoice)}), 200


# =====================================================================
# UPDATE  (metadata + line items; DRAFT only)
# =====================================================================
@invoices_bp.route('/<int:invoice_id>', methods=['PUT'])
@login_required
def update_invoice(invoice_id):
    invoice = _get_owned_invoice(invoice_id)
    if invoice is None:
        return jsonify({'errors': ['Invoice not found']}), 404

    if invoice.status != 'DRAFT':
        return jsonify({
            'errors': ['Only DRAFT invoices can be edited']
        }), 409

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    user = current_user()
    cleaned, errors = validate_invoice_data(data, user.id)
    if errors:
        return jsonify({'errors': errors}), 400

    invoice.customer_id = cleaned['customer'].id
    invoice.invoice_number = cleaned['invoice_number']
    invoice.issue_date = cleaned['issue_date']
    invoice.due_date = cleaned['due_date']
    invoice.discount = cleaned.get('discount', Decimal('0.00'))
    invoice.notes = cleaned.get('notes')

    # Replace line items wholesale
    invoice.line_items.clear()
    _build_line_items(invoice, cleaned['line_items'])
    invoice.recalculate_totals()

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'errors': ['An invoice with this number already exists']
        }), 409

    return jsonify({'invoice': _serialize_invoice(invoice)}), 200


# =====================================================================
# DELETE  (DRAFT only)
# =====================================================================
@invoices_bp.route('/<int:invoice_id>', methods=['DELETE'])
@login_required
def delete_invoice(invoice_id):
    invoice = _get_owned_invoice(invoice_id)
    if invoice is None:
        return jsonify({'errors': ['Invoice not found']}), 404

    if invoice.status != 'DRAFT':
        return jsonify({
            'errors': ['Only DRAFT invoices can be deleted']
        }), 409

    db.session.delete(invoice)
    db.session.commit()
    return '', 204


# =====================================================================
# SEND  (DRAFT → SENT)
# =====================================================================
@invoices_bp.route('/<int:invoice_id>/send', methods=['POST'])
@login_required
def send_invoice(invoice_id):
    """
    Transition a DRAFT invoice to SENT so payments can be recorded.
    """
    invoice = _get_owned_invoice(invoice_id)
    if invoice is None:
        return jsonify({'errors': ['Invoice not found']}), 404
    if invoice.status != 'DRAFT':
        return jsonify({'errors': ['Only DRAFT invoices can be sent']}), 409

    invoice.status = 'SENT'
    db.session.commit()
    return jsonify({'invoice': invoice.to_dict()}), 200