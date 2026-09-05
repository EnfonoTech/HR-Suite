"""
Monthly Loan Recovery Summary

Employee-loan recovery grouped by deduction month. Only submitted loans count —
draft and cancelled loans are not recoveries.
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "recovery_month", "label": _("Recovery Month"), "fieldtype": "Data", "width": 140},
		{"fieldname": "employee_count", "label": _("Employees"), "fieldtype": "Int", "width": 110},
		{"fieldname": "loan_count", "label": _("Loans"), "fieldtype": "Int", "width": 100},
		{"fieldname": "recovered_amount", "label": _("Recovered Amount"), "fieldtype": "Currency", "options": "currency", "width": 160},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	conditions = [
		"loan.docstatus = 1",
		"child.deduction_status = %(deduction_status)s",
		"child.deduction_date IS NOT NULL",
	]
	values = {"deduction_status": "Deducted"}

	if filters.get("company"):
		conditions.append("loan.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("employee"):
		conditions.append("loan.employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("from_date"):
		conditions.append("child.deduction_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("child.deduction_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			DATE_FORMAT(child.deduction_date, '%%Y-%%m') AS recovery_month,
			COUNT(DISTINCT loan.employee) AS employee_count,
			COUNT(DISTINCT loan.name) AS loan_count,
			SUM(child.deducted_amount) AS recovered_amount
		FROM `tabEmployee Loan Installment` child
		INNER JOIN `tabEmployee Loan` loan ON loan.name = child.parent
		{where}
		GROUP BY DATE_FORMAT(child.deduction_date, '%%Y-%%m')
		ORDER BY recovery_month DESC
		""",
		values,
		as_dict=True,
	)

	currency = None
	if filters.get("company"):
		currency = frappe.get_cached_value("Company", filters["company"], "default_currency")
	if not currency:
		currency = frappe.defaults.get_global_default("currency")

	for row in rows:
		row["currency"] = currency

	_append_total_row(rows, currency)
	return rows


def _append_total_row(rows, currency):
	"""Total only the money column.

	frappe's own `add_total_row` sums every numeric column, which would report
	"Employees 2" and "Loans 2" for ONE employee repaying ONE loan across two
	months. Employee and loan counts are DISTINCT counts per month and cannot be
	added up, so they are deliberately left blank on the total row.
	"""
	if not rows:
		return
	rows.append({
		"recovery_month": _("Total"),
		"employee_count": None,
		"loan_count": None,
		"recovered_amount": sum(flt(r.get("recovered_amount")) for r in rows),
		"currency": currency,
	})
