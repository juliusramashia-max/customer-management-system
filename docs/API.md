# API Reference

Every endpoint, its request shape, its response shape, and its error
codes. All endpoints are under `/api/v1/`.

**Authentication:** unless noted, every endpoint requires a logged-in
session. Unauthenticated requests receive `401 Unauthorized`.

**Money:** all monetary values in JSON are **strings** (e.g. `"250.00"`),
never numbers. This preserves precision — see
[DECISIONS.md](DECISIONS.md#adr-001).

**Errors:** errors always look like:

```json
{ "errors": ["human-readable message", "..."] }

Authentication
POST /auth/register
Create a new user.

Request body:

json
{ "email": "alice@example.com", "password": "secret123" }
Responses:

201 Created — { "message": "...", "user": {...} }

400 Bad Request — validation failure

409 Conflict — email already registered

POST /auth/login
Authenticate and start a session.

Request body:

json
{ "email": "alice@example.com", "password": "secret123" }
Responses:

200 OK — session cookie set; { "message": "...", "user": {...} }

400 — missing field

401 — invalid credentials (same message for wrong password and
unknown email — see DECISIONS.md)

POST /auth/logout
End the session. Requires an active session. Returns 200 OK with
{ "message": "Logged out" }. Returns 401 if unauthenticated.

GET /auth/me
Return the current user. Useful as a session probe.

Responses:

200 OK — { "user": {...} }

401 — no session

Customers
GET /customers
List the current user's customers.

Query parameters:

page (int, default 1)

per_page (int, default 20, max 100)

q (string) — case-insensitive search on name, email, company

Response:

json
{
  "items": [ { "id": 1, "name": "...", "email": "...", "...": "..." } ],
  "total": 42,
  "page": 1,
  "per_page": 20,
  "pages": 3
}
POST /customers
Create a customer.

Request body:

json
{
  "name": "Acme Corp",
  "email": "billing@acme.com",
  "phone": "+1 555-0101",
  "company": "Acme Corporation",
  "address": "123 Main St"
}
Responses:

201 Created — { "customer": {...} }

400 — validation error

409 — email already used for this user

GET /customers/<id>
Return one customer. 404 if not found or not owned.

PUT /customers/<id>
Update a customer. Same body as POST. Returns 200 with the updated
customer, 400 on validation failure, 404 if not found, 409 if the
email collides.

DELETE /customers/<id>
Delete a customer. Returns 204 No Content, 404 if not found.

Products
Same shape as customers, without the unique-email constraint.

Fields
name — required, max 100 chars

description — optional

unit_price — required, decimal string, >= 0

tax_rate — required, decimal string, 0 <= x <= 100

Endpoints
GET /products — list (page, per_page, q)

POST /products

GET /products/<id>

PUT /products/<id>

DELETE /products/<id>

Invoices
GET /invoices
List invoices.

Query parameters:

page, per_page

q — search on invoice number and notes

status — filter by status (DRAFT, SENT, PARTIALLY_PAID, PAID)

customer_id — filter to a specific customer

POST /invoices
Create an invoice with line items in one transaction.

Request body:

json
{
  "customer_id": 3,
  "invoice_number": "INV-2026-0001",
  "issue_date": "2026-09-14",
  "due_date": "2026-10-14",
  "discount": "0.00",
  "notes": "September services",
  "line_items": [
    { "product_id": 1, "quantity": 2 },
    { "product_id": 4, "quantity": 1 }
  ]
}
Rules enforced:

due_date must be on or after issue_date

At least one line item

Every line item references a product owned by the user

Quantity > 0

invoice_number unique per user

Response 201:

json
{
  "invoice": {
    "id": 7,
    "invoice_number": "INV-2026-0001",
    "subtotal": "620.00",
    "tax_amount": "81.00",
    "total": "701.00",
    "total_paid": "0.00",
    "outstanding_balance": "701.00",
    "is_overdue": false,
    "status": "DRAFT",
    "...": "..."
  }
}
GET /invoices/<id>
Returns the invoice plus line_items, payments, and credit_notes
arrays.

PUT /invoices/<id>
Update a DRAFT invoice. Same body as create; line items are replaced
wholesale. Non-draft invoices return 409 Conflict.

DELETE /invoices/<id>
Delete a DRAFT invoice. Non-draft return 409.

POST /invoices/<id>/send
Transition DRAFT → SENT. Required before payments can be recorded.
Returns 200 with the updated invoice, 409 if not DRAFT.

GET /invoices/<id>/pdf
Download the invoice as a PDF.

Response headers:

text
Content-Type: application/pdf
Content-Disposition: attachment; filename="INV-2026-0001.pdf"
Response body: raw PDF bytes.

Payments
GET /invoices/<id>/payments
List payments for an invoice, plus balance summary and the customer's
credit balance.

Response:

json
{
  "items": [ { "id": 1, "amount": "200.00", "...": "..." } ],
  "total": 2,
  "outstanding_balance": "200.00",
  "total_paid": "300.00",
  "customer": {
    "id": 3,
    "name": "Acme Corp",
    "credit_balance": "0.00",
    "credit_balance_display": "Due to you: 0.00"
  }
}
POST /invoices/<id>/payments
Record a payment.

Request body:

json
{
  "amount": "200.00",
  "payment_method": "BANK_TRANSFER",
  "payment_date": "2026-09-20",
  "reference": "TRX-001",
  "notes": "Partial payment"
}
Payment methods: CASH, BANK_TRANSFER, CARD, CHEQUE, OTHER
(case-insensitive; normalised to uppercase).

Responses:

201 — payment recorded. Includes payment, invoice, customer.
If the payment exceeded the outstanding balance, the response also
includes a credit_note object for the excess.

400 — validation error

404 — invoice not found or not owned

409 — invoice is DRAFT, or already PAID

GET /payments/<id>
Return one payment. 404 if not found or not owned.

DELETE /payments/<id>
Reverse a payment. 204 on success. 409 if the invoice has a credit
note from an overpayment — reverse the credit first.

Credit Notes
Credit notes are created automatically when a payment exceeds the
invoice's outstanding balance.

GET /credit-notes
List all credit notes for the current user.

GET /credit-notes/<id>
Read one. 404 if not found or not owned.

Dashboard & Reports
GET /dashboard
One-page business summary.

Response:

json
{
  "counts": { "customers": 10, "products": 5, "invoices": 42 },
  "totals": {
    "invoiced": "12500.00",
    "paid": "9000.00",
    "outstanding": "3500.00",
    "credits_issued": "150.00"
  },
  "invoices_by_status": { "DRAFT": 3, "SENT": 5, "PAID": 30, "PARTIALLY_PAID": 4 },
  "overdue": { "count": 2, "total_outstanding": "800.00" },
  "recent_invoices": [ "...up to 5..." ],
  "recent_payments": [ "...up to 5..." ]
}
GET /reports/outstanding
All non-draft invoices with an outstanding balance > 0, sorted by
due date ascending.

Response:

json
{
  "items": [
    {
      "invoice_id": 12,
      "invoice_number": "INV-2026-0042",
      "customer_id": 3,
      "customer_name": "Acme Corp",
      "due_date": "2026-09-30",
      "total": "500.00",
      "total_paid": "100.00",
      "outstanding_balance": "400.00",
      "is_overdue": true,
      "status": "PARTIALLY_PAID"
    }
  ],
  "count": 1,
  "total_outstanding": "400.00"
}
GET /reports/overdue
Same shape, restricted to past-due invoices with a balance > 0.

GET /reports/customer-balances
Per-customer summary.

Response:

json
{
  "items": [
    {
      "customer_id": 3,
      "customer_name": "Acme Corp",
      "email": "billing@acme.com",
      "invoiced": "3000.00",
      "paid": "2500.00",
      "outstanding": "500.00",
      "credit_balance": "0.00",
      "credit_balance_display": "Due to you: 0.00"
    }
  ],
  "count": 1
}
text

---

### Step 3: `docs/DECISIONS.md`

```markdown
# Design Decisions

Every non-obvious choice is recorded here, along with the context and
consequences. When you find yourself wondering "why is it like this?",
this file should answer.

Format is a lightweight ADR (Architecture Decision Record).

---

## ADR-001: Use Decimal, not Float, for Money

**Context.** Python's `float` is IEEE 754 binary floating point. It
cannot exactly represent most decimal fractions:

```python
>>> 0.1 + 0.2
0.30000000000000004
For scientific work, the error is irrelevant. For money, it is fatal —
invoices would drift by fractions of a cent, totals would not add up,
and reconciliations would fail.

Decision. Every money column is declared as
db.Numeric(10, 2), which maps to Python's decimal.Decimal.
Arithmetic happens entirely in Decimal. JSON serialisation converts
them to strings (e.g. "250.00") so clients get exact values.

Rounding uses ROUND_HALF_UP (commercial rounding) via money.py,
not Python's default ROUND_HALF_EVEN (banker's rounding).

Consequences.

No floating-point errors in totals or balances.

Decimal values are more verbose to write (must wrap literals in
Decimal('...')).

Non-Python API clients must parse strings, not JSON numbers.

Cross-language behaviour is well-defined: strings travel without loss.
