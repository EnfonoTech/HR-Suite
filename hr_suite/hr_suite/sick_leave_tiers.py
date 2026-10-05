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
of ones after it. Every submit and cancel therefore re-splits the whole year in date order and
re-books only the deductions that changed.

Days before the employee is eligible (3 months in Bahrain and Qatar, after probation in the
UAE) are unpaid and do not use up any tier. Days past the last tier are unpaid too.

Nothing here builds SQL from strings. Every f-string or .format() produces display text.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate

from hr_suite.hr_suite import leave_payroll as payroll
from hr_suite.hr_suite.leave_accrual import OVERRIDE_ROLE
from hr_suite.hr_suite.policy import get_policy
from hr_suite.hr_suite.utils import get_employee_salary_components

SICK_COMPONENT = "Sick Leave Deduction"
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


def _year_applications(employee, company, sick_type, on_date, exclude=None):
	start, end = leave_year_bounds(company, on_date)
	filters = {
		"employee": employee,
		"leave_type": sick_type,
		"docstatus": 1,
		"status": "Approved",
		"from_date": ["between", [start, end]],
	}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.get_all("Leave Application", filters=filters, fields=["name"], order_by="from_date asc, creation asc")


def _split_application(doc, policy, used_before):
	days = countable_days(doc.employee, doc.leave_type, doc.from_date, doc.to_date, doc.half_day, doc.half_day_date)
	return split_days(policy.sick_leave_tiers, used_before, days, eligible_from(policy, doc.employee))


# ── hooks ─────────────────────────────────────────────────────────────────────


def preview_split(doc, method=None):
	"""validate: show the split on a draft so the employee sees what will be paid."""
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if not _is_sick(doc, policy) or doc.docstatus != 0 or not (doc.from_date and doc.to_date):
		return

	used = 0.0
	for app in _year_applications(doc.employee, doc.company, doc.leave_type, doc.from_date):
		other = frappe.get_doc("Leave Application", app.name)
		if (getdate(other.from_date), other.creation) < (getdate(doc.from_date), doc.creation or other.creation):
			used += _split_application(other, policy, used)[1]

	segments, _used = _split_application(doc, policy, used)
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
	"""Take back this application's deductions, then re-split the year without it."""
	payroll.cancel_deductions([row["name"] for row in payroll.load_json(doc.get("sick_deduction_rows"))])
	policy = get_policy(doc.employee, on_date=doc.from_date)
	if policy.get("has_policy") and cint(policy.sick_leave_auto_split) and doc.leave_type == policy.sick_leave_type:
		resync_year(doc.employee, doc.from_date)


# ── the year ──────────────────────────────────────────────────────────────────


def resync_year(employee, on_date):
	"""Re-split every submitted sick leave of the leave year in date order; re-book what changed."""
	policy = get_policy(employee, on_date=on_date)
	if not policy.get("has_policy") or not cint(policy.sick_leave_auto_split):
		return []

	company = frappe.db.get_value("Employee", employee, "company")
	daily = _daily_rate(policy, employee)
	changed, used = [], 0.0

	for app in _year_applications(employee, company, policy.sick_leave_type, on_date):
		doc = frappe.get_doc("Leave Application", app.name)
		segments, consumed = _split_application(doc, policy, used)
		used += consumed
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
	"""Bring one application's split table and payroll deductions in line. True if anything changed."""
	rows = summarise(segments)
	existing = {row["month"]: row for row in payroll.load_json(doc.get("sick_deduction_rows"))}
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

	kept = []
	book = dict(desired)
	for month, row in existing.items():
		want = book.get(getdate(month))
		if want and abs(flt(want[1]) - flt(row["amount"])) < 0.0005:
			kept.append(row)
			book.pop(getdate(month))
		else:
			payroll.cancel_deductions([row["name"]])
			changed = True

	if book:
		component, currency = payroll.prepare_component(
			doc.employee, doc.company, _expense_account(doc.company), component=_component()
		)
		for month, (payroll_date, amount) in sorted(book.items()):
			name = payroll.book_deduction(doc, component, currency, payroll_date, amount)
			if name:
				kept.append({"name": name, "month": str(month), "amount": flt(amount, payroll.MONEY_PRECISION)})
				changed = True

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


def _expense_account(company):
	from hr_suite.hr_suite.doctype.annual_leave_disbursement.annual_leave_disbursement import (
		resolve_leave_salary_accounts,
	)

	return resolve_leave_salary_accounts(company)[0]
