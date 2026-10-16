"""Monthly leave accrual into the Leave Accrual Ledger, and the annual-leave rules around it.

The ledger is the audit trail and the SECOND balance: every month is a separate row (days
worked, leave days, leave-salary days). The leave-days balance itself stays in HRMS, because
Leave Application, payroll and the stock leave reports all read it there, so each ledger row
also tops up the employee's annual-leave Leave Allocation. Salary days exist only here.

Runs for a country only when its Country Config says "Leave Accrual Engine = HR Suite
Ledger". Anything else keeps the stock HRMS earned-leave accrual, which this module never
touches, so an existing site changes behaviour only when HR switches the country over.

Month rules (policy spec): a full month earns exactly the monthly rate whatever its calendar
length; the joining month, the exit month, annual-leave days and unpaid days reduce it;
sick leave does not.

Nothing here builds SQL from strings. Every f-string or .format() below produces text for
the user or the log.
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	cint,
	date_diff,
	flt,
	get_first_day,
	get_last_day,
	getdate,
	today,
)

from hr_suite.hr_suite.policy import LEDGER_ENGINE, get_policy, months_of_service

OVERRIDE_ROLE = "HR Leave Override"
MAX_CATCH_UP_MONTHS = 36
STANDARD_MONTH = 30.0


def month_bounds(on_date):
	on_date = getdate(on_date)
	return get_first_day(on_date), get_last_day(on_date)


# ── pure month arithmetic ─────────────────────────────────────────────────────


def accrual_for_month(
	period_start,
	period_end,
	joining,
	relieving,
	annual_leave_days,
	unpaid_days,
	leave_per_month,
	salary_per_month,
	basis="Over 30 Days",
):
	"""Leave and leave-salary days earned in one calendar month. Pure.

	A month with nothing excluded earns the full monthly rate, whether it has 28 or 31
	days. Otherwise the days worked are the calendar days left after excluding the days
	before joining, the days after exit, annual-leave days and unpaid days, counted either
	over 30 ("Over 30 Days", the default: joining 9 March = 23/30) or scaled to the
	month ("Month Fraction": 23/31 of 30).
	"""
	period_start, period_end = getdate(period_start), getdate(period_end)
	calendar = date_diff(period_end, period_start) + 1

	before = max(date_diff(getdate(joining), period_start), 0) if joining else 0
	after = max(date_diff(period_end, getdate(relieving)), 0) if relieving else 0
	excluded = min(calendar, before + after + flt(annual_leave_days) + flt(unpaid_days))

	if excluded <= 0:
		days_worked = STANDARD_MONTH
	elif basis == "Month Fraction":
		days_worked = STANDARD_MONTH * (calendar - excluded) / calendar
	else:
		days_worked = max(min(STANDARD_MONTH, calendar - excluded), 0.0)

	return frappe._dict(
		days_worked=flt(days_worked, 2),
		excluded_days=flt(excluded, 2),
		leave_days=flt(flt(leave_per_month) * days_worked / STANDARD_MONTH, 2),
		salary_days=flt(flt(salary_per_month) * days_worked / STANDARD_MONTH, 2),
	)


# ── data the month needs ──────────────────────────────────────────────────────


def get_leave_days(employee, start, end, leave_type):
	"""Approved days of one leave type inside a window (a leave straddling it is clipped)."""
	start, end = getdate(start), getdate(end)
	la = frappe.qb.DocType("Leave Application")
	rows = (
		frappe.qb.from_(la)
		.select(la.from_date, la.to_date, la.total_leave_days)
		.where(
			(la.employee == employee)
			& (la.docstatus == 1)
			& (la.status == "Approved")
			& (la.leave_type == leave_type)
			& (la.from_date <= end)
			& (la.to_date >= start)
		)
	).run(as_dict=True)

	days = 0.0
	for row in rows:
		leave_from, leave_to = getdate(row.from_date), getdate(row.to_date)
		if leave_from >= start and leave_to <= end:
			days += flt(row.total_leave_days)
		else:
			days += date_diff(min(leave_to, end), max(leave_from, start)) + 1
	return days


def get_salary_days_balance(employee, as_on=None):
	"""Earned leave-salary days: every ledger row for the employee up to as_on."""
	ledger = frappe.qb.DocType("Leave Accrual Ledger")
	query = frappe.qb.from_(ledger).select(ledger.salary_days).where(ledger.employee == employee)
	if as_on:
		query = query.where(ledger.period_end <= getdate(as_on))
	return flt(sum(flt(r.salary_days) for r in query.run(as_dict=True)), 2)


def _ledger_rows(employee, sources):
	ledger = frappe.qb.DocType("Leave Accrual Ledger")
	return (
		frappe.qb.from_(ledger)
		.select(ledger.name, ledger.period_start, ledger.period_end, ledger.source)
		.where((ledger.employee == employee) & (ledger.source.isin(list(sources))))
	).run(as_dict=True)


# ── HRMS allocation top-up ────────────────────────────────────────────────────


def _allocation_for(employee, leave_type, on_date):
	rows = frappe.get_all(
		"Leave Allocation",
		filters={
			"employee": employee,
			"leave_type": leave_type,
			"docstatus": 1,
			"from_date": ["<=", on_date],
			"to_date": [">=", on_date],
		},
		fields=["name"],
		order_by="from_date desc",
		limit=1,
	)
	return rows[0].name if rows else None


def _create_allocation(employee, leave_type, on_date, days):
	"""A Leave Allocation covering on_date, opened with `days`, inside the company's Leave Period."""
	from hr_suite.hr_suite.leave_setup import get_leave_period

	company, joining = frappe.db.get_value("Employee", employee, ["company", "date_of_joining"])
	period = get_leave_period(company, on_date)
	if period:
		start, end = frappe.db.get_value("Leave Period", period, ["from_date", "to_date"])
	else:
		start, end = getdate(on_date).replace(month=1, day=1), getdate(on_date).replace(month=12, day=31)

	allocation = frappe.get_doc(
		{
			"doctype": "Leave Allocation",
			"employee": employee,
			"leave_type": leave_type,
			"from_date": max(getdate(start), getdate(joining)),
			"to_date": end,
			"new_leaves_allocated": days,
			"leave_period": period or None,
		}
	)
	allocation.insert(ignore_permissions=True)
	allocation.submit()
	return allocation.name


def _credit_new_or_later_allocation(employee, leave_type, on_date, days):
	"""No allocation covers the month: open one, or, if HRMS refuses to back-date it, use the next.

	HRMS will not create an allocation that starts before an existing one that carries leave
	forward (BackDatedAllocationError), which is the case when the ledger starts accruing in
	December of a year whose following year's allocation already exists. The days are then
	credited to the earliest later allocation instead, dated on its first day, so the balance is
	right from then on and the accrual is not lost.
	"""
	from hrms.hr.doctype.leave_allocation.leave_allocation import BackDatedAllocationError
	from hrms.hr.utils import create_additional_leave_ledger_entry

	frappe.db.savepoint("hrs_new_allocation")
	try:
		return _create_allocation(employee, leave_type, on_date, days)
	except BackDatedAllocationError:
		# only the refused insert is undone, never the ledger rows already written this run
		frappe.db.rollback(save_point="hrs_new_allocation")
		later = frappe.get_all(
			"Leave Allocation",
			filters={"employee": employee, "leave_type": leave_type, "docstatus": 1, "from_date": [">", getdate(on_date)]},
			fields=["name", "from_date"],
			order_by="from_date asc",
			limit=1,
		)
		if not later:
			raise
		allocation = frappe.get_doc("Leave Allocation", later[0].name)
		allocation.db_set("total_leaves_allocated", flt(allocation.total_leaves_allocated) + days, update_modified=False)
		create_additional_leave_ledger_entry(allocation, days, getdate(allocation.from_date))
		return allocation.name


def post_to_hrms(employee, leave_type, days, on_date):
	"""Add `days` (negative to take off) to the employee's HRMS annual-leave balance.

	Mirrors what HRMS's own earned-leave job does to a live allocation: raise its total and
	write an additional Leave Ledger Entry. Creates the allocation when none covers the date
	and the amount is positive. Returns the allocation name, or None when nothing was posted.
	"""
	from hrms.hr.utils import create_additional_leave_ledger_entry

	days = flt(days)
	if not days:
		return None

	name = _allocation_for(employee, leave_type, on_date)
	if not name:
		if days < 0:
			frappe.msgprint(
				_("{0} has no {1} allocation covering {2}, so the {3} day reduction was recorded in the ledger only.").format(
					employee, leave_type, on_date, abs(days)
				),
				indicator="orange",
			)
			return None
		return _credit_new_or_later_allocation(employee, leave_type, on_date, days)

	allocation = frappe.get_doc("Leave Allocation", name)
	allocation.db_set("total_leaves_allocated", flt(allocation.total_leaves_allocated) + days, update_modified=False)
	create_additional_leave_ledger_entry(allocation, days, getdate(on_date))
	return name


# ── the job ───────────────────────────────────────────────────────────────────


def _first_period_start(policy, joining, employee):
	"""The first month this employee still has to accrue, or None when none is due."""
	start = get_first_day(getdate(joining))
	if policy.leave_ledger_start_date:
		start = max(start, get_first_day(getdate(policy.leave_ledger_start_date)))

	done = _ledger_rows(employee, ("Accrual", "Opening"))
	if done:
		last_end = max(getdate(r.period_end) for r in done)
		start = max(start, get_first_day(add_months(last_end, 1)))
	return start


def accrue_employee(employee, through=None):
	"""Write every ledger month still owed to one employee, up to the month `through` falls in.

	Safe to repeat: months already in the ledger are skipped, and a missed run is made up
	on the next one. Returns the names of the rows created.
	"""
	through = getdate(through or add_months(today(), -1))
	last_period_start = get_first_day(through)
	policy = get_policy(employee, on_date=get_last_day(through))
	if not policy.get("has_policy") or policy.leave_accrual_engine != LEDGER_ENGINE:
		return []

	joining, relieving = frappe.db.get_value("Employee", employee, ["date_of_joining", "relieving_date"])
	if not joining:
		return []

	from hr_suite.hr_suite.gratuity import get_unpaid_days

	created = []
	period_start = _first_period_start(policy, joining, employee)
	if date_diff(last_period_start, period_start) > MAX_CATCH_UP_MONTHS * 31:
		frappe.log_error(
			"{0} is more than {1} months behind; accruing the most recent {1}.".format(employee, MAX_CATCH_UP_MONTHS),
			"HR Suite: leave accrual catch-up capped",
		)
		period_start = add_months(last_period_start, -(MAX_CATCH_UP_MONTHS - 1))

	while period_start <= last_period_start:
		period_end = get_last_day(period_start)
		month_policy = get_policy(employee, on_date=period_end)
		annual = month_policy.get("annual") or frappe._dict()

		if getdate(joining) <= period_end and not (relieving and getdate(relieving) < period_start):
			result = accrual_for_month(
				period_start,
				period_end,
				joining,
				relieving,
				get_leave_days(employee, period_start, period_end, policy.annual_leave_type),
				get_unpaid_days(employee, period_start, period_end),
				flt(annual.get("leave_days_per_month")),
				flt(annual.get("salary_days_per_month")),
				policy.accrual_proration_basis,
			)
			row = frappe.get_doc(
				{
					"doctype": "Leave Accrual Ledger",
					"employee": employee,
					"source": "Accrual",
					"period_start": period_start,
					"period_end": period_end,
					"days_worked": result.days_worked,
					"leave_days": result.leave_days,
					"salary_days": result.salary_days,
					"remarks": _("Excluded {0} day(s); {1} leave band; {2}.").format(
						result.excluded_days,
						(month_policy.get("annual_band") or {}).get("label") or _("no"),
						", ".join(annual.get("overrides_used") or []) or _("no override"),
					),
				}
			)
			row.insert(ignore_permissions=True)
			created.append(row.name)

		period_start = get_first_day(add_months(period_start, 1))

	return created


def run_monthly_accrual(through=None):
	"""Scheduler entry: accrue every employee of a ledger-engine country. One failure never stops the rest."""
	summary = {"employees": 0, "rows": 0, "failed": []}
	through = getdate(through or add_months(today(), -1))
	window_start = get_first_day(through)

	employee_table = frappe.qb.DocType("Employee")
	employees = (
		frappe.qb.from_(employee_table)
		.select(employee_table.name)
		.where(
			(employee_table.date_of_joining <= get_last_day(through))
			& (
				(employee_table.status == "Active")
				| (employee_table.relieving_date >= window_start)
			)
		)
	).run(as_dict=True)

	for employee in employees:
		try:
			created = accrue_employee(employee.name, through)
			if created:
				summary["employees"] += 1
				summary["rows"] += len(created)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			summary["failed"].append(employee.name)
			frappe.log_error(frappe.get_traceback(), "HR Suite: leave accrual failed for " + employee.name)
	return summary


def legacy_annual_allocations(on_date=None):
	"""Annual-leave allocations that cover the date but that the ledger did not make.

	On the ledger engine the HRMS allocation is the ledger's own running total. An allocation
	made some other way (a Leave Policy Assignment of the old set-up, or by hand) sits underneath
	it, so the balance is that allocation PLUS everything accrued. Returned so HR can cancel it or
	fold it into the opening balance. [{"employee", "allocation", "leave_type", "days"}]
	"""
	on_date = getdate(on_date or today())
	allocations = frappe.get_all(
		"Leave Allocation",
		filters={"docstatus": 1, "from_date": ["<=", on_date], "to_date": [">=", on_date], "new_leaves_allocated": [">", 0]},
		fields=["name", "employee", "leave_type", "new_leaves_allocated"],
	)
	made = {r.leave_allocation for r in frappe.get_all("Leave Accrual Ledger", fields=["leave_allocation"]) if r.leave_allocation}
	policies, out = {}, []
	for row in allocations:
		if row.name in made:
			continue
		if row.employee not in policies:
			policies[row.employee] = get_policy(row.employee, on_date=on_date)
		policy = policies[row.employee]
		if policy.get("has_policy") and policy.leave_accrual_engine == LEDGER_ENGINE and row.leave_type == policy.annual_leave_type:
			out.append({"employee": row.employee, "allocation": row.name, "leave_type": row.leave_type, "days": flt(row.new_leaves_allocated, 2)})
	return out


@frappe.whitelist()
def run_accrual(employee=None, through=None):
	"""Run (or catch up) the accrual by hand, for one employee or everyone. HR Manager only.

	Also reports the annual-leave allocations the ledger did not make, which would add to the balance.
	"""
	frappe.only_for(("HR Manager", "System Manager"))
	if employee:
		result = {"employees": 1, "rows": len(accrue_employee(employee, through)), "failed": []}
	else:
		result = run_monthly_accrual(through)
	result["legacy_allocations"] = legacy_annual_allocations()
	return result


# ── annual-leave rules on a Leave Application ────────────────────────────────


def _balance_for_consumption(doc) -> float:
	"""The balance this application would draw on, the way HRMS's own check measures it.

	Computed here rather than read from Leave Application.leave_balance: that field is
	filled in by the browser form only, so on the server it is empty and reads as zero.
	"""
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	result = get_leave_balance_on(
		doc.employee,
		doc.leave_type,
		doc.from_date,
		doc.to_date,
		consider_all_leaves_in_the_allocation_period=True,
		for_consumption=True,
	)
	return flt(result.get("leave_balance_for_consumption"))


def check_annual_leave_rules(doc, method=None):
	"""Self-service stays inside the balance and the waiting period; only HR may go beyond.

	Applies to the annual-leave type of a ledger-engine country. The leave type allows a
	negative balance (so HRMS lets a long leave through and later accruals bring it back
	to zero), which makes THIS the only gate: without the HR Leave Override role an
	application may not exceed the balance or start before the eligibility date.
	"""
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if not policy.get("has_policy") or policy.leave_accrual_engine != LEDGER_ENGINE:
		return
	if doc.leave_type != policy.annual_leave_type:
		return
	if OVERRIDE_ROLE in frappe.get_roles():
		return

	waiting = cint(policy.annual_leave_eligible_after_months)
	if waiting and months_of_service(policy.date_of_joining, doc.from_date) < waiting:
		frappe.throw(
			_("Annual leave can be taken after {0} months of service. Ask HR to approve it as an exception.").format(waiting),
			title=_("Not yet eligible"),
		)

	balance = _balance_for_consumption(doc)
	if flt(doc.total_leave_days) > balance:
		frappe.throw(
			_("You are asking for {0} days but the balance is {1}. Only HR can approve annual leave beyond the balance.").format(
				flt(doc.total_leave_days), balance
			),
			title=_("Beyond leave balance"),
		)
