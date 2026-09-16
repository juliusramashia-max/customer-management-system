"""
PDF rendering for invoices.

Uses fpdf2 (pure Python) — no system dependencies.
All money values come from Decimal columns and are rendered as strings.

Layout notes:
  The header (letterhead, bill-to block, invoice metadata) is drawn via
  FPDF._header(), which fpdf2 calls automatically on every new page.
  That way, when a long invoice breaks across pages, the top of each
  page repeats the same information.

  The line-item table header is redrawn at the top of each page by
  tracking pdf.page inside the item loop.
"""
from datetime import datetime
from io import BytesIO

from fpdf import FPDF


# Page layout constants (A4, millimetres)
PAGE_WIDTH = 210
MARGIN_LEFT = 15
MARGIN_RIGHT = 15
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

# Line-item table column widths
COL_QTY = 20
COL_PRICE = 35
COL_AMOUNT = 35
COL_DESC = CONTENT_WIDTH - COL_QTY - COL_PRICE - COL_AMOUNT   # 90mm


def _money_str(value):
    """Format a Decimal as 'x.xx'. Never touches float."""
    return str(value)


class InvoicePDF(FPDF):
    """
    A PDF subclass that draws the invoice header on every page.

    We stash the invoice and user on the instance so _header() can
    read them without extra arguments.
    """

    def __init__(self, invoice, user):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.invoice = invoice
        self.user = user
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(MARGIN_LEFT, 15, MARGIN_RIGHT)

    # ---------------------------------------------------------------
    # Runs automatically on every new page
    # ---------------------------------------------------------------
    def header(self):
        inv = self.invoice

        # Letterhead
        self.set_font('Helvetica', 'B', 20)
        self.set_text_color(0, 0, 0)
        self.cell(0, 10, 'INVOICE', ln=1)

        self.set_font('Helvetica', '', 9)
        self.set_text_color(80, 80, 80)
        self.cell(0, 4, f'From: {self.user.email}', ln=1)
        self.set_text_color(0, 0, 0)
        self.ln(3)

        # Two-column metadata block
        customer = inv.customer
        issue = inv.issue_date.strftime('%Y-%m-%d') if inv.issue_date else '-'
        due = inv.due_date.strftime('%Y-%m-%d') if inv.due_date else '-'

        # Bill To (left) and invoice metadata (right)
        left_width = 100
        right_width = CONTENT_WIDTH - left_width

        # Save the y-position for both columns
        y_start = self.get_y()

        # --- Left column: Bill To ---
        self.set_font('Helvetica', 'B', 10)
        self.cell(left_width, 5, 'Bill To', ln=2)
        self.set_font('Helvetica', '', 9)
        self.cell(left_width, 4.5, customer.name, ln=2)
        if customer.company:
            self.cell(left_width, 4.5, customer.company, ln=2)
        if customer.address:
            self.cell(left_width, 4.5, customer.address, ln=2)
        self.cell(left_width, 4.5, customer.email, ln=2)
        if customer.phone:
            self.cell(left_width, 4.5, customer.phone, ln=2)

        # --- Right column: invoice metadata ---
        self.set_xy(MARGIN_LEFT + left_width, y_start)
        self.set_font('Helvetica', 'B', 9)
        self.cell(35, 5, 'Invoice #:', border=0)
        self.set_font('Helvetica', '', 9)
        self.cell(right_width - 35, 5, inv.invoice_number, border=0, ln=2)

        self.set_x(MARGIN_LEFT + left_width)
        self.set_font('Helvetica', 'B', 9)
        self.cell(35, 5, 'Issue Date:', border=0)
        self.set_font('Helvetica', '', 9)
        self.cell(right_width - 35, 5, issue, border=0, ln=2)

        self.set_x(MARGIN_LEFT + left_width)
        self.set_font('Helvetica', 'B', 9)
        self.cell(35, 5, 'Due Date:', border=0)
        self.set_font('Helvetica', '', 9)
        self.cell(right_width - 35, 5, due, border=0, ln=2)

        self.set_x(MARGIN_LEFT + left_width)
        self.set_font('Helvetica', 'B', 9)
        self.cell(35, 5, 'Status:', border=0)
        self.set_font('Helvetica', '', 9)
        self.cell(right_width - 35, 5, inv.status, border=0, ln=2)

        # Move below the taller column
        left_bottom = self.get_y()   # after the left column
        self.set_y(left_bottom + 4)

        # Thin divider
        self.set_draw_color(200, 200, 200)
        self.line(MARGIN_LEFT, self.get_y(), PAGE_WIDTH - MARGIN_RIGHT, self.get_y())
        self.set_draw_color(0, 0, 0)
        self.ln(4)

    # ---------------------------------------------------------------
    # Footer on every page
    # ---------------------------------------------------------------
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(120, 120, 120)
        self.cell(
            0, 10,
            f'Page {self.page_no()}',
            align='C',
        )
        self.set_text_color(0, 0, 0)


# =====================================================================
# Top-level renderer
# =====================================================================
def render_invoice_pdf(invoice, user) -> bytes:
    """
    Build a PDF for the given invoice and return the bytes.
    """
    pdf = InvoicePDF(invoice, user)
    pdf.add_page()      # triggers _header()

    # -----------------------------------------------------------------
    # Line items table
    # -----------------------------------------------------------------
    def draw_table_header():
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(COL_DESC, 7, 'Description', border=1, fill=True)
        pdf.cell(COL_QTY, 7, 'Qty', border=1, fill=True, align='R')
        pdf.cell(COL_PRICE, 7, 'Unit Price', border=1, fill=True, align='R')
        pdf.cell(COL_AMOUNT, 7, 'Amount', border=1, fill=True, align='R', ln=1)
        pdf.set_font('Helvetica', '', 9)

    draw_table_header()

    current_page = pdf.page
    for item in invoice.line_items:
        # If a page break just happened, redraw the table header
        if pdf.page != current_page:
            current_page = pdf.page
            draw_table_header()

        product_name = item.product.name if getattr(item, 'product', None) else '(item)'
        pdf.cell(COL_DESC, 6, product_name, border='LR')
        pdf.cell(COL_QTY, 6, str(item.quantity), border='LR', align='R')
        pdf.cell(COL_PRICE, 6, _money_str(item.unit_price), border='LR', align='R')
        pdf.cell(COL_AMOUNT, 6, _money_str(item.compute_subtotal()), border='LR', align='R', ln=1)

    # Closing table border
    pdf.cell(CONTENT_WIDTH, 0, '', border='T', ln=1)
    pdf.ln(4)

    # -----------------------------------------------------------------
    # Totals block
    # -----------------------------------------------------------------
    def totals_row(label, value, bold=False):
        pdf.set_font('Helvetica', 'B' if bold else '', 10)
        pdf.cell(COL_DESC, 6, '', border=0)
        pdf.cell(COL_QTY, 6, '', border=0)
        pdf.cell(COL_PRICE, 6, label, border=0, align='R')
        pdf.cell(COL_AMOUNT, 6, _money_str(value), border=0, align='R', ln=1)

    totals_row('Subtotal:', invoice.subtotal)
    if invoice.discount and str(invoice.discount) != '0.00':
        totals_row('Discount:', invoice.discount)
    totals_row('Tax:', invoice.tax_amount)
    totals_row('Total:', invoice.total, bold=True)
    totals_row('Paid:', invoice.total_paid())

    # Balance due — slightly emphasised
    balance = invoice.outstanding_balance()
    pdf.ln(2)
    pdf.set_draw_color(0, 0, 0)
    pdf.line(PAGE_WIDTH / 2, pdf.get_y(), PAGE_WIDTH - MARGIN_RIGHT, pdf.get_y())
    pdf.ln(2)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(COL_DESC, 8, '', border=0)
    pdf.cell(COL_QTY, 8, '', border=0)
    pdf.cell(COL_PRICE, 8, 'Balance Due:', border=0, align='R')
    pdf.cell(COL_AMOUNT, 8, _money_str(balance), border=0, align='R', ln=1)

    pdf.ln(6)

    # -----------------------------------------------------------------
    # Payment terms and notes
    # -----------------------------------------------------------------
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 6, 'Payment Terms', ln=1)
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5, 'Net 30 days from issue date.')

    if invoice.notes:
        pdf.ln(3)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, 'Notes', ln=1)
        pdf.set_font('Helvetica', '', 10)
        pdf.multi_cell(0, 5, invoice.notes)

    # -----------------------------------------------------------------
    # Return bytes
    # -----------------------------------------------------------------
    output = pdf.output(dest='S')
    if isinstance(output, str):
        output = output.encode('latin-1')
    return bytes(output)