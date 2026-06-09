import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class DisciplinaryAppeal(Document):

	def validate(self):
		self._validate_dates()
		self._sync_status()

	def _validate_dates(self):
		if self.hearing_date and self.appeal_date:
			if getdate(self.hearing_date) < getdate(self.appeal_date):
				frappe.throw(_("Hearing Date cannot be before Appeal Date"))

		if self.decision_date and self.appeal_date:
			if getdate(self.decision_date) < getdate(self.appeal_date):
				frappe.throw(_("Decision Date cannot be before Appeal Date"))

	def _sync_status(self):
		if self.decision:
			self.status = "Decided"
		elif self.hearing_date:
			self.status = "Hearing Scheduled"
		elif self.assigned_to:
			self.status = "Under Review"