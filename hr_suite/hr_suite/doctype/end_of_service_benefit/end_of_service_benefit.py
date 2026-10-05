import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate, nowdate

from hr_suite.hr_suite.utils import assert_employee_access, calculate_eosb_components, get_employee_basic_salary, get_employee_salary_components


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

		from hr_suite.hr_suite.utils import get_employee_work_country
		country = get_employee_work_country(self.employee)

		if country == "IN":
			self._calculate_eosb_india(salary_base)
			return

		# Every other country is the slab engine, reading the employee's own Country Config.
		# This used to run the Saudi formula for any country it did not recognise, which is
		# how Qatar and Kuwait employees silently got a Saudi gratuity.
		from hr_suite.hr_suite.gratuity import calculate_for_employee

		result = calculate_for_employee(
			self.employee,
			self.termination_date,
			self.termination_reason,
			deductions=self.eosb_deductions,
			base_override=salary_base,
		)
		self.years_of_service = result.years_of_service
		self.eosb_years_1_5 = result.eosb_years_1_5
		self.eosb_years_above_5 = result.eosb_years_above_5
		self.eosb_gross = result.gross_entitlement
		self.resignation_factor = result.factor
		self.resignation_factor_label = result.factor_label
		self.net_eosb = result.net_entitlement
		self.calendar_days = result.calendar_days
		self.unpaid_days = result.unpaid_days
		self.qualifying_days = result.qualifying_days
		self.gratuity_base_amount = result.base_amount
		self.gross_before_cap = result.gross_before_cap
		self.cap_amount = result.cap_amount
		self.is_partial_settlement = result.is_partial
		self.set("gratuity_breakdown", [])
		for row in result.breakdown:
			self.append("gratuity_breakdown", {k: row[k] for k in ("slab", "years_in_slab", "rate", "rate_unit", "amount")})
		self.calculation_notes = result.notes
		self._append_wage_basis_note(salary_base)

	def _calculate_eosb_india(self, salary_base):
		from hr_suite.hr_suite.utils import _calculate_india_gratuity

		years = date_diff(getdate(self.termination_date), getdate(self.joining_date)) / 365.0
		result = _calculate_india_gratuity(years, flt(salary_base), self.termination_reason or "", flt(self.eosb_deductions))
		self.years_of_service = round(years, 2)
		self.eosb_years_1_5 = 0
		self.eosb_years_above_5 = 0
		self.eosb_gross = flt(result.get("gross_entitlement"))
		self.resignation_factor = flt(result.get("factor"))
		self.resignation_factor_label = result.get("factor_label", "")
		self.net_eosb = flt(result.get("net_entitlement"))
		self.calculation_notes = f"Formula: {result.get('formula', '')}\n{result.get('notes', '')}"
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
		"""Mark the employee Left on approval — unless this is a partial settlement, which is
		gratuity accrued to date paid while the employee stays."""
		if not self.is_partial_settlement:
			frappe.db.set_value("Employee", self.employee, "status", "Left")


@frappe.whitelist()
def get_last_basic_salary(employee):
	"""Return the employee's latest basic salary for JS auto-fill."""
	assert_employee_access(employee)
	return get_employee_basic_salary(employee)


@frappe.whitelist()
def get_last_salary_components(employee):
	"""Return latest Saudi contract salary components for EOSB review."""
	assert_employee_access(employee)
	return get_employee_salary_components(employee)


@frappe.whitelist()
def calculate_eosb_preview(joining_date, termination_date, last_basic_salary,
		termination_reason, eosb_deductions=0, eosb_wage_basis=None, last_total_salary=0,
		employee=None, country=None):
	"""
	Gratuity calculation for the form preview. With an `employee` the figures come from that
	employee's own country policy, unpaid leave and nationality (the same call validate() makes);
	without one, from the explicit figures under `country` (Saudi Arabia when blank).
	Returns a dict with all computed fields.
	"""
	salary_base = last_basic_salary
	if eosb_wage_basis == "Total Contract Wage" and last_total_salary:
		salary_base = last_total_salary

	if employee:
		assert_employee_access(employee)
		from hr_suite.hr_suite.gratuity import calculate_for_employee
		from hr_suite.hr_suite.utils import get_employee_work_country

		if get_employee_work_country(employee) != "IN":
			result = calculate_for_employee(
				employee, termination_date, termination_reason,
				deductions=eosb_deductions, base_override=salary_base,
			)
			details = {
				"years_of_service": result.years_of_service,
				"eosb_years_1_5": result.eosb_years_1_5,
				"eosb_years_above_5": result.eosb_years_above_5,
				"eosb_gross": result.gross_entitlement,
				"resignation_factor": result.factor,
				"resignation_factor_label": result.factor_label,
				"net_eosb": result.net_entitlement,
				"calculation_notes": result.notes,
				"calendar_days": result.calendar_days,
				"unpaid_days": result.unpaid_days,
				"qualifying_days": result.qualifying_days,
				"gratuity_base_amount": result.base_amount,
				"gross_before_cap": result.gross_before_cap,
				"cap_amount": result.cap_amount,
				"is_partial_settlement": result.is_partial,
				"gratuity_breakdown": result.breakdown,
			}
		else:
			details = _preview_from_figures(joining_date, termination_date, salary_base, termination_reason, eosb_deductions, "SA")
	else:
		details = _preview_from_figures(joining_date, termination_date, salary_base, termination_reason, eosb_deductions, country)

	if eosb_wage_basis:
		details["calculation_notes"] = (
			f"{details.get('calculation_notes') or ''}\n"
			f"EOSB wage basis used: {eosb_wage_basis}. Salary base: {salary_base}."
		)
	return details


def _preview_from_figures(joining_date, termination_date, salary_base, termination_reason, eosb_deductions, country):
	return calculate_eosb_components(
		joining_date,
		termination_date,
		salary_base,
		termination_reason,
		eosb_deductions,
		country=country or "SA",
	)
