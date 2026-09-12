from app import app
from database import db
from models import User, Customer, Product, Invoice, LineItem, Payment
from datetime import datetime, timedelta
from decimal import Decimal

def setup_database():
    """Set up the database with tables and sample data."""
    
    print("=" * 60)
    print("DATABASE SETUP AND SAMPLE DATA")
    print("=" * 60)
    
    with app.app_context():
        # 1. Create tables
        print("\n📋 Creating tables...")
        db.create_all()
        print("✅ Tables created")
        
        # 2. Check if we already have data
        if User.query.count() > 0:
            print("ℹ️  Database already has data. Skipping sample data.")
            return
        
        # 3. Create sample user
        print("\n👤 Creating sample user...")
        user = User(
            email='demo@example.com',
            password_hash='hashed_password_here'  # In real app, use bcrypt
        )
        db.session.add(user)
        db.session.flush()
        print(f"   ✅ User created: {user.email} (ID: {user.id})")
        
        # 4. Create sample customers
        print("\n🏢 Creating sample customers...")
        customers = [
            Customer(
                user_id=user.id,
                name='John Doe',
                email='john@example.com',
                phone='+1 555-0101',
                company='ACME Corp',
                address='123 Main St, New York, NY 10001'
            ),
            Customer(
                user_id=user.id,
                name='Jane Smith',
                email='jane@example.com',
                phone='+1 555-0102',
                company='Smith Industries',
                address='456 Oak Ave, Los Angeles, CA 90001'
            )
        ]
        for customer in customers:
            db.session.add(customer)
        db.session.flush()
        print(f"   ✅ Created {len(customers)} customers")
        
        # 5. Create sample products
        print("\n📦 Creating sample products...")
        products = [
            Product(
                user_id=user.id,
                name='Web Development',
                description='Custom website development services',
                unit_price=Decimal('1500.00'),
                tax_rate=Decimal('15.00')
            ),
            Product(
                user_id=user.id,
                name='Consulting',
                description='Business consulting services',
                unit_price=Decimal('250.00'),
                tax_rate=Decimal('10.00')
            ),
            Product(
                user_id=user.id,
                name='Hosting',
                description='Web hosting services (annual)',
                unit_price=Decimal('120.00'),
                tax_rate=Decimal('5.00')
            )
        ]
        for product in products:
            db.session.add(product)
        db.session.flush()
        print(f"   ✅ Created {len(products)} products")
        
        # 6. Create sample invoices
        print("\n📄 Creating sample invoices...")
        customer1 = Customer.query.filter_by(email='john@example.com').first()
        customer2 = Customer.query.filter_by(email='jane@example.com').first()
        product1 = Product.query.filter_by(name='Web Development').first()
        product2 = Product.query.filter_by(name='Consulting').first()
        
        # Invoice 1 - For John Doe (Paid)
        invoice1 = Invoice(
            user_id=user.id,
            customer_id=customer1.id,
            invoice_number='INV-2026-0001',
            issue_date=datetime.utcnow() - timedelta(days=15),
            due_date=datetime.utcnow() + timedelta(days=15),
            status='PAID',
            notes='Web development project'
        )
        db.session.add(invoice1)
        db.session.flush()
        
        # Line items for invoice 1
        quantity1 = 1
        subtotal1 = quantity1 * product1.unit_price
        tax_amount1 = subtotal1 * (product1.tax_rate / 100)
        
        line_item1 = LineItem(
            invoice_id=invoice1.id,
            product_id=product1.id,
            quantity=quantity1,
            unit_price=product1.unit_price,
            subtotal=subtotal1,
            tax_rate=product1.tax_rate
        )
        db.session.add(line_item1)
        
        invoice1.subtotal = subtotal1
        invoice1.tax_amount = tax_amount1
        invoice1.total = subtotal1 + tax_amount1
        
        # Invoice 2 - For Jane Smith (Unpaid)
        invoice2 = Invoice(
            user_id=user.id,
            customer_id=customer2.id,
            invoice_number='INV-2026-0002',
            issue_date=datetime.utcnow() - timedelta(days=5),
            due_date=datetime.utcnow() + timedelta(days=25),
            status='SENT',
            notes='Consulting services'
        )
        db.session.add(invoice2)
        db.session.flush()
        
        # Line items for invoice 2
        quantity2 = 5
        subtotal2 = quantity2 * product2.unit_price
        tax_amount2 = subtotal2 * (product2.tax_rate / 100)
        
        line_item2 = LineItem(
            invoice_id=invoice2.id,
            product_id=product2.id,
            quantity=quantity2,
            unit_price=product2.unit_price,
            subtotal=subtotal2,
            tax_rate=product2.tax_rate
        )
        db.session.add(line_item2)
        
        invoice2.subtotal = subtotal2
        invoice2.tax_amount = tax_amount2
        invoice2.total = subtotal2 + tax_amount2
        
        db.session.commit()
        print(f"   ✅ Created {2} invoices with line items")
        
        print("\n" + "=" * 60)
        print("✅ DATABASE SETUP COMPLETE!")
        print("=" * 60)
        
        # Show summary
        print(f"\n📊 Summary:")
        print(f"   👤 Users: {User.query.count()}")
        print(f"   🏢 Customers: {Customer.query.count()}")
        print(f"   📦 Products: {Product.query.count()}")
        print(f"   📄 Invoices: {Invoice.query.count()}")
        print(f"   📋 Line Items: {LineItem.query.count()}")

if __name__ == '__main__':
    setup_database()
    