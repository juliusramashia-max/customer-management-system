"""
Credit note endpoints (read-only for Stage 6).

Credit notes are created internally by overpayments in payments.py.
This blueprint exposes them for display and reporting.

Later stages may add:
  - POST /credit-notes/<id>/apply   (apply to an invoice)
  - POST /credit-notes/<id>/refund
"""
from flask import Blueprint, jsonify

from models import CreditNote
from decorators import login_required, current_user

credit_notes_bp = Blueprint(
    'credit_notes', __name__, url_prefix='/api/v1/credit-notes'
)


@credit_notes_bp.route('', methods=['GET'])
@login_required
def list_credit_notes():
    """List all credit notes owned by the current user."""
    notes = (
        CreditNote.query
        .filter_by(user_id=current_user().id)
        .order_by(CreditNote.created_at.desc())
        .all()
    )
    return jsonify({
        'items': [cn.to_dict() for cn in notes],
        'total': len(notes),
    }), 200


@credit_notes_bp.route('/<int:credit_note_id>', methods=['GET'])
@login_required
def get_credit_note(credit_note_id):
    note = CreditNote.query.filter_by(
        id=credit_note_id,
        user_id=current_user().id,
    ).first()
    if note is None:
        return jsonify({'errors': ['Credit note not found']}), 404
    return jsonify({'credit_note': note.to_dict()}), 200