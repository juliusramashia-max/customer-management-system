# Customer Management System

A web application for small businesses and independent consultants to
manage customers, products/services, invoices, payments, and outstanding
balances — with automatic calculations, status tracking, and PDF invoice
generation.

Built with Flask, SQLAlchemy, and SQLite. Fully tested with pytest.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [API Overview](#api-overview)
- [Architecture](#architecture)
- [Data Model](#data-model)
- [Testing](#testing)
- [Business Rules](#business-rules)
- [Project Structure](#project-structure)
- [Design Decisions](#design-decisions)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Overview

Small businesses often manage invoices in spreadsheets, which makes it
easy to lose track of who owes what, to send duplicate invoice numbers,
or to miscalculate totals. This application provides a single place to:

- Track customers and products/services
- Issue invoices with itemised line items
- Automatically compute subtotals, tax, discounts, and totals
- Record full or partial payments
- See at a glance which accounts are paid, partially paid, or overdue
- Generate printable PDF invoices

Every business entity is **scoped to the current user** — this is a
multi-tenant system, so Alice's customers are invisible to Bob.

---

## Features

**Authentication**
- Email/password registration and login
- Session-based authentication with HTTP-only cookies
- Password hashing via Werkzeug (never plaintext)

**Customer Management**
- Create, read, update, and delete customers
- Search by name, email, or company
- Pagination on list views

**Product & Service Catalogue**
- CRUD with Decimal-accurate pricing
- Per-product tax rate (0–100%)

**Invoicing**
- Create invoices with multiple line items in a single request
- Automatic subtotal, tax, discount, and total calculation
- Unique invoice numbers per user
- Status lifecycle: `DRAFT` → `SENT` → `PARTIALLY_PAID` → `PAID`
- Historical stability: line items snapshot price and tax rate at
  creation time

**Payments & Credit Notes**
- Record full and partial payments
- Track outstanding balances
- Overpayment creates a **credit note** for the customer ("Due to you")
- Delete a payment to reverse it (blocked if a credit note exists)

**Reporting**
- Dashboard: counts, invoiced/paid/outstanding/credit totals,
  invoices by status, overdue totals, recent activity
- Outstanding invoices report
- Overdue invoices report
- Per-customer balance report

**PDF Invoices**
- Download any invoice as a PDF
- Letterhead and metadata repeat on every page
- Line item table headers repeat across page breaks

**Quality**
- 175+ automated tests
- IDOR protection at every resource boundary
- Decimal money arithmetic throughout

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Framework | Flask 2.3 |
| ORM | Flask-SQLAlchemy 3.0 |
| Migrations | Flask-Migrate |
| Database | SQLite (dev); any SQLAlchemy-supported DB in production |
| Auth | Werkzeug password hashing + Flask sessions |
| PDF | fpdf2 (pure Python) |
| Testing | pytest |
| Config | python-dotenv |

---

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git
- (Windows) PowerShell; (macOS/Linux) bash or zsh

### Setup

```bash
# 1. Clone
git clone https://github.com/juliusramashia-max/customer-management-system.git
cd customer-management-system

# 2. Virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env with a secret key
# Windows PowerShell
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" > .env
# macOS/Linux
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env

# 5. Create the database and sample data
python setup_db.py

# 6. Run
python app.py
```

The app listens on `http://localhost:5000`. Try `GET /health` to confirm.

### Sample Data

`setup_db.py` creates:

- One demo user: `demo@example.com` (any password; the hash is pre-set)
- Two customers
- Three products
- Two invoices with line items

If you want a clean slate at any time:

```bash
python setup_db.py --reset
```

(Or delete `instance/cms.db` and re-run the script.)

---

## API Overview

All endpoints are under `/api/v1/`. Full reference in [`docs/API.md`](docs/API.md).

| Method | URL | Purpose |
|--------|-----|---------|
| `POST` | `/auth/register` | Create a new user |
| `POST` | `/auth/login` | Authenticate and start a session |
| `POST` | `/auth/logout` | End the session |
| `GET`  | `/auth/me` | Return the current user |
| `GET`/`POST` | `/customers` | List / create customers |
| `GET`/`PUT`/`DELETE` | `/customers/<id>` | Read / update / delete |
| `GET`/`POST` | `/products` | List / create products |
| `GET`/`PUT`/`DELETE` | `/products/<id>` | Read / update / delete |
| `GET`/`POST` | `/invoices` | List / create invoices (with line items) |
| `GET`/`PUT`/`DELETE` | `/invoices/<id>` | Read / update / delete |
| `POST` | `/invoices/<id>/send` | Move a DRAFT invoice to SENT |
| `GET`  | `/invoices/<id>/pdf` | Download the invoice PDF |
| `GET`/`POST` | `/invoices/<id>/payments` | List / create payments |
| `GET`/`DELETE` | `/payments/<id>` | Read / delete a payment |
| `GET`  | `/credit-notes` | List credit notes (from overpayments) |
| `GET`  | `/dashboard` | Business summary |
| `GET`  | `/reports/outstanding` | Unpaid and partially paid invoices |
| `GET`  | `/reports/overdue` | Past-due invoices |
| `GET`  | `/reports/customer-balances` | Per-customer summary |

### Example: Create an Invoice

```http
POST /api/v1/invoices
Content-Type: application/json

{
  "customer_id": 3,
  "invoice_number": "INV-2026-0001",
  "issue_date": "2026-09-14",
  "due_date": "2026-10-14",
  "line_items": [
    { "product_id": 1, "quantity": 2 },
    { "product_id": 4, "quantity": 1 }
  ]
}
```

Response:

```json
{
  "invoice": {
    "id": 7,
    "invoice_number": "INV-2026-0001",
    "subtotal": "620.00",
    "tax_amount": "81.00",
    "total": "701.00",
    "outstanding_balance": "701.00",
    "status": "DRAFT",
    "...": "..."
  }
}
```

**Money fields are strings.** This preserves exactness — JSON numbers
are floating point, which loses precision.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Flask Application                    │
├──────────────────────────────────────────────────────────┤
│  Blueprints (routes)                                     │
│    auth.py          /api/v1/auth/*                       │
│    customers.py     /api/v1/customers/*                  │
│    products.py      /api/v1/products/*                   │
│    invoices.py      /api/v1/invoices/*                   │
│    payments.py      /api/v1/invoices/*/payments          │
│    credit_notes.py  /api/v1/credit-notes/*               │
│    reports.py       /api/v1/dashboard, /reports/*        │
├──────────────────────────────────────────────────────────┤
│  Shared helpers                                          │
│    decorators.py    login_required, current_user         │
│    validators.py    payload validation                   │
│    money.py         Decimal + ROUND_HALF_UP              │
│    pdf.py           invoice PDF renderer                 │
├──────────────────────────────────────────────────────────┤
│  Data layer                                              │
│    models.py        User, Customer, Product,             │
│                     Invoice, LineItem, Payment,          │
│                     CreditNote                           │
│    database.py      SQLAlchemy instance                  │
│    config.py        configuration from .env              │
├──────────────────────────────────────────────────────────┤
│  Database: SQLite (dev), any RDBMS via SQLAlchemy (prod) │
└──────────────────────────────────────────────────────────┘
```

**Request flow** (example: creating an invoice):

```
1. Client POST /api/v1/invoices with JSON
2. Flask routes to invoices.create_invoice
3. @login_required validates the session and loads the User
4. validate_invoice_data checks the payload and returns clean data
5. _build_line_items snapshots prices/taxes from products
6. invoice.recalculate_totals() computes subtotal, tax, total
7. db.session.commit() — one transaction, all or nothing
8. JSON response with the created invoice
```

---

## Data Model

```
User ──┬── has many Customers
       ├── has many Products
       └── has many Invoices

Customer ──┬── has many Invoices
           └── has many CreditNotes

Invoice ──┬── belongs to Customer
          ├── belongs to User
          ├── has many LineItems
          ├── has many Payments
          └── has many CreditNotes

LineItem ── belongs to Invoice
         └── references Product (price/tax snapshotted at creation)

Payment ── belongs to Invoice

CreditNote ── belongs to Customer
           └── optionally belongs to an Invoice
```

**Key constraints**

- `users.email` unique globally
- `(customers.user_id, customers.email)` unique per user
- `(invoices.user_id, invoices.invoice_number)` unique per user
- Every business entity carries `user_id` for tenant isolation
- Foreign keys cascade on invoice delete (line items and payments)

---

## Testing

```bash
# Run everything
pytest -v

# One module
pytest test_invoices.py -v

# One test
pytest test_auth.py::test_login_success -v
```

The test suite covers:

| File | Focus |
|------|-------|
| `test_app.py` | Health endpoint |
| `test_auth.py` | Registration, login, sessions, protected routes |
| `test_database.py` | Model roundtrips |
| `test_models.py` | Model helpers (`to_dict`, decimal precision) |
| `test_customers.py` | Customer CRUD, IDOR, search, pagination |
| `test_products.py` | Product CRUD, decimal validation |
| `test_invoices.py` | Invoice CRUD, calculations, snapshots, PDF, IDOR |
| `test_payments.py` | Payments, overpayment → credit note, IDOR |
| `test_reports.py` | Dashboard, reports, aggregation, IDOR |

**Before running tests, stop the Flask server** — SQLite is single-writer
and tests reset the database schema.

---

## Business Rules

The full set of rules is documented in
[`docs/DECISIONS.md`](docs/DECISIONS.md#business-rules). The headline
rules:

1. **Unique invoice numbers per user.** A user may reuse a number used
   by a different user.
2. **Invoices always belong to a customer.** No orphan invoices.
3. **Invoices must have at least one line item.**
4. **Quantity must be greater than zero.**
5. **Prices and payment amounts cannot be negative.**
6. **Money is Decimal, never float.** Two-decimal rounding uses
   `ROUND_HALF_UP` (commercial rounding).
7. **Historical stability.** Line items snapshot `unit_price` and
   `tax_rate` from the product at invoice creation. Changing a product
   later does not alter past invoices.
8. **Overpayment policy.** Overpayments are accepted. The excess is
   issued to the customer as a **credit note**, reported as
   "Due to you: X.XX".
9. **Status is derived and stored.**
   - `DRAFT`: created but not issued. Editable. No payments.
   - `SENT`: issued. Payments allowed.
   - `PARTIALLY_PAID`: some payments recorded, balance remains.
   - `PAID`: balance is zero.
   - `OVERDUE`: derived at read time (past due + balance > 0); not
     stored.

---

## Project Structure

```
customer-management-system/
├── app.py                Application factory / entry point
├── config.py             Environment-driven configuration
├── database.py           SQLAlchemy initialisation
├── models.py             All database models
│
├── auth.py               Authentication blueprint
├── customers.py          Customer blueprint
├── products.py           Product blueprint
├── invoices.py           Invoice blueprint
├── payments.py           Payment blueprint
├── credit_notes.py       Credit note blueprint
├── reports.py            Dashboard + reports blueprint
│
├── decorators.py         login_required, current_user
├── validators.py         Payload validation
├── money.py              Decimal rounding helpers
├── pdf.py                Invoice PDF renderer
│
├── setup_db.py           Create tables + sample data
├── check_tables.py       Inspect database contents
│
├── test_*.py             Test modules (one per blueprint)
├── requirements.txt      Python dependencies
├── .env.example          Environment template
├── .gitignore            Ignored files
├── README.md             This file
├── LICENSE               MIT
│
├── docs/
│   ├── API.md            Full endpoint reference
│   └── DECISIONS.md      Architecture decision records
│
└── instance/
    └── cms.db            SQLite database (gitignored)
```

---

## Design Decisions

The reasoning behind key choices is documented in
[`docs/DECISIONS.md`](docs/DECISIONS.md). Highlights:

- **[ADR-001](docs/DECISIONS.md#adr-001):** Decimal, not float, for
  money.
- **[ADR-002](docs/DECISIONS.md#adr-002):** Overpayment creates a
  credit note (rather than rejecting overpayment outright).
- **[ADR-003](docs/DECISIONS.md#adr-003):** Session-based auth over JWT.
- **[ADR-004](docs/DECISIONS.md#adr-004):** Invoice numbers supplied by
  the client, unique per user.
- **[ADR-005](docs/DECISIONS.md#adr-005):** Line items snapshot product
  price and tax rate.

---

## Known Limitations

- **No business profile.** Invoices render the user's email as the
  letterhead. A full `Business` model (name, address, logo, currency)
  is future work.
- **No product name on line items.** If a product is renamed, past
  invoices show the new name. Same for description.
- **No invoice emailing.** PDFs are downloaded, not sent.
- **No customer portal.** Customers cannot log in to see their own
  invoices.
- **No multi-currency.** All amounts are currency-neutral.
- **SQLite in development.** Deploy with Postgres or MySQL — change
  `DATABASE_URL` and re-run `db.create_all()`.
- **Werkzeug debug server.** Not for production. Use gunicorn/uWSGI
  behind nginx.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

Built as a learning project to demonstrate a substantial, well-tested
web application beyond a single-table CRUD. Thank you to everyone who
has reviewed early versions and provided feedback.
