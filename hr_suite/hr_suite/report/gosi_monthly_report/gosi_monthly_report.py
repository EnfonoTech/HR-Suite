"""
GOSI Monthly Report

Monthly social-insurance contributions. Cancelled contributions are excluded and
amounts are shown in the company's own currency.
"""
import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Contribution"), "fieldtype": "Link", "options": "GOSI Contribution", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 140},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 120},
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 100},
		{"fieldname": "year", "label": _("Year"), "fieldtype": "Int", "width": 80},
		{"fieldname": "contribution_base", "label": _("Base"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "employee_rate", "label": _("Emp. Rate %"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "employer_rate", "label": _("Empr. Rate %"), "fieldtype": "Percent", "width": 140},
		{"fieldname": "employee_contribution", "label": _("Emp. Amount"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "employer_contribution", "label": _("Empr. Amount"), "fieldtype": "Currency", "options": "currency", "width": 160},
		{"fieldname": "total_contribution", "label": _("Total"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "payment_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "document_status", "label": _("Doc Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	conditions = ["gosi.docstatus < 2"]
	values = {}

	if filters.get("company"):
		conditions.append("gosi.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("employee"):
		conditions.append("gosi.employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("month"):
		conditions.append("gosi.month = %(month)s")
		values["month"] = filters["month"]
	if filters.get("year"):
		conditions.append("gosi.year = %(year)s")
		values["year"] = cint(filters["year"])
	if filters.get("payment_status"):
		conditions.append("gosi.payment_status = %(payment_status)s")
		values["payment_status"] = filters["payment_status"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			gosi.docstatus,
			gosi.name,
			gosi.employee,
			gosi.employee_name,
			gosi.nationality,
			gosi.month,
			gosi.year,
			gosi.contribution_base,
			gosi.employee_contribution_rate AS employee_rate,
			gosi.employer_contribution_rate AS employer_rate,
			gosi.employee_contribution,
			gosi.employer_contribution,
			gosi.total_contribution,
			gosi.payment_status,
			comp.default_currency AS currency
		FROM `tabGOSI Contribution` gosi
		LEFT JOIN `tabCompany` comp ON comp.name = gosi.company
		{where}
		ORDER BY gosi.year DESC, gosi.month, gosi.employee_name
		""",
		values,
		as_dict=True,
	)

	return label_document_status(rows)


def label_document_status(rows):
	"""Name the draft rows.

	Drafts are kept on purpose — this is a working register, not a filing — but a
	draft contribution carries a payable amount and, without this column, is
	indistinguishable on screen from one that has actually been submitted.
	Raw English values: a UI filter would send them back for comparison.
	"""
	for row in rows:
		row["document_status"] = "Draft" if not row.pop("docstatus", 0) else "Submitted"
	return rows
