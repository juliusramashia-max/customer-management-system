"""
Product/Service CRUD endpoints.

Same structure as customers.py: every route is scoped to the current
user, pagination and search are supported, and IDOR is prevented by
filtering on user_id.
"""
from flask import Blueprint, request, jsonify

from database import db
from models import Product
from validators import validate_product_data
from decorators import login_required, current_user

products_bp = Blueprint('products', __name__, url_prefix='/api/v1/products')


def _get_owned_product(product_id):
    """
    Fetch a product that belongs to the current user.

    Returns None if the product doesn't exist OR belongs to someone
    else — the two cases are indistinguishable to callers, which is
    the intended behaviour for IDOR protection.
    """
    return Product.query.filter_by(
        id=product_id,
        user_id=current_user().id,
    ).first()


# =====================================================================
# LIST
# =====================================================================
@products_bp.route('', methods=['GET'])
@login_required
def list_products():
    """
    List the current user's products.

    Query params:
      page      (int, default 1)
      per_page  (int, default 20, max 100)
      q         (str, optional) — substring search on name / description
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

    query = Product.query.filter_by(user_id=current_user().id)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Product.name.ilike(like),
                Product.description.ilike(like),
            )
        )

    pagination = query.order_by(Product.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'items': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }), 200


# =====================================================================
# CREATE
# =====================================================================
@products_bp.route('', methods=['POST'])
@login_required
def create_product():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    cleaned, errors = validate_product_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    product = Product(
        user_id=current_user().id,
        name=cleaned['name'],
        description=cleaned.get('description'),
        unit_price=cleaned['unit_price'],       # Decimal
        tax_rate=cleaned['tax_rate'],           # Decimal
    )
    db.session.add(product)
    db.session.commit()

    return jsonify({'product': product.to_dict()}), 201


# =====================================================================
# READ ONE
# =====================================================================
@products_bp.route('/<int:product_id>', methods=['GET'])
@login_required
def get_product(product_id):
    product = _get_owned_product(product_id)
    if product is None:
        return jsonify({'errors': ['Product not found']}), 404
    return jsonify({'product': product.to_dict()}), 200


# =====================================================================
# UPDATE
# =====================================================================
@products_bp.route('/<int:product_id>', methods=['PUT'])
@login_required
def update_product(product_id):
    product = _get_owned_product(product_id)
    if product is None:
        return jsonify({'errors': ['Product not found']}), 404

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'errors': ['Request must be JSON']}), 400

    cleaned, errors = validate_product_data(data)
    if errors:
        return jsonify({'errors': errors}), 400

    product.name = cleaned['name']
    product.description = cleaned.get('description')
    product.unit_price = cleaned['unit_price']
    product.tax_rate = cleaned['tax_rate']

    db.session.commit()
    return jsonify({'product': product.to_dict()}), 200


# =====================================================================
# DELETE
# =====================================================================
@products_bp.route('/<int:product_id>', methods=['DELETE'])
@login_required
def delete_product(product_id):
    product = _get_owned_product(product_id)
    if product is None:
        return jsonify({'errors': ['Product not found']}), 404

    db.session.delete(product)
    db.session.commit()
    return '', 204