# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, get_first_day, get_last_day


# Fallback name for the Salary Component that carries a penalty onto the Salary Slip.
# Overridden per site by Hr Suite Settings -> penalty_salary_component.
PENALTY_DEDUCTION_COMPONENT = "Penalty Deduction"

PENALTY_PAYROLL_ERROR_TITLE = "HR Suite: penalty not booked into payroll"


REPEAT_STATUS_MAP = {
	0: "First",
	1: "Second",
	2: "Third",
}


class EmployeePenalty(Document):

	def before_save(self):
		self._set_repeat_status_and_value()

	def _set_repeat_status_and_value(self):
		if not (self.employee and self.penalty_type and self.penalty_date):
			return

		penalty_date = getdate(self.penalty_date)
		month_start = get_first_day(penalty_date)
		month_end = get_last_day(penalty_date)

		filters = {
			"docstatus": 1,
			"employee": self.employee,
			"penalty_type": self.penalty_type,
			"penalty_date": ["between", [month_start, month_end]],
		}
		if self.name:
			filters["name"] = ["!=", self.name]

		prior_count = frappe.db.count("Employee Penalty", filters)

		self.repeat_status = REPEAT_STATUS_MAP.get(prior_count, "Fourth")

		repeat_key = self.repeat_status.lower()
		value_field = f"{repeat_key}_value"

		pt = frappe.get_doc("Penalty Type", self.penalty_type)
		self.penalty_value = pt.get(value_field) or 0

	def on_submit(self):
		if self.status != "Approved":
			frappe.throw(_("Status must be 'Approved' before submitting"))
		self._create_additional_salary()

	def _create_additional_salary(self):
		"""Book the penalty as an `Additional Salary`, or refuse and say why.

		Two defects were fixed here, both of the same class as the Employee Loan one:

		* the Salary Component used to be created with NO `Salary Component Account`.
		  `PayrollEntry.get_salary_component_account` (payroll_entry.py:334-349) throws
		  `Please set account in Salary Component {0}` when the accrual Journal Entry
		  reaches such a component, and that throw sits inside the one try/except that
		  rolls a whole payroll run back — so a single penalty could destroy the run,
		  and it is also why Finance had nothing to post against.
		* `Additional Salary.currency` is mandatory and read-only, so a server-side
		  creator has to set it (hrms sets it in every one of its own creators, e.g.
		  employee_incentive.py:30). Without it the insert fails on a mandatory field.
		"""
		if not self.penalty_value or flt(self.penalty_value) <= 0:
			return

		base_salary = self._get_base_salary()
		if not base_salary:
			frappe.msgprint(
				_("Could not find base salary for employee. Additional Salary not created."),
				indicator="orange",
			)
			return

		salary_component, reason = self._get_penalty_salary_component()
		if reason:
			frappe.msgprint(reason, title=_("Penalty Not Deducted"), indicator="orange")
			return

		currency = self._get_currency()
		if not currency:
			frappe.msgprint(
				_(
					"{0} has no submitted Salary Structure Assignment, so the payroll currency is "
					"unknown and the penalty was not booked into payroll."
				).format(self.employee),
				title=_("Penalty Not Deducted"),
				indicator="orange",
			)
			return

		amount = (flt(base_salary) / 30) * flt(self.penalty_value)

		additional_salary = frappe.get_doc({
			"doctype": "Additional Salary",
			"employee": self.employee,
			"company": self.company,
			"currency": currency,
			"salary_component": salary_component,
			"amount": amount,
			"payroll_date": self.posting_date,
			"is_recurring": 0,
			"ref_doctype": self.doctype,
			"ref_docname": self.name,
			"overwrite_salary_structure_amount": 0,
			"deduct_full_tax_on_selected_payroll_date": 0,
		})
		additional_salary.insert(ignore_permissions=True)
		additional_salary.submit()

		self.db_set("additional_salary", additional_salary.name, update_modified=False)

	def _get_base_salary(self):
		assignment = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": self.employee, "docstatus": 1},
			"base",
			order_by="from_date desc",
		)
		return assignment or 0

	def _get_currency(self):
		from hr_suite.hr_suite.integrations.hrms import get_employee_payroll_currency

		return get_employee_payroll_currency(self.employee, self.posting_date, self.company)

	def _get_penalty_salary_component(self):
		"""(component_name, reason). An empty `reason` means it is safe to post."""
		from hr_suite.hr_suite.integrations.hrms import ensure_salary_component_account

		component = (
			frappe.db.get_single_value("Hr Suite Settings", "penalty_salary_component")
			or PENALTY_DEDUCTION_COMPONENT
		)

		ok, reason = ensure_salary_component_account(
			component,
			self.company,
			component_type="Deduction",
			# A penalty is a fixed sum already expressed in days of pay; scaling it again
			# by payment days would charge less than the penalty that was approved.
			depends_on_payment_days=0,
			error_title=PENALTY_PAYROLL_ERROR_TITLE,
		)
		return component, ("" if ok else reason)

	def on_cancel(self):
		self._cancel_additional_salary()

	def _cancel_additional_salary(self):
		if not self.additional_salary:
			return
		if frappe.db.exists("Additional Salary", self.additional_salary):
			doc = frappe.get_doc("Additional Salary", self.additional_salary)
			if doc.docstatus == 1:
				doc.cancel()
		self.db_set("additional_salary", None, update_modified=False)
