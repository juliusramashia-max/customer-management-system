from app import app
from database import db
from models import User, Customer, Product, Invoice, LineItem, Payment
from datetime import datetime

def test_create_user():
    """Test creating a user."""
    with app.app_context():
        # Create user
        user = User(
            email='test@example.com',
            password_hash='hashed_password_here'
        )
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ User created with ID: {user.id}")
        
        # Create customer
        customer = Customer(
            user_id=user.id,
            name='John Doe',
            email='john@example.com',
            phone='+1234567890',
            company='ACME Corp'
        )
        db.session.add(customer)
        db.session.commit()
        
        print(f"✅ Customer created with ID: {customer.id}")
        
        # Create product
        product = Product(
            user_id=user.id,
            name='Web Development',
            description='Custom website development',
            unit_price=1000,
            tax_rate=15
        )
        db.session.add(product)
        db.session.commit()
        
        print(f"✅ Product created with ID: {product.id}")
        
        return user, customer, product

def test_create_invoice():
    """Test creating an invoice with line items."""
    with app.app_context():
        # Get existing data
        user = User.query.first()
        customer = Customer.query.first()
        product = Product.query.first()
        
        if not all([user, customer, product]):
            print("❌ Need existing user, customer, and product")
            return
        
        # Create invoice
        invoice = Invoice(
            user_id=user.id,
            customer_id=customer.id,
            invoice_number='INV-2026-0001',
            issue_date=datetime.utcnow(),
            due_date=datetime.utcnow() + timedelta(days=30),
            subtotal=0,
            discount=0,
            tax_amount=0,
            total=0,
            status='DRAFT'
        )
        db.session.add(invoice)
        db.session.flush()  # Get ID without committing
        
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
        
        print(f"✅ Invoice created: {invoice.invoice_number}")
        print(f"   Subtotal: {invoice.subtotal}")
        print(f"   Tax: {invoice.tax_amount}")
        print(f"   Total: {invoice.total}")
        
        return invoice

if __name__ == '__main__':
    print("=" * 50)
    print("TESTING DATABASE MODELS")
    print("=" * 50)
    
    test_create_user()
    print()
    test_create_invoice()
    print()
    print("✅ All tests completed!")