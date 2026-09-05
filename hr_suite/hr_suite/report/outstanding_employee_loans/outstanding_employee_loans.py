"""
Outstanding Employee Loans

Open balance per Employee Loan. Only submitted loans are outstanding — a draft loan
has not been granted and a cancelled loan owes nothing, so both are excluded.
"""
import frappe
from frappe import _
from frappe.utils import flt


OPEN_INSTALLMENT_STATUSES = ("Pending", "Deferred")


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Employee Loan", "width": 160},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 140},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 120},
		{"fieldname": "loan_amount", "label": _("Loan Amount"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "total_deducted", "label": _("Recovered"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "outstanding_balance", "label": _("Outstanding"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "next_due_date", "label": _("Next Due Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "next_installment_amount", "label": _("Next Installment"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 90, "hidden": 1},
	]


def get_data(filters):
	conditions = ["loan.docstatus = 1"]
	values = {"open_1": OPEN_INSTALLMENT_STATUSES[0], "open_2": OPEN_INSTALLMENT_STATUSES[1]}

	if filters.get("company"):
		conditions.append("loan.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("employee"):
		conditions.append("loan.employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("status"):
		conditions.append("loan.status = %(status)s")
		values["status"] = filters["status"]
	if not filters.get("include_settled"):
		conditions.append("IFNULL(loan.outstanding_balance, 0) > 0")

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			loan.name AS loan,
			loan.employee,
			loan.employee_name,
			loan.company,
			loan.loan_amount,
			loan.total_deducted,
			loan.outstanding_balance,
			(
				SELECT child.due_date
				FROM `tabEmployee Loan Installment` child
				WHERE child.parent = loan.name
					AND child.parenttype = 'Employee Loan'
					AND child.deduction_status IN (%(open_1)s, %(open_2)s)
				ORDER BY child.due_date, child.idx
				LIMIT 1
			) AS next_due_date,
			(
				SELECT child.outstanding_amount
				FROM `tabEmployee Loan Installment` child
				WHERE child.parent = loan.name
					AND child.parenttype = 'Employee Loan'
					AND child.deduction_status IN (%(open_1)s, %(open_2)s)
				ORDER BY child.due_date, child.idx
				LIMIT 1
			) AS next_installment_amount,
			loan.status,
			comp.default_currency AS currency
		FROM `tabEmployee Loan` loan
		LEFT JOIN `tabCompany` comp ON comp.name = loan.company
		{where}
		ORDER BY loan.outstanding_balance DESC, loan.modified DESC
		""",
		values,
		as_dict=True,
	)

	_append_total_row(rows)
	return rows


def _append_total_row(rows):
	"""Total only the money columns.

	frappe's blanket `add_total_row` also summed `next_installment_amount` — the
	size of each loan's NEXT single instalment — which is not a meaningful total.
	"""
	if not rows:
		return
	rows.append({
		"employee_name": _("Total"),
		"loan_amount": sum(flt(r.get("loan_amount")) for r in rows),
		"total_deducted": sum(flt(r.get("total_deducted")) for r in rows),
		"outstanding_balance": sum(flt(r.get("outstanding_balance")) for r in rows),
		"currency": rows[0].get("currency"),
	})
