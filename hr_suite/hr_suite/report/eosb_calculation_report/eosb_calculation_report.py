"""
EOSB Calculation Report

End of Service Benefit calculations. Cancelled documents are excluded, and the
amounts are rendered in the company's own currency rather than the site default —
Steel Force runs on BHD with three decimals.
"""
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Document"), "fieldtype": "Link", "options": "End of Service Benefit", "width": 160},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "joining_date", "label": _("Joining Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "termination_date", "label": _("Termination"), "fieldtype": "Date", "width": 120},
		{"fieldname": "years_of_service", "label": _("Years"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "termination_reason", "label": _("Reason"), "fieldtype": "Data", "width": 200},
		{"fieldname": "last_basic_salary", "label": _("Basic Salary"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "eosb_gross", "label": _("Gross EOSB"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "resignation_factor", "label": _("Factor"), "fieldtype": "Float", "precision": 4, "width": 100},
		{"fieldname": "net_eosb", "label": _("Net EOSB"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "payment_status", "label": _("Payment"), "fieldtype": "Data", "width": 120},
		{"fieldname": "document_status", "label": _("Doc Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	conditions = ["eosb.docstatus < 2"]
	values = {}

	if filters.get("company"):
		conditions.append("eosb.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("employee"):
		conditions.append("eosb.employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("payment_status"):
		conditions.append("eosb.payment_status = %(payment_status)s")
		values["payment_status"] = filters["payment_status"]
	if filters.get("from_date"):
		conditions.append("eosb.termination_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("eosb.termination_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			eosb.docstatus,
			eosb.name, eosb.employee, eosb.employee_name, eosb.joining_date,
			eosb.termination_date, eosb.years_of_service, eosb.termination_reason,
			eosb.last_basic_salary, eosb.eosb_gross, eosb.resignation_factor,
			eosb.net_eosb, eosb.payment_status,
			comp.default_currency AS currency
		FROM `tabEnd of Service Benefit` eosb
		LEFT JOIN `tabCompany` comp ON comp.name = eosb.company
		{where}
		ORDER BY eosb.termination_date DESC
		""",
		values,
		as_dict=True,
	)

	return label_document_status(rows)


def label_document_status(rows):
	"""Name the draft rows.

	Drafts are kept on purpose — this is a working register — but a draft EOSB
	carries a net amount payable to a leaver and, without this column, reads on
	screen exactly like a submitted one. Raw English values, not translated: a UI
	filter would send them straight back for comparison.
	"""
	for row in rows:
		row["document_status"] = "Draft" if not row.pop("docstatus", 0) else "Submitted"
	return rows
