"""
performance.py — HR Suite Performance Management server logic.

Backs the Steel Force Performance Appraisal Form 2025, which is delivered as
Custom Fields + one child table on the stock HRMS ``Appraisal`` (see
``hr_suite/hr_suite/performance_setup.py``).

Deliberately a separate module from ``hr_suite/hr_suite/integrations/hrms.py``,
which is already overloaded.
"""

import datetime

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import cint, cstr, date_diff, flt, getdate, today

from hr_suite.hr_suite.doctype.appraisal_criterion_rating.appraisal_criterion_rating import (
	validate_criterion_row,
)
from hr_suite.hr_suite.performance_setup import (
	APPRAISAL_TEMPLATE_NAME,
	STEEL_FORCE_CRITERIA,
)
from hr_suite.hr_suite.utils import assert_doctype_permissions

RATINGS_FIELD = "custom_criterion_ratings"
MAX_SCORE_PER_CRITERION = 5

# Grade bands from the printed form, expressed against its own 75-point maximum
# (15 criteria x 5). They are applied proportionally when the criterion count is
# not 15, so a 10-criterion form (max 50) uses 40 / 35.3 / 30 / 20.7 instead:
#   60-75 Excellent | 53-59 Very Good | 45-52 Good | 31-44 Average | <=30 Poor
# The comparison is done as ``score * 75 >= band * max_total`` so the scaling is
# exact integer arithmetic and no band gets a rounding hole.
REFERENCE_MAX_TOTAL = 75
GRADE_BANDS = (
	("Excellent", 60),
	("Very Good", 53),
	("Good", 45),
	("Average", 31),
)
LOWEST_GRADE = "Poor"

# A cycle at least this long is treated as an annual cycle when defaulting
# custom_report_type (roughly 9 months, so a Jan-Dec cycle qualifies and a
# Jan-Jun one does not).
ANNUAL_CYCLE_MIN_DAYS = 275

# Disciplinary sources surfaced on the form. Each entry is
# (doctype, date fieldname, extra fields to show). Every one is guarded with
# frappe.db.exists("DocType", ...) so the panel degrades cleanly when a doctype
# is missing from the site.
DISCIPLINARY_SOURCES = (
	("Employee Warning Notice", "warning_date", ["warning_level", "status"]),
	("Employee Penalty", "penalty_date", ["penalty_type", "penalty_value", "repeat_status", "status"]),
	("Disciplinary Procedure", "incident_date", ["violation_type", "penalty_type", "status"]),
	("Absence Case", "absence_start_date", ["absence_type", "absence_days", "status"]),
)


# ─── Grading ───────────────────────────────────────────────────────────────────


def get_grade(score: int, max_total: int) -> str:
	"""Band a whole-number score against a (possibly rescaled) maximum."""
	score = cint(score)
	max_total = cint(max_total)
	if not max_total or score <= 0:
		return ""

	for grade, band_score in GRADE_BANDS:
		if score * REFERENCE_MAX_TOTAL >= band_score * max_total:
			return grade
	return LOWEST_GRADE


# ─── validate hook ─────────────────────────────────────────────────────────────


def validate_appraisal(doc, method=None):
	"""``Appraisal`` validate doc event — totals, grades, reviewer rule, defaults.

	Never touches ``Appraisal.start_date`` / ``end_date``: core's
	``validate_duplicate()`` uses them for overlap detection, so writing them would
	make a Mid-Term and an Annual appraisal for the same employee mutually exclusive.
	"""
	if not doc.meta.has_field(RATINGS_FIELD):
		# Custom fields not provisioned yet (fresh install, mid-migrate).
		return

	_set_period_defaults(doc)
	_set_years_in_current_role(doc)

	rows = doc.get(RATINGS_FIELD) or []
	appraiser_total = 0
	reviewer_total = 0
	reviewer_scored = False

	for row in rows:
		validate_criterion_row(row)

		appraiser = cint(row.appraiser_rating)
		reviewer = cint(row.reviewer_rating)
		appraiser_total += appraiser
		reviewer_total += reviewer

		if reviewer:
			reviewer_scored = True
			# Reviewer instruction on the form: replicate the appraiser's score when
			# agreeing, otherwise comment on the criteria disagreed with.
			if reviewer != appraiser and not cstr(row.reviewer_comments).strip():
				frappe.throw(
					_(
						"Row #{0} ({1}): the Reviewer scored {2} against the Appraiser's {3}. "
						"Reviewer Comments are mandatory whenever the two scores differ."
					).format(row.idx, row.criterion or _("criterion"), reviewer, appraiser or 0),
					title=_("Reviewer Comments Required"),
				)

	max_total = len(rows) * MAX_SCORE_PER_CRITERION

	doc.custom_appraiser_total = appraiser_total
	doc.custom_reviewer_total = reviewer_total
	doc.custom_max_total = max_total
	doc.custom_appraiser_grade = get_grade(appraiser_total, max_total)
	# The official grade is the reviewer's whenever a reviewer has scored.
	doc.custom_performance_grade = get_grade(
		reviewer_total if reviewer_scored else appraiser_total, max_total
	)


def _set_period_defaults(doc) -> None:
	"""Default our own period fields (and the report type) from the Appraisal Cycle.

	Only ever writes to ``custom_period_from`` / ``custom_period_to`` — never to
	``Appraisal.start_date`` / ``end_date``.

	``custom_report_type`` is reqd, and ``AppraisalCycle.create_appraisals_for_cycle()``
	inserts appraisals programmatically without it, which would otherwise fail with a
	MandatoryError. The mandatory check runs after ``validate`` (document.py:309-310),
	so defaulting it here keeps bulk creation from a cycle working. The value stays
	editable — a human confirms or changes it before submit.
	"""
	if not doc.appraisal_cycle:
		return

	cycle = frappe.db.get_value(
		"Appraisal Cycle", doc.appraisal_cycle, ["start_date", "end_date"], as_dict=True
	)
	if not cycle:
		return

	if not doc.get("custom_period_from"):
		doc.custom_period_from = cycle.start_date
	if not doc.get("custom_period_to"):
		doc.custom_period_to = cycle.end_date

	if not doc.get("custom_report_type") and cycle.start_date and cycle.end_date:
		span = date_diff(cycle.end_date, cycle.start_date)
		doc.custom_report_type = "Annual Appraisal" if span >= ANNUAL_CYCLE_MIN_DAYS else "Mid-Term Appraisal"


def _set_years_in_current_role(doc) -> None:
	if not doc.employee:
		return
	as_of = doc.get("custom_date_of_review") or doc.get("custom_period_to") or today()
	doc.custom_years_in_current_role = get_years_in_current_role(doc.employee, as_of)


def get_years_in_current_role(employee: str, as_of=None) -> float:
	"""Years since the latest designation change, falling back to Date of Joining.

	A designation change is recorded as an ``Employee Property History`` row
	(fields: ``property`` / ``current`` / ``new`` / ``fieldname``) on a submitted
	``Employee Promotion`` (``promotion_date``) or ``Employee Transfer``
	(``transfer_date``). The child table itself carries no date, so the parents are
	fetched first and the child rows are then read in a single batched query.
	"""
	as_of = getdate(as_of or today())

	start_date = None
	parents = {}

	for doctype, date_field in (
		("Employee Promotion", "promotion_date"),
		("Employee Transfer", "transfer_date"),
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		for row in frappe.get_all(
			doctype,
			filters={"employee": employee, "docstatus": 1},
			fields=["name", date_field],
		):
			parents[row.name] = row.get(date_field)

	if parents and frappe.db.exists("DocType", "Employee Property History"):
		changes = frappe.get_all(
			"Employee Property History",
			filters={"parent": ["in", list(parents.keys())], "fieldname": "designation"},
			fields=["parent"],
		)
		dates = [parents.get(c.parent) for c in changes if parents.get(c.parent)]
		dates = [getdate(d) for d in dates if getdate(d) <= as_of]
		if dates:
			start_date = max(dates)

	if not start_date:
		start_date = frappe.db.get_value("Employee", employee, "date_of_joining")

	if not start_date:
		return 0.0

	start_date = getdate(start_date)
	if start_date > as_of:
		return 0.0

	# 365.25 absorbs leap years; the field is shown to 1 decimal.
	return flt(date_diff(as_of, start_date) / 365.25, 1)


# ─── Whitelisted API ───────────────────────────────────────────────────────────


def _get_editable_appraisal(appraisal: str):
	appraisal = cstr(appraisal)
	if not appraisal or not frappe.db.exists("Appraisal", appraisal):
		frappe.throw(_("Appraisal {0} not found").format(appraisal), frappe.DoesNotExistError)

	doc = frappe.get_doc("Appraisal", appraisal)
	assert_doctype_permissions("Appraisal", "write", doc=doc)

	if doc.docstatus != 0:
		frappe.throw(_("Appraisal {0} is not a draft and can no longer be edited").format(doc.name))

	if not doc.meta.has_field(RATINGS_FIELD):
		frappe.throw(_("Criterion Ratings are not set up on this site. Run bench migrate for HR Suite."))

	return doc


@frappe.whitelist()
def load_criteria(appraisal: str) -> dict:
	"""Fill ``custom_criterion_ratings`` from the Appraisal Template, without duplicating.

	Falls back to the seeded Steel Force criteria (in printed order) when the
	appraisal has no template, or the template has no rating criteria.
	"""
	doc = _get_editable_appraisal(appraisal)

	existing = {cstr(row.criterion) for row in (doc.get(RATINGS_FIELD) or [])}
	criteria = _get_template_criteria(doc.appraisal_template) or _get_seeded_criteria()
	added = 0

	for criterion in criteria:
		if criterion in existing:
			continue
		doc.append(RATINGS_FIELD, {"criterion": criterion})
		existing.add(criterion)
		added += 1

	if added:
		doc.save()

	return {"added": added, "total": len(doc.get(RATINGS_FIELD) or [])}


def _get_template_criteria(template: str | None) -> list:
	if not template or not frappe.db.exists("Appraisal Template", template):
		return []
	rows = frappe.get_all(
		"Employee Feedback Rating",
		filters={"parenttype": "Appraisal Template", "parent": template},
		fields=["criteria"],
		order_by="idx asc",
	)
	return [r.criteria for r in rows if r.criteria]


def _get_seeded_criteria() -> list:
	"""All Employee Feedback Criteria, Steel Force ones first in printed order."""
	if not frappe.db.exists("DocType", "Employee Feedback Criteria"):
		return []
	available = set(frappe.get_all("Employee Feedback Criteria", pluck="name"))
	ordered = [c for c in STEEL_FORCE_CRITERIA if c in available]
	ordered += sorted(available - set(ordered))
	return ordered


@frappe.whitelist()
def copy_appraiser_ratings_to_reviewer(appraisal: str) -> dict:
	"""'Replicate if agreeing' — copy every Appraiser score onto the Reviewer column."""
	doc = _get_editable_appraisal(appraisal)

	copied = 0
	for row in doc.get(RATINGS_FIELD) or []:
		appraiser = cint(row.appraiser_rating)
		if not appraiser or cint(row.reviewer_rating) == appraiser:
			continue
		row.reviewer_rating = appraiser
		row.reviewer_comments = None
		copied += 1

	if copied:
		doc.save()

	return {"copied": copied}


@frappe.whitelist()
def get_performance_history(employee: str, from_date: str, to_date: str) -> dict:
	"""Attendance, leave-without-pay and disciplinary history for the review period.

	The printed form instructs the appraiser to score Punctuality, Attendance and
	Discipline strictly from this historical data, so the form has to surface it.
	One query per source; no N+1.
	"""
	employee = cstr(employee)
	if not employee or not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)

	assert_doctype_permissions("Employee", "read", doc=employee)

	from_date = getdate(from_date)
	to_date = getdate(to_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	return {
		"employee": employee,
		"from_date": cstr(from_date),
		"to_date": cstr(to_date),
		"attendance": _get_attendance_summary(employee, from_date, to_date),
		"leave_without_pay_days": _get_lwp_days(employee, from_date, to_date),
		"disciplinary": _get_disciplinary_history(employee, from_date, to_date),
	}


def _get_attendance_summary(employee: str, from_date, to_date) -> dict:
	summary = {
		"present": 0,
		"absent": 0,
		"half_day": 0,
		"on_leave": 0,
		"work_from_home": 0,
		"late_entry": 0,
		"early_exit": 0,
		"total_marked": 0,
		"checkins": 0,
	}

	if not frappe.db.exists("DocType", "Attendance"):
		return summary

	# late_entry / early_exit are Check fields on Attendance (Employee Checkin has
	# no such flags), so the whole summary comes out of one grouped query.
	attendance = frappe.qb.DocType("Attendance")
	rows = (
		frappe.qb.from_(attendance)
		.select(
			attendance.status,
			Count(attendance.name).as_("count"),
			Sum(attendance.late_entry).as_("late_entry"),
			Sum(attendance.early_exit).as_("early_exit"),
		)
		.where(
			(attendance.employee == employee)
			& (attendance.docstatus == 1)
			& (attendance.attendance_date >= from_date)
			& (attendance.attendance_date <= to_date)
		)
		.groupby(attendance.status)
	).run(as_dict=True)

	status_map = {
		"Present": "present",
		"Absent": "absent",
		"Half Day": "half_day",
		"On Leave": "on_leave",
		"Work From Home": "work_from_home",
	}
	for row in rows:
		key = status_map.get(row.status)
		count = cint(row.count)
		if key:
			summary[key] += count
		summary["total_marked"] += count
		summary["late_entry"] += cint(row.late_entry)
		summary["early_exit"] += cint(row.early_exit)

	if frappe.db.exists("DocType", "Employee Checkin"):
		checkin = frappe.qb.DocType("Employee Checkin")
		# Employee Checkin.time is a Datetime, so the date bounds have to be widened
		# to cover the whole of the last day.
		period_start = datetime.datetime.combine(from_date, datetime.time.min)
		period_end = datetime.datetime.combine(to_date, datetime.time.max)
		result = (
			frappe.qb.from_(checkin)
			.select(Count(checkin.name).as_("count"))
			.where(
				(checkin.employee == employee)
				& (checkin.log_type == "IN")
				& (checkin.time >= period_start)
				& (checkin.time <= period_end)
			)
		).run(as_dict=True)
		summary["checkins"] = cint(result[0].count) if result else 0

	return summary


def _get_lwp_days(employee: str, from_date, to_date) -> float:
	"""Days taken against a Leave Type flagged is_lwp, in one joined query."""
	if not frappe.db.exists("DocType", "Leave Application"):
		return 0.0

	application = frappe.qb.DocType("Leave Application")
	leave_type = frappe.qb.DocType("Leave Type")
	rows = (
		frappe.qb.from_(application)
		.inner_join(leave_type)
		.on(application.leave_type == leave_type.name)
		.select(Sum(application.total_leave_days).as_("days"))
		.where(
			(application.employee == employee)
			& (application.docstatus == 1)
			& (application.status == "Approved")
			& (leave_type.is_lwp == 1)
			& (application.from_date <= to_date)
			& (application.to_date >= from_date)
		)
	).run(as_dict=True)

	return flt(rows[0].days) if rows and rows[0].days else 0.0


def _get_disciplinary_history(employee: str, from_date, to_date) -> list:
	"""One query per configured source; missing doctypes are skipped silently."""
	history = []

	for doctype, date_field, extra_fields in DISCIPLINARY_SOURCES:
		if not frappe.db.exists("DocType", doctype):
			continue

		meta = frappe.get_meta(doctype)
		fields = ["name", date_field] + [f for f in extra_fields if meta.has_field(f)]

		try:
			rows = frappe.get_all(
				doctype,
				filters={
					"employee": employee,
					"docstatus": ["!=", 2],
					date_field: ["between", [from_date, to_date]],
				},
				fields=fields,
				# date_field comes from the DISCIPLINARY_SOURCES constant, never user input
				order_by=date_field + " desc",
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "HR Suite: performance history query failed")
			continue

		for row in rows:
			history.append(
				{
					"doctype": doctype,
					"name": row.name,
					"date": cstr(row.get(date_field) or ""),
					"details": {
						f: cstr(row.get(f) or "")
						for f in extra_fields
						if meta.has_field(f) and row.get(f) not in (None, "")
					},
				}
			)

	history.sort(key=lambda r: r["date"], reverse=True)
	return history


@frappe.whitelist()
def get_default_template() -> str:
	"""Name of the seeded Steel Force template, or an empty string when absent."""
	if frappe.db.exists("Appraisal Template", APPRAISAL_TEMPLATE_NAME):
		return APPRAISAL_TEMPLATE_NAME
	return ""
