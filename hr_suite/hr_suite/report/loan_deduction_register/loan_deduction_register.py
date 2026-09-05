"""
Loan Deduction Register

One row per recovered Employee Loan installment. Only installments belonging to a
submitted loan are counted — a draft or cancelled loan is not a recovery.
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Employee Loan", "width": 150},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "installment_number", "label": _("Installment #"), "fieldtype": "Int", "width": 90},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "deduction_date", "label": _("Deduction Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "deducted_amount", "label": _("Deducted Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "payroll_reference", "label": _("Payroll"), "fieldtype": "Link", "options": "Monthly Payroll", "width": 150},
		{"fieldname": "deduction_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	conditions = [
		"loan.docstatus = 1",
		"child.deduction_status = %(deduction_status)s",
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
			loan.name AS loan,
			loan.employee,
			loan.employee_name,
			child.installment_number,
			child.due_date,
			child.deduction_date,
			child.deducted_amount,
			child.payroll_reference,
			child.deduction_status,
			comp.default_currency AS currency
		FROM `tabEmployee Loan Installment` child
		INNER JOIN `tabEmployee Loan` loan ON loan.name = child.parent
		LEFT JOIN `tabCompany` comp ON comp.name = loan.company
		{where}
		ORDER BY child.deduction_date DESC, loan.employee_name ASC
		""",
		values,
		as_dict=True,
	)

	_append_total_row(rows)
	return rows


def _append_total_row(rows):
	"""Total only the money column — never `installment_number`, which is an
	identifier. frappe's blanket `add_total_row` was summing it to nonsense."""
	if not rows:
		return
	rows.append({
		"employee_name": _("Total"),
		"deducted_amount": sum(flt(r.get("deducted_amount")) for r in rows),
		"currency": rows[0].get("currency"),
	})
