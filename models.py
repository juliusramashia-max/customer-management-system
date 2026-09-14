from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from database import db


class User(db.Model):
    """User account model."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    customers = db.relationship('Customer', backref='user', lazy=True)
    products = db.relationship('Product', backref='user', lazy=True)
    invoices = db.relationship('Invoice', backref='user', lazy=True)

    def set_password(self, plaintext):
        """Hash and store the password. Never store plaintext."""
        self.password_hash = generate_password_hash(plaintext)

    def check_password(self, plaintext):
        """Return True if plaintext matches the stored hash."""
        return check_password_hash(self.password_hash, plaintext)

    def to_dict(self):
        """Safe serialisation — NEVER include password_hash."""
        return {
            'id': self.id,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Customer(db.Model):
    """Customer model."""
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    company = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'email', name='unique_user_email'),
    )

    # Relationships
    invoices = db.relationship('Invoice', backref='customer', lazy=True)

    def to_dict(self):
        """Serialise customer for JSON. user_id is intentionally omitted."""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'address': self.address,
            'company': self.company,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Product(db.Model):
    """Product/Service model."""
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Serialise product for JSON. Decimals become strings to preserve precision."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'unit_price': str(self.unit_price),
            'tax_rate': str(self.tax_rate),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Invoice(db.Model):
    """Invoice model."""
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    invoice_number = db.Column(db.String(50), nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='DRAFT')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'invoice_number', name='unique_invoice_number'),
    )

    # Relationships
    line_items = db.relationship(
        'LineItem', backref='invoice', lazy=True, cascade='all, delete-orphan'
    )
    payments = db.relationship(
        'Payment', backref='invoice', lazy=True, cascade='all, delete-orphan'
    )

    def to_dict(self):
        """Serialise invoice for JSON. Decimals become strings."""
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'invoice_number': self.invoice_number,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'subtotal': str(self.subtotal),
            'discount': str(self.discount),
            'tax_amount': str(self.tax_amount),
            'total': str(self.total),
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class LineItem(db.Model):
    """Invoice line item model."""
    __tablename__ = 'line_items'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False)

    def to_dict(self):
        """Serialise line item for JSON. Decimals become strings."""
        return {
            'id': self.id,
            'invoice_id': self.invoice_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'unit_price': str(self.unit_price),
            'subtotal': str(self.subtotal),
            'tax_rate': str(self.tax_rate),
        }


class Payment(db.Model):
    """Payment model."""
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)

    def to_dict(self):
        """Serialise payment for JSON. Decimal becomes a string."""
        return {
            'id': self.id,
            'invoice_id': self.invoice_id,
            'amount': str(self.amount),
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'payment_method': self.payment_method,
            'reference': self.reference,
            'notes': self.notes,
        }