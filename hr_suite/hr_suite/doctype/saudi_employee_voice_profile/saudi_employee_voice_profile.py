import frappe
from frappe.model.document import Document


class SaudiEmployeeVoiceProfile(Document):
	def validate(self):
		if self.employee and not self.employee_name:
			self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")