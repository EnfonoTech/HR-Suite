import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class HRComplianceActionLog(Document):

	def validate(self):
		self._validate_dates()
		self._sync_status()

	def _validate_dates(self):
		if self.due_date and self.action_date and getdate(self.due_date) < getdate(self.action_date):
			frappe.throw(_("Due Date cannot be before Action Date"))

		if self.completed_on and self.action_date and getdate(self.completed_on) < getdate(self.action_date):
			frappe.throw(_("Completed On cannot be before Action Date"))

	def _sync_status(self):
		if self.completed_on:
			self.status = "Completed"
		elif self.assigned_to and self.status == "Open":
			self.status = "In Progress"