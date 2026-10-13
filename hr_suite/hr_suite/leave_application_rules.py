"""Two country-policy rules on the stock Leave Application, plus the Leave Policy link behind one.

1. Annual leave before the minimum service (Country Config > Annual Leave Before Minimum
   Service): Allow does nothing here (leave salary is simply not paid, see the Leave Salary
   Settlement); Block refuses the application; Unpaid lets it through and has payroll deduct
   those days, one Additional Salary deduction per calendar month.

2. "Can Be Taken From Leave" on a Leave Policy row: leave of type X draws its days from the
   balance of type Y (Emergency Leave taken from Annual Leave). The days are checked against
   Y's balance when the application is saved and, once it is approved, the ledger entry HRMS
   wrote against X is moved to Y, so Y's balance falls and X's never does. Cancelling the
   application removes the entry as HRMS always does (it deletes by transaction name).

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from hr_suite.hr_suite import leave_payroll as payroll
from hr_suite.hr_suite.leave_accrual import OVERRIDE_ROLE
from hr_suite.hr_suite.policy import LEDGER_ENGINE, get_policy

UNPAID_COMPONENT = "Leave Before Minimum Service Deduction"


# ── hooks ─────────────────────────────────────────────────────────────────────


def validate(doc, method=None):
	_check_minimum_service(doc)
	_check_source_balance(doc)


def on_submit(doc, method=None):
	if doc.status != "Approved":
		return
	_move_ledger_to_source(doc)
	_book_unpaid_deductions(doc)


def on_cancel(doc, method=None):
	payroll.cancel_deductions([row["name"] for row in payroll.load_json(doc.get("unpaid_deduction_rows"))])
	doc.db_set("unpaid_deduction_rows", "", update_modified=False)


def validate_policy_rows(doc, method=None):
	"""Leave Policy: a leave type cannot draw on itself, and a drawing type may go below zero."""
	for row in doc.get("leave_policy_details") or []:
		source = row.get("can_be_taken_from_leave")
		if not source:
			continue
		if source == row.leave_type:
			frappe.throw(
				_("Row {0}: {1} cannot be taken from itself.").format(row.idx, frappe.bold(row.leave_type)),
				title=_("Invalid Leave Policy"),
			)
		if not cint(frappe.db.get_value("Leave Type", row.leave_type, "allow_negative")):
			# HRMS refuses an application when the type's OWN balance is empty. The check that
			# counts here is the source's, done by validate() above, so the type must not refuse.
			frappe.db.set_value("Leave Type", row.leave_type, "allow_negative", 1)
			frappe.msgprint(
				_("{0} now allows a negative balance of its own: its days are taken from {1} and checked there.").format(
					frappe.bold(row.leave_type), frappe.bold(source)
				),
				indicator="blue",
			)


# ── source of the days ────────────────────────────────────────────────────────


def get_source_leave_type(employee, leave_type, on_date):
	"""The leave type `leave_type` is taken from for this employee on that date, or None."""
	assignment = frappe.qb.DocType("Leave Policy Assignment")
	detail = frappe.qb.DocType("Leave Policy Detail")
	row = (
		frappe.qb.from_(assignment)
		.inner_join(detail)
		.on(detail.parent == assignment.leave_policy)
		.select(detail.can_be_taken_from_leave)
		.where(
			(assignment.employee == employee)
			& (assignment.docstatus == 1)
			& (assignment.effective_from <= getdate(on_date))
			& (assignment.effective_to >= getdate(on_date))
			& (detail.leave_type == leave_type)
			& (detail.can_be_taken_from_leave.isnotnull())
			& (detail.can_be_taken_from_leave != "")
		)
		.orderby(assignment.effective_from, order=frappe.qb.desc)
		.limit(1)
	).run()
	return row[0][0] if row else None


def _check_source_balance(doc):
	if not (doc.employee and doc.leave_type and doc.from_date and doc.to_date) or doc.status == "Rejected":
		return
	source = get_source_leave_type(doc.employee, doc.leave_type, doc.from_date)
	if not source:
		return

	from hrms.hr.doctype.leave_application.leave_application import (
		get_leave_balance_on,
		get_number_of_leave_days,
	)

	days = flt(
		get_number_of_leave_days(doc.employee, doc.leave_type, doc.from_date, doc.to_date, doc.half_day, doc.half_day_date)
	)
	balance = flt(get_leave_balance_on(doc.employee, source, doc.from_date))
	if days > balance and not _may_go_negative(doc, source):
		frappe.throw(
			_("{0} is taken from {1}, which has {2} day(s) left; {3} are needed.").format(
				frappe.bold(doc.leave_type), frappe.bold(source), flt(balance, 2), flt(days, 2)
			),
			title=_("Insufficient Balance"),
		)


def _may_go_negative(doc, source):
	"""The source type may run below zero if its own setting says so; annual leave on the ledger engine
	only for HR with the Leave Override role, exactly as for an annual leave application itself."""
	if not cint(frappe.db.get_value("Leave Type", source, "allow_negative")):
		return False
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if policy.get("has_policy") and source == policy.annual_leave_type and policy.leave_accrual_engine == LEDGER_ENGINE:
		return OVERRIDE_ROLE in frappe.get_roles()
	return True


def _move_ledger_to_source(doc):
	source = get_source_leave_type(doc.employee, doc.leave_type, doc.from_date)
	if not source:
		return
	for name in frappe.get_all(
		"Leave Ledger Entry",
		filters={"transaction_name": doc.name, "transaction_type": "Leave Application", "leave_type": doc.leave_type, "docstatus": 1},
		pluck="name",
	):
		frappe.db.set_value("Leave Ledger Entry", name, "leave_type", source, update_modified=False)


# ── annual leave before the minimum service ───────────────────────────────────


def _is_early_annual_leave(doc):
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if not policy.get("has_policy") or doc.leave_type != policy.annual_leave_type:
		return None, 0
	joining = policy.get("date_of_joining")
	minimum = cint(policy.leave_salary_min_service_days)
	if not joining or not minimum or not doc.from_date:
		return None, 0
	if date_diff(doc.from_date, getdate(joining)) >= minimum:
		return None, 0
	return policy, minimum


def _check_minimum_service(doc):
	if doc.status == "Rejected" or not (doc.employee and doc.leave_type and doc.from_date):
		return
	policy, minimum = _is_early_annual_leave(doc)
	if policy and policy.annual_leave_before_min_service == "Block":
		frappe.throw(
			_("{0} has not completed the {1} days of service needed before annual leave can be taken "
			  "(joined {2}).").format(doc.employee_name or doc.employee, minimum, policy.date_of_joining),
			title=_("Minimum Service Not Met"),
		)


def _book_unpaid_deductions(doc):
	policy, _minimum = _is_early_annual_leave(doc)
	if not policy or policy.annual_leave_before_min_service != "Unpaid":
		return

	from hr_suite.hr_suite.utils import compute_leave_salary, split_days_by_month

	per_month = flt(policy.leave_salary_days_per_month) or 30.0
	monthly = flt(compute_leave_salary(doc.employee, per_month)["total"], payroll.MONEY_PRECISION)
	chunks = split_days_by_month(doc.from_date, doc.to_date)
	if not monthly or not chunks:
		return
	component = payroll.ensure_deduction_component(
		UNPAID_COMPONENT,
		"LMS",
		"Takes back pay for annual leave taken before the minimum service. Created by HR Suite.",
	)
	from hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement import (
		resolve_leave_salary_accounts,
	)

	component, currency = payroll.prepare_component(
		doc.employee, doc.company, resolve_leave_salary_accounts(doc.company)[0], component=component
	)
	booked = []
	for month_start, amount in payroll.month_amounts(monthly, per_month, chunks).items():
		name = payroll.book_deduction(doc, component, currency, max(getdate(month_start), getdate(doc.from_date)), amount)
		if name:
			booked.append({"name": name, "month": str(month_start), "amount": flt(amount, payroll.MONEY_PRECISION)})
	doc.db_set("unpaid_deduction_rows", payroll.dump_json(booked), update_modified=False)
