"""
hr_suite/api.py
Employee insights and self-service APIs.
"""

import calendar
import datetime
import json
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import (
	cint,
	flt,
	get_first_day,
	get_last_day,
	getdate,
	now_datetime,
	nowdate,
	time_diff_in_seconds,
)

from hr_suite.hr_suite.utils import assert_employee_access


ELEVATED_ROLES = {"HR Manager", "HR User", "System Manager"}
ORG_TREE_GLOBAL_ROLES = {"HR Manager", "HR User", "System Manager"}
ORG_TREE_MANAGER_ROLES = {"Department Approver", "Leave Approver"}
ORG_TREE_ROOT_VALUE = "__org_root__"
ORG_TREE_UNASSIGNED_DEPARTMENT = "__unassigned_department__"

WORKFLOW_AUDIT_TARGETS = (
	{
		"key": "annual_leave",
		"workflow_name": "Annual Leave Approval Workflow",
		"fixture": "workflow/annual_leave_approval_workflow/annual_leave_approval_workflow.json",
	},
	{
		"key": "sick_leave",
		"workflow_name": "Sick Leave Approval Workflow",
		"fixture": "workflow/sick_leave_approval_workflow/sick_leave_approval_workflow.json",
	},
	{
		"key": "overtime",
		"workflow_name": "Overtime Approval Workflow",
		"fixture": "workflow/overtime_approval_workflow/overtime_approval_workflow.json",
	},
	{
		"key": "salary_adjustment",
		"workflow_name": "Salary Adjustment Workflow",
		"fixture": "workflow/salary_adjustment_workflow/salary_adjustment_workflow.json",
	},
	{
		"key": "termination",
		"workflow_name": "Termination Approval Workflow",
		"fixture": "workflow/termination_approval_workflow/termination_approval_workflow.json",
	},
)


def _get_employee_for_user(user=None):
	user = user or frappe.session.user
	employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not employee:
		frappe.throw(_("Your account is not linked to an active employee record. Please contact the system administrator."))
	return employee


def _get_employee_profile(employee):
	return frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "branch", "department", "image", "company", "designation"],
		as_dict=True,
	)


def _require_employee_context():
	if frappe.session.user == "Guest":
		frappe.throw(_("You must be logged in first."), frappe.PermissionError)

	employee = _get_employee_for_user()
	return employee, _get_employee_profile(employee)


def _get_location_for_branch(branch):
	if not branch:
		return None
	return frappe.db.get_value(
		"Shift Location",
		{"hrsuite_branch": branch, "hrsuite_is_active": 1},
		[
			"name",
			"location_name",
			"hrsuite_branch as branch",
			"latitude",
			"longitude",
			"checkin_radius as allowed_radius_meters",
			"hrsuite_plus_code as plus_code",
			"hrsuite_location_source as location_source",
			"hrsuite_address_reference as address_reference",
			"hrsuite_default_shift_type as default_shift_type",
			"hrsuite_enforce_schedule as enforce_schedule",
			"hrsuite_voice_verification_policy as voice_verification_policy",
			"hrsuite_voice_challenge_ttl_seconds as voice_challenge_ttl_seconds",
			"hrsuite_voice_max_duration_seconds as voice_max_duration_seconds",
		],
		as_dict=True,
	)


def _get_active_employee_for_user(user=None):
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name") or frappe.db.get_value(
		"Employee", {"user_id": user}, "name"
	)



def _workflow_fixture_path(relative_path):
	return Path(__file__).resolve().parent / relative_path


def _load_workflow_snapshot(config):
	workflow_name = config["workflow_name"]
	if frappe.db.exists("Workflow", workflow_name):
		doc = frappe.get_doc("Workflow", workflow_name)
		return {
			"workflow_name": doc.workflow_name,
			"document_type": doc.document_type,
			"states": [dict(row) for row in doc.states],
			"transitions": [dict(row) for row in doc.transitions],
			"source": "database",
		}

	with _workflow_fixture_path(config["fixture"]).open(encoding="utf-8") as handle:
		payload = json.load(handle)
	payload["source"] = "fixture"
	return payload


def _is_negative_workflow_transition(transition):
	text = " ".join(
		str(transition.get(field) or "").lower()
		for field in ("action", "next_state")
	)
	return any(keyword in text for keyword in ("reject", "rejected", "cancel", "cancelled", "reset", "return", "Rejected", "cancelled"))


def _get_workflow_start_state(snapshot):
	states = [state.get("state") for state in snapshot.get("states") or [] if state.get("state")]
	if "Draft" in states:
		return "Draft"
	for state_name in states:
		if "draft" in state_name.lower() or "draft" in state_name:
			return state_name
	incoming_states = {transition.get("next_state") for transition in snapshot.get("transitions") or []}
	for state_name in states:
		if state_name not in incoming_states:
			return state_name
	return states[0] if states else None


def _build_workflow_route(snapshot):
	states = {state.get("state"): state for state in snapshot.get("states") or [] if state.get("state")}
	transitions = snapshot.get("transitions") or []
	current_state = _get_workflow_start_state(snapshot)
	route = []
	visited = set()

	while current_state and current_state not in visited:
		visited.add(current_state)
		state_meta = states.get(current_state) or {}
		candidate_transitions = [transition for transition in transitions if transition.get("state") == current_state]
		approval_candidates = [transition for transition in candidate_transitions if not _is_negative_workflow_transition(transition)]
		selected_transition = approval_candidates[0] if approval_candidates else None
		route.append(
			{
				"state": current_state,
				"doc_status": state_meta.get("doc_status"),
				"editable_by": state_meta.get("allow_edit"),
				"action": selected_transition.get("action") if selected_transition else None,
				"allowed_role": selected_transition.get("allowed") if selected_transition else None,
				"next_state": selected_transition.get("next_state") if selected_transition else None,
			}
		)
		if not selected_transition:
			break
		current_state = selected_transition.get("next_state")

	return route


def _build_workflow_route_audit_entry(config):
	snapshot = _load_workflow_snapshot(config)
	negative_transitions = [
		{
			"state": transition.get("state"),
			"action": transition.get("action"),
			"allowed_role": transition.get("allowed"),
			"next_state": transition.get("next_state"),
		}
		for transition in snapshot.get("transitions") or []
		if _is_negative_workflow_transition(transition)
	]
	return {
		"key": config["key"],
		"workflow_name": snapshot.get("workflow_name"),
		"document_type": snapshot.get("document_type"),
		"source": snapshot.get("source"),
		"approval_route": _build_workflow_route(snapshot),
		"alternate_transitions": negative_transitions,
	}


def _has_org_tree_global_access(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(ORG_TREE_GLOBAL_ROLES.intersection(set(frappe.get_roles(user))))


def _has_org_tree_manager_scope(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if ORG_TREE_MANAGER_ROLES.intersection(roles):
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


def _ensure_org_tree_access(user=None):
	if _has_org_tree_global_access(user) or _has_org_tree_manager_scope(user):
		return
	frappe.throw(_("Only HR or direct approvers can open the organization tree."), frappe.PermissionError)


def _get_org_tree_scope_rows(company=None, branch=None, department=None, user=None):
	user = user or frappe.session.user
	_ensure_org_tree_access(user)

	conditions = ["status = 'Active'"]
	values = {}

	if company:
		conditions.append("company = %(company)s")
		values["company"] = company
	if branch:
		conditions.append("branch = %(branch)s")
		values["branch"] = branch
	if department:
		conditions.append("department = %(department)s")
		values["department"] = department

	if not _has_org_tree_global_access(user):
		scope_conditions = ["leave_approver = %(review_user)s", "expense_approver = %(review_user)s"]
		values["review_user"] = user
		scope_employee = _get_active_employee_for_user(user)
		if scope_employee:
			scope_conditions.extend(["name = %(scope_employee)s", "reports_to = %(scope_employee)s"])
			values["scope_employee"] = scope_employee
		conditions.append("(" + " OR ".join(scope_conditions) + ")")

	where = " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT
			name,
			employee_name,
			designation,
			department,
			branch,
			company,
			reports_to,
			user_id,
			leave_approver,
			expense_approver
		FROM `tabEmployee`
		WHERE {where}
		ORDER BY department ASC, employee_name ASC, name ASC
		""",
		values,
		as_dict=True,
	)


def _department_key(department_name):
	return f"department::{department_name or ORG_TREE_UNASSIGNED_DEPARTMENT}"


def _employee_key(employee_name):
	return f"employee::{employee_name}"


def _normalize_department_name(department_name):
	return department_name or ORG_TREE_UNASSIGNED_DEPARTMENT


def _department_label(department_name):
	return department_name or _("Unassigned Department")


def _get_direct_reports(rows, employee_name, department_name=None):
	department_name = _normalize_department_name(department_name) if department_name is not None else None
	return [
		row
		for row in rows
		if row.reports_to == employee_name
		and (
			department_name is None
			or _normalize_department_name(row.department) == department_name
		)
	]


def _get_department_manager_count(rows, department_name):
	department_name = _normalize_department_name(department_name)
	count = 0
	for row in rows:
		if _normalize_department_name(row.department) != department_name:
			continue
		if _get_direct_reports(rows, row.name, department_name=department_name):
			count += 1
	return count


def _build_department_tree_node(department_name, rows):
	department_rows = [row for row in rows if _normalize_department_name(row.department) == department_name]
	approver_users = {
		user
		for row in department_rows
		for user in (row.leave_approver, row.expense_approver)
		if user
	}
	return {
		"value": _department_key(None if department_name == ORG_TREE_UNASSIGNED_DEPARTMENT else department_name),
		"title": _department_label(None if department_name == ORG_TREE_UNASSIGNED_DEPARTMENT else department_name),
		"expandable": bool(department_rows),
		"node_type": "department",
		"department": None if department_name == ORG_TREE_UNASSIGNED_DEPARTMENT else department_name,
		"department_label": _department_label(None if department_name == ORG_TREE_UNASSIGNED_DEPARTMENT else department_name),
		"employee_count": len(department_rows),
		"manager_count": _get_department_manager_count(rows, department_name),
		"approver_count": len(approver_users),
	}


def _build_employee_tree_node(row, rows):
	row_map = {employee.name: employee for employee in rows}
	department_name = _normalize_department_name(row.department)
	direct_reports = _get_direct_reports(rows, row.name, department_name=department_name)
	reference_manager = row_map.get(row.reports_to)
	return {
		"value": _employee_key(row.name),
		"title": row.employee_name or row.name,
		"expandable": bool(direct_reports),
		"node_type": "employee",
		"employee": row.name,
		"employee_name": row.employee_name,
		"designation": row.designation,
		"department": row.department,
		"department_label": _department_label(row.department),
		"branch": row.branch,
		"company": row.company,
		"reports_to": row.reports_to,
		"reports_to_name": reference_manager.employee_name if reference_manager else None,
		"user_id": row.user_id,
		"leave_approver": row.leave_approver,
		"expense_approver": row.expense_approver,
		"direct_report_count": len(direct_reports),
	}


def _get_department_root_employees(rows, department_name):
	department_name = _normalize_department_name(department_name)
	row_map = {employee.name: employee for employee in rows}
	department_rows = [row for row in rows if _normalize_department_name(row.department) == department_name]
	root_rows = []
	for row in department_rows:
		manager = row_map.get(row.reports_to)
		if not manager or _normalize_department_name(manager.department) != department_name:
			root_rows.append(row)
	return root_rows


@frappe.whitelist(methods=["GET", "POST"])
def get_employee_org_hierarchy_summary(company=None, branch=None, department=None):
	rows = _get_org_tree_scope_rows(company=company, branch=branch, department=department)
	approver_users = {
		user
		for row in rows
		for user in (row.leave_approver, row.expense_approver)
		if user
	}
	manager_count = sum(1 for row in rows if _get_direct_reports(rows, row.name))
	return {
		"root_label": company or _("Hr Suite Organization"),
		"scope_label": _("Organization-wide") if _has_org_tree_global_access() else _("Team scope"),
		"employee_count": len(rows),
		"department_count": len({_normalize_department_name(row.department) for row in rows}),
		"manager_count": manager_count,
		"approver_count": len(approver_users),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_employee_org_tree_nodes(parent=None, is_root=False, company=None, branch=None, department=None):
	rows = _get_org_tree_scope_rows(company=company, branch=branch, department=department)
	if cint(is_root) or parent in (None, "", ORG_TREE_ROOT_VALUE):
		departments = sorted({_normalize_department_name(row.department) for row in rows}, key=lambda value: _department_label(None if value == ORG_TREE_UNASSIGNED_DEPARTMENT else value))
		return [_build_department_tree_node(department_name, rows) for department_name in departments]

	if parent and str(parent).startswith("department::"):
		department_name = str(parent).split("::", 1)[1] or ORG_TREE_UNASSIGNED_DEPARTMENT
		root_rows = sorted(
			_get_department_root_employees(rows, department_name),
			key=lambda row: ((row.employee_name or row.name or "").lower(), row.name),
		)
		return [_build_employee_tree_node(row, rows) for row in root_rows]

	if parent and str(parent).startswith("employee::"):
		employee_name = str(parent).split("::", 1)[1]
		parent_row = next((row for row in rows if row.name == employee_name), None)
		if not parent_row:
			return []
		direct_reports = sorted(
			_get_direct_reports(rows, employee_name, department_name=_normalize_department_name(parent_row.department)),
			key=lambda row: ((row.employee_name or row.name or "").lower(), row.name),
		)
		return [_build_employee_tree_node(row, rows) for row in direct_reports]

	return []


@frappe.whitelist(methods=["GET"])
def get_workflow_route_audit(workflow_key=None):
	if frappe.session.user == "Guest":
		frappe.throw(_("You must be logged in first."), frappe.PermissionError)

	targets = WORKFLOW_AUDIT_TARGETS
	if workflow_key:
		targets = [config for config in WORKFLOW_AUDIT_TARGETS if config["key"] == workflow_key]
	return [_build_workflow_route_audit_entry(config) for config in targets]


def _get_contract_hours_per_day(employee):
	working_hours = frappe.db.get_value(
		"Country Employment Contract",
		{"employee": employee, "contract_status": "Active"},
		"working_hours_per_day",
		order_by="start_date desc",
	)
	return flt(working_hours or 8)


def _get_period_bounds(month=None, year=None):
	"""Resolve a month/year pair that arrives over HTTP into a safe date window.

	`month` and `year` reach here from the whitelisted `get_attendance_insights`
	endpoint, so they are arbitrary strings. `int()` raised a bare ValueError on
	anything non-numeric, and an out-of-range month produced an unhelpful
	"2026-13-01 is not a valid date string" further down. Both are coerced with
	cint and range-checked here instead.
	"""
	today = getdate(nowdate())

	month_number = cint(month) or today.month
	if not 1 <= month_number <= 12:
		frappe.throw(_("Month must be between 1 and 12."), title=_("Invalid Period"))

	year_number = cint(year) or today.year
	if not 1900 <= year_number <= 2999:
		frappe.throw(_("Year {0} is out of range.").format(year_number), title=_("Invalid Period"))

	anchor = datetime.date(year_number, month_number, 1)
	return get_first_day(anchor), get_last_day(anchor), month_number, year_number


def _get_payroll_snapshot(employee):
	rows = frappe.db.sql(
		"""
		SELECT
			child.gosi_employee_deduction,
			child.sick_leave_deduction,
			child.loan_deduction,
			child.total_deductions,
			child.overtime_addition,
			child.net_salary,
			parent.month,
			parent.year,
			parent.status
		FROM `tabMonthly Payroll Employee` child
		INNER JOIN `tabMonthly Payroll` parent ON parent.name = child.parent
		WHERE child.employee = %s AND parent.docstatus = 1
		ORDER BY parent.year DESC, parent.modified DESC
		LIMIT 1
		""",
		employee,
		as_dict=True,
	)
	if not rows:
		return None

	row = rows[0]
	return {
		"period": f"{row.month} {row.year}",
		"status": row.status,
		"gosi_deduction": flt(row.gosi_employee_deduction),
		"sick_leave_deduction": flt(row.sick_leave_deduction),
		"loan_deduction": flt(row.loan_deduction),
		"total_deductions": flt(row.total_deductions),
		"overtime_addition": flt(row.overtime_addition),
		"net_salary": flt(row.net_salary),
	}


def _get_attendance_insights(employee, month=None, year=None):
	from_date, to_date, month_number, year_number = _get_period_bounds(month, year)
	working_hours_target = _get_contract_hours_per_day(employee)

	# Derived from HRMS Attendance rather than a cached monthly summary DocType, so the
	# numbers always match what the Attendance records actually say.
	attendance_rows = frappe.get_all(
		"Attendance",
		filters={"employee": employee, "attendance_date": ["between", [from_date, to_date]], "docstatus": 1},
		fields=["status", "working_hours", "late_entry", "early_exit", "leave_type"],
	)

	total_hours = round(sum(flt(row.working_hours) for row in attendance_rows), 2)
	recorded_days = len(attendance_rows)
	shortfall_days = sum(
		1 for row in attendance_rows if flt(row.working_hours) and flt(row.working_hours) < working_hours_target
	)
	early_exit_days = sum(1 for row in attendance_rows if row.early_exit)
	late_entry_days = sum(1 for row in attendance_rows if row.late_entry)
	present_days = sum(
		1 for row in attendance_rows if row.status in ("Present", "Work From Home")
	) + 0.5 * sum(1 for row in attendance_rows if row.status == "Half Day")
	absent_days = sum(1 for row in attendance_rows if row.status == "Absent")

	return {
		"period_label": f"{calendar.month_name[month_number]} {year_number}",
		"present_days": present_days,
		"absent_days": absent_days,
		"late_days": late_entry_days,
		"late_minutes_total": _get_late_minutes(employee, from_date, to_date),
		"overtime_hours_total": _get_overtime_hours(employee, from_date, to_date),
		"recorded_days": recorded_days,
		"total_hours": total_hours,
		"average_hours": round(total_hours / recorded_days, 2) if recorded_days else 0,
		"shortfall_days": shortfall_days,
		"early_exit_days": early_exit_days,
		"target_hours_per_day": working_hours_target,
		"leave_days": _get_leave_day_split(attendance_rows),
		"payroll": _get_payroll_snapshot(employee),
	}


LEAVE_BUCKET_KEYWORDS = {
	"annual": ("annual", "earned", "privilege"),
	"sick": ("sick",),
	"special": ("maternity", "paternity", "marriage", "bereavement", "compassionate", "hajj", "exam", "study"),
}


def _get_leave_day_split(attendance_rows):
	"""Split On Leave days by leave type, using the same buckets the mobile app expects."""
	split = {"annual": 0.0, "sick": 0.0, "special": 0.0, "other": 0.0}
	for row in attendance_rows:
		if row.status != "On Leave":
			continue
		leave_type = (row.leave_type or "").lower()
		bucket = next(
			(
				name
				for name, words in LEAVE_BUCKET_KEYWORDS.items()
				if any(word in leave_type for word in words)
			),
			"other",
		)
		split[bucket] += 1
	return split


def _get_late_minutes(employee, from_date, to_date):
	"""Minutes late per day = first check-in after the shift's expected start."""
	from hr_suite.hr_suite.attendance_policy import resolve_mobile_attendance_policy

	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": 1,
			"late_entry": 1,
		},
		fields=["attendance_date", "in_time"],
	)
	if not rows:
		return 0

	# One policy lookup per distinct date, not per row — resolving it hits Shift Assignment
	# and Shift Type each time.
	expected_starts = {}
	total = 0
	for row in rows:
		if not row.in_time:
			continue
		day = getdate(row.attendance_date)
		if day not in expected_starts:
			expected_starts[day] = resolve_mobile_attendance_policy(employee, day, None).get("expected_start")
		expected_start = expected_starts[day]
		if not expected_start:
			continue
		minutes = time_diff_in_seconds(row.in_time, expected_start) / 60
		if minutes > 0:
			total += minutes
	return int(round(total))


def _get_overtime_hours(employee, from_date, to_date):
	"""Approved overtime for the period, from HR Suite's own Overtime Request."""
	if not frappe.db.exists("DocType", "Overtime Request"):
		return 0.0

	rows = frappe.get_all(
		"Overtime Request",
		filters={
			"employee": employee,
			"date": ["between", [from_date, to_date]],
			"approval_status": "Approved",
			"docstatus": 1,
		},
		fields=["overtime_hours"],
	)
	return round(sum(flt(row.overtime_hours) for row in rows), 2)


@frappe.whitelist()
def get_employee_paid_payroll_history(employee, limit=10):
	if not employee:
		return []

	# `limit` arrives over HTTP on this whitelisted endpoint; int() raised ValueError
	# on anything non-numeric. cint() coerces, and 0 falls back to the default.
	limit = max(1, min(cint(limit) or 10, 50))
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee not found."))

	employee_doc = frappe.get_doc("Employee", employee)
	frappe.has_permission("Employee", "read", doc=employee_doc, throw=True)

	if not frappe.has_permission("Monthly Payroll", "read"):
		return []

	rows = frappe.db.sql(
		"""
		SELECT
			parent.name AS payroll,
			parent.period_label,
			parent.month,
			parent.year,
			parent.posting_date,
			parent.status,
			parent.payroll_journal_entry,
			child.gross_salary,
			child.total_deductions,
			child.net_salary,
			child.salary_mode
		FROM `tabMonthly Payroll Employee` child
		INNER JOIN `tabMonthly Payroll` parent ON parent.name = child.parent
		WHERE child.employee = %s
			AND parent.docstatus = 1
			AND IFNULL(parent.payroll_journal_entry, '') != ''
		ORDER BY parent.posting_date DESC, parent.modified DESC
		LIMIT %s
		""",
		(employee, limit),
		as_dict=True,
	)

	history = []
	for row in rows:
		period_label = row.period_label or f"{row.month} {row.year}"
		history.append(
			{
				"payroll": row.payroll,
				"period_label": period_label,
				"posting_date": str(row.posting_date) if row.posting_date else None,
				"status": row.status,
				"journal_entry": row.payroll_journal_entry,
				"gross_salary": flt(row.gross_salary),
				"total_deductions": flt(row.total_deductions),
				"net_salary": flt(row.net_salary),
				"salary_mode": row.salary_mode,
			}
		)

	return history


@frappe.whitelist()
def get_attendance_insights(month=None, year=None):
	employee, _profile = _require_employee_context()
	return _get_attendance_insights(employee, month=month, year=year)


@frappe.whitelist()
def get_available_locations():
	employee, profile = _require_employee_context()
	branch = profile.branch
	filters = {"hrsuite_is_active": 1}
	if not ELEVATED_ROLES.intersection(set(frappe.get_roles())):
		filters["hrsuite_branch"] = branch

	return frappe.get_all(
		"Shift Location",
		filters=filters,
		fields=[
			"name",
			"location_name",
			"hrsuite_branch as branch",
			"latitude",
			"longitude",
			"checkin_radius as allowed_radius_meters",
			"hrsuite_plus_code as plus_code",
			"hrsuite_location_source as location_source",
		],
		order_by="location_name asc",
	)


@frappe.whitelist()
def sync_branch_employee_directory():
	from hr_suite.hr_suite.doctype.hr_suite_settings.hr_suite_settings import sync_branch_employee_directory as _sync

	return _sync()


@frappe.whitelist()
def download_employee_branch_template():
	from hr_suite.hr_suite.doctype.hr_suite_settings.hr_suite_settings import (
		download_employee_branch_template as _download,
	)

	return _download()


@frappe.whitelist()
def import_employee_branch_template(file_url=None):
	from hr_suite.hr_suite.doctype.hr_suite_settings.hr_suite_settings import import_employee_branch_template as _import

	return _import(file_url=file_url)


# ─── Payroll Adjustment Items Helpers ─────────────────────────────────────────

@frappe.whitelist()
def fetch_approved_overtime_for_payroll(payroll_name):
	"""
	Fetches all approved, unlinked Overtime Requests for the payroll period
	and populates adjustment items on matching employee rows.
	Fetch approved overtime requests not linked to a payroll and add them as adjustment items.
	"""
	doc = frappe.get_doc("Monthly Payroll", payroll_name)
	frappe.has_permission("Monthly Payroll", "write", doc=doc, throw=True)

	month_map = {
		"January": 1, "February": 2, "March": 3,
		"April": 4, "May": 5, "June": 6,
		"July": 7, "August": 8, "September": 9,
		"October": 10, "November": 11, "December": 12,
	}
	month_num = month_map.get(doc.month, 0)
	if not month_num:
		frappe.throw(_("Invalid month in payroll"))

	# `year` is a Data field on Monthly Payroll, so int() would raise a bare ValueError
	# on anything non-numeric and the period would then be built from it regardless.
	year_num = cint(doc.year)
	if not 1900 <= year_num <= 2999:
		frappe.throw(_("Invalid year {0} in payroll.").format(doc.year))

	last_day = calendar.monthrange(year_num, month_num)[1]
	period_start = datetime.date(year_num, month_num, 1)
	period_end = datetime.date(year_num, month_num, last_day)

	overtime_requests = frappe.get_all(
		"Overtime Request",
		filters={
			"docstatus": 1,
			"approval_status": "Approved",
			"date": ["between", [period_start, period_end]],
			"payroll_period": ["in", ["", None]],
			"company": doc.company,
		},
		fields=["name", "employee", "employee_name", "overtime_hours", "overtime_amount", "date"],
	)

	if not overtime_requests:
		frappe.msgprint(_("No approved overtime requests found for this period."))
		return {"added": 0}

	# Build employee lookup for rows included in this payroll
	payroll_employees = {row.employee for row in doc.employees if row.employee}

	added = 0
	for ot in overtime_requests:
		if ot.employee not in payroll_employees:
			continue

		# Check if already added
		already_exists = False
		for item in getattr(doc, "adjustment_items", []) or []:
			if item.reference_doctype == "Overtime Request" and item.reference_name == ot.name:
				already_exists = True
				break
		if already_exists:
			continue

		doc.append("adjustment_items", {
			"employee": ot.employee,
			"item_type": "Addition",
			"description": _("Overtime {0}h on {1}").format(
				ot.overtime_hours, ot.date
			),
			"amount": flt(ot.overtime_amount),
			"reference_doctype": "Overtime Request",
			"reference_name": ot.name,
		})

		# Mark OT as linked
		frappe.db.set_value("Overtime Request", ot.name, "payroll_period", doc.name)
		added += 1

	if added:
		doc.save()
		frappe.msgprint(
			_("Added {0} overtime adjustment items.").format(added),
			indicator="green",
		)

	return {"added": added}


@frappe.whitelist()
def add_payroll_adjustment_item(payroll_name, employee, item_type, description, amount):
	"""
	Add a single adjustment item to a payroll employee row.
	Add a single adjustment item for an employee in payroll.
	"""
	doc = frappe.get_doc("Monthly Payroll", payroll_name)
	frappe.has_permission("Monthly Payroll", "write", doc=doc, throw=True)

	target_row = None
	for row in doc.employees:
		if row.employee == employee:
			target_row = row
			break

	if not target_row:
		frappe.throw(_("Employee {0} not found in payroll.").format(employee))

	doc.append("adjustment_items", {
		"employee": employee,
		"item_type": item_type,
		"description": description,
		"amount": flt(amount),
	})
	doc.save()

	return {"status": "ok"}

@frappe.whitelist()
def get_employee_work_country(employee: str) -> str:
	"""Guarded HTTP wrapper — the helper itself is called internally without a session check."""
	assert_employee_access(employee)

	from hr_suite.hr_suite.utils import get_employee_work_country as _work_country

	return _work_country(employee)


@frappe.whitelist()
def get_settlement_estimate(employee: str, termination_reason: str, termination_date: str = None) -> dict:
	"""Guarded HTTP wrapper — end-of-service money must not be readable for any employee."""
	assert_employee_access(employee)

	from hr_suite.hr_suite.utils import get_settlement_estimate as _settlement

	return _settlement(employee, termination_reason, termination_date)
