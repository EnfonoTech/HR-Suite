import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class EmployeeWarningNotice(Document):
	def validate(self):
		self._validate_dates()
		self._sync_status()

	def on_update(self):
		self._sync_reverse_link("Investigation Record", self.investigation_record)
		self._sync_reverse_link("Disciplinary Procedure", self.disciplinary_procedure)

	def _sync_reverse_link(self, doctype, name):
		if not name:
			return
		linked_notice = frappe.db.get_value(doctype, name, "employee_warning_notice")
		if linked_notice and linked_notice != self.name:
			return
		if linked_notice != self.name:
			frappe.db.set_value(doctype, name, "employee_warning_notice", self.name, update_modified=False)

	def _validate_dates(self):
		if self.due_date and self.warning_date and getdate(self.due_date) < getdate(self.warning_date):
			frappe.throw(_("Due Date cannot be before Warning Date"))

		if self.employee_acknowledged_on and self.warning_date and getdate(self.employee_acknowledged_on) < getdate(self.warning_date):
			frappe.throw(_("Acknowledgement date cannot be before Warning Date"))

	def _sync_status(self):
		if self.employee_acknowledged_on:
			self.status = "Acknowledged"
		elif not self.status:
			self.status = "Issued"