"""
utils.py — Helper functions for Hr Suite calculations.
"""
import frappe
from frappe import _
from frappe.utils import cint, cstr, date_diff, flt, getdate


def assert_doctype_permissions(doctype: str, permission_types, doc=None):
	if isinstance(permission_types, str):
		permission_types = (permission_types,)

	for permission_type in permission_types:
		frappe.has_permission(doctype, permission_type, doc=doc, throw=True)


def assert_employee_access(employee: str = None, ptype: str = "read"):
	"""Guard whitelisted endpoints that expose one employee's data.

	Every mobile/self-service endpoint takes the employee as an argument, so without this a
	self-service user could read any colleague's salary, permit or leave data by changing it.

	Some government-portal endpoints accept a permit number with no employee attached (a
	pre-hire lookup); those are restricted to HR instead, because they still spend a request
	against the client's portal quota.
	"""
	if employee:
		frappe.has_permission("Employee", ptype, doc=employee, throw=True)
		return

	frappe.only_for(("HR User", "HR Manager", "System Manager"))


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
		"Country Employment Contract",
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
		"Annual Leave",
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
	Return annual leave days for the employee based on their work country's Country Config.
	Falls back to Hr Suite Settings for SA or when no Country Config is found.
	"""
	emp = frappe.get_doc("Employee", employee)
	joining_date = getdate(emp.date_of_joining)
	ref_date = getdate(date) if date else getdate()
	years = date_diff(ref_date, joining_date) / 365.0

	# Load settings once — used both in Country Config path and fallback
	settings = frappe.get_single("Hr Suite Settings")
	threshold = flt(settings.annual_leave_years_threshold) or 5

	country = get_employee_work_country(employee)
	cfg = get_country_config(country)
	if cfg and cfg.leave_types:
		# Collect day values from every "annual leave" row — Country Config may express
		# the below/above-threshold tiers either as two fields on one row, or as two
		# separate rows (e.g. "Annual Leave" and "Annual Leave (5+ Years)"). Either way,
		# the lower value is the below-threshold entitlement and the higher value is the
		# above-threshold one — this avoids relying on which row happens to be listed first.
		day_values = []
		for lt in cfg.leave_types:
			lt_name = (lt.leave_type_name or "").lower()
			if "annual" not in lt_name:
				continue
			# Use explicit None-checks so a configured 0 isn't treated as "missing"
			for raw in (lt.get("days_below_threshold"), lt.get("days_per_year"), lt.get("days_above_threshold")):
				if raw is not None:
					day_values.append(flt(raw))

		day_values = [d for d in day_values if d > 0]
		if day_values:
			days_below = min(day_values)
			days_above = max(day_values)
			return int(days_above) if years >= threshold else int(days_below)

	# Fallback: SA defaults from Hr Suite Settings
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
		return 1.0, "Resignation ≥ 2 yrs — Full EOSB"

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
		eosb_years_1_5 = round((monthly_basic * 2 / 3) * years, 2)
		eosb_years_above_5 = 0.0
	else:
		eosb_years_1_5 = round((monthly_basic * 2 / 3) * 5, 2)
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
	  3. nationality on the active Country Employment Contract
	"""
	if not employee:
		return False

	# 1. Explicit Employee Type field — highest priority
	if frappe.db.has_column("Employee", "hr_suite_employee_type"):
		emp_type = frappe.db.get_value("Employee", employee, "hr_suite_employee_type") or ""
		if emp_type in ("Saudi National", "National"):
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


_NATIONALITY_KEYWORDS = {
	"SA": ["saudi"],
	"AE": ["emirati", "emirian", "united arab"],
	"BH": ["bahraini"],
	"OM": ["omani"],
	"KW": ["kuwaiti"],
	"QA": ["qatari"],
}


def get_employees_is_national_map(employees: list[str], country_code: str) -> dict:
	"""Batched national/expat classification. Tri-state.

	Returns {employee: True | False | None} where **None means "not classified"** — the
	employee has neither an Employee Type nor a nationality anywhere, so no honest answer
	exists. Callers that must produce a boolean (statutory rate lookups) collapse None to
	False via get_employee_is_national(); callers that report a position to a human
	(the LMRA register) show the unclassified count instead of guessing.

	Three queries regardless of headcount, so it is safe inside a report over the whole
	company. The resolution order is identical to the single-employee function it backs:
	hr_suite_employee_type → Employee.nationality → Country Employment Contract.nationality.
	"""
	if not employees or not country_code:
		return {}

	names = [cstr(e) for e in employees if e]
	if not names:
		return {}

	target = cstr(country_code).upper()
	meta = frappe.get_meta("Employee")

	fields = ["name"]
	has_type = frappe.db.has_column("Employee", "hr_suite_employee_type")
	has_nationality = meta.has_field("nationality")
	if has_type:
		fields.append("hr_suite_employee_type")
	if has_nationality:
		fields.append("nationality")

	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", names]},
		fields=fields,
		limit_page_length=0,
	)
	by_employee = {r["name"]: r for r in rows}

	# Contract nationality is only needed for the employees the master could not answer.
	needs_contract = [
		n for n in names
		if not cstr((by_employee.get(n) or {}).get("hr_suite_employee_type"))
		and not cstr((by_employee.get(n) or {}).get("nationality"))
	]
	contract_nationality = get_contract_nationality_lookup(needs_contract) if needs_contract else {}

	# country_name_to_code hits the Country table; memoise so a 500-row report does not
	# repeat the same lookup 500 times.
	code_cache: dict = {}

	def to_code(value: str) -> str:
		key = cstr(value).strip()
		if key not in code_cache:
			code_cache[key] = country_name_to_code(key)
		return code_cache[key]

	result = {}
	for name in names:
		row = by_employee.get(name) or {}

		emp_type = cstr(row.get("hr_suite_employee_type"))
		if "National" in emp_type:
			result[name] = True
			continue
		if emp_type == "Expatriate":
			result[name] = False
			continue

		nationality = cstr(row.get("nationality")) or cstr(contract_nationality.get(name))
		if not nationality:
			result[name] = None
			continue

		nat_code = to_code(nationality)
		if nat_code:
			result[name] = nat_code == target
			continue

		nat_lower = nationality.lower()
		keywords = _NATIONALITY_KEYWORDS.get(target, [])
		result[name] = any(kw in nat_lower for kw in keywords) if keywords else None

	return result


def get_employee_is_national(employee: str, country_code: str) -> bool:
	"""
	Generalised national/expat check for any GCC country.
	Returns True if the employee is a national of the given country.
	Resolution: hr_suite_employee_type → nationality field → contract nationality.

	Thin wrapper over get_employees_is_national_map so there is exactly one copy of the
	rule. An unclassifiable employee collapses to False here, which is the behaviour the
	statutory-rate callers (Country Employment Contract, integrations/hrms) already relied on.
	"""
	if not employee or not country_code:
		return False
	return bool(get_employees_is_national_map([employee], country_code).get(employee))


def get_employee_nationality(employee: str) -> str:
	"""Return the employee's nationality string. Use get_employee_is_national() for statutory logic."""
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
		"Country Employment Contract",
		filters={"employee": ["in", employees], "docstatus": ["<", 2]},
		fields=["employee", "nationality"],
		order_by="start_date desc, modified desc",
		limit_page_length=0,
	):
		if row.get("nationality") and row.employee not in lookup:
			lookup[row.employee] = row.nationality
	return lookup


# ─── Global Country Helpers ────────────────────────────────────────────────────

_COUNTRY_NAME_TO_CODE = {
    # Saudi Arabia
    "saudi arabia": "SA", "ksa": "SA",
    # United Arab Emirates
    "united arab emirates": "AE", "uae": "AE",
    # Bahrain
    "bahrain": "BH",
    # India
    "india": "IN",
    # Oman
    "oman": "OM",
}


def country_name_to_code(country_name: str) -> str:
    """Convert a Frappe country name (e.g. 'Saudi Arabia') to an ISO-2 code.

    Primary lookup: Country.code field in Frappe's Country DocType.
    Fallback: static map for offline/test environments.
    """
    if not country_name:
        return ""
    key = country_name.strip()
    # Direct ISO-2 pass-through
    if len(key) == 2 and key.upper() in ("SA", "AE", "BH", "IN", "OM", "QA", "KW", "JO", "EG", "GB", "US"):
        return key.upper()
    # Use Frappe's Country DocType code field — works for any country, not just our 5
    try:
        code = frappe.db.get_value("Country", key, "code") or ""
        if code:
            return code.upper()
    except Exception:
        pass
    # Fallback to static map
    return _COUNTRY_NAME_TO_CODE.get(key.lower(), "")


def get_employee_work_country(employee: str) -> str:
    """
    Return the ISO-2 work country code for an employee.

    Resolution order:
    1. Active Country Employment Contract.work_country
    2. Employee.work_country (hr_suite Custom Field, install.EMPLOYEE_MASTER_FIELDS)
    3. Employee's Company.country → mapped to ISO-2 code
    4. Hr Suite Settings.default_work_country (global fallback)

    Step 2 is what makes multi-country payroll resolvable per EMPLOYEE. Without it the
    only per-person answer came from a submitted Country Employment Contract, and an
    employee master uploaded without contracts could only ever inherit its Company's
    country — so two countries inside one company were indistinguishable.
    """
    if not employee:
        return ""

    # 1. Active Country Employment Contract — a submitted, dated legal document, so it
    #    outranks the master field below.
    row = frappe.db.get_value(
        "Country Employment Contract",
        {"employee": employee, "contract_status": "Active"},
        "work_country",
        order_by="start_date desc",
    )
    if row:
        return row.strip().upper()

    # The Employee field is a Custom Field, so a bench part-way through install/migrate
    # can legitimately not have it yet. Read both values in one query either way.
    employee_fields = ["company"]
    has_work_country = frappe.db.has_column("Employee", "work_country")
    if has_work_country:
        employee_fields.append("work_country")

    employee_row = frappe.db.get_value("Employee", employee, employee_fields, as_dict=True) or frappe._dict()

    # 2. The Employee's own Work Country. Run through country_name_to_code so a record
    #    holding "Bahrain" resolves the same as one holding "BH".
    if has_work_country:
        code = country_name_to_code(cstr(employee_row.get("work_country")).strip())
        if code:
            return code

    # 3. Derive from Employee's Company country (Frappe standard field)
    company = employee_row.get("company") or ""
    if company:
        company_country = frappe.db.get_value("Company", company, "country") or ""
        code = country_name_to_code(company_country)
        if code:
            return code

    # 4. Global default in Hr Suite Settings (stored as a Country Link — resolve to ISO-2)
    default = frappe.db.get_single_value("Hr Suite Settings", "default_work_country") or ""
    return country_name_to_code(default)


def get_country_config(country_code: str):
    """Return the Country Config document for a given ISO-2 code, or None."""
    if not country_code:
        return None
    from hr_suite.hr_suite.doctype.country_config.country_config import CountryConfig
    return CountryConfig.get_for(country_code)


def get_active_country_contract(employee: str, fields=None, as_dict=True):
    """Return the active Country Employment Contract for an employee."""
    field_list = fields or [
        "name", "basic_salary", "housing_allowance", "transport_allowance",
        "other_allowances", "total_salary", "work_country", "currency",
    ]
    # Try Country Employment Contract first
    row = frappe.db.get_value(
        "Country Employment Contract",
        {"employee": employee, "contract_status": "Active"},
        field_list,
        as_dict=as_dict,
        order_by="start_date desc",
    )
    return row


def get_employee_basic_salary_global(employee: str) -> float:
    """Return basic salary from Country Employment Contract, then Saudi contract, then CTC."""
    contract = get_active_country_contract(employee, ["basic_salary"], as_dict=True) or {}
    basic = flt(contract.get("basic_salary"))
    if basic:
        return basic
    return flt(frappe.db.get_value("Employee", employee, "ctc") or 0)


# ─── Multi-Country Settlement ─────────────────────────────────────────────────

def calculate_settlement(
    employee: str,
    termination_reason: str,
    termination_date: str = None,
    eosb_deductions: float = 0,
) -> dict:
    """
    Dispatch to the correct settlement formula based on the employee's work_country.
    Returns a unified dict with keys: formula, years_of_service, basic_salary,
    gross_entitlement, factor, factor_label, net_entitlement, notes.
    """
    country = get_employee_work_country(employee)
    emp = frappe.get_doc("Employee", employee)
    joining = emp.date_of_joining
    term_date = getdate(termination_date) if termination_date else getdate()
    basic = get_employee_basic_salary_global(employee)
    years = date_diff(term_date, getdate(joining)) / 365.0

    if country == "AE":
        return _calculate_uae_gratuity(employee, years, basic, termination_reason, eosb_deductions)
    if country == "IN":
        return _calculate_india_gratuity(years, basic, termination_reason, eosb_deductions)
    if country == "BH":
        return _calculate_bh_indemnity(years, basic, termination_reason, eosb_deductions)
    if country == "OM":
        return _calculate_om_indemnity(years, basic, termination_reason, eosb_deductions)
    # Default: SA EOSB
    result = calculate_eosb_components(joining, term_date, basic, termination_reason, eosb_deductions)
    result["formula"] = "EOSB-SA"
    result["gross_entitlement"] = result.get("eosb_gross", 0)
    result["net_entitlement"] = result.get("net_eosb", 0)
    result["factor_label"] = result.get("resignation_factor_label", "")
    return result


def _calculate_uae_gratuity(employee: str, years: float, basic: float, reason: str, deductions: float) -> dict:
    """
    UAE Gratuity per Article 51 / 132 of UAE Labour Law 2021.
    - Years 1–5 : 21 calendar days basic per year
    - Years 5+  : 30 calendar days basic per year
    - Capped at 2 years' total wage
    - Resignation < 1yr: no gratuity. 1–3yrs: 1/3. 3–5yrs: 2/3. 5+yrs: full.
    """
    daily = basic / 30.0
    if years < 1:
        gross = 0.0
    elif years <= 5:
        gross = round(21 * daily * years, 2)
    else:
        gross_1_5 = round(21 * daily * 5, 2)
        gross_above = round(30 * daily * (years - 5), 2)
        gross = round(gross_1_5 + gross_above, 2)

    # 2-year salary cap
    annual_salary = basic * 12
    cap = round(annual_salary * 2, 2)
    if gross > cap:
        gross = cap

    # Resignation scaling
    is_resignation = text_matches_tokens(reason, "resignation")
    if is_resignation:
        if years < 1:
            factor, label = 0.0, "Resignation < 1yr — No Gratuity"
        elif years < 3:
            factor, label = 1/3, "Resignation 1–3yrs — 1/3 Gratuity"
        elif years < 5:
            factor, label = 2/3, "Resignation 3–5yrs — 2/3 Gratuity"
        else:
            factor, label = 1.0, "Resignation 5+yrs — Full Gratuity"
    else:
        factor, label = 1.0, "Full Gratuity"

    net = round(max(0, gross * factor - flt(deductions)), 2)
    return {
        "formula": "Gratuity-AE",
        "years_of_service": round(years, 2),
        "basic_salary": basic,
        "gross_entitlement": gross,
        "factor": factor,
        "factor_label": label,
        "net_entitlement": net,
        "notes": (
            f"UAE Gratuity\nYears: {years:.2f}\nBasic: {basic:,.2f} AED/month\n"
            f"Daily rate: {daily:.2f}\nGross: {gross:,.2f}\n2yr cap: {cap:,.2f}\n"
            f"Factor: {factor} ({label})\nNet: {net:,.2f}"
        ),
    }


def _calculate_india_gratuity(years: float, basic: float, reason: str, deductions: float) -> dict:
    """
    Payment of Gratuity Act 1972.
    Eligible after 5 years continuous service.
    Formula: (15/26) × last basic × completed years.
    Statutory ceiling: ₹20,00,000.
    """
    CEILING = 2000000.0
    completed = int(years)  # only complete years count (fraction ≥ 6 months rounds up)
    if years - completed >= 0.5:
        completed += 1

    if completed < 5:
        gross = 0.0
        label = "Not Eligible — < 5 years service"
    else:
        gross = min(round((15 / 26) * basic * completed, 2), CEILING)
        label = f"Eligible — {completed} completed years"

    is_dismissal = text_matches_tokens(reason, "dismissal", "misconduct")
    factor = 0.0 if is_dismissal and completed < 5 else 1.0
    label = "Forfeited — Termination for Cause" if is_dismissal and gross else label

    net = round(max(0, gross * factor - flt(deductions)), 2)
    return {
        "formula": "Gratuity-IN",
        "years_of_service": round(years, 2),
        "basic_salary": basic,
        "gross_entitlement": gross,
        "factor": factor,
        "factor_label": label,
        "net_entitlement": net,
        "notes": (
            f"India Gratuity Act\nYears: {years:.2f} ({completed} completed)\n"
            f"Basic: ₹{basic:,.2f}/month\nGross: ₹{gross:,.2f}\n"
            f"Ceiling: ₹20,00,000\n{label}\nNet: ₹{net:,.2f}"
        ),
    }


def _calculate_bh_indemnity(years: float, basic: float, reason: str, deductions: float) -> dict:
    """
    Bahrain Labour Law — Article 116–117.
    First 3 years: ½ month per year.
    After 3 years: 1 month per year.
    """
    if years <= 0:
        gross = 0.0
    elif years <= 3:
        gross = round((basic / 2) * years, 2)
    else:
        gross = round((basic / 2) * 3 + basic * (years - 3), 2)

    is_resignation = text_matches_tokens(reason, "resignation")
    if is_resignation and years < 1:
        factor, label = 0.0, "Resignation < 1yr — No Indemnity"
    elif is_resignation:
        factor, label = 0.5, "Resignation — 50% Indemnity"
    else:
        factor, label = 1.0, "Full Indemnity"

    net = round(max(0, gross * factor - flt(deductions)), 2)
    return {
        "formula": "Indemnity-BH",
        "years_of_service": round(years, 2),
        "basic_salary": basic,
        "gross_entitlement": gross,
        "factor": factor,
        "factor_label": label,
        "net_entitlement": net,
        "notes": (
            f"Bahrain Indemnity (Art. 116–117)\nYears: {years:.2f}\nBasic: {basic:,.2f} BHD/month\n"
            f"Gross: {gross:,.2f}\n{label}\nNet: {net:,.2f}"
        ),
    }


def _calculate_om_indemnity(years: float, basic: float, reason: str, deductions: float) -> dict:
    """
    Oman Labour Law — Article 39–40.
    First 3 years: 15 days basic per year.
    After 3 years: 1 month basic per year.
    Expatriates only — Omani nationals covered by PASI.
    """
    daily = basic / 30.0
    if years <= 0:
        gross = 0.0
    elif years <= 3:
        gross = round(15 * daily * years, 2)
    else:
        gross_1_3 = round(15 * daily * 3, 2)
        gross_above = round(basic * (years - 3), 2)
        gross = round(gross_1_3 + gross_above, 2)

    is_resignation = text_matches_tokens(reason, "resignation")
    factor, label = (0.5, "Resignation — 50% Indemnity") if is_resignation else (1.0, "Full Indemnity")
    if is_resignation and years < 1:
        factor, label = 0.0, "Resignation < 1yr — No Indemnity"

    net = round(max(0, gross * factor - flt(deductions)), 2)
    return {
        "formula": "Indemnity-OM",
        "years_of_service": round(years, 2),
        "basic_salary": basic,
        "gross_entitlement": gross,
        "factor": factor,
        "factor_label": label,
        "net_entitlement": net,
        "notes": (
            f"Oman Indemnity (Art. 39–40)\nYears: {years:.2f}\nBasic: {basic:,.2f} OMR/month\n"
            f"Gross: {gross:,.2f}\n{label}\nNet: {net:,.2f}"
        ),
    }


def get_settlement_estimate(employee: str, termination_reason: str, termination_date: str = None) -> dict:
    """Return the settlement estimate for any country. Exposed via api.get_settlement_estimate."""
    return calculate_settlement(employee, termination_reason, termination_date)


def seed_country_leave_types(employee: str):
    """Create Leave Allocations in Frappe HRMS from the employee's Country Config."""
    country = get_employee_work_country(employee)
    cfg = get_country_config(country)
    if not cfg or not cfg.leave_types:
        return

    emp_doc = frappe.get_doc("Employee", employee)
    year = getdate().year

    for row in cfg.leave_types:
        lt_name = row.frappe_leave_type_name or row.leave_type_name
        if not frappe.db.exists("Leave Type", lt_name):
            frappe.get_doc({
                "doctype": "Leave Type",
                "leave_type_name": lt_name,
                "max_continuous_days_allowed": 0,
                "is_optional_leave": row.is_optional,
                "allow_negative": 0,
            }).insert(ignore_permissions=True)

        if frappe.db.exists("Leave Allocation", {
            "employee": employee,
            "leave_type": lt_name,
            "docstatus": ["<", 2],
            "from_date": [">=", f"{year}-01-01"],
        }):
            continue

        if row.gender_specific == "Male Only" and emp_doc.gender != "Male":
            continue
        if row.gender_specific == "Female Only" and emp_doc.gender != "Female":
            continue

        alloc = frappe.get_doc({
            "doctype": "Leave Allocation",
            "employee": employee,
            "employee_name": emp_doc.employee_name,
            "leave_type": lt_name,
            "from_date": f"{year}-01-01",
            "to_date": f"{year}-12-31",
            "new_leaves_allocated": row.days_per_year or 0,
            "carry_forward": 1 if row.max_carry_forward_days else 0,
        })
        try:
            alloc.insert(ignore_permissions=True)
            alloc.submit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"HR Suite: Leave allocation failed for {employee} / {lt_name}")


def get_sick_leave_pay(employee: str, sick_days_this_year: int) -> dict:
	"""Sick-leave pay treatment for a day of sick leave, from the employee's own country.

	STATUTORY DISCIPLINE — why this no longer bands by default
	----------------------------------------------------------
	This used to read three fields off ``Country Leave Type Row`` — ``full_pay_days`` /
	``partial_pay_days`` / ``partial_pay_percentage`` — that have never existed on that
	DocType. ``lt.get()`` therefore returned None every time and every country silently
	fell through to the literals 30 / 60 / 75%, which are a Saudi Article-117 shape. On
	the Bahrain site that produced a live contradiction: a 35-day Sick Leave Application
	told HR "this leave will be at Partial Pay 75% per Bahrain labor law", while the
	Salary Slip paid 100% of all 55 days — Bahrain's Country Config declares ONE 55-day
	row at Full Pay, so ``Leave Type.is_ppl`` is 0 and no day is docked.

	The declared mechanism for a tiered entitlement is ``Country Leave Type Row``
	``pay_treatment`` + ``paid_fraction`` (see ``leave_setup._pay_treatment_fields``),
	and that is what actually reaches ``Salary Slip``. This function reads THAT, so the
	warning HR sees and the money the payslip pays come from one declaration.

	Returns ``{"rate", "label", "is_declared", "declared_days", "country"}``:
	  * ``rate``          fraction of a normal day's pay, from the declared treatment
	  * ``is_declared``   False when the country's config says nothing about the band
	                      that applies at this day count. A caller MUST NOT present the
	                      rate as that country's statutory position when this is False.
	  * ``declared_days`` total sick days the country's config actually declares
	The global Hr Suite Settings band is used only for a country with NO Country Config
	sick row at all, and even then it is reported as not declared for that country.
	"""
	country = get_employee_work_country(employee)
	cfg = get_country_config(country)
	used = flt(sick_days_this_year)

	rows = []
	if cfg and cfg.leave_types:
		rows = [lt for lt in cfg.leave_types if "sick" in cstr(lt.leave_type_name).lower()]

	if rows:
		# Walk the declared bands in config order; each row's days_per_year is the width
		# of its own band. A client who declares 15 Full Pay + 20 Partially Paid 0.5 +
		# 20 Unpaid gets exactly that; a client who declares one 55-day Full Pay row gets
		# 55 days at full pay, which is Bahrain's configured position today.
		consumed = 0.0
		for lt in rows:
			width = flt(lt.get("days_per_year"))
			if width <= 0:
				continue
			consumed += width
			if used <= consumed:
				return _declared_sick_pay(lt, country, consumed)

		# Past everything the config declares. No declared treatment covers these days,
		# so say so instead of assuming a reduced or nil rate.
		return {
			"rate": 1.0,
			"label": _("Not declared beyond {0} days").format(cint(consumed)),
			"is_declared": False,
			"declared_days": consumed,
			"country": country,
		}

	# No Country Config sick row for this country: fall back to the site-wide Hr Suite
	# Settings band, still flagged as not declared FOR THIS COUNTRY because it is a
	# global default rather than this jurisdiction's confirmed position.
	settings = frappe.get_single("Hr Suite Settings")
	full_days = cint(settings.sick_leave_full_pay_days)
	partial_days = cint(settings.sick_leave_partial_pay_days)
	partial_pct = flt(settings.sick_leave_partial_pay_percentage) / 100
	base = {"is_declared": False, "declared_days": 0.0, "country": country}

	if not full_days or used <= full_days:
		# Nothing configured anywhere, or still inside the configured full-pay band.
		return dict(base, rate=1.0, label=_("Full Pay"))
	if used <= full_days + partial_days:
		return dict(base, rate=partial_pct, label=_("Partial Pay {0}%").format(round(partial_pct * 100)))
	return dict(base, rate=0.0, label=_("No Pay"))


def _declared_sick_pay(row, country: str, declared_days: float) -> dict:
	"""One declared sick-leave band, expressed as a pay rate."""
	treatment = cstr(row.get("pay_treatment") or "Full Pay")
	base = {"is_declared": True, "declared_days": declared_days, "country": country}

	if treatment == "Unpaid":
		return dict(base, rate=0.0, label=_("Unpaid"))

	if treatment == "Partially Paid":
		fraction = flt(row.get("paid_fraction"))
		if 0 < fraction < 1:
			return dict(base, rate=fraction, label=_("Partial Pay {0}%").format(round(fraction * 100)))
		# "Partially Paid" with no usable fraction declares nothing usable.
		return dict(base, rate=1.0, label=_("Paid fraction not set"), is_declared=False)

	return dict(base, rate=1.0, label=_("Full Pay"))


# ─── Work permit / country labelling (client ticket 3.1 — Bahrain LMRA) ────────
#
# Every entitlement, rate and window below is READ from Country Config. Nothing in this
# block hardcodes a statutory number; where the config is silent the helper returns an
# unset value and the caller is expected to say so rather than substitute a default.

def get_employee_work_country_map(employees: list[str]) -> dict:
	"""Batched get_employee_work_country().

	Same resolution order and therefore the same answer as the single-employee function:
	  1. Active Country Employment Contract.work_country
	  2. Employee.work_country
	  3. Employee's Company.country
	  4. Hr Suite Settings.default_work_country
	Four queries regardless of headcount, so a company-wide report does not issue one
	query per employee.
	"""
	if not employees:
		return {}

	names = [cstr(e) for e in employees if e]
	if not names:
		return {}

	code_cache: dict = {}

	def to_code(value: str) -> str:
		key = cstr(value).strip()
		if key not in code_cache:
			code_cache[key] = country_name_to_code(key)
		return code_cache[key]

	# 1. Active contracts (a submitted, dated legal document outranks the master field)
	contract_country = {}
	for row in frappe.get_all(
		"Country Employment Contract",
		filters={"employee": ["in", names], "contract_status": "Active"},
		fields=["employee", "work_country", "start_date"],
		order_by="start_date desc",
		limit_page_length=0,
	):
		if row.get("work_country") and row.employee not in contract_country:
			contract_country[row.employee] = cstr(row.work_country).strip().upper()

	# 2/3. Employee master + its company
	employee_fields = ["name", "company"]
	has_work_country = frappe.db.has_column("Employee", "work_country")
	if has_work_country:
		employee_fields.append("work_country")

	employee_rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", names]},
		fields=employee_fields,
		limit_page_length=0,
	)
	by_employee = {r["name"]: r for r in employee_rows}

	companies = {cstr(r.get("company")) for r in employee_rows if r.get("company")}
	company_country = {}
	if companies:
		for row in frappe.get_all(
			"Company",
			filters={"name": ["in", list(companies)]},
			fields=["name", "country"],
			limit_page_length=0,
		):
			company_country[row["name"]] = to_code(row.get("country") or "")

	# 4. Global default
	default_code = to_code(
		frappe.db.get_single_value("Hr Suite Settings", "default_work_country") or ""
	)

	resolved = {}
	for name in names:
		if contract_country.get(name):
			resolved[name] = contract_country[name]
			continue

		row = by_employee.get(name) or {}
		if has_work_country:
			code = to_code(cstr(row.get("work_country")))
			if code:
				resolved[name] = code
				continue

		code = company_country.get(cstr(row.get("company")), "")
		resolved[name] = code or default_code

	return resolved


# Wording used only when the client has configured no Country Config row at all for the
# country. They are generic English nouns, not a statutory position.
_FALLBACK_PERMIT_LABEL = "Work Permit"
_FALLBACK_NATIONAL_ID_LABEL = "National ID"
_FALLBACK_ALERT_DAYS = 90


def get_permit_labels(country_code: str) -> dict:
	"""Permit / national-ID wording and expiry window for a country.

	`primary_permit_label` and `national_id_label` are Country Config fields the client
	owns ("CPR / Work Permit" and "CPR Number" for Bahrain, "Iqama" for Saudi Arabia), so
	the UI and the reports say what the client's own configuration says.
	"""
	config = get_country_config(cstr(country_code).strip().upper())
	if not config:
		return {
			"country_code": cstr(country_code).strip().upper(),
			"country_name": "",
			"currency": "",
			"permit_label": _FALLBACK_PERMIT_LABEL,
			"national_id_label": _FALLBACK_NATIONAL_ID_LABEL,
			"alert_days": _FALLBACK_ALERT_DAYS,
			"configured": False,
		}

	return {
		"country_code": cstr(config.country_code).upper(),
		"country_name": cstr(config.country_name),
		"currency": cstr(config.currency),
		"permit_label": cstr(config.primary_permit_label) or _FALLBACK_PERMIT_LABEL,
		"national_id_label": cstr(config.national_id_label) or _FALLBACK_NATIONAL_ID_LABEL,
		"alert_days": cint(config.permit_expiry_alert_days) or _FALLBACK_ALERT_DAYS,
		"configured": True,
	}


def get_recurring_permit_fee_config(country_code: str) -> dict:
	"""Recurring per-worker government permit fee for a country (Bahrain: LMRA).

	The AMOUNT and the APPLICABILITY are client configuration, not knowledge encoded
	here. Both default to unset:
	  * `monthly_fee` 0        — no fee is charged until the client enters the rate
	  * `applies_to` ""        — nobody is in scope until the client says who is
	`is_configured` is False unless BOTH are set, and every caller must show
	"not configured" rather than a number when it is False.
	"""
	config = get_country_config(cstr(country_code).strip().upper())
	if not config:
		return {
			"authority": "",
			"monthly_fee": 0.0,
			"applies_to": "",
			"currency": "",
			"notes": "",
			"is_configured": False,
		}

	monthly_fee = flt(config.get("monthly_permit_fee_per_worker"))
	applies_to = cstr(config.get("recurring_permit_fee_applies_to"))
	return {
		"authority": cstr(config.get("recurring_permit_fee_authority")),
		"monthly_fee": monthly_fee,
		"applies_to": applies_to,
		"currency": cstr(config.currency),
		"notes": cstr(config.get("recurring_permit_fee_notes")),
		"is_configured": bool(monthly_fee > 0 and applies_to),
	}
