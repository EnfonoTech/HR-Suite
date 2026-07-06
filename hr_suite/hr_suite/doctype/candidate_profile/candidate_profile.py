import frappe
from frappe.model.document import Document


class CandidateProfile(Document):
	def validate(self):
		if not self.status:
			self.status = "Applied"

		if self.linked_employee and self.status not in ("Onboarded", "Accepted"):
			self.status = "Onboarded"

	def on_update(self):
		if self.status == "Accepted" and not self.linked_employee:
			self._auto_create_employee()

	def _auto_create_employee(self):
		"""When a candidate is accepted, create a draft Employee + Onboarding automatically."""
		company = (
			frappe.db.get_value("Job Requisition", self.job_requisition, "company")
			if self.job_requisition
			else frappe.defaults.get_global_default("company")
		)
		joining_date = self.expected_joining_date or frappe.utils.nowdate()

		emp = frappe.get_doc({
			"doctype": "Employee",
			"first_name": self.first_name,
			"last_name": self.last_name,
			"gender": self.gender,
			"date_of_birth": self.date_of_birth,
			"company": company or "",
			"status": "Active",
			"date_of_joining": joining_date,
			"personal_email": self.email_address,
			"cell_number": self.mobile_number,
		})
		emp.insert(ignore_permissions=True)

		# Create Employee Onboarding in Draft
		frappe.get_doc({
			"doctype": "Employee Onboarding",
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"company": company or "",
			"custom_candidate_profile": self.name,
			"date_of_joining": joining_date,
			"boarding_begins_on": joining_date,
			"boarding_status": "Pending",
		}).insert(ignore_permissions=True)

		self.db_set("linked_employee", emp.name)
		self.db_set("status", "Onboarded")

		frappe.msgprint(
			frappe._("Employee {0} and Onboarding record created automatically.").format(emp.employee_name),
			indicator="green",
			alert=True,
		)
