"""LMRA Work Permit Register (client ticket 3.1).

The LMRA position for a company: for every employee working in the selected country,
which work permit is on file, when it expires, how long is left, and — where the client
has configured the rate — what the recurring per-worker fee costs per month.

Two things this report deliberately does NOT do:

  * It does not talk to the LMRA portal. There is no credential, no sandbox and no agreed
    API contract for this client, so nothing here is or pretends to be an integration.
  * It does not know the LMRA fee. The amount and the scope come from
    `Country Config.monthly_permit_fee_per_worker` / `recurring_permit_fee_applies_to`,
    both of which ship unset. Until the client enters them, the fee columns are blank and
    the summary says "not configured" — it never substitutes a guessed tariff.

Starting from Employee rather than from Work Permit Iqama is the point: the compliance
question LMRA asks is "which of your workers has no valid permit", and a report driven
off the permit table can only ever list the permits that already exist.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, date_diff, flt, getdate, today

from hr_suite.hr_suite.utils import (
	get_employees_is_national_map,
	get_employee_work_country_map,
	get_permit_labels,
	get_recurring_permit_fee_config,
)

NO_PERMIT = "No Permit Record"
_EMPLOYEE_STATUSES = ("Active", "Inactive", "Suspended", "Left")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	country = cstr(filters.get("work_country")).strip().upper()
	if not country:
		frappe.throw(_("Select a Work Country."))

	labels = get_permit_labels(country)
	fee = get_recurring_permit_fee_config(country)
	currency = fee.get("currency") or _company_currency(filters.get("company"))

	rows = get_data(filters, country, labels, fee, currency)
	columns = get_columns(labels, fee)
	message = get_message(country, labels, fee)
	summary = get_report_summary(rows, fee, currency, labels)

	# Working key, not a column — drop it before the rows leave the server.
	for row in rows:
		row.pop("_in_fee_scope", None)

	return columns, rows, message, None, summary


# ─── Columns ──────────────────────────────────────────────────────────────────

def get_columns(labels: dict, fee: dict) -> list:
	permit = labels.get("permit_label") or _("Work Permit")
	national_id = labels.get("national_id_label") or _("National ID")

	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 190},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
		{"fieldname": "employee_status", "label": _("Employee Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 120},
		{"fieldname": "worker_class", "label": _("Worker Class"), "fieldtype": "Data", "width": 120},
		{"fieldname": "national_id", "label": national_id, "fieldtype": "Data", "width": 140},
		{"fieldname": "permit_record", "label": _("Permit Record"), "fieldtype": "Link", "options": "Work Permit Iqama", "width": 150},
		{"fieldname": "permit_number", "label": _("{0} No.").format(permit), "fieldtype": "Data", "width": 150},
		{"fieldname": "permit_issue_date", "label": _("Issue Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "permit_expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "days_to_expiry", "label": _("Days Left"), "fieldtype": "Int", "width": 90},
		{"fieldname": "permit_status", "label": _("Permit Status"), "fieldtype": "Data", "width": 140},
		{
			"fieldname": "monthly_permit_fee",
			"label": _("Monthly {0} Fee").format(fee.get("authority") or _("Permit")),
			"fieldtype": "Currency",
			# `options: "currency"` reads the per-row currency field. This site is BHD with
			# 3 decimals; a Currency column without it formats against the system default.
			"options": "currency",
			"width": 150,
		},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


# ─── Data ─────────────────────────────────────────────────────────────────────

def get_data(filters, country: str, labels: dict, fee: dict, currency: str) -> list:
	employees = _get_employees(filters)
	if not employees:
		return []

	names = [e["name"] for e in employees]
	work_country = get_employee_work_country_map(names)
	in_scope = [e for e in employees if work_country.get(e["name"]) == country]
	if not in_scope:
		return []

	scoped_names = [e["name"] for e in in_scope]
	national_map = get_employees_is_national_map(scoped_names, country)
	permits = _get_current_permits(scoped_names)

	window = cint(filters.get("expiring_within_days"))
	if window <= 0:
		window = cint(labels.get("alert_days")) or 90

	as_on = today()
	status_filter = cstr(filters.get("permit_status")).strip()
	show_missing = cint(filters.get("show_employees_without_permit", 1))

	rows = []
	for emp in in_scope:
		permit = permits.get(emp["name"]) or {}
		expiry = permit.get("work_permit_expiry_date")

		if permit and expiry:
			days_left = date_diff(expiry, as_on)
			status = _status_for(days_left, window)
		elif permit:
			# A permit record exists but carries no expiry date — the compliance gap is
			# the missing date, so it must not read as "Active".
			days_left = None
			status = NO_PERMIT
		else:
			days_left = None
			status = NO_PERMIT

		if status == NO_PERMIT and not show_missing:
			continue
		if status_filter and status != status_filter:
			continue

		is_national = national_map.get(emp["name"])
		rows.append({
			"employee": emp["name"],
			"employee_name": emp.get("employee_name"),
			"company": emp.get("company"),
			"employee_status": emp.get("status"),
			"nationality": _nationality_label(emp, permit),
			"worker_class": _worker_class(is_national),
			"national_id": cstr(emp.get("national_id")) or cstr(permit.get("iqama_number")),
			"permit_record": permit.get("name"),
			"permit_number": permit.get("work_permit_number"),
			"permit_issue_date": permit.get("work_permit_issue_date"),
			"permit_expiry_date": expiry,
			"days_to_expiry": days_left,
			"permit_status": status,
			"monthly_permit_fee": _fee_for(is_national, fee),
			"currency": currency,
			# Not a column — the summary counts it.
			"_in_fee_scope": _in_fee_scope(is_national, fee),
		})

	rows.sort(key=lambda r: (
		r["permit_status"] != NO_PERMIT,
		r["days_to_expiry"] if r["days_to_expiry"] is not None else 10**6,
		cstr(r["employee_name"]),
	))
	return rows


def _get_employees(filters) -> list:
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters["company"]

	status = cstr(filters.get("employee_status") or "Active")
	if status != "All":
		if status not in _EMPLOYEE_STATUSES:
			frappe.throw(_("Invalid Employee Status filter."))
		conditions["status"] = status

	fields = ["name", "employee_name", "company", "status"]
	# national_id is an hr_suite Custom Field (install.EMPLOYEE_MASTER_FIELDS); a bench
	# part-way through migrate can legitimately not have it yet.
	has_national_id = frappe.db.has_column("Employee", "national_id")
	has_nationality = frappe.get_meta("Employee").has_field("nationality")
	if has_national_id:
		fields.append("national_id")
	if has_nationality:
		fields.append("nationality")

	return frappe.get_all(
		"Employee",
		filters=conditions,
		fields=fields,
		limit_page_length=0,
		order_by="employee_name asc",
	)


def _get_current_permits(employees: list) -> dict:
	"""Latest submitted permit per employee — one query, not one per employee.

	"Latest" is the furthest work_permit_expiry_date; where two records share it (or
	neither has one) the most recently modified wins, which is the record HR last touched.
	"""
	if not employees:
		return {}

	rows = frappe.get_all(
		"Work Permit Iqama",
		filters={"employee": ["in", employees], "docstatus": 1},
		fields=[
			"name", "employee", "work_permit_number", "work_permit_issue_date",
			"work_permit_expiry_date", "work_permit_status", "iqama_number",
			"nationality", "modified",
		],
		limit_page_length=0,
	)

	current = {}
	for row in rows:
		held = current.get(row["employee"])
		if held is None or _permit_sort_key(row) > _permit_sort_key(held):
			current[row["employee"]] = row
	return current


def _permit_sort_key(row):
	expiry = row.get("work_permit_expiry_date")
	# cstr on `modified`: the tuple is only compared element-by-element, but keeping every
	# member the same type means a NULL modified can never raise on a datetime comparison.
	return (
		1 if expiry else 0,
		getdate(expiry) if expiry else getdate("1900-01-01"),
		cstr(row.get("modified")),
	)


def _status_for(days_left: int, window: int) -> str:
	if days_left < 0:
		return "Expired"
	if days_left <= window:
		return "Expiring Soon"
	return "Active"


def _nationality_label(emp: dict, permit: dict) -> str:
	return cstr(emp.get("nationality")) or cstr(permit.get("nationality"))


def _worker_class(is_national) -> str:
	"""Tri-state. "Not classified" is a real answer, and an actionable one — an employee
	with no Employee Type and no nationality cannot be counted for or against the fee."""
	if is_national is None:
		return _("Not classified")
	return _("National") if is_national else _("Expatriate")


def _in_fee_scope(is_national, fee: dict) -> bool:
	if not fee.get("is_configured"):
		return False
	applies_to = fee.get("applies_to")
	if applies_to == "All Employees":
		return True
	if applies_to == "Expatriate Employees":
		# Unclassified employees are NOT assumed to be expatriates. They are reported
		# separately so HR classifies them rather than trusting a guessed liability.
		return is_national is False
	return False


def _fee_for(is_national, fee: dict):
	return flt(fee.get("monthly_fee")) if _in_fee_scope(is_national, fee) else None


def _company_currency(company) -> str:
	if not company:
		return frappe.db.get_default("currency") or ""
	return cstr(frappe.get_cached_value("Company", company, "default_currency"))


# ─── Message & summary ────────────────────────────────────────────────────────

def get_message(country: str, labels: dict, fee: dict) -> str:
	notes = []

	if not labels.get("configured"):
		notes.append(
			_("No Country Config record exists for {0}, so generic labels and a {1}-day "
			  "expiry window are being used.").format(country, labels.get("alert_days"))
		)

	if not fee.get("is_configured"):
		authority = fee.get("authority") or _("the labour authority")
		notes.append(
			_("Recurring permit fee is NOT configured for {0}. Set "
			  "<b>Monthly Fee per Worker</b> and <b>Fee Applies To</b> on Country Config "
			  "{1} once the current {2} tariff has been confirmed in writing — until then "
			  "no monthly liability is calculated and the fee column stays blank.")
			.format(country, country, authority)
		)
	elif fee.get("notes"):
		notes.append(frappe.utils.escape_html(cstr(fee.get("notes"))))

	if not notes:
		return ""
	return "<br>".join("&bull; " + n for n in notes)


def get_report_summary(rows: list, fee: dict, currency: str, labels: dict) -> list:
	total = len(rows)
	missing = sum(1 for r in rows if r["permit_status"] == NO_PERMIT)
	expiring = sum(1 for r in rows if r["permit_status"] == "Expiring Soon")
	expired = sum(1 for r in rows if r["permit_status"] == "Expired")
	unclassified = sum(1 for r in rows if r["worker_class"] == _("Not classified"))
	chargeable = sum(1 for r in rows if r.get("_in_fee_scope"))

	summary = [
		{"value": total, "label": _("Workers in scope"), "datatype": "Int", "indicator": "Blue"},
		{"value": missing, "label": _("No permit on file"), "datatype": "Int",
		 "indicator": "Red" if missing else "Green"},
		{"value": expired, "label": _("Expired"), "datatype": "Int",
		 "indicator": "Red" if expired else "Green"},
		{"value": expiring, "label": _("Expiring within window"), "datatype": "Int",
		 "indicator": "Orange" if expiring else "Green"},
	]

	if unclassified:
		summary.append({
			"value": unclassified,
			"label": _("Worker class not set"),
			"datatype": "Int",
			"indicator": "Orange",
		})

	if fee.get("is_configured"):
		monthly = flt(fee.get("monthly_fee")) * chargeable
		summary.extend([
			{"value": chargeable, "label": _("Fee-bearing workers"), "datatype": "Int", "indicator": "Blue"},
			{"value": monthly, "label": _("Monthly liability"), "datatype": "Currency",
			 "currency": currency, "indicator": "Blue"},
			{"value": monthly * 12, "label": _("Annualised"), "datatype": "Currency",
			 "currency": currency, "indicator": "Grey"},
		])
	else:
		summary.append({
			"value": _("Not configured"),
			"label": _("Monthly {0} liability").format(fee.get("authority") or _("permit fee")),
			"datatype": "Data",
			"indicator": "Orange",
		})

	return summary
