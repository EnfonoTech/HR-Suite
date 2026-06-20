import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

DEWS_DEFAULT_RATE = 5.83  # 21 days / 12 months of gross


class DEWSContribution(Document):

    def validate(self):
        self._calculate()
        self._update_cumulative()
        self.period_label = f"{self.month} {self.year}"

    def on_submit(self):
        self._create_journal_entry()

    def _calculate(self):
        self.employer_contribution = round(
            flt(self.gross_salary) * flt(self.employer_contribution_rate or DEWS_DEFAULT_RATE) / 100, 2
        )

    def _update_cumulative(self):
        prev_total = flt(frappe.db.sql(
            """SELECT SUM(employer_contribution) FROM `tabDEWS Contribution`
               WHERE employee = %s AND docstatus = 1 AND name != %s""",
            (self.employee, self.name or ""), as_list=True
        )[0][0] or 0)
        self.cumulative_balance = round(prev_total + flt(self.employer_contribution), 2)

    def _create_journal_entry(self):
        if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
            return
        if not flt(self.employer_contribution):
            return

        company = self.company
        from hr_suite.hr_suite.doctype.statutory_contribution.statutory_contribution import _find_account
        expense_acct = _find_account(company, ["DEWS", "Gratuity", "End of Service", "Salary Expense"], "Expense")
        payable_acct = _find_account(company, ["DEWS", "Gratuity Payable", "End of Service Payable"], "Liability")

        if not expense_acct or not payable_acct:
            frappe.msgprint(_("Could not find GL accounts for DEWS journal entry."), indicator="orange")
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
            "user_remark": f"DEWS Contribution — {self.employee_name} — {self.period_label}",
            "accounts": [
                {"account": expense_acct, "debit_in_account_currency": flt(self.employer_contribution),
                 "party_type": "Employee", "party": self.employee,
                 "reference_type": "DEWS Contribution", "reference_name": self.name},
                {"account": payable_acct, "credit_in_account_currency": flt(self.employer_contribution),
                 "reference_type": "DEWS Contribution", "reference_name": self.name},
            ],
        })
        je.insert()
        je.submit()
        self.db_set("journal_entry", je.name)
        frappe.msgprint(_(f"Journal Entry {je.name} created for DEWS contribution."), indicator="green")
