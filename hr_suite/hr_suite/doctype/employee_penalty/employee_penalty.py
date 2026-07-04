# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, get_first_day, get_last_day


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
		if not self.penalty_value or self.penalty_value <= 0:
			return

		base_salary = self._get_base_salary()
		if not base_salary:
			frappe.msgprint(_("Could not find base salary for employee. Additional Salary not created."), indicator="orange")
			return

		salary_component = self._get_penalty_salary_component()
		amount = (base_salary / 30) * self.penalty_value

		additional_salary = frappe.get_doc({
			"doctype": "Additional Salary",
			"employee": self.employee,
			"company": self.company,
			"salary_component": salary_component,
			"amount": amount,
			"payroll_date": self.posting_date,
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

	def _get_penalty_salary_component(self):
		component = frappe.db.get_single_value("Hr Suite Settings", "penalty_salary_component")
		if not component:
			component = "Penalty Deduction"

		if not frappe.db.exists("Salary Component", component):
			frappe.get_doc({
				"doctype": "Salary Component",
				"salary_component": component,
				"salary_component_abbr": component[:4].upper(),
				"type": "Deduction",
				"is_tax_applicable": 0,
			}).insert(ignore_permissions=True)

		return component

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
