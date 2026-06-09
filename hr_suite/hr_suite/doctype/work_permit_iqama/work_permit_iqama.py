import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today

from hr_suite.hr_suite.utils import get_employee_nationality


class WorkPermitIqama(Document):

	def validate(self):
		self._set_nationality()
		self._calculate_iqama_status()
		self._calculate_permit_status()

	def _set_nationality(self):
		if self.employee and not self.nationality:
			self.nationality = get_employee_nationality(self.employee)

	def _calculate_iqama_status(self):
		if not self.iqama_expiry_date:
			return
		days = date_diff(self.iqama_expiry_date, today())
		self.days_to_iqama_expiry = days
		settings = frappe.get_single("Hr Suite Settings")
		alert_days = int(settings.iqama_expiry_alert_days or 90)

		if days < 0:
			self.iqama_status = "Expired"
		elif days <= alert_days:
			self.iqama_status = "Expiring Soon"
		else:
			self.iqama_status = "Active"

	def _calculate_permit_status(self):
		if not self.work_permit_expiry_date:
			self.work_permit_status = "N/A"
			return
		days = date_diff(self.work_permit_expiry_date, today())
		self.days_to_permit_expiry = days

		if days < 0:
			self.work_permit_status = "Expired"
		elif days <= 90:
			self.work_permit_status = "Expiring Soon"
		else:
			self.work_permit_status = "Active"
