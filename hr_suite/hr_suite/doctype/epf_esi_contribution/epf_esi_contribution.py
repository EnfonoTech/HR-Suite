import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

ESI_GROSS_CEILING = 21000.0
EPF_WAGE_CEILING = 15000.0
EPF_ADMIN_CHARGE_RATE = 0.005  # 0.5% EDLI


class EPFESIContribution(Document):

    def validate(self):
        self._compute_epf()
        self._compute_esi()
        self._compute_totals()
        self.period_label = f"{self.month} {self.year}"

    def on_submit(self):
        self._create_journal_entry()

    def _compute_epf(self):
        basic = flt(self.basic_salary)
        if self.voluntary_pf:
            wage = basic
        else:
            wage = min(basic, EPF_WAGE_CEILING)
        self.epf_wage = round(wage, 2)

        self.employee_epf = round(wage * flt(self.employee_epf_rate) / 100, 2)
        self.eps_contribution = round(min(wage, EPF_WAGE_CEILING) * flt(self.eps_rate) / 100, 2)
        self.employer_epf = round(wage * flt(self.employer_epf_rate) / 100, 2)
        self.edli_contribution = round(min(wage, EPF_WAGE_CEILING) * EPF_ADMIN_CHARGE_RATE, 2)
        self.total_epf = round(self.employee_epf + self.employer_epf + self.eps_contribution + self.edli_contribution, 2)

    def _compute_esi(self):
        gross = flt(self.gross_salary) or flt(self.basic_salary)
        self.esi_applicable = 1 if gross <= ESI_GROSS_CEILING else 0
        if not self.esi_applicable:
            self.employee_esi = 0
            self.employer_esi = 0
            self.total_esi = 0
            return
        self.employee_esi = round(gross * flt(self.employee_esi_rate) / 100, 2)
        self.employer_esi = round(gross * flt(self.employer_esi_rate) / 100, 2)
        self.total_esi = round(self.employee_esi + self.employer_esi, 2)

    def _compute_totals(self):
        self.total_employee_deduction = round(flt(self.employee_epf) + flt(self.employee_esi), 2)
        self.total_employer_contribution = round(
            flt(self.employer_epf) + flt(self.eps_contribution) + flt(self.edli_contribution) + flt(self.employer_esi), 2
        )

    def _create_journal_entry(self):
        if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
            return
        total = self.total_employee_deduction + self.total_employer_contribution
        if not total:
            return

        company = self.company
        from hr_suite.hr_suite.doctype.statutory_contribution.statutory_contribution import (
            _find_account, _period_last_day
        )
        expense_acct = _find_account(company, ["PF", "EPF", "Provident Fund", "Statutory", "Salary Expense"], "Expense")
        payable_acct = _find_account(company, ["EPF", "PF Payable", "Statutory Payable", "ESI Payable"], "Liability")

        if not expense_acct or not payable_acct:
            frappe.msgprint(_("Could not find GL accounts for EPF/ESI journal entry."), indicator="orange")
            return

        import calendar
        MONTHS = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
                  "July":7,"August":8,"September":9,"October":10,"November":11,"December":12}
        m = MONTHS.get(self.month, 1)
        last = calendar.monthrange(int(self.year), m)[1]
        posting_date = f"{self.year}-{m:02d}-{last:02d}"

        je = frappe.get_doc({
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": company,
            "posting_date": posting_date,
            "user_remark": f"EPF/ESI — {self.employee_name} — {self.period_label}",
            "accounts": [
                {"account": expense_acct, "debit_in_account_currency": total,
                 "party_type": "Employee", "party": self.employee,
                 "reference_type": "EPF ESI Contribution", "reference_name": self.name},
                {"account": payable_acct, "credit_in_account_currency": total,
                 "reference_type": "EPF ESI Contribution", "reference_name": self.name},
            ],
        })
        je.insert()
        je.submit()
        self.db_set("journal_entry", je.name)
        frappe.msgprint(_(f"Journal Entry {je.name} created for EPF/ESI."), indicator="green")
