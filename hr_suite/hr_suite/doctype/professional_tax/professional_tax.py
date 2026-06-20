import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# Monthly PT slabs per state (gross monthly salary → PT amount in INR)
# Format: list of (threshold, pt_amount) — pick first where gross > threshold
PT_SLABS = {
    "Karnataka": [
        (0, 0), (15000, 200), (999999, 200),
    ],
    "Maharashtra": [
        (0, 0), (7500, 175), (10000, 200), (999999, 200),
    ],
    "West Bengal": [
        (0, 0), (8500, 90), (10000, 110), (15000, 130), (25000, 150), (40000, 174), (999999, 208),
    ],
    "Tamil Nadu": [
        (0, 0), (3500, 0), (5000, 55), (7500, 115), (10000, 170), (12500, 225), (999999, 208),
    ],
    "Telangana": [
        (0, 0), (15000, 150), (20000, 200), (999999, 200),
    ],
    "Andhra Pradesh": [
        (0, 0), (15000, 150), (20000, 200), (999999, 200),
    ],
    "Kerala": [
        (0, 0), (1999, 0), (2999, 20), (4999, 30), (7499, 50), (9999, 75), (11999, 100), (14999, 125), (19999, 166), (29999, 188), (49999, 300), (999999, 312),
    ],
    "Gujarat": [
        (0, 0), (5999, 0), (8999, 80), (11999, 150), (999999, 200),
    ],
    "Goa": [
        (0, 0), (15000, 0), (25000, 100), (40000, 150), (999999, 200),
    ],
    "Madhya Pradesh": [
        (0, 0), (18750, 0), (999999, 208),
    ],
    "Odisha": [
        (0, 0), (5000, 0), (6000, 25), (8000, 40), (10000, 60), (15000, 80), (20000, 100), (25000, 125), (999999, 200),
    ],
}
DEFAULT_SLAB = [(0, 0), (10000, 100), (999999, 200)]


def _get_pt_amount(state: str, gross: float) -> tuple[float, str]:
    slabs = PT_SLABS.get(state, DEFAULT_SLAB)
    pt = 0
    slab_label = "₹0"
    for threshold, amount in sorted(slabs, key=lambda x: x[0]):
        if gross > threshold:
            pt = amount
            slab_label = f">{threshold:,} → ₹{amount}"
    return float(pt), slab_label


class ProfessionalTax(Document):

    def validate(self):
        pt, label = _get_pt_amount(self.state, flt(self.gross_salary))
        self.pt_amount = pt
        self.pt_slab_label = label
        self.period_label = f"{self.month} {self.year}"

    def on_submit(self):
        self._create_journal_entry()

    def _create_journal_entry(self):
        if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
            return
        if not flt(self.pt_amount):
            return

        company = self.company
        from hr_suite.hr_suite.doctype.statutory_contribution.statutory_contribution import _find_account
        expense_acct = _find_account(company, ["Professional Tax", "PT", "Salary Expense"], "Expense")
        payable_acct = _find_account(company, ["Professional Tax Payable", "PT Payable", "Statutory Payable"], "Liability")

        if not expense_acct or not payable_acct:
            frappe.msgprint(_("Could not find GL accounts for Professional Tax journal entry."), indicator="orange")
            return

        import calendar
        MONTHS = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
                  "July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
        m = MONTHS.get(self.month, 1)
        last = calendar.monthrange(int(self.year), m)[1]

        je = frappe.get_doc({
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": company,
            "posting_date": f"{self.year}-{m:02d}-{last:02d}",
            "user_remark": f"Professional Tax ({self.state}) — {self.employee_name} — {self.period_label}",
            "accounts": [
                {"account": expense_acct, "debit_in_account_currency": flt(self.pt_amount),
                 "party_type": "Employee", "party": self.employee,
                 "reference_type": "Professional Tax", "reference_name": self.name},
                {"account": payable_acct, "credit_in_account_currency": flt(self.pt_amount),
                 "reference_type": "Professional Tax", "reference_name": self.name},
            ],
        })
        je.insert()
        je.submit()
        self.db_set("journal_entry", je.name)
        frappe.msgprint(_(f"Journal Entry {je.name} created for Professional Tax."), indicator="green")


@frappe.whitelist()
def get_pt_for_state(state: str, gross_salary: float) -> dict:
    pt, label = _get_pt_amount(state, flt(gross_salary))
    return {"pt_amount": pt, "slab_label": label}
