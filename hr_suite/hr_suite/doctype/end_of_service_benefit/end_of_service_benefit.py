import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from hr_suite.hr_suite.utils import calculate_eosb_components, get_employee_basic_salary, get_employee_salary_components


class EndofServiceBenefit(Document):

	def validate(self):
		self._fetch_joining_date()
		self._calculate_eosb()

	def _fetch_joining_date(self):
		emp = frappe.get_doc("Employee", self.employee)
		self.joining_date = emp.date_of_joining

	def _calculate_eosb(self):
		if not self.joining_date or not self.termination_date:
			return

		salary_base = self._get_salary_base_for_eosb()
		details = calculate_eosb_components(
			self.joining_date,
			self.termination_date,
			salary_base,
			self.termination_reason,
			self.eosb_deductions,
		)
		self.years_of_service = details["years_of_service"]
		self.eosb_years_1_5 = details["eosb_years_1_5"]
		self.eosb_years_above_5 = details["eosb_years_above_5"]
		self.eosb_gross = details["eosb_gross"]
		self.resignation_factor = details["resignation_factor"]
		self.resignation_factor_label = details["resignation_factor_label"]
		self.net_eosb = details["net_eosb"]
		self.calculation_notes = details["calculation_notes"]
		self._append_wage_basis_note(salary_base)

	def _get_salary_base_for_eosb(self):
		basis = getattr(self, "eosb_wage_basis", None) or "Basic Salary"
		if basis == "Total Contract Wage":
			if not getattr(self, "last_total_salary", None):
				components = get_employee_salary_components(self.employee)
				self.last_total_salary = components.get("total_salary")
			return self.last_total_salary or self.last_basic_salary
		if basis == "Manual Legal Review":
			self.legal_review_required = 1
		return self.last_basic_salary

	def _append_wage_basis_note(self, salary_base):
		if not hasattr(self, "eosb_wage_basis"):
			return
		review_note = _(
			"EOSB wage basis used: {0}. Salary base: {1}. Legal review required: {2}."
		).format(self.eosb_wage_basis, salary_base, _("Yes") if self.legal_review_required else _("No"))
		self.calculation_notes = f"{self.calculation_notes}\n{review_note}" if self.calculation_notes else review_note

	def on_submit(self):
		"""Update employee status on approval — always set to 'Left'."""
		frappe.db.set_value("Employee", self.employee, "status", "Left")


@frappe.whitelist()
def get_last_basic_salary(employee):
	"""Return the employee's latest basic salary for JS auto-fill."""
	return get_employee_basic_salary(employee)


@frappe.whitelist()
def get_last_salary_components(employee):
	"""Return latest Saudi contract salary components for EOSB review."""
	return get_employee_salary_components(employee)


@frappe.whitelist()
def calculate_eosb_preview(joining_date, termination_date, last_basic_salary,
		termination_reason, eosb_deductions=0, eosb_wage_basis=None, last_total_salary=0):
	"""
	Standalone EOSB calculation for JS preview (mirrors _calculate_eosb logic).
	Returns a dict with all computed fields.
	"""
	salary_base = last_basic_salary
	if eosb_wage_basis == "Total Contract Wage" and last_total_salary:
		salary_base = last_total_salary
	details = calculate_eosb_components(
		joining_date,
		termination_date,
		salary_base,
		termination_reason,
		eosb_deductions,
	)
	if eosb_wage_basis:
		details["calculation_notes"] = (
			f"{details.get('calculation_notes') or ''}\n"
			f"EOSB wage basis used: {eosb_wage_basis}. Salary base: {salary_base}."
		)
	return details
