import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from hr_suite.hr_suite.utils import (
    assert_doctype_permissions,
    get_country_config,
    get_employee_work_country,
)


class StatutoryContribution(Document):

    def validate(self):
        self._auto_set_country()
        self._apply_rates_from_config()
        self._apply_ceiling()
        self._calculate()
        self._set_period_label()

    def on_submit(self):
        self._create_journal_entry()

    def _auto_set_country(self):
        if not self.work_country and self.employee:
            self.work_country = get_employee_work_country(self.employee) or ""

    def _apply_rates_from_config(self):
        if self.employee_contribution_rate and self.employer_contribution_rate:
            return
        cfg = get_country_config(self.work_country)
        if not cfg:
            return
        if self.is_national:
            self.employee_contribution_rate = flt(cfg.national_employee_rate)
            self.employer_contribution_rate = flt(cfg.national_employer_rate)
        else:
            self.employee_contribution_rate = flt(cfg.expat_employee_rate)
            self.employer_contribution_rate = flt(cfg.expat_employer_rate)

    def _apply_ceiling(self):
        cfg = get_country_config(self.work_country)
        if not cfg or not flt(cfg.contribution_ceiling):
            self.contribution_ceiling_applied = 0
            return
        ceiling = flt(cfg.contribution_ceiling)
        if flt(self.contribution_base) > ceiling:
            self.contribution_base = ceiling
            self.contribution_ceiling_applied = 1

    def _calculate(self):
        base = flt(self.contribution_base)
        self.employee_contribution = round(base * flt(self.employee_contribution_rate) / 100, 2)
        self.employer_contribution = round(base * flt(self.employer_contribution_rate) / 100, 2)
        self.total_contribution = round(self.employee_contribution + self.employer_contribution, 2)

    def _set_period_label(self):
        self.period_label = f"{self.month} {self.year}"

    def _create_journal_entry(self):
        if self.journal_entry and frappe.db.exists("Journal Entry", self.journal_entry):
            return
        if not flt(self.total_contribution):
            return

        company = self.company
        expense_acct = _find_account(company, ["Social Insurance", "Statutory", "Salary Expense"], "Expense")
        payable_acct = _find_account(company, [self.scheme, "Social Insurance", "Statutory Payable"], "Liability")

        if not expense_acct or not payable_acct:
            frappe.msgprint(
                _(f"Could not find GL accounts for {self.scheme} journal entry. "
                  "Configure Social Insurance accounts in Chart of Accounts."),
                indicator="orange",
            )
            return

        je = frappe.get_doc({
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": company,
            "posting_date": _period_last_day(self.month, self.year),
            "user_remark": f"{self.scheme} — {self.employee_name} — {self.period_label}",
            "accounts": [
                {"account": expense_acct, "debit_in_account_currency": flt(self.total_contribution),
                 "party_type": "Employee", "party": self.employee,
                 "reference_type": "Statutory Contribution", "reference_name": self.name},
                {"account": payable_acct, "credit_in_account_currency": flt(self.total_contribution),
                 "reference_type": "Statutory Contribution", "reference_name": self.name},
            ],
        })
        assert_doctype_permissions("Journal Entry", ("create", "submit"))
        je.insert()
        je.submit()
        self.db_set("journal_entry", je.name)
        frappe.msgprint(_(f"Journal Entry {je.name} created for {self.scheme} contribution."), indicator="green")


def _find_account(company, keywords, root_type):
    for kw in keywords:
        acct = frappe.db.get_value(
            "Account",
            {"company": company, "account_name": ["like", f"%{kw}%"], "root_type": root_type, "is_group": 0},
            "name",
        )
        if acct:
            return acct
    return None


def _period_last_day(month_name, year):
    import calendar
    MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
               "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}
    m = MONTHS.get(month_name, 1)
    last = calendar.monthrange(int(year), m)[1]
    return f"{year}-{m:02d}-{last:02d}"


@frappe.whitelist()
def generate_for_month(company: str, month: str, year: int):
    """Bulk-create Statutory Contribution records for all active employees."""
    frappe.has_permission("Statutory Contribution", "create", throw=True)
    employees = frappe.get_all(
        "Employee",
        filters={"company": company, "status": "Active"},
        fields=["name", "employee_name"],
    )
    created = 0
    for emp in employees:
        country = get_employee_work_country(emp.name) or "SA"
        cfg = get_country_config(country)
        if not cfg or cfg.statutory_scheme in ("EPF+ESI", "DEWS", "None", ""):
            continue
        scheme = cfg.statutory_scheme
        if frappe.db.exists("Statutory Contribution",
                            {"employee": emp.name, "month": month, "year": year, "scheme": scheme}):
            continue
        from hr_suite.hr_suite.utils import get_employee_basic_salary
        base = get_employee_basic_salary(emp.name)
        doc = frappe.get_doc({
            "doctype": "Statutory Contribution",
            "employee": emp.name,
            "company": company,
            "work_country": country,
            "scheme": scheme,
            "month": month,
            "year": year,
            "contribution_base": base,
        })
        doc.insert()
        created += 1
    frappe.msgprint(_(f"Created {created} Statutory Contribution records for {month} {year}."), indicator="green")
    return created
