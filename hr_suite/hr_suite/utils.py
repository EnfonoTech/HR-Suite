"""
utils.py — Helper functions for Hr Suite calculations.
"""
import frappe
from frappe import _
from frappe.utils import cstr, date_diff, flt, getdate


def assert_doctype_permissions(doctype: str, permission_types, doc=None):
	if isinstance(permission_types, str):
		permission_types = (permission_types,)

	for permission_type in permission_types:
		frappe.has_permission(doctype, permission_type, doc=doc, throw=True)


def text_matches_tokens(value, *tokens: str) -> bool:
	normalized = cstr(value or "").strip().lower()
	if not normalized:
		return False
	return any(cstr(token).strip().lower() in normalized for token in tokens if cstr(token).strip())


def assert_positive_basic_salary(employee_label: str, basic_salary: float, context_label: str):
	if flt(basic_salary) > 0:
		return
	frappe.throw(
		_(
			"Basic salary for {0} must be greater than zero before {1}.<br>"
			"Employee {0} basic salary must be greater than zero before {1}."
		).format(employee_label, context_label),
		title=_("Missing Basic Salary"),
	)


def get_overlap_days(start_date, end_date, range_start, range_end) -> int:
	period_start = max(getdate(start_date), getdate(range_start))
	period_end = min(getdate(end_date), getdate(range_end))
	if period_end < period_start:
		return 0
	return date_diff(period_end, period_start) + 1


def calculate_prorated_sick_leave_deduction(leave_rows: list, month_start, month_end, fallback_daily_salary: float = 0.0) -> float:
	deduction = 0.0
	for row in leave_rows or []:
		overlap_days = get_overlap_days(row.get("from_date"), row.get("to_date"), month_start, month_end)
		if overlap_days <= 0:
			continue

		total_days = flt(row.get("total_days") or overlap_days)
		daily_salary = flt(row.get("daily_salary") or fallback_daily_salary)
		full_pay = flt(overlap_days) * daily_salary
		actual_pay = flt(row.get("leave_pay_amount")) * (flt(overlap_days) / total_days if total_days else 0)
		if full_pay > actual_pay:
			deduction += round(full_pay - actual_pay, 2)

	return round(deduction, 2)


def get_active_contract(employee: str, fields=None, as_dict=True):
	field_list = fields or [
		"name",
		"basic_salary",
		"housing_allowance",
		"transport_allowance",
		"other_allowances",
		"total_salary",
	]
	return frappe.db.get_value(
		"Saudi Employment Contract",
		{"employee": employee, "contract_status": "Active"},
		field_list,
		as_dict=as_dict,
		order_by="start_date desc",
	)


def get_employee_basic_salary(employee: str) -> float:
	contract = get_active_contract(employee, ["basic_salary"], as_dict=True) or {}
	basic_salary = flt(contract.get("basic_salary"))
	if basic_salary:
		return basic_salary
	return flt(frappe.db.get_value("Employee", employee, "ctc") or 0)


def get_employee_salary_components(employee: str) -> dict:
	contract = get_active_contract(
		employee,
		["basic_salary", "housing_allowance", "transport_allowance", "other_allowances", "total_salary"],
		as_dict=True,
	) or {}
	basic = flt(contract.get("basic_salary") or frappe.db.get_value("Employee", employee, "ctc") or 0)
	housing = flt(contract.get("housing_allowance") or 0)
	transport = flt(contract.get("transport_allowance") or 0)
	other = flt(contract.get("other_allowances") or 0)
	total = flt(contract.get("total_salary") or (basic + housing + transport + other))
	return {
		"basic_salary": basic,
		"housing_allowance": housing,
		"transport_allowance": transport,
		"other_allowances": other,
		"total_salary": total,
	}


def get_annual_leave_days_taken(employee: str, leave_year: int, exclude_name: str | None = None) -> float:
	filters = {
		"employee": employee,
		"docstatus": 1,
	}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]

	rows = frappe.get_all(
		"Saudi Annual Leave",
		filters=filters,
		fields=["leave_start_date", "leave_end_date", "total_leave_days", "half_day"],
	)
	year_start = f"{leave_year}-01-01"
	year_end = f"{leave_year}-12-31"
	total = 0.0
	for row in rows:
		overlap_days = get_overlap_days(row.leave_start_date, row.leave_end_date, year_start, year_end)
		if overlap_days <= 0:
			continue
		if getattr(row, "half_day", 0):
			total += 0.5
			continue
		document_days = max(flt(row.total_leave_days), flt(date_diff(row.leave_end_date, row.leave_start_date) + 1))
		total += flt(row.total_leave_days or overlap_days) * (flt(overlap_days) / document_days if document_days else 0)
	return round(total, 2)


def get_annual_leave_balance(employee: str, reference_date: str | None = None, exclude_name: str | None = None) -> dict:
	reference = getdate(reference_date) if reference_date else getdate()
	entitlement = get_annual_leave_entitlement(employee, reference)
	taken = get_annual_leave_days_taken(employee, reference.year, exclude_name=exclude_name)
	return {
		"entitled": entitlement,
		"taken": taken,
		"balance": flt(entitlement) - flt(taken),
		"year": reference.year,
	}


def get_annual_leave_entitlement(employee: str, date: str = None) -> int:
	"""
	Return the number of annual leave days based on years of service (Article 109).
	< 5 years: 21 days | >= 5 years: 30 days
	"""
	emp = frappe.get_doc("Employee", employee)
	joining_date = getdate(emp.date_of_joining)
	ref_date = getdate(date) if date else getdate()
	years = date_diff(ref_date, joining_date) / 365.0
	settings = frappe.get_single("Hr Suite Settings")
	threshold = flt(settings.annual_leave_years_threshold) or 5
	return int(settings.annual_leave_after_threshold or 30) if years >= threshold else int(settings.annual_leave_before_threshold or 21)


def get_eosb_amount(employee: str, termination_reason: str, termination_date: str = None) -> dict:
	"""
	Calculate End of Service Benefit (EOSB) per Article 84 of Saudi Labor Law.

	Returns dict with:
		- years_of_service
		- eosb_gross        (before resignation factor)
		- resignation_factor
		- eosb_net          (actual entitlement)
	"""
	emp = frappe.get_doc("Employee", employee)
	details = calculate_eosb_components(
		emp.date_of_joining,
		termination_date or getdate(),
		get_employee_basic_salary(employee),
		termination_reason,
	)

	return {
		"years_of_service": details["years_of_service"],
		"monthly_basic": details["monthly_basic"],
		"eosb_gross": details["eosb_gross"],
		"resignation_factor": details["resignation_factor"],
		"eosb_net": details["net_eosb"],
	}


def _get_resignation_factor(years: float, termination_reason: str) -> float:
	"""
	Resignation factor:
	- Resignation < 2 years  -> 0
	- Resignation 2-10 years -> 1/3
	- Resignation > 10 years -> 2/3
	- Termination by employer / contract end / death -> 1.0
	- Disciplinary dismissal (Article 80) -> 0
	"""
	return get_eosb_factor_and_label(termination_reason, years)[0]


def get_eosb_factor_and_label(termination_reason: str, years: float) -> tuple[float, str]:
	reason = termination_reason or ""
	if text_matches_tokens(reason, "dismissal", "dismissal"):
		return 0.0, "Disciplinary Dismissal — No EOSB"

	if text_matches_tokens(reason, "resignation", "resignation"):
		if years < 2:
			return 0.0, "Resignation < 2 yrs — No EOSB"
		if years <= 10:
			return round(1 / 3, 4), "Resignation 2–10 yrs — 1/3 EOSB"
		return round(2 / 3, 4), "Resignation > 10 yrs — 2/3 EOSB"

	return 1.0, "Full EOSB"


def build_eosb_notes(years, monthly_basic, eosb_years_1_5, eosb_years_above_5, eosb_gross, factor, label, net_eosb):
	return (
		f"Years of service: {years:.2f} years\n"
		f"Basic salary: {monthly_basic:,.2f}\n"
		f"EOSB years 1-5: {eosb_years_1_5:,.2f}\n"
		f"EOSB years >5: {eosb_years_above_5:,.2f}\n"
		f"Total EOSB: {eosb_gross:,.2f}\n"
		f"Resignation factor: {factor} ({label})\n"
		f"Net EOSB: {net_eosb:,.2f}"
	)


def calculate_eosb_components(joining_date, termination_date, last_basic_salary, termination_reason, eosb_deductions=0) -> dict:
	joining = getdate(joining_date)
	termination = getdate(termination_date)
	if termination <= joining:
		frappe.throw(
			_(
				"Termination date must be after the joining date.<br>"
				"End of service date must be after the joining date."
			),
			title=_("Invalid Date"),
		)

	monthly_basic = flt(last_basic_salary)
	if monthly_basic <= 0:
		frappe.throw(
			_("Last basic salary must be greater than zero."),
			title=_("Missing Basic Salary"),
		)

	deductions = flt(eosb_deductions)
	if deductions < 0:
		frappe.throw(
			_("EOSB deductions cannot be negative."),
			title=_("Invalid Deduction"),
		)

	total_days = date_diff(termination, joining)
	years = total_days / 365.0
	if years < 1:
		eosb_years_1_5 = 0.0
		eosb_years_above_5 = 0.0
	elif years <= 5:
		eosb_years_1_5 = round((monthly_basic / 2) * years, 2)
		eosb_years_above_5 = 0.0
	else:
		eosb_years_1_5 = round((monthly_basic / 2) * 5, 2)
		eosb_years_above_5 = round(monthly_basic * (years - 5), 2)

	eosb_gross = round(eosb_years_1_5 + eosb_years_above_5, 2)
	factor, label = get_eosb_factor_and_label(termination_reason, years)
	net_eosb = round(eosb_gross * factor - deductions, 2)
	if net_eosb < 0:
		frappe.throw(
			_("EOSB deductions exceed the payable amount."),
			title=_("Invalid Deduction"),
		)

	return {
		"years_of_service": round(years, 2),
		"monthly_basic": monthly_basic,
		"eosb_years_1_5": eosb_years_1_5,
		"eosb_years_above_5": eosb_years_above_5,
		"eosb_gross": eosb_gross,
		"resignation_factor": factor,
		"resignation_factor_label": label,
		"net_eosb": net_eosb,
		"calculation_notes": build_eosb_notes(
			years,
			monthly_basic,
			eosb_years_1_5,
			eosb_years_above_5,
			eosb_gross,
			factor,
			label,
			net_eosb,
		),
	}


def get_gosi_rates(nationality: str = "", employee: str = "") -> dict:
	"""
	Return GOSI contribution rates.
	Pass employee name for the most accurate result (uses hr_suite_is_saudi checkbox first).
	Passing nationality string alone still works as a fallback.
	"""
	settings = frappe.get_single("Hr Suite Settings")

	is_saudi = (
		get_employee_is_saudi(employee)
		if employee
		else is_saudi_nationality(nationality)
	)

	if is_saudi:
		return {
			"employee_rate": flt(settings.gosi_saudi_employee_rate) or 10.0,
			"employer_rate": flt(settings.gosi_saudi_employer_rate) or 12.0,
		}
	return {
		"employee_rate": flt(settings.gosi_non_saudi_employee_rate) or 0.0,
		"employer_rate": flt(settings.gosi_non_saudi_employer_rate) or 2.0,
	}


def is_saudi_nationality(nationality: str) -> bool:
	text = (nationality or "").strip().lower()
	if not text:
		return False
	return text in ("sa", "saudi", "saudi national", "saudi arabia") or "saudi" in text


def get_employee_is_saudi(employee: str) -> bool:
	"""
	Determine if an employee is a Saudi national.
	Resolution order:
	  1. hr_suite_employee_type Select field on Employee ("Saudi National" / "Expatriate")
	  2. nationality text field on Employee (ERPNext standard field)
	  3. nationality on the active Saudi Employment Contract
	"""
	if not employee:
		return False

	# 1. Explicit Employee Type field — highest priority
	if frappe.db.has_column("Employee", "hr_suite_employee_type"):
		emp_type = frappe.db.get_value("Employee", employee, "hr_suite_employee_type") or ""
		if emp_type == "Saudi National":
			return True
		if emp_type == "Expatriate":
			return False

	# 2. Nationality text field on Employee
	nationality = ""
	if frappe.get_meta("Employee").has_field("nationality"):
		nationality = frappe.db.get_value("Employee", employee, "nationality") or ""

	# 3. Fallback: contract nationality
	if not nationality:
		nationality = get_contract_nationality_lookup([employee]).get(employee) or ""

	return is_saudi_nationality(nationality)


def get_employee_nationality(employee: str) -> str:
	"""Return the employee's nationality string. Use get_employee_is_saudi() for GOSI logic."""
	if not employee:
		return ""

	if frappe.get_meta("Employee").has_field("nationality"):
		nat = frappe.db.get_value("Employee", employee, "nationality") or ""
		if nat:
			return nat

	return get_contract_nationality_lookup([employee]).get(employee) or ""


def get_contract_nationality_lookup(employees: list[str]) -> dict[str, str]:
	if not employees:
		return {}

	lookup = {}
	for row in frappe.get_all(
		"Saudi Employment Contract",
		filters={"employee": ["in", employees], "docstatus": ["<", 2]},
		fields=["employee", "nationality"],
		order_by="start_date desc, modified desc",
		limit_page_length=0,
	):
		if row.get("nationality") and row.employee not in lookup:
			lookup[row.employee] = row.nationality
	return lookup


def get_sick_leave_pay(employee: str, sick_days_this_year: int) -> dict:
	"""
	Calculate sick leave pay per Article 117:
	  Days 1-30   -> 100%
	  Days 31-90  -> 75%
	  Days 91-120 -> 0%
	"""
	settings = frappe.get_single("Hr Suite Settings")
	full_days = int(settings.sick_leave_full_pay_days or 30)
	partial_days = int(settings.sick_leave_partial_pay_days or 60)
	partial_pct = flt(settings.sick_leave_partial_pay_percentage or 75) / 100

	used = sick_days_this_year
	if used <= full_days:
		return {"rate": 1.0, "label": "Full Pay"}
	elif used <= full_days + partial_days:
		return {"rate": partial_pct, "label": f"Partial Pay {partial_pct*100:.0f}%"}
	else:
		return {"rate": 0.0, "label": "No Pay"}
