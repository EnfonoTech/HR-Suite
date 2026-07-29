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

		self.db_set("linked_employee", emp.name)
		self.db_set("status", "Onboarded")

		onboarding = self._create_onboarding(emp, company, joining_date)

		if onboarding:
			message = frappe._("Employee {0} and Onboarding {1} created automatically.").format(
				emp.employee_name, onboarding
			)
		else:
			message = frappe._("Employee {0} created automatically. Create the Onboarding manually.").format(
				emp.employee_name
			)

		frappe.msgprint(message, indicator="green", alert=True)

	def _create_onboarding(self, emp, company, joining_date):
		"""Create the HRMS Employee Onboarding for the newly created Employee.

		HRMS keys onboarding off a Job Applicant — it rejects a second onboarding for the
		same applicant, and builds the boarding project name from it — so a Job Applicant is
		reused or created first. With no email address there is nothing to key one on, so
		onboarding is skipped rather than created half-formed.
		"""
		if not frappe.db.exists("DocType", "Employee Onboarding"):
			return None

		job_applicant = self._ensure_job_applicant()
		if not job_applicant:
			return None

		existing = frappe.db.exists(
			"Employee Onboarding", {"job_applicant": job_applicant, "docstatus": ("!=", 2)}
		)
		if existing:
			return existing

		try:
			onboarding = frappe.get_doc({
				"doctype": "Employee Onboarding",
				"job_applicant": job_applicant,
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"company": company or "",
				"custom_candidate_profile": self.name,
				"date_of_joining": joining_date,
				"boarding_begins_on": joining_date,
				"boarding_status": "Pending",
			})
			onboarding.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: Employee Onboarding auto-create failed for " + self.name,
			)
			return None

		return onboarding.name

	def _ensure_job_applicant(self):
		"""Reuse the Job Applicant for this candidate's email, or create one."""
		if not self.email_address:
			return None

		existing = frappe.db.get_value("Job Applicant", {"email_id": self.email_address}, "name")
		if existing:
			return existing

		applicant_name = self.candidate_name or " ".join(
			part for part in (self.first_name, self.last_name) if part
		)
		if not applicant_name:
			return None

		try:
			applicant = frappe.get_doc({
				"doctype": "Job Applicant",
				"applicant_name": applicant_name,
				"email_id": self.email_address,
				"phone_number": self.mobile_number or "",
				"status": "Accepted",
			})
			applicant.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: Job Applicant auto-create failed for " + self.name,
			)
			return None

		return applicant.name
