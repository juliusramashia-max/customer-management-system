import pytest
from app import app
from database import db
from models import User, Customer, Product, Invoice, LineItem, Payment
from datetime import datetime, timedelta
from decimal import Decimal


@pytest.fixture
def test_app():
    """Set up the app and an in-memory database for each test."""
    # Use an in-memory database (starts empty every time)
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.create_all()      # ← THIS IS THE CRITICAL LINE
        yield app
        db.session.remove()
        db.drop_all()


def test_create_user(test_app):
    """Test creating a user."""
    with test_app.app_context():
        user = User(
            email='test@example.com',
            password_hash='hashed_password_here'
        )
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert user.email == 'test@example.com'
        assert user.created_at is not None


def test_create_invoice(test_app):
    """Test creating an invoice with line items."""
    with test_app.app_context():
        # Create prerequisite data
        user = User(email='test@example.com', password_hash='hash')
        db.session.add(user)
        db.session.commit()

        customer = Customer(
            user_id=user.id,
            name='John Doe',
            email='john@example.com'
        )
        db.session.add(customer)
        db.session.commit()

        product = Product(
            user_id=user.id,
            name='Web Development',
            unit_price=Decimal('1000.00'),
            tax_rate=Decimal('15.00')
        )
        db.session.add(product)
        db.session.commit()

        # Now create an invoice
        invoice = Invoice(
            user_id=user.id,
            customer_id=customer.id,
            invoice_number='INV-2026-0001',
            due_date=datetime.utcnow() + timedelta(days=30),
            status='DRAFT'
        )
        db.session.add(invoice)
        db.session.flush()

        quantity = 2
        subtotal = quantity * product.unit_price
        tax_amount = subtotal * (product.tax_rate / 100)

        line_item = LineItem(
            invoice_id=invoice.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.unit_price,
            subtotal=subtotal,
            tax_rate=product.tax_rate
        )
        db.session.add(line_item)

        invoice.subtotal = subtotal
        invoice.tax_amount = tax_amount
        invoice.total = subtotal + tax_amount

        db.session.commit()

        assert invoice.id is not None
        assert invoice.invoice_number == 'INV-2026-0001'
        assert invoice.total == Decimal('2300.00')
        assert len(invoice.line_items) == 1