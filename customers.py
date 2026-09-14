"""
Customer CRUD endpoints.

Every route here is protected by @login_required and scoped to the
current user. This is the pattern we'll repeat for products, invoices,
and payments.
"""
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from database import db
from models import Customer
from validators import validate_customer_data
from decorators import login_required, current_user

customers_bp = Blueprint('customers', __name__, url_prefix='/api/v1/customers')


def _get_owned_customer(customer_id):
    """
    Fetch a customer that belongs to the current user.

    Returns None if the customer doesn't exist OR belongs to someone else.
    This is the IDOR protection: callers never see other users' data.
    """
    return Customer.query.filter_by(
        id=customer_id,
        user_id=current_user().id,
    ).first()


# =====================================================================
# LIST  (with pagination + search)
# =====================================================================
@customers_bp.route('', methods=['GET'])
@login_required
def list_customers():
    """
    List the current user's customers.

    Query params:
      page      (int, default 1)
      per_page  (int, default 20, max 100)
      q         (str, optional) — substring search on name/email/company
    """
    # --- Parse and validate query params ---
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

    # --- Build the query, always scoped to the current user ---
    query = Customer.query.filter_by(user_id=current_user().id)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Customer.name.ilike(like),
                Customer.email.ilike(like),
                Customer.company.ilike(like),
            )
        )

    # --- Paginate ---
    pagination = query.order_by(Customer.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [c.to_dict() for c in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }), 200


# =====================================================================
# CREATE
# =====================================================================
@customers_bp.route('', methods=['POST'])
@login_required
def create_customer():
    user = current_user() 
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    cleaned, errors = validate_customer_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    customer = Customer(
        user_id=current_user().id,
        name=cleaned['name'],
        email=cleaned['email'],
        phone=cleaned.get('phone'),
        company=cleaned.get('company'),
        address=cleaned.get('address'),
    )
    db.session.add(customer)
    try:
        db.session.commit()
    except IntegrityError:
        # The (user_id, email) unique constraint was violated
        db.session.rollback()
        return jsonify({'errors': ['A customer with this email already exists']}), 409

    return jsonify({'customer': customer.to_dict()}), 201


# =====================================================================
# READ ONE
# =====================================================================
@customers_bp.route('/<int:customer_id>', methods=['GET'])
@login_required
def get_customer(customer_id):
    user = current_user() 
    customer = _get_owned_customer(customer_id)
    if customer is None:
        # 404 for both "doesn't exist" and "belongs to someone else"
        return jsonify({'errors': ['Customer not found']}), 404
    return jsonify({'customer': customer.to_dict()}), 200


# =====================================================================
# UPDATE  (full replace)
# =====================================================================
@customers_bp.route('/<int:customer_id>', methods=['PUT'])
@login_required
def update_customer(customer_id):
    user = current_user() 
    customer = _get_owned_customer(customer_id)
    if customer is None:
        return jsonify({'errors': ['Customer not found']}), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    cleaned, errors = validate_customer_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    customer.name = cleaned['name']
    customer.email = cleaned['email']
    customer.phone = cleaned.get('phone')
    customer.company = cleaned.get('company')
    customer.address = cleaned.get('address')

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'errors': ['A customer with this email already exists']}), 409

    return jsonify({'customer': customer.to_dict()}), 200


# =====================================================================
# DELETE
# =====================================================================
@customers_bp.route('/<int:customer_id>', methods=['DELETE'])
@login_required
def delete_customer(customer_id):
    user = current_user() 
    customer = _get_owned_customer(customer_id)
    if customer is None:
        return jsonify({'errors': ['Customer not found']}), 404

    db.session.delete(customer)
    db.session.commit()
    return '', 204