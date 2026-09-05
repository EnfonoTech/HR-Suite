"""
Contract Expiry Report

Country Employment Contracts whose end date falls inside the alert window.
Cancelled contracts are excluded; the contract type and status are filters, not
hardcoded assumptions.
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, today


DEFAULT_ALERT_DAYS = 60


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Contract"), "fieldtype": "Link", "options": "Country Employment Contract", "width": 180},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "contract_type", "label": _("Type"), "fieldtype": "Data", "width": 160},
		{"fieldname": "start_date", "label": _("Start"), "fieldtype": "Date", "width": 110},
		{"fieldname": "end_date", "label": _("End"), "fieldtype": "Date", "width": 110},
		{"fieldname": "days_to_expiry", "label": _("Days Left"), "fieldtype": "Int", "width": 120},
		{"fieldname": "contract_status", "label": _("Status"), "fieldtype": "Data", "width": 130},
		{"fieldname": "document_status", "label": _("Doc Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "basic_salary", "label": _("Basic Salary"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	# Report filters arrive over HTTP as strings; int() raises ValueError on anything
	# non-numeric and took the whole report down with a traceback. cint() coerces.
	days = cint(filters.get("alert_days"))
	if days <= 0:
		days = DEFAULT_ALERT_DAYS
	cutoff = add_days(today(), days)

	# Only the internally-built condition list is interpolated; every user value is a %(name)s bind.
	conditions = [
		"c.docstatus < 2",
		"c.end_date IS NOT NULL",
		"c.end_date <= %(cutoff)s",
	]
	values = {"cutoff": cutoff}

	if filters.get("company"):
		conditions.append("c.company = %(company)s")
		values["company"] = filters["company"]

	if filters.get("contract_type"):
		conditions.append("c.contract_type = %(contract_type)s")
		values["contract_type"] = filters["contract_type"]

	contract_status = filters.get("contract_status") or "Active"
	if contract_status != "All":
		conditions.append("c.contract_status = %(contract_status)s")
		values["contract_status"] = contract_status

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			c.docstatus,
			c.name, c.employee, c.employee_name, c.contract_type,
			c.start_date, c.end_date, c.contract_status, c.basic_salary,
			COALESCE(c.currency, comp.default_currency) AS currency
		FROM `tabCountry Employment Contract` c
		LEFT JOIN `tabCompany` comp ON comp.name = c.company
		{where}
		ORDER BY c.end_date ASC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		row["days_to_expiry"] = date_diff(row["end_date"], today())
		# Drafts are kept on purpose (a contract being prepared still expires), but
		# without this column a draft is indistinguishable from a live contract.
		# Raw English values, not translated: a UI filter would compare them server-side.
		row["document_status"] = "Draft" if not row.pop("docstatus", 0) else "Submitted"

	return rows
