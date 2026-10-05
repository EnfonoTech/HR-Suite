"""Keep leave days out of regular payroll, and take back what a rejoin undoes.

A leave salary settlement pays the leave days itself. HRMS, meanwhile, treats an approved
annual-leave day as a PAID day, so month-end payroll would pay those same days again. The
fix is the one the older Annual Leave Disbursement already uses and payroll already reads:
an Additional Salary DEDUCTION on the covering payslip, one per calendar month, through the
Leave Salary Recovery component. This module is that mechanism, shared by the settlement's
exclusion of the leave days and by its rejoin adjustments.

Each deduction is a fixed sum (the component does not depend on payment days), is refused
when the month's payslip is already submitted (it could never be taken), and is cancelled
when the settlement is. Nothing here builds SQL from strings.
"""

import frappe
from frappe import _
from frappe.utils import cstr, flt, formatdate, getdate

from hr_suite.hr_suite.utils import get_leave_salary_recovery_component, get_leave_salary_terms

ERROR_TITLE = "HR Suite: leave salary payroll adjustment"
MONEY_PRECISION = 3


def refuse_if_payroll_already_ran(employee, payroll_date, amount, currency):
	"""A month already paid can never read this deduction, so do not book one."""
	slip = frappe.db.get_value(
		"Salary Slip",
		{
			"employee": employee,
			"docstatus": 1,
			"start_date": ["<=", payroll_date],
			"end_date": [">=", payroll_date],
		},
		"name",
	)
	if not slip:
		return
	frappe.throw(
		_("Salary Slip {0} for {1} is already submitted, so the {2} {3} adjustment for that month "
		  "can never be taken. Cancel and re-run that payslip first, or settle it by hand outside payroll.").format(
			slip, formatdate(payroll_date), flt(amount), currency
		),
		title=_("Payroll Already Run"),
	)


def prepare_component(employee, company, expense_account):
	"""(component name, currency) for the deductions, or throws with a finished sentence."""
	from hr_suite.hr_suite.integrations.hrms import ensure_salary_component_account, get_employee_payroll_currency

	terms = get_leave_salary_terms(employee)
	component = get_leave_salary_recovery_component(company, terms.get("recovery_component"))
	ok, reason = ensure_salary_component_account(
		component,
		company,
		component_type="Deduction",
		fallback_account=expense_account,
		depends_on_payment_days=0,
		error_title=ERROR_TITLE,
	)
	if not ok:
		frappe.throw(reason, title=_("Leave Salary Cannot Be Kept Out Of Payroll"))

	currency = get_employee_payroll_currency(employee, None, company)
	if not currency:
		frappe.throw(
			_("{0} has no submitted Salary Structure Assignment, so payroll cannot be adjusted for this leave.").format(
				employee
			),
			title=_("No Salary Structure"),
		)
	return component, currency


def book_deduction(doc, component, currency, payroll_date, amount):
	"""One submitted Additional Salary deduction tied to `doc`. Returns its name."""
	amount = flt(amount, MONEY_PRECISION)
	if amount <= 0:
		return None
	refuse_if_payroll_already_ran(doc.employee, payroll_date, amount, currency)
	row = frappe.get_doc(
		{
			"doctype": "Additional Salary",
			"employee": doc.employee,
			"company": doc.company,
			"currency": currency,
			"salary_component": component,
			"amount": amount,
			"payroll_date": getdate(payroll_date),
			"is_recurring": 0,
			"ref_doctype": doc.doctype,
			"ref_docname": doc.name,
			# An extra deduction alongside whatever the structure holds, never an overwrite.
			"overwrite_salary_structure_amount": 0,
			"deduct_full_tax_on_selected_payroll_date": 0,
		}
	)
	row.insert(ignore_permissions=True)
	row.submit()
	return row.name


def cancel_deductions(names):
	"""Cancel booked deductions. A payslip that already took one stops the whole cancellation."""
	for name in names or []:
		if frappe.db.get_value("Additional Salary", name, "docstatus") == 1:
			frappe.get_doc("Additional Salary", name).cancel()


def month_amounts(gross_monthly, days_per_month, chunks):
	"""{month_start: deduction} for leave days spread over months, each capped at one month's pay."""
	daily = flt(gross_monthly) / (flt(days_per_month) or 30.0)
	return {
		month_start: min(flt(gross_monthly), flt(daily * days, MONEY_PRECISION))
		for month_start, days in chunks
	}


def load_json(value):
	import json

	try:
		return json.loads(cstr(value)) if value else []
	except ValueError:
		return []


def dump_json(value):
	import json

	return json.dumps(value, default=str)
