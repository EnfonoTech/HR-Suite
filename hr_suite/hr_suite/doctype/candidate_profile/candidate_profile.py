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

		`job_applicant` and `job_offer` are BOTH mandatory on the core HRMS DocType and
		hr_suite must leave them that way. With `job_applicant` blank,
		`EmployeeOnboarding.set_employee` (hrms/hr/doctype/employee_onboarding/
		employee_onboarding.py:22-24) resolves the employee with
		`get_value("Employee", {"job_applicant": None})` and binds the onboarding to an
		arbitrary employee, while `validate_duplicate_employee_onboarding` (:26-34) matches
		every other blank-applicant onboarding and so permits exactly ONE of them site-wide.

		So a real Job Applicant and a real (draft) Job Offer are reused or created first.
		When either cannot be built — no email to key an applicant on, no designation for
		the offer — onboarding is skipped rather than created half-formed.
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

		job_offer = self._ensure_job_offer(job_applicant, company, joining_date)
		if not job_offer:
			return None

		try:
			onboarding = frappe.get_doc({
				"doctype": "Employee Onboarding",
				"job_applicant": job_applicant,
				"job_offer": job_offer,
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
				"designation": self._get_designation() or "",
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

	def _ensure_job_offer(self, job_applicant, company, joining_date):
		"""Reuse the Job Applicant's Job Offer, or create a draft one.

		`Employee Onboarding.job_offer` is mandatory in core HRMS. `JobOffer.validate`
		(hrms/hr/doctype/job_offer/job_offer.py:17-27) allows only one non-cancelled offer
		per applicant, so an existing one is reused rather than duplicated.

		The offer is left in DRAFT deliberately: hr_suite registers
		`Job Offer: on_submit -> integrations.hrms.on_job_offer_submit`, which creates an
		Employee. The Employee has already been created by `_auto_create_employee` at this
		point, so submitting here would risk a duplicate. HRMS does not require the offer to
		be submitted for the onboarding to reference it.
		"""
		if not frappe.db.exists("DocType", "Job Offer"):
			return None

		existing = frappe.db.get_value(
			"Job Offer", {"job_applicant": job_applicant, "docstatus": ("!=", 2)}, "name"
		)
		if existing:
			return existing

		designation = self._get_designation()
		if not designation or not company:
			frappe.log_error(
				"Job Offer needs a designation and a company. Candidate "
				+ self.name
				+ " has designation="
				+ (designation or "(none)")
				+ ", company="
				+ (company or "(none)")
				+ ". Employee Onboarding was skipped — set Designation on the Candidate "
				"Profile (or on its Job Requisition) and create the Onboarding manually.",
				"HR Suite: Job Offer auto-create skipped",
			)
			return None

		try:
			offer = frappe.get_doc({
				"doctype": "Job Offer",
				"job_applicant": job_applicant,
				"offer_date": joining_date or frappe.utils.nowdate(),
				"designation": designation,
				"company": company,
				# Leave the applicant's own status alone — JobOffer.on_change pushes an
				# "Accepted"/"Rejected" offer status back onto the Job Applicant.
				"status": "Awaiting Response",
			})
			offer.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: Job Offer auto-create failed for " + self.name,
			)
			return None

		return offer.name

	def _get_designation(self):
		"""Designation for the Job Applicant / Job Offer, from the profile or requisition."""
		if self.designation:
			return self.designation
		if self.job_requisition:
			return frappe.db.get_value("Job Requisition", self.job_requisition, "designation")
		return None
