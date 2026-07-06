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
	  3. nationality on the active Saudi Employment Contract
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


def get_employee_is_national(employee: str, country_code: str) -> bool:
	"""
	Generalised national/expat check for any GCC country.
	Returns True if the employee is a national of the given country.
	Resolution: hr_suite_employee_type → nationality field → contract nationality.
	"""
	if not employee or not country_code:
		return False

	# Explicit Employee Type field — covers all countries via "National" / "Expatriate"
	if frappe.db.has_column("Employee", "hr_suite_employee_type"):
		emp_type = frappe.db.get_value("Employee", employee, "hr_suite_employee_type") or ""
		if "National" in emp_type:
			return True
		if emp_type == "Expatriate":
			return False

	# Nationality text field
	nationality = ""
	if frappe.get_meta("Employee").has_field("nationality"):
		nationality = frappe.db.get_value("Employee", employee, "nationality") or ""
	if not nationality:
		nationality = get_contract_nationality_lookup([employee]).get(employee) or ""

	nat_code = country_name_to_code(nationality)
	if nat_code:
		return nat_code == country_code.upper()

	# Fallback: keyword match per country
	nat_lower = nationality.lower()
	keywords = {
		"SA": ["saudi"],
		"AE": ["emirati", "emirian", "united arab"],
		"BH": ["bahraini"],
		"OM": ["omani"],
		"KW": ["kuwaiti"],
		"QA": ["qatari"],
	}
	return any(kw in nat_lower for kw in keywords.get(country_code.upper(), []))


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
		"Saudi Employment Contract",
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


@frappe.whitelist()
def get_employee_work_country(employee: str) -> str:
    """
    Return the ISO-2 work country code for an employee.

    Resolution order:
    1. Active Country Employment Contract.work_country
    2. Employee's Company.country → mapped to ISO-2 code
    3. Hr Suite Settings.default_work_country (global fallback)
    """
    if not employee:
        return ""

    # 1. Active Country Employment Contract
    row = frappe.db.get_value(
        "Country Employment Contract",
        {"employee": employee, "contract_status": "Active"},
        "work_country",
        order_by="start_date desc",
    )
    if row:
        return row.strip().upper()

    # 2. Derive from Employee's Company country (Frappe standard field)
    company = frappe.db.get_value("Employee", employee, "company") or ""
    if company:
        company_country = frappe.db.get_value("Company", company, "country") or ""
        code = country_name_to_code(company_country)
        if code:
            return code

    # 3. Global default in Hr Suite Settings
    default = frappe.db.get_single_value("Hr Suite Settings", "default_work_country") or ""
    return default.strip().upper()


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
    if row:
        return row
    # Fall back to Saudi Employment Contract for backward compatibility
    return get_active_contract(employee, fields=fields, as_dict=as_dict)


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


@frappe.whitelist()
def get_settlement_estimate(employee: str, termination_reason: str, termination_date: str = None) -> dict:
    """Whitelisted: return settlement estimate for any country — called from front-end."""
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
	"""
	Calculate sick leave pay per country labor law:
	- SA/GCC: Days 1-30 full, 31-90 partial (75%), 91+ no pay (configurable via Settings)
	- IN: As per Factories Act / ESI — 91+ days ESI-funded sick leave
	- Others: Reads Country Config sick leave type if defined, else SA defaults
	"""
	country = get_employee_work_country(employee)
	cfg = get_country_config(country)

	# Try to read sick leave rules from Country Config leave_types
	if cfg and cfg.leave_types:
		for lt in cfg.leave_types:
			lt_name = (lt.leave_type_name or "").lower()
			if "sick" in lt_name:
				# Use explicit None-checks so configured 0 isn't overridden by the SA default
				fd_raw = lt.get("full_pay_days")
				pd_raw = lt.get("partial_pay_days")
				pp_raw = lt.get("partial_pay_percentage")
				full_days = int(fd_raw) if fd_raw is not None else 30
				partial_days = int(pd_raw) if pd_raw is not None else 60
				partial_pct = flt(pp_raw if pp_raw is not None else 75) / 100
				used = sick_days_this_year
				if used <= full_days:
					return {"rate": 1.0, "label": "Full Pay"}
				elif used <= full_days + partial_days:
					return {"rate": partial_pct, "label": f"Partial Pay {partial_pct*100:.0f}%"}
				return {"rate": 0.0, "label": "No Pay"}

	# Fallback to Hr Suite Settings (SA defaults)
	settings = frappe.get_single("Hr Suite Settings")
	full_days = int(settings.sick_leave_full_pay_days or 30)
	partial_days = int(settings.sick_leave_partial_pay_days or 60)
	partial_pct = flt(settings.sick_leave_partial_pay_percentage or 75) / 100
	used = sick_days_this_year
	if used <= full_days:
		return {"rate": 1.0, "label": "Full Pay"}
	elif used <= full_days + partial_days:
		return {"rate": partial_pct, "label": f"Partial Pay {partial_pct*100:.0f}%"}
	return {"rate": 0.0, "label": "No Pay"}
