"""Team Attendance Review.

Supervisor-facing review of scheduled attendance, late/early exceptions,
and voice-verification readiness for the selected day.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime, nowdate

from hr_suite.hr_suite.api import _get_location_for_branch
from hr_suite.hr_suite.attendance_policy import (
	VOICE_POLICY_DISABLED,
	VOICE_POLICY_REQUIRED,
	resolve_mobile_attendance_policy,
	summarize_schedule_status,
)
from hr_suite.hr_suite.voice_verification import VOICE_VERIFICATION_STATUS_PASSED


GLOBAL_REVIEW_ROLES = {"HR Manager", "HR User", "System Manager"}
MANAGER_REVIEW_ROLES = {"Department Approver", "Leave Approver"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.attendance_date = getdate(filters.get("attendance_date") or nowdate())
	filters.only_exceptions = cint(filters.get("only_exceptions") or 0)
	_ensure_review_access()
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 140},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch", "width": 130},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 150},
		{"fieldname": "attendance_status", "label": _("Attendance Status"), "fieldtype": "Data", "width": 180},
		{"fieldname": "schedule_status", "label": _("Shift Status"), "fieldtype": "Data", "width": 190},
		{"fieldname": "shift_type", "label": _("Saudi Shift"), "fieldtype": "Link", "options": "Saudi Shift Type", "width": 140},
		{"fieldname": "attendance_location", "label": _("Location"), "fieldtype": "Link", "options": "Attendance Location", "width": 150},
		{"fieldname": "expected_start", "label": _("Expected Start"), "fieldtype": "Datetime", "width": 165},
		{"fieldname": "expected_end", "label": _("Expected End"), "fieldtype": "Datetime", "width": 165},
		{"fieldname": "first_in", "label": _("First In"), "fieldtype": "Datetime", "width": 155},
		{"fieldname": "last_out", "label": _("Last Out"), "fieldtype": "Datetime", "width": 155},
		{"fieldname": "late_minutes", "label": _("Late Min"), "fieldtype": "Int", "width": 110},
		{"fieldname": "early_exit_minutes", "label": _("Early Exit Min"), "fieldtype": "Int", "width": 120},
		{"fieldname": "voice_policy", "label": _("Voice Policy"), "fieldtype": "Data", "width": 170},
		{"fieldname": "voice_profile", "label": _("Voice Profile"), "fieldtype": "Data", "width": 150},
		{"fieldname": "voice_verification_status", "label": _("Last Voice Check"), "fieldtype": "Data", "width": 170},
		{"fieldname": "attention_flags", "label": _("Attention Flags"), "fieldtype": "Data", "width": 240},
	]


def get_data(filters):
	employees = _get_scoped_employees(filters)
	if not employees:
		return []

	employee_names = [row.name for row in employees]
	branch_locations = _get_branch_location_map(employees)
	daily_map = _get_daily_attendance_map(employee_names, filters.attendance_date)
	checkin_map = _get_checkin_map(employee_names, filters.attendance_date)
	voice_profile_map = _get_voice_profile_map(employee_names)
	rows = []

	for employee in employees:
		checkins = checkin_map.get(employee.name, [])
		latest_checkin = checkins[-1] if checkins else None
		first_in = next((row.time for row in checkins if row.log_type == "IN"), None)
		last_out = next((row.time for row in reversed(checkins) if row.log_type == "OUT"), None)
		daily_attendance = daily_map.get(employee.name)
		location = branch_locations.get(employee.branch)
		policy = resolve_mobile_attendance_policy(employee.name, filters.attendance_date, location)
		reference_time = _get_reference_time(filters.attendance_date, policy)
		schedule_status = summarize_schedule_status(
			policy,
			reference_time=reference_time,
			last_log_type=latest_checkin.log_type if latest_checkin else None,
		)
		voice_profile = voice_profile_map.get(employee.name)
		voice_profile_status = _get_voice_profile_status(voice_profile)
		late_minutes = cint((daily_attendance or {}).get("late_minutes") or (latest_checkin or {}).get("late_minutes") or 0)
		early_exit_minutes = cint((daily_attendance or {}).get("early_exit_minutes") or (latest_checkin or {}).get("early_exit_minutes") or 0)
		row = {
			"employee": employee.name,
			"employee_name": employee.employee_name,
			"company": employee.company,
			"branch": employee.branch,
			"department": employee.department,
			"attendance_status": _get_attendance_status_label(checkins),
			"schedule_status": schedule_status.get("label"),
			"shift_type": (daily_attendance or {}).get("shift_type") or policy.get("shift_type"),
			"attendance_location": (daily_attendance or {}).get("attendance_location") or (latest_checkin or {}).get("attendance_location") or (location or {}).get("name"),
			"expected_start": (daily_attendance or {}).get("expected_start_time") or policy.get("expected_start"),
			"expected_end": (daily_attendance or {}).get("expected_end_time") or policy.get("expected_end"),
			"first_in": first_in or (daily_attendance or {}).get("in_time"),
			"last_out": last_out or (daily_attendance or {}).get("out_time"),
			"late_minutes": late_minutes,
			"early_exit_minutes": early_exit_minutes,
			"voice_policy": policy.get("voice_policy"),
			"voice_profile": voice_profile_status,
			"voice_verification_status": (latest_checkin or {}).get("voice_verification_status") or _("No voice check"),
			"_daily_attendance_name": (daily_attendance or {}).get("name"),
			"_latest_checkin_name": (latest_checkin or {}).get("name"),
			"_voice_profile_name": (voice_profile or {}).get("name"),
		}
		attention_state = _build_attention_state(
			filters.attendance_date,
			policy,
			checkins,
			row,
			voice_profile,
		)
		flags = attention_state["labels"]
		if filters.only_exceptions and not flags:
			continue
		row["attention_flags"] = ", ".join(flags) if flags else _("On track")
		row["_has_flags"] = bool(flags)
		row["_flag_no_movement"] = "no_movement" in attention_state["keys"]
		row["_flag_open_shift"] = "open_shift" in attention_state["keys"]
		row["_flag_late"] = "late" in attention_state["keys"]
		row["_flag_early_exit"] = "early_exit" in attention_state["keys"]
		row["_flag_voice_profile_missing"] = "voice_profile_missing" in attention_state["keys"]
		row["_flag_voice_verification_pending"] = "voice_verification_pending" in attention_state["keys"]
		rows.append(row)

	rows.sort(key=lambda row: (0 if row["_has_flags"] else 1, row.get("employee_name") or row.get("employee") or ""))
	for row in rows:
		row.pop("_has_flags", None)
	return rows


def _ensure_review_access(user=None):
	if _has_global_review_access(user) or _has_manager_scope(user):
		return
	frappe.throw(_("Only HR or direct approvers can open Team Attendance Review."), frappe.PermissionError)


def _has_global_review_access(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(GLOBAL_REVIEW_ROLES.intersection(set(frappe.get_roles(user))))


def _has_manager_scope(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if MANAGER_REVIEW_ROLES.intersection(roles):
		return True
	return bool(
		frappe.db.sql(
			"""
			SELECT name
			FROM `tabEmployee`
			WHERE leave_approver = %(user)s OR expense_approver = %(user)s
			LIMIT 1
			""",
			{"user": user},
		)
	)


def _get_scoped_employees(filters):
	conditions = ["status = 'Active'"]
	values = {}
	user = frappe.session.user

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters.company
	if filters.get("branch"):
		conditions.append("branch = %(branch)s")
		values["branch"] = filters.branch
	if filters.get("department"):
		conditions.append("department = %(department)s")
		values["department"] = filters.department
	if filters.get("employee"):
		conditions.append("name = %(employee)s")
		values["employee"] = filters.employee

	if not _has_global_review_access(user):
		conditions.append("(leave_approver = %(review_user)s OR expense_approver = %(review_user)s)")
		values["review_user"] = user

	where = " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT name, employee_name, branch, department, company
		FROM `tabEmployee`
		WHERE {where}
		ORDER BY employee_name ASC, name ASC
		""",
		values,
		as_dict=True,
	)


def _get_branch_location_map(employees):
	locations = {}
	for branch in {row.branch for row in employees if row.branch}:
		locations[branch] = _get_location_for_branch(branch)
	return locations


def _get_daily_attendance_map(employee_names, attendance_date):
	rows = frappe.get_all(
		"Saudi Daily Attendance",
		filters={"employee": ["in", employee_names], "attendance_date": attendance_date, "docstatus": 1},
		fields=[
			"name",
			"employee",
			"status",
			"shift_type",
			"attendance_location",
			"expected_start_time",
			"expected_end_time",
			"in_time",
			"out_time",
			"late_minutes",
			"early_exit_minutes",
		],
	)
	return {row.employee: row for row in rows}


def _get_checkin_map(employee_names, attendance_date):
	rows = frappe.get_all(
		"Saudi Employee Checkin",
		filters={
			"employee": ["in", employee_names],
			"time": ["between", [f"{attendance_date} 00:00:00", f"{attendance_date} 23:59:59"]],
		},
		fields=[
			"name",
			"employee",
			"log_type",
			"time",
			"attendance_location",
			"shift_type",
			"late_minutes",
			"early_exit_minutes",
			"voice_verification_status",
			"verification_mode",
		],
		order_by="time asc",
	)
	grouped = defaultdict(list)
	for row in rows:
		grouped[row.employee].append(row)
	return grouped


def _get_voice_profile_map(employee_names):
	if not frappe.db.exists("DocType", "Saudi Employee Voice Profile"):
		return {}
	rows = frappe.get_all(
		"Saudi Employee Voice Profile",
		filters={"employee": ["in", employee_names]},
		fields=["name", "employee", "enrollment_status", "is_active", "last_enrolled_on"],
		ignore_permissions=True,
	)
	return {row.employee: row for row in rows}


def _get_voice_profile_status(voice_profile):
	if not voice_profile:
		return _("Not enrolled")
	if cint(voice_profile.is_active) and voice_profile.enrollment_status == "Enrolled":
		return _("Enrolled")
	return voice_profile.enrollment_status or _("Not enrolled")


def _get_attendance_status_label(checkins):
	if not checkins:
		return _("No movement")
	return _("Checked in") if checkins[-1].log_type == "IN" else _("Checked out")


def _get_reference_time(attendance_date, policy):
	today_date = getdate(nowdate())
	if attendance_date == today_date:
		return now_datetime()
	if attendance_date < today_date:
		return policy.get("checkout_window_end") or policy.get("expected_end") or get_datetime(f"{attendance_date} 23:59:59")
	return policy.get("checkin_window_start") or policy.get("expected_start") or get_datetime(f"{attendance_date} 00:00:00")


def _build_attention_state(attendance_date, policy, checkins, row, voice_profile):
	flags = []
	keys = set()
	voice_policy = policy.get("voice_policy")
	today_date = getdate(nowdate())

	if attendance_date <= today_date and not checkins and policy.get("expected_start"):
		flags.append(_("No movement"))
		keys.add("no_movement")
	if checkins and checkins[-1].log_type == "IN":
		flags.append(_("Open shift"))
		keys.add("open_shift")
	if cint(row.get("late_minutes")) > 0:
		flags.append(_("Late"))
		keys.add("late")
	if cint(row.get("early_exit_minutes")) > 0:
		flags.append(_("Early exit"))
		keys.add("early_exit")
	if voice_policy and voice_policy != VOICE_POLICY_DISABLED and _get_voice_profile_status(voice_profile) != _("Enrolled"):
		flags.append(_("Voice profile missing"))
		keys.add("voice_profile_missing")
	if voice_policy == VOICE_POLICY_REQUIRED and checkins:
		last_voice_status = row.get("voice_verification_status")
		if last_voice_status and last_voice_status != VOICE_VERIFICATION_STATUS_PASSED:
			flags.append(_("Voice verification pending"))
			keys.add("voice_verification_pending")
	return {"labels": flags, "keys": keys}
