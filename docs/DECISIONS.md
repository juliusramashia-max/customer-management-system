ADR-002: Overpayments Create a Credit Note
Context. When a payment exceeds the invoice's outstanding balance,
there are three common options:

Reject. Return a 400. Simple; user must retry with the right
amount.

Accept; record the excess as customer credit. The invoice is
paid; the customer's account shows a positive balance ("Due to
you: X.XX").

Accept; issue a separate credit note document. Same as (2), but
the credit is a first-class entity, auditable and reversible.

Decision. Option 3. A CreditNote row is created for the excess,
linked to both the customer and the invoice it came from.

Consequences.

The customer's credit_balance is the sum of their credit notes.

Payments that triggered a credit note cannot be deleted until the
credit note is reversed (guarded in payments.delete_payment).

A future feature can apply credits to outstanding invoices or refund
them. The data model supports this; only the UI/endpoints are missing.

The invoice's own outstanding balance clamps to zero — the excess
lives on the customer, not the invoice.

ADR-003: Session-Based Auth, Not JWT
Context. Two common patterns for authenticating an HTTP API:

Server-signed cookies (sessions). Flask's session uses a
signed cookie with a server-side secret. Logout is
session.clear().

JSON Web Tokens (JWT). Stateless; useful when the API serves
multiple front-ends or mobile clients.

Decision. Sessions.

Consequences.

Simpler: no token storage, no refresh flow, no revocation list.

Suitable for a single web app served from the same origin.

Works with HttpOnly and SameSite=Lax cookies, which mitigates
XSS-based theft and most CSRF.

If a mobile or third-party client is added later, we would migrate to
JWT and keep sessions as a compatibility layer.

ADR-004: Client-Supplied Invoice Numbers
Context. Invoice numbers could be:

Server-generated — the server picks the next in sequence.

Client-supplied — the user types the number.

Decision. Client-supplied, unique per user.

Consequences.

Users can match their existing accounting system's numbering.

Uniqueness is enforced by a (user_id, invoice_number) DB constraint.

A future GET /invoices/next-number can offer a suggested number
without removing the client's ability to override.

ADR-005: Line Items Snapshot Price and Tax Rate
Context. When an invoice references a product, the invoice could:

Reference the current product price — always reads
product.unit_price when displaying.

Snapshot the price at creation time — stores unit_price on the
line item.

The project brief says "historical invoice data must remain stable."

Decision. Snapshot. LineItem.unit_price and LineItem.tax_rate
are set from the product at invoice creation and never updated by
product changes.

Consequences.

If the product's price changes tomorrow, yesterday's invoices still
show the original price.

Editing a DRAFT invoice re-snapshots from the current product state
(because the line items are replaced wholesale).

Known gap: product name and description are still looked up live
from Product, so renaming a product does change how old invoices
read. See "Known Limitations" in the README. Fixing this would
require also snapshotting product_name — a small schema change
deferred to a future stage.

ADR-006: Identical Error Messages for Login Failures
Context. When login fails, we could return:

Different messages for "unknown email" vs "wrong password" — helpful
to legitimate users, but leaks which emails are registered (user
enumeration).

The same message for both — security-first, no leak.

Decision. Same message: "Invalid email or password", same status
code (401).

We also run a dummy password check when the email is not found, so
that the two paths take approximately the same amount of time. Without
this, timing differences (a real check takes ~100ms; a missing user
takes ~0ms) would allow enumeration via latency.

Consequences.

Attackers cannot enumerate valid emails via login.

Legitimate users get a slightly less helpful error message. This is
a deliberate trade-off.

ADR-007: IDOR Protection by Filtering on user_id
Context. Multi-tenant APIs are vulnerable to Insecure Direct
Object Reference (IDOR) — a user accesses another user's data by
guessing IDs. This is the #1 API vulnerability.

Decision. Every route that reads or mutates a business entity
filters on current_user().id:

python
Customer.query.filter_by(id=customer_id, user_id=current_user().id).first()
Not found and not-owned return the same 404. This is centralised in
one helper per resource (_get_owned_*), so it is not repeated across
routes.

Consequences.

A logged-in user cannot see, edit, or delete another user's data,
even if they know the ID.

Error responses don't leak whether the ID exists.

Test suites have IDOR tests per resource that fail loudly if this
pattern is ever broken.

ADR-008: Compute Aggregates on Demand, Don't Cache
Context. The dashboard and reports aggregate over the user's whole
dataset — invoices, payments, credit notes. These could be:

Computed on demand at each request.

Cached in a summary table updated on every write.

Decision. Compute on demand.

Consequences.

Always correct — no risk of drift between stored totals and reality.

Simpler — no cache invalidation logic.

Acceptable for the target scale (a small business with hundreds to
thousands of rows). If performance becomes an issue, caching can be
added without changing the API.

Business Rules (Consolidated)
Derived from the brief and the decisions above.

User emails are unique globally.

Customer emails are unique per user.

Invoice numbers are unique per user.

Invoices always reference an existing customer owned by the
user.

Invoices must have at least one line item.

Line item quantities must be greater than zero.

Unit prices, tax rates, discounts, and payment amounts cannot be
negative.

Tax rates are percentages (0–100).

Money is stored and computed in Decimal, rounded to 2 dp with
ROUND_HALF_UP.

Line item prices and tax rates are snapshotted at creation for
historical stability.

Invoice status is stored (DRAFT, SENT, PARTIALLY_PAID, PAID) and
recalculated after every payment mutation.

Overdue status is derived (not stored) from
due_date < now AND outstanding > 0 AND status NOT IN (DRAFT, PAID, ARCHIVED).

Overpayments are accepted and issued as credit notes to the
customer.

A payment that triggered a credit note cannot be deleted until
the credit note is reversed.

IDOR protection applies to every resource: reads and writes are
filtered by the owning user_id.

JSON money values are strings, never numbers.
