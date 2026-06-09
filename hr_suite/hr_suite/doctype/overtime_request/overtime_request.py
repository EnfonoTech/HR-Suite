import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from hr_suite.hr_suite.utils import assert_doctype_permissions, assert_positive_basic_salary, get_employee_basic_salary as get_current_basic_salary, text_matches_tokens


class OvertimeRequest(Document):

	OVERTIME_RATE = 1.5
	WORKING_HOURS_PER_MONTH = 240  # 8 h/day × 30 days

	def validate(self):
		self._validate_overtime_hours()
		self._fetch_salary()
		self._calculate_overtime()

	def _validate_overtime_hours(self):
		"""Overtime does not exceed a reasonable limit (total daily hours must not exceed 12)."""
		total = (self.normal_hours or 0) + (self.overtime_hours or 0)
		if total > 12:
			frappe.throw(
				_("Total working hours per day (normal + overtime) cannot exceed 12 hours.<br>"
				  "Total daily working hours (regular + overtime) cannot exceed 12 hours."),
				title=_("Hours Limit Exceeded"),
			)
		if (self.overtime_hours or 0) <= 0:
			frappe.throw(_("Overtime hours must be greater than 0"))

	def _fetch_salary(self):
		"""Fetch the basic salary from the employee's active contract."""
		self.monthly_basic = get_current_basic_salary(self.employee)
		assert_positive_basic_salary(self.employee_name or self.employee, self.monthly_basic, _("calculating overtime"))
		self.overtime_rate = self.OVERTIME_RATE

		self.hourly_rate = round(self.monthly_basic / self.WORKING_HOURS_PER_MONTH, 4)

	def _calculate_overtime(self):
		"""Calculate overtime amount = hours x hourly rate x 1.5"""
		self.overtime_amount = round(
			flt(self.overtime_hours) * flt(self.hourly_rate) * self.OVERTIME_RATE, 2
		)

	def on_submit(self):
		"""On approval: create a journal entry instead of Additional Salary."""
		if not text_matches_tokens(self.approval_status, "approved", "approved"):
			frappe.throw(
				_("Cannot submit unless Approval Status is 'Approved'.<br>"
				  "Approval is only possible when approval status is set to Approved."),
				title=_("Not Approved"),
			)
		self._create_overtime_journal_entry()

	def _create_overtime_journal_entry(self):
		"""Create a journal entry to post the overtime amount instead of Additional Salary."""
		if self.overtime_journal_entry:
			return

		if not flt(self.overtime_amount) > 0:
			return

		company = self.company


		expense_account = (
			frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Overtime%"],
				 "root_type": "Expense", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Salary%"],
				 "root_type": "Expense", "is_group": 0},
				"name",
			)
			or frappe.db.get_value(
				"Account",
				{"company": company, "root_type": "Expense", "is_group": 0},
				"name",
			)
		)

		payable_account = (
			frappe.db.get_value(
				"Account",
				{"company": company, "account_name": ["like", "%Salary Payable%"],
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
				_("Could not find accounts for Overtime Journal Entry. "
				  "Please configure Salary/Overtime expense accounts in the Chart of Accounts."),
				title=_("Account Not Found"),
				indicator="orange",
			)
			return

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": self.date or nowdate(),
			"user_remark": (
				f"Overtime Pay — {self.employee_name} — {self.date} — "
				f"{self.overtime_hours}h × {self.overtime_rate} = {flt(self.overtime_amount):.2f} SAR"
			),
			"accounts": [
				{
					"account": expense_account,
					"debit_in_account_currency": flt(self.overtime_amount),
					"party_type": "Employee",
					"party": self.employee,
					"reference_type": "Overtime Request",
					"reference_name": self.name,
				},
				{
					"account": payable_account,
					"credit_in_account_currency": flt(self.overtime_amount),
					"reference_type": "Overtime Request",
					"reference_name": self.name,
				},
			],
		})
		assert_doctype_permissions("Journal Entry", ("create", "submit"))
		je.insert()
		je.submit()

		self.db_set("overtime_journal_entry", je.name)
		frappe.msgprint(
			_("Journal Entry <b>{0}</b> created for overtime of {1} SAR.").format(
				je.name, flt(self.overtime_amount)
			),
			title=_("Journal Entry Created"),
			indicator="green",
		)


@frappe.whitelist()
def create_overtime_journal_entry(doc, method=None):
	"""Hook called from hooks.py on_submit — delegates to document method."""
	if isinstance(doc, str):
		doc = frappe.get_doc("Overtime Request", doc)
	# Guard: _create_overtime_journal_entry() already ran inside on_submit(); avoid double-creation
	if not doc.overtime_journal_entry:
		doc._create_overtime_journal_entry()


@frappe.whitelist()
def get_employee_basic_salary(employee):
	"""Return the employee's current basic salary for JS auto-fill."""
	return get_current_basic_salary(employee)
