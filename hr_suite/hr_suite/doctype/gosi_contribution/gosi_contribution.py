import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from hr_suite.hr_suite.utils import (
	assert_doctype_permissions,
	assert_employee_access,
	get_contract_nationality_lookup,
	get_employee_basic_salary as get_current_basic_salary,
	get_employee_is_saudi,
	get_employee_nationality,
	is_saudi_nationality,
)


GOSI_MAX_BASE = 45000.0


class GOSIContribution(Document):

	def validate(self):
		self._set_nationality()
		self._apply_gosi_rates()
		self._calculate_contributions()
		self._set_period_label()
		self._cap_contribution_base()

	def _set_nationality(self):
		if not self.nationality:
			self.nationality = get_employee_nationality(self.employee) or ""

	def _apply_gosi_rates(self):
		"""Determine GOSI rates — uses hr_suite_employee_type on Employee as primary source."""
		settings = frappe.get_single("Hr Suite Settings")
		# get_employee_is_saudi checks Employee Type field first, then nationality text, then contract
		is_saudi = (
			get_employee_is_saudi(self.employee)
			if self.employee
			else is_saudi_nationality(self.nationality)
		)
		if is_saudi:
			self.employee_contribution_rate = flt(settings.gosi_saudi_employee_rate) or 10.0
			self.employer_contribution_rate = flt(settings.gosi_saudi_employer_rate) or 12.0
		else:
			self.employee_contribution_rate = flt(settings.gosi_non_saudi_employee_rate) or 0.0
			self.employer_contribution_rate = flt(settings.gosi_non_saudi_employer_rate) or 2.0

	def _cap_contribution_base(self):
		"""Contribution base does not exceed 45,000 SAR."""
		if flt(self.contribution_base) > GOSI_MAX_BASE:
			frappe.msgprint(
				_(f"GOSI contribution base capped at {GOSI_MAX_BASE:,.0f} SAR per GOSI regulations.<br>"
				  f"Contribution base capped at {GOSI_MAX_BASE:,.0f} SAR per GOSI regulations."),
				title=_("Base Capped"),
				indicator="orange",
			)
			self.contribution_base = GOSI_MAX_BASE

	def _calculate_contributions(self):
		base = flt(self.contribution_base)
		self.employee_contribution = round(base * (flt(self.employee_contribution_rate) / 100), 2)
		self.employer_contribution = round(base * (flt(self.employer_contribution_rate) / 100), 2)
		self.total_contribution = round(self.employee_contribution + self.employer_contribution, 2)

	def _set_period_label(self):
		self.period_label = f"{self.month} {self.year}"


@frappe.whitelist()
def create_payroll_entries(doc, method=None):
	"""
	Hook called when GOSI Contribution is submitted.
	Creates a journal entry recording the GOSI contribution in the ledger:
	  Debit  : Social Insurance Expense Account
	  Credit : Social Insurance Payable Account
	"""
	if isinstance(doc, str):
		doc = frappe.get_doc("GOSI Contribution", doc)

	if not flt(doc.total_contribution) > 0:
		return


	if doc.journal_entry and frappe.db.exists("Journal Entry", doc.journal_entry):
		return

	company = doc.company


	expense_account = (
		frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Social Insurance%"],
			 "root_type": "Expense", "is_group": 0},
			"name",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Insurance%"],
			 "root_type": "Expense", "is_group": 0},
			"name",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Salary%"],
			 "root_type": "Expense", "is_group": 0},
			"name",
		)
	)

	payable_account = (
		frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%GOSI%"],
			 "root_type": "Liability", "is_group": 0},
			"name",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Social Insurance%"],
			 "root_type": "Liability", "is_group": 0},
			"name",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Payable", "is_group": 0},
			"name",
		)
	)

	if not expense_account or not payable_account:
		frappe.msgprint(
			_("Could not find accounts for GOSI Journal Entry. "
			  "Please configure Social Insurance accounts in the Chart of Accounts.<br>"
			  "Could not find accounts for GOSI journal entry. Please configure social insurance accounts."),
			title=_("Account Not Found"),
			indicator="orange",
		)
		return


	import calendar as _cal
	_MONTH_MAP = {
		"January": 1, "February": 2, "March": 3, "April": 4,
		"May": 5, "June": 6, "July": 7, "August": 8,
		"September": 9, "October": 10, "November": 11, "December": 12,
	}
	month_num = _MONTH_MAP.get((doc.month or "").split("/")[0].strip(), 1)
	last_day = _cal.monthrange(int(doc.year), month_num)[1]
	posting_date = f"{doc.year}-{month_num:02d}-{last_day:02d}"


	je = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"company": company,
		"posting_date": posting_date,
		"user_remark": (
			f"GOSI Contribution — {doc.employee_name} — {doc.period_label} "
			f"(Emp: {flt(doc.employee_contribution):.2f} SAR + "
			f"Employer: {flt(doc.employer_contribution):.2f} SAR)"
		),
		"accounts": [
			{
				"account": expense_account,
				"debit_in_account_currency": flt(doc.total_contribution),
				"party_type": "Employee",
				"party": doc.employee,
				"reference_type": "GOSI Contribution",
				"reference_name": doc.name,
			},
			{
				"account": payable_account,
				"credit_in_account_currency": flt(doc.total_contribution),
				"reference_type": "GOSI Contribution",
				"reference_name": doc.name,
			},
		],
	})
	assert_doctype_permissions("Journal Entry", ("create", "submit"))
	je.insert()
	je.submit()

	doc.db_set("journal_entry", je.name)
	frappe.msgprint(
		_("Journal Entry <b>{0}</b> created for GOSI contribution of {1}.<br>"
		  "Journal entry <b>{0}</b> created for GOSI contribution for employee {1}.").format(
			je.name, doc.employee_name
		),
		title=_("Journal Entry Created"),
		indicator="green",
	)


@frappe.whitelist()
def get_employee_basic_salary(employee):
	"""Return the employee's current basic salary for JS auto-fill."""
	assert_employee_access(employee)
	return get_current_basic_salary(employee)


@frappe.whitelist()
def generate_gosi_for_month(company: str, month: str, year: int):
	"""
	Create GOSI records for all active employees in the company for a given month.
	Called from a button in the control panel.
	"""
	frappe.has_permission("GOSI Contribution", "create", throw=True)

	employees = frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		fields=_get_employee_fetch_fields(),
	)
	contract_nationalities = get_contract_nationality_lookup([emp.name for emp in employees])

	created = 0
	for emp in employees:

		if frappe.db.exists(
			"GOSI Contribution",
			{"employee": emp.name, "month": month, "year": year, "company": company},
		):
			continue


		base = get_current_basic_salary(emp.name)

		doc = frappe.get_doc({
			"doctype": "GOSI Contribution",
			"employee": emp.name,
			"company": company,
			"month": month,
			"year": year,
			"nationality": emp.get("nationality") or contract_nationalities.get(emp.name) or "",
			"contribution_base": min(base, GOSI_MAX_BASE),
		})
		doc.insert()
		created += 1

	frappe.msgprint(
		_(f"Created {created} GOSI Contribution records for {month} {year}.<br>"
		  f"Created {created} GOSI contribution record(s) for {month} {year}."),
		title=_("GOSI Generated"),
		indicator="green",
	)

	return created


def _get_employee_fetch_fields():
	fields = ["name", "employee_name"]
	if frappe.get_meta("Employee").has_field("nationality"):
		fields.append("nationality")
	return fields
