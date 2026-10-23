"""Resolve the leave / sick / gratuity policy that applies to one employee.

The policy lives on Country Config (one record per country). The Employee's country is
resolved by utils.get_employee_work_country — active contract, then Employee.work_country,
then Company.country — and an optional override block on the Employee layers company-specific
terms on top (the KSA "30 days leave, 21 days salary" option, the 2-year leave cycle, the
air-ticket entitlement). Nothing here writes; later phases (accrual, settlement, gratuity)
all read the policy through get_policy() so there is exactly one place that decides it.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, nowdate

from hr_suite.hr_suite.utils import get_employee_work_country

OVERRIDE_FIELDS = (
	"override_leave_days_per_year",
	"override_salary_days_per_year",
	"override_leave_cycle_years",
	"override_ticket_entitled",
	"override_ticket_amount",
	"override_ticket_every_months",
)


def months_of_service(joining_date, on_date=None) -> int:
	"""Completed calendar months from the joining date to on_date (0 if not yet joined)."""
	if not joining_date:
		return 0
	start = getdate(joining_date)
	end = getdate(on_date or nowdate())
	if end < start:
		return 0
	months = (end.year - start.year) * 12 + (end.month - start.month)
	if end.day < start.day:
		months -= 1
	return max(months, 0)


def resolve_annual_band(bands, service_months: int):
	"""The band with the highest service_from_months not above the service completed.

	None when the employee has not reached the first band (UAE: nothing accrues in the
	first six months).
	"""
	chosen = None
	for band in sorted(bands or [], key=lambda b: cint(b.get("service_from_months"))):
		if cint(band.get("service_from_months")) <= cint(service_months):
			chosen = band
	return chosen


LEDGER_ENGINE = "HR Suite Ledger"


def _annual_leave_type(cfg) -> str:
	"""The HRMS Leave Type that carries annual leave: the row that accrues monthly."""
	for row in cfg.get("leave_types") or []:
		if cstr(row.get("accrual_frequency")).strip() == "Monthly":
			return cstr(row.get("frappe_leave_type_name") or row.get("leave_type_name")).strip() or "Annual Leave"
	return "Annual Leave"


def _sick_leave_type(cfg) -> str:
	"""The HRMS Leave Type that carries sick leave: the first declared row with 'sick' in its name."""
	for row in cfg.get("leave_types") or []:
		name = cstr(row.get("frappe_leave_type_name") or row.get("leave_type_name")).strip()
		if "sick" in name.lower():
			return name
	return "Sick Leave"


def _rows(doc, table, fields):
	return [{f: row.get(f) for f in fields} for row in (doc.get(table) or [])]


def get_country_policy(country_code: str):
	"""Country-level policy as plain dicts, or None when the country has no Country Config."""
	name = frappe.db.get_value("Country Config", {"country_code": cstr(country_code).upper()}, "name")
	if not name:
		return None
	cfg = frappe.get_cached_doc("Country Config", name)
	return frappe._dict(
		country_code=cfg.country_code,
		country_name=cfg.country_name,
		config=cfg.name,
		annual_leave_bands=_rows(
			cfg, "annual_leave_bands",
			("label", "service_from_months", "leave_days_per_year", "salary_days_per_year"),
		),
		leave_accrual_engine=cfg.leave_accrual_engine or "",
		leave_ledger_start_date=cfg.leave_ledger_start_date,
		accrual_proration_basis=cfg.accrual_proration_basis or "Over 30 Days",
		annual_leave_type=_annual_leave_type(cfg),
		annual_leave_eligible_after_months=cint(cfg.annual_leave_eligible_after_months),
		annual_leave_carry_forward_rule=cfg.annual_leave_carry_forward_rule or "",
		annual_leave_carry_forward_years=cint(cfg.annual_leave_carry_forward_years),
		annual_leave_carry_forward_cap_days=flt(cfg.annual_leave_carry_forward_cap_days),
		leave_salary_days_per_month=flt(cfg.leave_salary_days_per_month) or 30,
		leave_salary_components=cfg.leave_salary_components or "",
		leave_salary_min_earned_days=flt(cfg.leave_salary_min_earned_days),
		leave_salary_min_service_days=cint(cfg.leave_salary_min_service_days),
		pay_worked_days_in_settlement=cint(cfg.pay_worked_days_in_settlement),
		leave_salary_pay_on_exit=cint(cfg.leave_salary_pay_on_exit),
		annual_leave_before_min_service=cfg.annual_leave_before_min_service or "Allow",
		sick_leave_window=cfg.sick_leave_window or "Leave Period",
		sick_leave_auto_split=cint(cfg.sick_leave_auto_split),
		sick_leave_type=_sick_leave_type(cfg),
		max_probation_days=cint(cfg.max_probation_days),
		sick_leave_days_per_year=cint(cfg.sick_leave_days_per_year),
		sick_leave_eligible_after_months=cint(cfg.sick_leave_eligible_after_months),
		sick_leave_after_probation=cint(cfg.sick_leave_after_probation),
		sick_leave_requires_certificate=cint(cfg.sick_leave_requires_certificate),
		sick_leave_tiers=_rows(cfg, "sick_leave_tiers", ("tier_days", "pay_percent")),
		gratuity_base=cfg.gratuity_base or "Basic Salary",
		gratuity_cap_months=flt(cfg.gratuity_cap_months),
		gratuity_min_service_years=flt(cfg.gratuity_min_service_years),
		gratuity_forfeited_on_dismissal=cint(cfg.gratuity_forfeited_on_dismissal),
		gratuity_unpaid_leave_deducted=cint(cfg.gratuity_unpaid_leave_deducted),
		gratuity_scheme_end_date=cfg.gratuity_scheme_end_date,
		gratuity_slabs=_rows(cfg, "gratuity_slabs", ("from_years", "to_years", "rate_unit", "rate_value")),
		gratuity_resignation_factors=_rows(
			cfg, "gratuity_resignation_factors", ("from_years", "to_years", "payable_percent")
		),
		nationals_pension_scheme=cfg.nationals_pension_scheme or "",
		gratuity_nationals_also_entitled=cint(cfg.gratuity_nationals_also_entitled),
	)


def _employee_overrides(employee: str) -> dict:
	"""The override block of one Employee; empty when the custom fields are not installed yet."""
	columns = frappe.db.get_table_columns("Employee")
	fields = [f for f in OVERRIDE_FIELDS if f in columns]
	if not fields:
		return {}
	return frappe.db.get_value("Employee", employee, fields, as_dict=True) or {}


def apply_overrides(policy, band, overrides: dict):
	"""Layer an Employee's override block over the country band. Pure, so it is testable.

	Returns the annual entitlement that applies: leave days and leave-salary days per year,
	the accrual cycle in years, the ticket entitlement, and which overrides were used.
	"""
	leave_days = flt(band.get("leave_days_per_year")) if band else 0.0
	salary_days = flt(band.get("salary_days_per_year")) if band else 0.0
	used = []

	if flt(overrides.get("override_leave_days_per_year")) > 0:
		leave_days = flt(overrides.get("override_leave_days_per_year"))
		used.append("leave days per year")
	if flt(overrides.get("override_salary_days_per_year")) > 0:
		salary_days = flt(overrides.get("override_salary_days_per_year"))
		used.append("salary days per year")
	cycle = cint(overrides.get("override_leave_cycle_years")) or 1
	if cint(overrides.get("override_leave_cycle_years")):
		used.append("leave cycle")
	if cint(overrides.get("override_ticket_entitled")):
		used.append("air ticket")

	return frappe._dict(
		leave_days_per_year=leave_days,
		salary_days_per_year=salary_days,
		leave_days_per_month=round(leave_days / 12, 4),
		salary_days_per_month=round(salary_days / 12, 4),
		leave_cycle_years=cycle,
		ticket_entitled=cint(overrides.get("override_ticket_entitled")),
		ticket_amount=flt(overrides.get("override_ticket_amount")),
		ticket_every_months=cint(overrides.get("override_ticket_every_months")),
		overrides_used=used,
	)


def get_policy(employee: str, on_date=None):
	"""Everything the policy engine decides for one employee on one date."""
	if not employee:
		return frappe._dict()

	country = get_employee_work_country(employee)
	country_policy = get_country_policy(country) if country else None
	joining = frappe.db.get_value("Employee", employee, "date_of_joining")
	months = months_of_service(joining, on_date)

	if not country_policy:
		return frappe._dict(
			employee=employee, country_code=country, has_policy=0,
			service_months=months, date_of_joining=joining,
		)

	band = resolve_annual_band(country_policy.annual_leave_bands, months)
	annual = apply_overrides(country_policy, band, _employee_overrides(employee))

	return frappe._dict(
		country_policy,
		employee=employee,
		has_policy=1,
		date_of_joining=joining,
		service_months=months,
		annual_band=band,
		annual=annual,
		leave_can_be_taken=int(months >= country_policy.annual_leave_eligible_after_months),
	)


@frappe.whitelist()
def get_employee_policy(employee: str):
	"""The resolved policy for the Employee form's read-only panel."""
	if not frappe.has_permission("Employee", "read", doc=employee):
		frappe.throw(_("You do not have permission to read this Employee."), frappe.PermissionError)
	return get_policy(employee)
