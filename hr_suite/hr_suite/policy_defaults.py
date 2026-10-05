"""Legal-default leave, sick-leave and gratuity policy for each GCC country.

Source: the Steel Force "Leave, Leave Salary, Gratuity & HR Payment Advice" functional
spec (Sept 2026), which carries the labour-law position of each country as of that date
(KSA amendments, Oman RD 53/2023, GCC sick pay). These are defaults, never mandates: a
Country Config row an administrator has edited is never rewritten (see apply_policy_defaults),
and the client's legal adviser must confirm them before go-live.

Tables are a list of dicts keyed by the child doctype's fieldnames. Scalars are plain
Country Config fields.
"""

import frappe
from frappe.utils import flt

MONTHS = "Months of wage per year"
DAYS = "Days of wage per year"
WEEKS = "Weeks of wage per year"

POLICY_DEFAULTS = {
	"SA": {
		"scalars": {
			"annual_leave_eligible_after_months": 0,
			"annual_leave_carry_forward_rule": "Per Company Policy",
			"sick_leave_days_per_year": 120,
			"sick_leave_eligible_after_months": 0,
			"gratuity_base": "Basic Salary",
			"nationals_pension_scheme": "GOSI",
			"leave_salary_min_earned_days": 30,
			"leave_salary_min_service_days": 365,
		},
		"annual_leave_bands": [
			{"label": "Up to 5 years", "service_from_months": 0, "leave_days_per_year": 21, "salary_days_per_year": 21},
			{"label": "After 5 years", "service_from_months": 60, "leave_days_per_year": 30, "salary_days_per_year": 30},
		],
		"sick_leave_tiers": [
			{"tier_days": 30, "pay_percent": 100},
			{"tier_days": 60, "pay_percent": 75},
			{"tier_days": 30, "pay_percent": 0},
		],
		"gratuity_slabs": [
			{"from_years": 0, "to_years": 5, "rate_unit": MONTHS, "rate_value": 0.5},
			{"from_years": 5, "to_years": 0, "rate_unit": MONTHS, "rate_value": 1},
		],
		"gratuity_resignation_factors": [
			{"from_years": 0, "to_years": 2, "payable_percent": 0},
			{"from_years": 2, "to_years": 5, "payable_percent": 33.33},
			{"from_years": 5, "to_years": 10, "payable_percent": 66.67},
			{"from_years": 10, "to_years": 0, "payable_percent": 100},
		],
		"checks": {"gratuity_nationals_also_entitled": 1, "gratuity_forfeited_on_dismissal": 1},
	},
	"BH": {
		"scalars": {
			"annual_leave_eligible_after_months": 12,
			"annual_leave_carry_forward_rule": "Settle Or Carry Within Years",
			"annual_leave_carry_forward_years": 2,
			"sick_leave_days_per_year": 55,
			"sick_leave_eligible_after_months": 3,
			"gratuity_base": "Basic Salary",
			"gratuity_scheme_end_date": "2024-03-01",
			"nationals_pension_scheme": "SIO",
			"leave_salary_min_earned_days": 30,
			"leave_salary_min_service_days": 365,
		},
		"annual_leave_bands": [
			{"label": "Standard", "service_from_months": 0, "leave_days_per_year": 30, "salary_days_per_year": 30},
		],
		"sick_leave_tiers": [
			{"tier_days": 15, "pay_percent": 100},
			{"tier_days": 20, "pay_percent": 50},
			{"tier_days": 20, "pay_percent": 0},
		],
		"gratuity_slabs": [
			{"from_years": 0, "to_years": 3, "rate_unit": MONTHS, "rate_value": 0.5},
			{"from_years": 3, "to_years": 0, "rate_unit": MONTHS, "rate_value": 1},
		],
		"gratuity_resignation_factors": [],
		"notes": {
			"gratuity_policy_notes": (
				"Service up to 28 Feb 2024 is paid by the employer on the slabs above. From "
				"1 March 2024 end-of-service is funded by SIO through monthly contributions. "
				"Confirm that the SIO scheme covers every expatriate hired before March 2024."
			),
		},
	},
	"OM": {
		"scalars": {
			"annual_leave_eligible_after_months": 6,
			"annual_leave_carry_forward_rule": "Up To Cap",
			"annual_leave_carry_forward_cap_days": 30,
			"sick_leave_days_per_year": 182,
			"sick_leave_eligible_after_months": 0,
			"gratuity_base": "Basic Salary",
			"nationals_pension_scheme": "SPF",
			"leave_salary_min_earned_days": 30,
			"leave_salary_min_service_days": 365,
		},
		"annual_leave_bands": [
			{"label": "Standard", "service_from_months": 0, "leave_days_per_year": 30, "salary_days_per_year": 30},
		],
		"sick_leave_tiers": [
			{"tier_days": 21, "pay_percent": 100},
			{"tier_days": 14, "pay_percent": 75},
			{"tier_days": 35, "pay_percent": 50},
			{"tier_days": 112, "pay_percent": 35},
		],
		"gratuity_slabs": [
			{"from_years": 0, "to_years": 0, "rate_unit": MONTHS, "rate_value": 1},
		],
		"gratuity_resignation_factors": [],
	},
	"AE": {
		"scalars": {
			"annual_leave_eligible_after_months": 6,
			"annual_leave_carry_forward_rule": "Per Company Policy",
			"sick_leave_days_per_year": 90,
			"gratuity_base": "Basic Salary",
			"gratuity_cap_months": 24,
			"gratuity_min_service_years": 1,
			"nationals_pension_scheme": "GPSSA",
			"leave_salary_min_earned_days": 30,
			"leave_salary_min_service_days": 365,
		},
		"annual_leave_bands": [
			{"label": "Months 6-12", "service_from_months": 6, "leave_days_per_year": 24, "salary_days_per_year": 24},
			{"label": "After 1 year", "service_from_months": 12, "leave_days_per_year": 30, "salary_days_per_year": 30},
		],
		"sick_leave_tiers": [
			{"tier_days": 15, "pay_percent": 100},
			{"tier_days": 30, "pay_percent": 50},
			{"tier_days": 45, "pay_percent": 0},
		],
		"gratuity_slabs": [
			{"from_years": 0, "to_years": 5, "rate_unit": DAYS, "rate_value": 21},
			{"from_years": 5, "to_years": 0, "rate_unit": DAYS, "rate_value": 30},
		],
		"gratuity_resignation_factors": [],
		"checks": {"sick_leave_after_probation": 1},
	},
	"QA": {
		"scalars": {
			"annual_leave_eligible_after_months": 12,
			"annual_leave_carry_forward_rule": "Per Company Policy",
			"sick_leave_days_per_year": 84,
			"sick_leave_eligible_after_months": 3,
			"gratuity_base": "Basic Salary",
			"gratuity_min_service_years": 1,
			"nationals_pension_scheme": "GRSIA",
			"leave_salary_min_earned_days": 30,
			"leave_salary_min_service_days": 365,
		},
		"annual_leave_bands": [
			{"label": "Up to 5 years", "service_from_months": 0, "leave_days_per_year": 21, "salary_days_per_year": 21},
			{"label": "After 5 years", "service_from_months": 60, "leave_days_per_year": 28, "salary_days_per_year": 28},
		],
		"sick_leave_tiers": [
			{"tier_days": 14, "pay_percent": 100},
			{"tier_days": 28, "pay_percent": 50},
			{"tier_days": 42, "pay_percent": 0},
		],
		"gratuity_slabs": [
			{"from_years": 0, "to_years": 0, "rate_unit": WEEKS, "rate_value": 3},
		],
		"gratuity_resignation_factors": [],
		"notes": {"gratuity_policy_notes": "Three weeks of basic wage per year is the statutory minimum; a contract may give more. Minimum one year of service."},
	},
	"KW": {
		"scalars": {
			"annual_leave_eligible_after_months": 9,
			"annual_leave_carry_forward_rule": "Per Company Policy",
			"sick_leave_days_per_year": 75,
			"sick_leave_eligible_after_months": 0,
			"gratuity_base": "Basic Salary",
			"gratuity_cap_months": 18,
			"nationals_pension_scheme": "PIFSS",
			"leave_salary_min_earned_days": 30,
			"leave_salary_min_service_days": 365,
		},
		"annual_leave_bands": [
			{"label": "Standard", "service_from_months": 0, "leave_days_per_year": 30, "salary_days_per_year": 30},
		],
		"sick_leave_tiers": [
			{"tier_days": 15, "pay_percent": 100},
			{"tier_days": 10, "pay_percent": 75},
			{"tier_days": 10, "pay_percent": 50},
			{"tier_days": 10, "pay_percent": 25},
			{"tier_days": 30, "pay_percent": 0},
		],
		"gratuity_slabs": [
			{"from_years": 0, "to_years": 5, "rate_unit": DAYS, "rate_value": 15},
			{"from_years": 5, "to_years": 0, "rate_unit": MONTHS, "rate_value": 1},
		],
		"gratuity_resignation_factors": [
			{"from_years": 0, "to_years": 3, "payable_percent": 0},
			{"from_years": 3, "to_years": 5, "payable_percent": 50},
			{"from_years": 5, "to_years": 10, "payable_percent": 66.67},
			{"from_years": 10, "to_years": 0, "payable_percent": 100},
		],
		"notes": {
			"gratuity_policy_notes": (
				"The spec says only 'reduced under 10 years' for resignation; the bands here "
				"follow the commonly cited reading (nothing under 3 years, half to 5, two-thirds "
				"to 10, full at 10+). VERIFY with the client's legal adviser before go-live."
			),
		},
	},
}

_TABLES = (
	"annual_leave_bands",
	"sick_leave_tiers",
	"gratuity_slabs",
	"gratuity_resignation_factors",
)


def apply_policy_defaults(country_code: str, config_name: str) -> bool:
	"""Fill an existing Country Config with this country's legal policy defaults.

	Idempotent and non-destructive, because it runs on every migrate:

	* a policy table is filled only while it is EMPTY — a row an administrator has
	  edited or deleted down to a different set is never rewritten, and a table the
	  administrator cleared on purpose is refilled only if they clear it AND the seed
	  has something to say, which is the accepted cost of a self-healing top-up;
	* a number is filled only while it is 0, a text field only while blank. Zero is not
	  an entitlement anybody chose (see _TOPUP_NUMERIC_FIELDS in install.py);
	* Check fields are set only on the pass that first fills the policy tables: unticked
	  is a real answer, so a later migrate must never tick one back.

	Returns True when something was written.
	"""
	seed = POLICY_DEFAULTS.get((country_code or "").upper())
	if not seed or not config_name:
		return False

	doc = frappe.get_doc("Country Config", config_name)
	changed = False

	for field, value in seed.get("scalars", {}).items():
		current = doc.get(field)
		if isinstance(value, (int, float)):
			if flt(value) and not flt(current):
				doc.set(field, value)
				changed = True
		elif current in (None, ""):
			doc.set(field, value)
			changed = True

	for field, value in seed.get("notes", {}).items():
		if not doc.get(field):
			doc.set(field, value)
			changed = True

	first_fill = False
	for table in _TABLES:
		rows = seed.get(table) or []
		if rows and not doc.get(table):
			for row in rows:
				doc.append(table, dict(row))
			changed = first_fill = True

	if first_fill:
		for field, value in seed.get("checks", {}).items():
			doc.set(field, value)

	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.logger().info(f"HR Suite: applied leave/gratuity policy defaults to Country Config {config_name}")
	return changed
