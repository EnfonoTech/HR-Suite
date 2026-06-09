import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, date_diff


class SaudiEmploymentContract(Document):
	# ─── Validation ─────────────────────────────────────────────────────────────

	def validate(self):
		self._validate_probation_period()
		self._calculate_probation_end_date()
		self._calculate_total_salary()
		self._validate_end_date()

	def _validate_probation_period(self):
		"""Total probation period must not exceed 180 days (Art.53)."""
		total_probation = (self.probation_period_days or 0) + (self.extended_probation_days or 0)
		if total_probation > 180:
			frappe.throw(
				_("Total probation period cannot exceed 180 days per Saudi Labor Law Art. 53.<br>"
				  "Total probation period must not exceed 180 days per Article 53 of Saudi Labor Law."),
				title=_("Probation Period Exceeded"),
			)

	def _calculate_probation_end_date(self):
		"""Calculate the probation end date."""
		if self.start_date and self.probation_period_days:
			total_days = (self.probation_period_days or 0) + (self.extended_probation_days or 0)
			self.probation_end_date = add_days(self.start_date, total_days)

	def _calculate_total_salary(self):
		"""Calculate total salary."""
		self.total_salary = (
			(self.basic_salary or 0)
			+ (self.housing_allowance or 0)
			+ (self.transport_allowance or 0)
			+ (self.other_allowances or 0)
		)

	def _validate_end_date(self):
		"""Validate the end date for fixed-term contracts."""
		if self.contract_type == "Fixed Term" and not self.end_date:
			frappe.throw(
				_("End Date is required for Fixed Term contracts."),
				title=_("End Date Required"),
			)
		if self.end_date and self.start_date:
			if getdate(self.end_date) <= getdate(self.start_date):
				frappe.throw(
					_("End Date must be after Start Date."),
					title=_("Invalid Date"),
				)

	# ─── On Submit ──────────────────────────────────────────────────────────────

	def on_submit(self):
		self.contract_status = "Active"
		self.db_set("contract_status", "Active")
		self._sync_employee_fields()

	def _sync_employee_fields(self):
		"""Sync GOSI base salary, Saudi national flag, and key contract details onto Employee."""
		from hr_suite.hr_suite.utils import is_saudi_nationality
		updates = {}
		if self.basic_salary:
			updates["hr_suite_gosi_salary"] = self.basic_salary
		if self.designation:
			updates["designation"] = self.designation
		if self.department:
			updates["department"] = self.department
		if self.start_date and not frappe.db.get_value("Employee", self.employee, "date_of_joining"):
			updates["date_of_joining"] = self.start_date
		# Auto-set Employee Type from contract nationality
		if self.nationality and frappe.db.has_column("Employee", "hr_suite_employee_type"):
			updates["hr_suite_employee_type"] = (
				"Saudi National" if is_saudi_nationality(self.nationality) else "Expatriate"
			)
		if updates:
			frappe.db.set_value("Employee", self.employee, updates)
