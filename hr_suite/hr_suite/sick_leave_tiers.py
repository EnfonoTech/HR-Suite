"""Sick leave paid in tiers, split automatically on the Leave Application.

The employee applies for "Sick Leave" and nothing else. The days of that application are laid
along the country's pay tiers (Country Config > Sick Leave Policy) starting from what the
employee has already used in the leave year, so day 31 of a Saudi employee's year is the
first at 75%. HRMS keeps paying the leave in full; payroll takes the unpaid share back with an
Additional Salary deduction, one per calendar month, through the "Sick Leave Deduction"
component (hr_suite.leave_payroll). Sick leave never touches the annual-leave balance.

Applies to a country only when its Country Config ticks "Split Sick Leave Into Pay Tiers
Automatically": a site that already models tiers as separate part-pay Leave Types would
otherwise have the pay reduced twice.

Because tiers are consumed in date order, an application submitted late can change the split
of ones after it. Every submit and cancel therefore re-splits every sick leave from the affected
date onward, in date order, and re-books only what changed. A month whose payslip is already
submitted is never touched: the difference is booked as an adjustment on the next open payroll
date, a further deduction when more is unpaid or an earning when less is.

The span in which sick days count towards the tiers is Country Config > Sick Leave Pay Window:
the company Leave Period (the default), the calendar year, a rolling 12 months looking back from
each leave, or the service year from the joining anniversary.

Days before the employee is eligible (3 months in Bahrain and Qatar, after probation in the
UAE) are unpaid and do not use up any tier. Days past the last tier are unpaid too.

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate

from hr_suite.hr_suite import leave_payroll as payroll
from hr_suite.hr_suite.leave_accrual import OVERRIDE_ROLE
from hr_suite.hr_suite.policy import get_policy, months_of_service
from hr_suite.hr_suite.utils import get_employee_salary_components

SICK_COMPONENT = "Sick Leave Deduction"
ADJUSTMENT_COMPONENT = "Sick Leave Adjustment"
BEFORE_ELIGIBLE = "Before eligibility"
BEYOND_TIERS = "Beyond annual entitlement"


# ── pure ──────────────────────────────────────────────────────────────────────


def split_days(tiers, used_before, days, eligible_from=None):
	"""Lay `days` [(date, weight)] along the pay tiers. Pure.

	`tiers` is [{"tier_days", "pay_percent"}] in order and `used_before` the tier days already
	consumed this year. Returns (segments, consumed): segments are dicts of date, weight,
	pay_percent and label, one per day (split where a day straddles a tier edge), and
	consumed is the tier days these days used.
	"""
	edges, running = [], 0.0
	for index, tier in enumerate(tiers):
		running += flt(tier["tier_days"])
		edges.append((running, flt(tier["pay_percent"]), index))

	position = flt(used_before)
	consumed = 0.0
	segments = []
	for day, weight in days:
		if eligible_from and getdate(day) < getdate(eligible_from):
			segments.append({"date": day, "weight": weight, "pay_percent": 0.0, "label": BEFORE_ELIGIBLE})
			continue
		remaining = flt(weight)
		while remaining > 1e-9:
			tier = next((e for e in edges if position < e[0] - 1e-9), None)
			if not tier:
				segments.append({"date": day, "weight": remaining, "pay_percent": 0.0, "label": BEYOND_TIERS})
				remaining = 0
				break
			take = min(remaining, tier[0] - position)
			segments.append({"date": day, "weight": take, "pay_percent": tier[1], "label": _tier_label(tier[1])})
			position += take
			consumed += take
			remaining -= take
	return segments, flt(consumed, 4)


def _tier_label(pay_percent):
	if flt(pay_percent) >= 100:
		return "Full pay"
	if flt(pay_percent) <= 0:
		return "Unpaid"
	return "{0:g}% pay".format(flt(pay_percent))


def summarise(segments):
	"""Group consecutive segments with the same label into the rows the application shows."""
	rows = []
	for seg in segments:
		last = rows[-1] if rows else None
		if last and last["tier_label"] == seg["label"] and last["pay_percent"] == seg["pay_percent"]:
			last["days"] = flt(last["days"] + seg["weight"], 2)
			last["to_date"] = seg["date"]
		else:
			rows.append(
				{
					"tier_label": seg["label"],
					"days": flt(seg["weight"], 2),
					"pay_percent": seg["pay_percent"],
					"from_date": seg["date"],
					"to_date": seg["date"],
				}
			)
	return rows


def unpaid_equivalent(segments):
	"""Days not paid, counting a half-pay day as half a day."""
	return flt(sum(s["weight"] * (1 - flt(s["pay_percent"]) / 100.0) for s in segments), 2)


def monthly_deductions(segments, daily_rate):
	"""{month_start: [payroll_date, amount]} payroll must take back for these segments."""
	out = {}
	for seg in segments:
		share = seg["weight"] * (1 - flt(seg["pay_percent"]) / 100.0)
		if share <= 0:
			continue
		month = get_first_day(getdate(seg["date"]))
		entry = out.setdefault(month, [getdate(seg["date"]), 0.0])
		entry[1] += share * flt(daily_rate)
	return {m: [d, flt(a, payroll.MONEY_PRECISION)] for m, (d, a) in out.items()}


# ── data ──────────────────────────────────────────────────────────────────────


def leave_year_bounds(company, on_date):
	"""The company's Leave Period covering the date, else the calendar year."""
	from hr_suite.hr_suite.leave_setup import get_leave_period

	period = get_leave_period(company, on_date)
	if period:
		start, end = frappe.db.get_value("Leave Period", period, ["from_date", "to_date"])
		return getdate(start), getdate(end)
	year = getdate(on_date).year
	return getdate("{0}-01-01".format(year)), getdate("{0}-12-31".format(year))


def window_start(policy, employee, company, on_date):
	"""First day whose sick leave counts towards the tiers of a leave starting on `on_date`."""
	mode = policy.get("sick_leave_window") or "Leave Period"
	on_date = getdate(on_date)
	if mode == "Rolling 12 Months":
		return add_days(add_months(on_date, -12), 1)
	if mode == "Calendar Year":
		return getdate("{0}-01-01".format(on_date.year))
	if mode == "Service Year" and policy.get("date_of_joining"):
		joining = getdate(policy.date_of_joining)
		years = max(months_of_service(joining, on_date) // 12, 0)
		return add_months(joining, 12 * years)
	return leave_year_bounds(company, on_date)[0]


def countable_days(employee, leave_type, from_date, to_date, half_day=0, half_day_date=None):
	"""[(date, weight)] the application counts: holidays skipped unless the type includes them."""
	from hrms.hr.utils import get_holiday_dates_for_employee

	holidays = set()
	if not cint(frappe.db.get_value("Leave Type", leave_type, "include_holiday")):
		try:
			holidays = {getdate(h) for h in get_holiday_dates_for_employee(employee, from_date, to_date)}
		except Exception:
			holidays = set()

	days, day, end = [], getdate(from_date), getdate(to_date)
	while day <= end:
		if day not in holidays:
			half = cint(half_day) and (day == getdate(half_day_date) if half_day_date else getdate(from_date) == end)
			days.append((day, 0.5 if half else 1.0))
		day = add_days(day, 1)
	return days


def eligible_from(policy, employee):
	"""The first day paid sick leave is available, or None when it is from joining."""
	joining = getdate(policy.date_of_joining) if policy.get("date_of_joining") else None
	if not joining:
		return None
	candidates = []
	if cint(policy.sick_leave_eligible_after_months):
		candidates.append(add_months(joining, cint(policy.sick_leave_eligible_after_months)))
	if cint(policy.sick_leave_after_probation):
		confirmed = frappe.db.get_value("Employee", employee, "final_confirmation_date")
		candidates.append(getdate(confirmed) if confirmed else add_days(joining, cint(policy.max_probation_days) or 90))
	return max(candidates) if candidates else None


def _is_sick(doc, policy):
	return bool(
		policy.get("has_policy") and cint(policy.sick_leave_auto_split) and doc.leave_type == policy.sick_leave_type
	)


def _daily_rate(policy, employee):
	gross = flt(get_employee_salary_components(employee).get("total_salary"))
	return gross / (flt(policy.leave_salary_days_per_month) or 30.0)


def _applications_from(employee, sick_type, lower, exclude=None):
	"""Submitted, approved sick leave dated on or after `lower`, in the order tiers are consumed."""
	filters = {
		"employee": employee,
		"leave_type": sick_type,
		"docstatus": 1,
		"status": "Approved",
		"from_date": [">=", lower],
	}
	if exclude:
		filters["name"] = ["!=", exclude]
	names = frappe.get_all("Leave Application", filters=filters, pluck="name", order_by="from_date asc, creation asc")
	return [frappe.get_doc("Leave Application", name) for name in names]


def _order_key(doc):
	from datetime import datetime

	return (getdate(doc.from_date), doc.creation or datetime.max)


def walk(policy, apps):
	"""[(application, segments, consumed)] with each leave starting from what earlier ones used.

	`apps` are Leave Application documents (a draft may be among them). Earlier leave counts only
	when it falls inside the window of the one being split, so a new leave in a later window
	starts afresh and a rolling window drops what is more than 12 months old.
	"""
	history, out = [], []
	for app in sorted(apps, key=_order_key):
		start = window_start(policy, app.employee, app.company, app.from_date)
		used = sum(consumed for day, consumed in history if day >= start)
		segments, consumed = _split_application(app, policy, used)
		history.append((getdate(app.from_date), consumed))
		out.append((app, segments, consumed))
	return out


def _split_application(doc, policy, used_before):
	days = countable_days(doc.employee, doc.leave_type, doc.from_date, doc.to_date, doc.half_day, doc.half_day_date)
	return split_days(policy.sick_leave_tiers, used_before, days, eligible_from(policy, doc.employee))


# ── hooks ─────────────────────────────────────────────────────────────────────


def preview_split(doc, method=None):
	"""validate: show the split on a draft so the employee sees what will be paid."""
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if not _is_sick(doc, policy) or doc.docstatus != 0 or not (doc.from_date and doc.to_date):
		return

	lower = window_start(policy, doc.employee, doc.company, doc.from_date)
	others = _applications_from(doc.employee, doc.leave_type, lower, exclude=doc.name if not doc.is_new() else None)
	for app, segments, _consumed in walk(policy, others + [doc]):
		if app is doc:
			doc.set("sick_tier_split", summarise(segments))
			doc.sick_unpaid_equivalent = unpaid_equivalent(segments)
			doc.sick_split_note = _note(segments)


def require_certificate(doc, method=None):
	"""before_submit: sick leave needs a medical certificate where the policy says so."""
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if not _is_sick(doc, policy) or not cint(policy.sick_leave_requires_certificate):
		return
	if doc.get("medical_certificate") or OVERRIDE_ROLE in frappe.get_roles():
		return
	frappe.throw(
		_("Attach the medical certificate before submitting sick leave. Without one only HR with the "
		  "{0} role can submit it.").format(OVERRIDE_ROLE),
		title=_("Medical Certificate Required"),
	)


def on_submit(doc, method=None):
	"""A new sick leave can shift the tiers of every later one: re-split the year."""
	resync_year(doc.employee, doc.from_date)


def on_cancel(doc, method=None):
	"""Take back this application's pay effect, then re-split what came after it."""
	try:
		_reconcile_payroll(doc, {})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: sick leave pay reversal failed for " + doc.name)
		frappe.msgprint(
			_("The payroll deductions of {0} could not all be taken back. See the Error Log.").format(doc.name),
			title=_("Sick Pay Not Reversed"),
			indicator="orange",
		)
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if policy.get("has_policy") and cint(policy.sick_leave_auto_split) and doc.leave_type == policy.sick_leave_type:
		resync_year(doc.employee, doc.from_date)


# ── the year ──────────────────────────────────────────────────────────────────


def resync_year(employee, on_date):
	"""Re-split every submitted sick leave from the affected date onward, in date order.

	Despite the name it covers every window the date can reach: a leave in one window can only
	shift the ones after it, and a rolling window reaches 12 months back. Re-books only what changed.
	"""
	policy = get_policy(employee, on_date=on_date)
	if not policy.get("has_policy") or not cint(policy.sick_leave_auto_split):
		return []

	company = frappe.db.get_value("Employee", employee, "company")
	daily = _daily_rate(policy, employee)
	lower = window_start(policy, employee, company, on_date)
	changed = []

	for doc, segments, _consumed in walk(policy, _applications_from(employee, policy.sick_leave_type, lower)):
		try:
			if _apply(doc, segments, monthly_deductions(segments, daily)):
				changed.append(doc.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "HR Suite: sick leave pay split failed for " + doc.name)
			frappe.msgprint(
				_("The sick-pay deduction for {0} could not be booked, so payroll will pay it in full. "
				  "Fix the cause (see the Error Log) and save the leave again, or deduct it by hand.").format(doc.name),
				title=_("Sick Pay Not Deducted"),
				indicator="orange",
			)
	return changed


def _apply(doc, segments, desired):
	"""Bring one application's split table and payroll in line. True if anything changed."""
	rows = summarise(segments)
	changed = False

	if _table_differs(doc, rows):
		frappe.db.delete("Leave Application Sick Tier", {"parent": doc.name})
		for index, row in enumerate(rows, start=1):
			frappe.get_doc(
				{
					"doctype": "Leave Application Sick Tier",
					"parent": doc.name,
					"parenttype": "Leave Application",
					"parentfield": "sick_tier_split",
					"idx": index,
					**row,
				}
			).db_insert()
		changed = True
	doc.db_set(
		{"sick_unpaid_equivalent": unpaid_equivalent(segments), "sick_split_note": _note(segments)},
		update_modified=False,
	)

	if _reconcile_payroll(doc, desired):
		changed = True
	return changed


def _reconcile_payroll(doc, desired):
	"""Make the Additional Salary rows booked for `doc` add up to `desired`, month by month.

	`desired` is {month_start: [payroll_date, amount]} of deductions. An open month's rows are
	cancelled and re-booked. A month whose payslip is already submitted is left alone and the
	difference is booked on the next open payroll date: a deduction for more, an earning for less.
	Rows are kept signed (an earning refund is negative) in `sick_deduction_rows`.
	"""
	rows = payroll.load_json(doc.get("sick_deduction_rows"))
	by_month = {}
	for row in rows:
		by_month.setdefault(row["month"], []).append(row)
	wanted = {str(month): entry for month, entry in (desired or {}).items()}

	kept, changed = [], False
	deduction = adjustment = None  # (component, currency), resolved only when needed

	def resolve(component, component_type):
		return payroll.prepare_component(
			doc.employee, doc.company, _expense_account(doc.company), component=component, component_type=component_type
		)

	for month in sorted(set(by_month) | set(wanted)):
		existing = by_month.get(month, [])
		booked = flt(sum(flt(r["amount"]) for r in existing), payroll.MONEY_PRECISION)
		originals = [r for r in existing if not r.get("adjustment")]
		payroll_date = getdate(
			wanted[month][0] if month in wanted else (originals[0].get("date") if originals else None) or month
		)
		want = flt(wanted[month][1], payroll.MONEY_PRECISION) if month in wanted else 0.0

		if abs(want - booked) < 0.0005:
			kept.extend(existing)
			continue
		changed = True

		if not payroll.slip_covering(doc.employee, payroll_date):
			payroll.cancel_deductions([r["name"] for r in existing])
			if want > 0:
				deduction = deduction or resolve(_component(), "Deduction")
				name = payroll.book_deduction(doc, deduction[0], deduction[1], payroll_date, want)
				if name:
					kept.append({"name": name, "month": month, "date": str(payroll_date), "amount": want})
			continue

		kept.extend(existing)
		delta = flt(want - booked, payroll.MONEY_PRECISION)
		when = payroll.next_open_date(doc.employee)
		if delta > 0:
			deduction = deduction or resolve(_component(), "Deduction")
			name = payroll.book_additional_salary(doc, deduction[0], deduction[1], when, delta, check_closed=False)
		else:
			adjustment = adjustment or resolve(_adjustment_component(), "Earning")
			name = payroll.book_additional_salary(doc, adjustment[0], adjustment[1], when, -delta, check_closed=False)
		if name:
			kept.append({"name": name, "month": month, "date": str(when), "amount": delta, "adjustment": 1})

	doc.db_set("sick_deduction_rows", payroll.dump_json(kept), update_modified=False)
	return changed


def _table_differs(doc, rows):
	current = frappe.get_all(
		"Leave Application Sick Tier",
		filters={"parent": doc.name},
		fields=["tier_label", "days", "pay_percent", "from_date", "to_date"],
		order_by="idx asc",
	)
	if len(current) != len(rows):
		return True
	for have, want in zip(current, rows):
		if (have.tier_label, flt(have.days, 2), flt(have.pay_percent), getdate(have.from_date), getdate(have.to_date)) != (
			want["tier_label"], flt(want["days"], 2), flt(want["pay_percent"]), getdate(want["from_date"]), getdate(want["to_date"]),
		):
			return True
	return False


def _note(segments):
	parts = [
		"{0:g} {1}".format(r["days"], r["tier_label"].lower() if r["tier_label"] != "Full pay" else "full pay")
		for r in summarise(segments)
	]
	return ", ".join(parts)


def _component():
	return payroll.ensure_deduction_component(
		SICK_COMPONENT,
		"SLD",
		"Takes back the unpaid share of sick leave that HRMS paid in full. Created by HR Suite.",
	)


def _adjustment_component():
	return payroll.ensure_component(
		ADJUSTMENT_COMPONENT,
		"SLA",
		"Earning",
		"Gives back sick-leave pay that was deducted in a closed month and later turned out to be due. "
		"Created by HR Suite.",
	)


def _expense_account(company):
	from hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement import (
		resolve_leave_salary_accounts,
	)

	return resolve_leave_salary_accounts(company)[0]
