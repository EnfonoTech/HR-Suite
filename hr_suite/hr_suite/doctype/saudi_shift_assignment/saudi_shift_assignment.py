import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class SaudiShiftAssignment(Document):
	def validate(self):
		if self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date."))

		if self.status != "Active":
			return

		overlap = frappe.db.sql(
			"""
			SELECT name
			FROM `tabSaudi Shift Assignment`
			WHERE employee = %(employee)s
			  AND status = 'Active'
			  AND docstatus < 2
			  AND name != %(name)s
			  AND start_date <= %(end_date)s
			  AND (end_date IS NULL OR end_date = '' OR end_date >= %(start_date)s)
			LIMIT 1
			""",
			{
				"employee": self.employee,
				"name": self.name or "",
				"start_date": self.start_date,
				"end_date": self.end_date or "9999-12-31",
			},
			as_dict=True,
		)
		if overlap:
			frappe.throw(_("Employee already has an active Saudi Shift Assignment in this period."))
