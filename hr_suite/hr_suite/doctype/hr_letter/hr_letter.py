# Copyright (c) 2026, Enfono and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HRLetter(Document):

	def validate(self):
		self._set_nationality()

	def _set_nationality(self):
		"""Employee has no core nationality field on every site, so resolve it via HR Suite."""
		if self.nationality or not self.employee:
			return

		from hr_suite.hr_suite.utils import get_employee_nationality

		self.nationality = get_employee_nationality(self.employee)

	def on_submit(self):
		self.status = "Issued"
		self.db_set("status", "Issued")

	def on_cancel(self):
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")
