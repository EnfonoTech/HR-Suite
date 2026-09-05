# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt

"""Pre-Payroll Allocation Register.

Every allocation read onto a Payroll Preview for a company and period, grouped by
employee, with the source and origin documents as clickable links. Read-only: it reports
what the previews found, it never recomputes payroll.
"""

import frappe
from frappe import _
from frappe.utils import cstr, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	return get_columns(), get_data(filters)


def validate_filters(filters):
	if not filters.company:
		frappe.throw(_("Company is required."))

	if not (filters.from_date and filters.to_date):
		frappe.throw(_("From Date and To Date are required."))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_columns():
	return [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "entry_type",
			"label": _("Entry Type"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "salary_component",
			"label": _("Salary Component"),
			"fieldtype": "Link",
			"options": "Salary Component",
			"width": 160,
		},
		{
			"fieldname": "amount",
			"label": _("Amount"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "posting_date",
			"label": _("Posting Date"),
			"fieldtype": "Date",
			"width": 105,
		},
		{
			"fieldname": "source_doctype",
			"label": _("Source DocType"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 150,
		},
		{
			"fieldname": "source_name",
			"label": _("Source Document"),
			"fieldtype": "Dynamic Link",
			"options": "source_doctype",
			"width": 170,
		},
		{
			"fieldname": "origin_doctype",
			"label": _("Origin DocType"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 150,
		},
		{
			"fieldname": "origin_name",
			"label": _("Origin Document"),
			"fieldtype": "Dynamic Link",
			"options": "origin_doctype",
			"width": 170,
		},
		{
			"fieldname": "description",
			"label": _("Description"),
			"fieldtype": "Small Text",
			"width": 300,
		},
		{
			"fieldname": "payroll_preview",
			"label": _("Payroll Preview"),
			"fieldtype": "Link",
			"options": "Payroll Preview",
			"width": 150,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 90,
			"hidden": 1,
		},
	]


def get_data(filters):
	Preview = frappe.qb.DocType("Payroll Preview")
	Allocation = frappe.qb.DocType("Payroll Preview Allocation")

	query = (
		frappe.qb.from_(Allocation)
		.join(Preview)
		.on(Preview.name == Allocation.parent)
		.select(
			Allocation.employee,
			Allocation.employee_name,
			Allocation.entry_type,
			Allocation.salary_component,
			Allocation.amount,
			Allocation.posting_date,
			Allocation.source_doctype,
			Allocation.source_name,
			Allocation.origin_doctype,
			Allocation.origin_name,
			Allocation.description,
			Preview.name.as_("payroll_preview"),
			Preview.currency,
			Preview.last_refreshed_on,
			Preview.start_date.as_("preview_start_date"),
			Preview.end_date.as_("preview_end_date"),
		)
		.where(
			(Allocation.parenttype == "Payroll Preview")
			& (Preview.company == filters.company)
			& (Preview.start_date <= filters.to_date)
			& (Preview.end_date >= filters.from_date)
		)
		.orderby(Allocation.employee_name)
		.orderby(Allocation.employee)
		.orderby(Allocation.entry_type)
		.orderby(Allocation.posting_date)
	)

	if filters.employee:
		query = query.where(Allocation.employee == filters.employee)

	if filters.entry_type:
		query = query.where(Allocation.entry_type == filters.entry_type)

	if filters.payroll_preview:
		query = query.where(Preview.name == filters.payroll_preview)

	return deduplicate_by_source(query.run(as_dict=True))


def deduplicate_by_source(rows: list) -> list:
	"""Keep one row per source document PER PAYROLL PERIOD.

	Several Payroll Previews may cover the same period - a second one is exactly what a
	user makes after fixing something - and each of them mirrors the SAME underlying
	Additional Salary, advance or penalty. Reporting all of them would list every item
	once per preview and, with the total row on, add the same money up twice. The row
	from the most recently refreshed preview wins.

	The preview period is part of the key, and must stay part of it. The same source
	document legitimately recurs period after period - a recurring Additional Salary pays
	every month of its window, and one Employee Loan carries a separate installment in
	each month - and every one of those rows carries the SAME `source_name`. Keying on the
	source alone therefore collapses a twelve-month register down to a single occurrence
	and under-reports the commitment, which is the opposite of the defect this function
	exists to fix.
	"""
	newest = {}
	for row in rows:
		key = (
			cstr(row.get("preview_start_date")),
			cstr(row.get("preview_end_date")),
			row.get("employee"),
			row.get("source_doctype"),
			row.get("source_name"),
			row.get("entry_type"),
			row.get("salary_component"),
		)
		current = newest.get(key)
		if current is None or _refresh_order(row) > _refresh_order(current):
			newest[key] = row

	ordered = sorted(
		newest.values(),
		key=lambda row: (
			cstr(row.get("employee_name")),
			cstr(row.get("employee")),
			cstr(row.get("entry_type")),
			cstr(row.get("posting_date")),
			cstr(row.get("preview_start_date")),
		),
	)

	for row in ordered:
		row.pop("last_refreshed_on", None)
		row.pop("preview_start_date", None)
		row.pop("preview_end_date", None)

	return ordered


def _refresh_order(row) -> tuple:
	return (cstr(row.get("last_refreshed_on")), cstr(row.get("payroll_preview")))
