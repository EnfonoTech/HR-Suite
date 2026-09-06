# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Mirror the employee's current salary structure onto the Employee record.

The Salary tab used to show a bank account and nothing about what the person is
actually paid. This module fills that gap: it reads the employee's active
Salary Structure Assignment, expands the structure into real component figures,
and writes them onto the Employee as a read-only table.

Why we do not compute the amounts ourselves
-------------------------------------------
Salary Structure rows can be flat amounts, formulas over `base`, or conditional.
Re-implementing that arithmetic would drift from payroll the first time somebody
writes a formula we did not anticipate. Instead we ask HRMS to build a throwaway
Salary Slip (`for_preview=1`, never saved) and read the numbers it produced, so
this screen and the payslip can only ever agree.

The mirror is written with `frappe.db` rather than `employee.save()` on purpose:
these are derived fields, and saving the Employee would fire the whole Employee
validate/on_update chain (including our own hooks) every time a salary structure
is assigned.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, today

COMPONENTS_FIELD = "custom_salary_components"
CHILD_DOCTYPE = "Employee Salary Component"


def get_current_assignment(employee: str, as_on=None) -> dict | None:
	"""Latest submitted Salary Structure Assignment in force on `as_on`."""
	as_on = getdate(as_on or today())
	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters={"employee": employee, "docstatus": 1, "from_date": ["<=", as_on]},
		fields=["name", "salary_structure", "base", "from_date", "currency"],
		order_by="from_date desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def _build_preview_slip(assignment: dict, employee: str, as_on=None):
	"""Ask HRMS to evaluate the structure for this employee. Never saved."""
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

	return make_salary_slip(
		assignment["salary_structure"],
		employee=employee,
		posting_date=getdate(as_on or today()),
		for_preview=1,
		ignore_permissions=True,
	)


def sync_employee_salary(employee: str, as_on=None) -> dict:
	"""Rebuild the salary mirror on one Employee. Returns a short result dict."""
	if not frappe.db.exists("Employee", employee):
		return {"employee": employee, "synced": False, "reason": "no such employee"}

	assignment = get_current_assignment(employee, as_on)

	# Clear first, so an employee whose assignment was cancelled does not keep
	# showing figures that no longer have a document behind them.
	frappe.db.delete(CHILD_DOCTYPE, {"parent": employee, "parentfield": COMPONENTS_FIELD})

	if not assignment:
		_write_header(employee, None, 0.0, 0.0, 0.0)
		return {"employee": employee, "synced": True, "components": 0, "reason": "no submitted assignment"}

	try:
		slip = _build_preview_slip(assignment, employee, as_on)
	except Exception:
		# A structure that cannot be evaluated (bad formula, missing account) must
		# not block whatever the user was actually doing — record it and move on.
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Salary snapshot failed for {employee}",
		)
		_write_header(employee, assignment, 0.0, 0.0, 0.0)
		return {"employee": employee, "synced": False, "reason": "structure could not be evaluated"}

	idx = 0
	earnings = deductions = 0.0
	for component_type, rows in (("Earning", slip.get("earnings") or []), ("Deduction", slip.get("deductions") or [])):
		for row in rows:
			amount = flt(row.get("amount"))
			if not amount:
				continue  # a zero row tells the reader nothing
			idx += 1
			if component_type == "Earning":
				earnings += amount
			else:
				deductions += amount
			frappe.get_doc(
				{
					"doctype": CHILD_DOCTYPE,
					"parent": employee,
					"parenttype": "Employee",
					"parentfield": COMPONENTS_FIELD,
					"idx": idx,
					"salary_component": row.get("salary_component"),
					"component_type": component_type,
					"amount": amount,
					"depends_on_payment_days": row.get("depends_on_payment_days") or 0,
				}
			).insert(ignore_permissions=True)

	_write_header(employee, assignment, earnings, deductions, earnings - deductions)
	return {"employee": employee, "synced": True, "components": idx, "net": earnings - deductions}


def _write_header(employee: str, assignment: dict | None, earnings: float, deductions: float, net: float) -> None:
	frappe.db.set_value(
		"Employee",
		employee,
		{
			"custom_salary_structure": (assignment or {}).get("salary_structure"),
			"custom_salary_base": flt((assignment or {}).get("base")),
			"custom_salary_effective_from": (assignment or {}).get("from_date"),
			"custom_total_earnings": flt(earnings),
			"custom_total_deductions": flt(deductions),
			"custom_net_salary": flt(net),
			"custom_salary_synced_on": now_datetime(),
		},
		update_modified=False,
	)


# ─── Hook entry points ──────────────────────────────────────────────────────────
def on_salary_structure_assignment_change(doc, method=None):
	"""Keep the Employee mirror in step with the assignment that drives it."""
	if not doc.get("employee"):
		return
	sync_employee_salary(doc.employee)


# ─── API ────────────────────────────────────────────────────────────────────────
@frappe.whitelist()
def refresh_salary_snapshot(employee: str, as_on: str | None = None) -> dict:
	"""Refresh one employee's salary mirror from the desk.

	Reads salary figures, so it requires read access to that Employee.
	"""
	if not isinstance(employee, str) or not employee:
		frappe.throw(_("Employee is required"))
	if not frappe.has_permission("Employee", "read", doc=employee):
		frappe.throw(_("Not permitted to read {0}").format(employee), frappe.PermissionError)

	result = sync_employee_salary(employee, as_on)
	frappe.db.commit()
	return result


@frappe.whitelist()
def rebuild_all_salary_snapshots(company: str | None = None) -> dict:
	"""One-off/scheduled rebuild across active employees. Manager-only."""
	if not frappe.has_permission("Employee", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	filters = {"status": "Active"}
	if company:
		filters["company"] = company

	employees = frappe.get_all("Employee", filters=filters, pluck="name")
	synced = 0
	for name in employees:
		if sync_employee_salary(name).get("synced"):
			synced += 1
	frappe.db.commit()
	return {"total": len(employees), "synced": synced}
