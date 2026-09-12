import pytest
from app import app
from database import db
from models import User, Customer, Product, Invoice, LineItem, Payment
from datetime import datetime, timedelta
from decimal import Decimal

@pytest.fixture
def client():
    """Create test client with database setup."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

def test_user_model(client):
    """Test User model."""
    with app.app_context():
        user = User(email='test@example.com', password_hash='hash')
        db.session.add(user)
        db.session.commit()
        
        assert user.id is not None
        assert user.email == 'test@example.com'
        assert user.created_at is not None

def test_customer_model(client):
    """Test Customer model."""
    with app.app_context():
        user = User(email='test@example.com', password_hash='hash')
        db.session.add(user)
        db.session.commit()
        
        customer = Customer(
            user_id=user.id,
            name='John Doe',
            email='john@example.com',
            phone='+1234567890',
            company='ACME Corp'
        )
        db.session.add(customer)
        db.session.commit()
        
        assert customer.id is not None
        assert customer.name == 'John Doe'
        assert customer.user_id == user.id

def test_product_model(client):
    """Test Product model."""
    with app.app_context():
        user = User(email='test@example.com', password_hash='hash')
        db.session.add(user)
        db.session.commit()
        
        product = Product(
            user_id=user.id,
            name='Web Development',
            unit_price=Decimal('1000.00'),
            tax_rate=Decimal('15.00')
        )
        db.session.add(product)
        db.session.commit()
        
        assert product.id is not None
        assert product.unit_price == Decimal('1000.00')
        assert product.tax_rate == Decimal('15.00')

def test_invoice_with_line_items(client):
    """Test invoice creation with line items."""
    with app.app_context():
        # Create user, customer, product
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
        
        # Create invoice
        invoice = Invoice(
            user_id=user.id,
            customer_id=customer.id,
            invoice_number='INV-2026-0001',
            due_date=datetime.utcnow() + timedelta(days=30),
            status='DRAFT'
        )
        db.session.add(invoice)
        db.session.flush()
        
        # Create line item
        quantity = 2
        unit_price = product.unit_price
        subtotal = quantity * unit_price
        tax_amount = subtotal * (product.tax_rate / 100)
        
        line_item = LineItem(
            invoice_id=invoice.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=subtotal,
            tax_rate=product.tax_rate
        )
        db.session.add(line_item)
        
        # Update invoice totals
        invoice.subtotal = subtotal
        invoice.tax_amount = tax_amount
        invoice.total = subtotal + tax_amount
        
        db.session.commit()
        
        # Assertions
        assert invoice.id is not None
        assert invoice.invoice_number == 'INV-2026-0001'
        assert invoice.subtotal == Decimal('2000.00')
        assert invoice.tax_amount == Decimal('300.00')
        assert invoice.total == Decimal('2300.00')
        assert len(invoice.line_items) == 1
        assert invoice.line_items[0].quantity == 2

def test_payment_model(client):
    """Test payment model."""
    with app.app_context():
        # Create user, customer, product, invoice (similar to above)
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
        
        invoice = Invoice(
            user_id=user.id,
            customer_id=customer.id,
            invoice_number='INV-2026-0002',
            due_date=datetime.utcnow() + timedelta(days=30),
            total=Decimal('2300.00'),
            status='SENT'
        )
        db.session.add(invoice)
        db.session.commit()
        
        # Create payment
        payment = Payment(
            invoice_id=invoice.id,
            amount=Decimal('1000.00'),
            payment_method='Bank Transfer',
            reference='TRX-001'
        )
        db.session.add(payment)
        db.session.commit()
        
        assert payment.id is not None
        assert payment.amount == Decimal('1000.00')
        assert payment.payment_method == 'Bank Transfer'
        assert payment.invoice_id == invoice.id

        