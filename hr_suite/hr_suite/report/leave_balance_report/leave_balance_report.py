"""
Leave Balance Report

Annual-leave entitlement and consumption per employee.

Two leave systems can coexist on this site and they are DISJOINT:

  * Hr Suite's own submittable `Annual Leave` doctype, which writes NO Leave Ledger
    Entry and is invisible to every HRMS leave report, and
  * HRMS's Leave Application -> Leave Ledger Entry, which Hr Suite never reads.

Reading only one of them reports zero consumption for every employee whose leave was
recorded in the other — which is exactly what this report used to do. It now reads
both, shows them in separate columns, and totals them, so neither source is hidden.
"""
import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, today

from hr_suite.hr_suite.utils import get_annual_leave_days_taken, get_annual_leave_entitlement


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 140},
		{"fieldname": "date_of_joining", "label": _("Joining Date"), "fieldtype": "Date", "width": 130},
		{"fieldname": "years_of_service", "label": _("Years"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "entitlement", "label": _("Entitlement"), "fieldtype": "Int", "width": 110},
		{"fieldname": "leave_allocated", "label": _("Allocated (Leave Ledger)"), "fieldtype": "Float", "precision": 1, "width": 170},
		{"fieldname": "suite_leave_taken", "label": _("Taken (Annual Leave)"), "fieldtype": "Float", "precision": 1, "width": 160},
		{"fieldname": "ledger_leave_taken", "label": _("Taken (Leave Ledger)"), "fieldtype": "Float", "precision": 1, "width": 160},
		{"fieldname": "leave_taken", "label": _("Total Taken"), "fieldtype": "Float", "precision": 1, "width": 120},
		{"fieldname": "leave_balance", "label": _("Balance"), "fieldtype": "Float", "precision": 1, "width": 110},
	]


def get_data(filters):
	year = cint(filters.get("year")) or getdate(today()).year

	conditions = []
	values = {}

	if not filters.get("include_inactive"):
		conditions.append("e.status = 'Active'")
	if filters.get("company"):
		conditions.append("e.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("department"):
		conditions.append("e.department = %(department)s")
		values["department"] = filters["department"]
	if filters.get("employee"):
		conditions.append("e.name = %(employee)s")
		values["employee"] = filters["employee"]

	where = "WHERE " + " AND ".join(conditions) if conditions else ""

	employees = frappe.db.sql(
		f"""
		SELECT e.name AS employee, e.employee_name, e.department,
			e.date_of_joining, e.company
		FROM `tabEmployee` e
		{where}
		ORDER BY e.employee_name
		""",
		values,
		as_dict=True,
	)

	if not employees:
		return []

	# One grouped query for every employee instead of a lookup per row.
	ledger = get_ledger_totals([emp.employee for emp in employees], filters.get("leave_type"), year)

	as_on = today()
	result = []

	for emp in employees:
		joining = getdate(emp.date_of_joining) if emp.date_of_joining else None
		years = flt(date_diff(as_on, joining)) / 365.0 if joining else 0.0

		entitlement = cint(get_annual_leave_entitlement(emp.employee))
		suite_taken = flt(get_annual_leave_days_taken(emp.employee, year))

		emp_ledger = ledger.get(emp.employee) or {}
		ledger_allocated = flt(emp_ledger.get("allocated"))
		ledger_taken = flt(emp_ledger.get("taken"))

		total_taken = suite_taken + ledger_taken

		result.append(
			{
				"employee": emp.employee,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"date_of_joining": emp.date_of_joining,
				"years_of_service": flt(years, 2),
				"entitlement": entitlement,
				"leave_allocated": ledger_allocated,
				"suite_leave_taken": suite_taken,
				"ledger_leave_taken": ledger_taken,
				"leave_taken": total_taken,
				"leave_balance": flt(entitlement) - total_taken,
			}
		)

	return result


def get_ledger_totals(employees, leave_type, year):
	"""Allocated and consumed days per employee from the HRMS Leave Ledger, for `year`.

	`leaves` is positive for an allocation and negative for consumption. An expiry
	entry is also negative but carries is_expired = 1 — it withdraws an unused
	allocation and is not leave the employee took, so it is netted off the allocation
	instead of being counted as consumption.
	"""
	if not employees or not frappe.db.exists("DocType", "Leave Ledger Entry"):
		return {}

	values = {
		"employees": employees,
		"year_start": f"{cint(year)}-01-01",
		"year_end": f"{cint(year)}-12-31",
	}

	leave_type_condition = "AND lle.leave_type LIKE %(leave_type_pattern)s"
	if leave_type:
		leave_type_condition = "AND lle.leave_type = %(leave_type)s"
		values["leave_type"] = leave_type
	else:
		# Scope of this report is annual leave; the filter narrows it to one type.
		values["leave_type_pattern"] = "%Annual%"

	rows = frappe.db.sql(
		f"""
		SELECT
			lle.employee,
			SUM(CASE WHEN lle.leaves > 0 THEN lle.leaves ELSE 0 END)
				- SUM(CASE WHEN lle.leaves < 0 AND lle.is_expired = 1 THEN -lle.leaves ELSE 0 END)
				AS allocated,
			SUM(CASE WHEN lle.leaves < 0 AND IFNULL(lle.is_expired, 0) = 0 THEN -lle.leaves ELSE 0 END)
				AS taken
		FROM `tabLeave Ledger Entry` lle
		WHERE lle.docstatus = 1
			AND lle.employee IN %(employees)s
			AND lle.from_date <= %(year_end)s
			AND lle.to_date >= %(year_start)s
			{leave_type_condition}
		GROUP BY lle.employee
		""",
		values,
		as_dict=True,
	)

	return {row.employee: row for row in rows}
