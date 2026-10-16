"""Gratuity Liability: what the company owes each active employee in end-of-service gratuity today.

Two figures per employee, both from the Country Config policy and worked as if the employment ended
on the As On date: if the company ends it (full gratuity, or none where a country forfeits), and if
the employee resigns (the resignation factors). Amounts are in each employee's own currency; the
total row adds only when one currency is in scope.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hr_suite.hr_suite.utils import calculate_settlement, get_employee_work_country


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 130},
		{"fieldname": "country", "label": _("Country"), "fieldtype": "Data", "width": 70},
		{"fieldname": "date_of_joining", "label": _("Joined"), "fieldtype": "Date", "width": 100},
		{"fieldname": "service_years", "label": _("Qualifying Years"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "wage_base", "label": _("Wage Base"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "liability_termination", "label": _("If Company Ends It"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "liability_resignation", "label": _("If Employee Resigns"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 80},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	as_on = getdate(filters.get("as_on") or today())
	employee = frappe.qb.DocType("Employee")
	query = (
		frappe.qb.from_(employee)
		.select(employee.name, employee.employee_name, employee.company, employee.date_of_joining)
		.where((employee.status == "Active") & (employee.date_of_joining < as_on))
		.orderby(employee.company).orderby(employee.employee_name)
	)
	for field in ("company", "department"):
		if filters.get(field):
			query = query.where(employee[field] == filters[field])

	rows = []
	for emp in query.run(as_dict=True):
		country = get_employee_work_country(emp.name)
		currency = frappe.get_cached_value("Company", emp.company, "default_currency")
		row = {"employee": emp.name, "employee_name": emp.employee_name, "company": emp.company, "country": country,
			"date_of_joining": emp.date_of_joining, "currency": currency}
		try:
			ended = calculate_settlement(emp.name, "Termination by Employer", as_on)
			resigned = calculate_settlement(emp.name, "Resignation", as_on)
		except Exception as error:
			row["note"] = _("Not calculated: {0}").format(str(error)[:120])
			rows.append(row)
			continue

		row.update(
			service_years=flt(ended.get("qualifying_days") / 365.0 if ended.get("qualifying_days") else ended.get("years_of_service"), 2),
			wage_base=flt(ended.get("basic_salary")),
			liability_termination=flt(ended.get("net_entitlement")),
			liability_resignation=flt(resigned.get("net_entitlement")),
			note=ended.get("factor_label") if flt(ended.get("net_entitlement")) == 0 else "",
		)
		rows.append(row)
	return rows
