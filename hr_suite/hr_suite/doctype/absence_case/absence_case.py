import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


class AbsenceCase(Document):

	def validate(self):
		self._validate_dates()
		self._calculate_absence_days()
		self._sync_status()

	def _validate_dates(self):
		if self.absence_end_date and self.absence_start_date:
			if getdate(self.absence_end_date) < getdate(self.absence_start_date):
				frappe.throw(_("Absence End Date cannot be before Absence Start Date"))

		if self.show_cause_deadline and self.absence_start_date:
			if getdate(self.show_cause_deadline) < getdate(self.absence_start_date):
				frappe.throw(_("Show Cause Deadline cannot be before Absence Start Date"))

	def _calculate_absence_days(self):
		if self.absence_start_date and self.absence_end_date:
			self.absence_days = date_diff(self.absence_end_date, self.absence_start_date) + 1
		else:
			self.absence_days = 1 if self.absence_start_date else 0

	def _sync_status(self):
		if self.disciplinary_procedure:
			self.status = "Escalated"
		elif self.employee_response:
			self.status = "Employee Responded"
		elif self.notice_sent:
			self.status = "Notice Sent"