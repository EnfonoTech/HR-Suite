import frappe


ELEVATED_ROLES = {"HR Manager", "HR User", "System Manager", "Leave Approver"}
DEPARTMENT_APPROVER_ROLE = "Department Approver"
DIRECT_MANAGER_FIELDS = ("leave_approver", "expense_approver")
ANNUAL_LEAVE_FINANCE_ROLE = "Accounts Manager"
ANNUAL_LEAVE_FINANCE_VISIBLE_STATES = {"Pending Finance Approval", "Approved"}


def _has_elevated_access(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(ELEVATED_ROLES.intersection(set(frappe.get_roles(user))))


def _get_employee_for_user(user=None):
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def _has_department_approver_role(user=None):
	user = user or frappe.session.user
	return DEPARTMENT_APPROVER_ROLE in frappe.get_roles(user)


def _get_branch_for_user(user=None):
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user}, "branch")


def _employee_query(doctype, user=None):
	if _has_elevated_access(user):
		return ""

	employee = _get_employee_for_user(user)
	if not employee:
		return "1=0"

	return f"`tab{doctype}`.`employee` = {frappe.db.escape(employee)}"


def _branch_query(doctype, user=None):
	if _has_elevated_access(user):
		return ""

	branch = _get_branch_for_user(user)
	if not branch:
		return "1=0"

	return f"`tab{doctype}`.`branch` = {frappe.db.escape(branch)}"


def _employee_permission(doc, user=None):
	if _has_elevated_access(user):
		return True

	employee = _get_employee_for_user(user)
	return bool(employee and getattr(doc, "employee", None) == employee)


def _get_existing_employee_fields(fieldnames):
	return tuple(fieldname for fieldname in fieldnames if frappe.db.has_column("Employee", fieldname))


def _employee_or_approver_query(doctype, approver_fields=None, user=None):
	if _has_elevated_access(user):
		return ""

	user = user or frappe.session.user
	conditions = []
	employee = _get_employee_for_user(user)
	if employee:
		conditions.append(f"`tab{doctype}`.`employee` = {frappe.db.escape(employee)}")

	approver_fields = _get_existing_employee_fields(approver_fields or ())
	manager_employee = _get_employee_for_user(user)
	if _has_department_approver_role(user) and (approver_fields or manager_employee):
		approver_checks = [
			f"`tabEmployee`.`{fieldname}` = {frappe.db.escape(user)}" for fieldname in approver_fields
		]
		if "reports_to" in _get_existing_employee_fields(("reports_to",)) and manager_employee:
			approver_checks.append(f"`tabEmployee`.`reports_to` = {frappe.db.escape(manager_employee)}")
		conditions.append(
			f"EXISTS (SELECT 1 FROM `tabEmployee` WHERE `tabEmployee`.`name` = `tab{doctype}`.`employee` AND ({' OR '.join(approver_checks)}))"
		)

	if not conditions:
		return "1=0"

	return "(" + " OR ".join(conditions) + ")"


def _employee_or_approver_permission(doc, approver_fields=None, user=None):
	if _has_elevated_access(user):
		return True

	user = user or frappe.session.user
	employee = _get_employee_for_user(user)
	if employee and getattr(doc, "employee", None) == employee:
		return True

	approver_fields = _get_existing_employee_fields(approver_fields or ())
	if not _has_department_approver_role(user):
		return False

	approver_values = frappe.db.get_value("Employee", getattr(doc, "employee", None), list(approver_fields), as_dict=True) or {}
	if any(approver_values.get(fieldname) == user for fieldname in approver_fields):
		return True

	manager_employee = _get_employee_for_user(user)
	if manager_employee and frappe.db.has_column("Employee", "reports_to"):
		return frappe.db.get_value("Employee", getattr(doc, "employee", None), "reports_to") == manager_employee

	return False


def _workflow_role_query(doctype, role, allowed_states, user=None):
	user = user or frappe.session.user
	if role not in frappe.get_roles(user):
		return ""

	escaped_states = ", ".join(frappe.db.escape(state) for state in sorted(allowed_states))
	return f"`tab{doctype}`.`workflow_state` in ({escaped_states})"


def _workflow_role_permission(doc, role, allowed_states, user=None):
	user = user or frappe.session.user
	return role in frappe.get_roles(user) and getattr(doc, "workflow_state", None) in allowed_states


def _branch_permission(doc, user=None):
	if _has_elevated_access(user):
		return True

	branch = _get_branch_for_user(user)
	return bool(branch and getattr(doc, "branch", None) == branch)


def get_saudi_employee_checkin_query(user=None):
	return _employee_query("Saudi Employee Checkin", user)


def has_saudi_employee_checkin_permission(doc, user=None, permission_type=None):
	return _employee_permission(doc, user)


def get_saudi_daily_attendance_query(user=None):
	return _employee_query("Saudi Daily Attendance", user)


def has_saudi_daily_attendance_permission(doc, user=None, permission_type=None):
	return _employee_permission(doc, user)


def get_monthly_attendance_record_query(user=None):
	return _employee_query("Monthly Attendance Record", user)


def has_monthly_attendance_record_permission(doc, user=None, permission_type=None):
	return _employee_permission(doc, user)


def get_saudi_annual_leave_query(user=None):
	if _has_elevated_access(user):
		return ""

	conditions = []
	employee_scope = _employee_or_approver_query("Saudi Annual Leave", DIRECT_MANAGER_FIELDS, user)
	if employee_scope and employee_scope != "1=0":
		conditions.append(employee_scope)

	finance_scope = _workflow_role_query(
		"Saudi Annual Leave",
		ANNUAL_LEAVE_FINANCE_ROLE,
		ANNUAL_LEAVE_FINANCE_VISIBLE_STATES,
		user,
	)
	if finance_scope:
		conditions.append(finance_scope)

	return "(" + " OR ".join(conditions) + ")" if conditions else "1=0"


def has_saudi_annual_leave_permission(doc, user=None, permission_type=None):
	if _employee_or_approver_permission(doc, DIRECT_MANAGER_FIELDS, user):
		return True

	return _workflow_role_permission(
		doc,
		ANNUAL_LEAVE_FINANCE_ROLE,
		ANNUAL_LEAVE_FINANCE_VISIBLE_STATES,
		user,
	)


def get_saudi_sick_leave_query(user=None):
	return _employee_or_approver_query("Saudi Sick Leave", DIRECT_MANAGER_FIELDS, user)


def has_saudi_sick_leave_permission(doc, user=None, permission_type=None):
	return _employee_or_approver_permission(doc, DIRECT_MANAGER_FIELDS, user)


def get_overtime_request_query(user=None):
	return _employee_or_approver_query("Overtime Request", DIRECT_MANAGER_FIELDS, user)


def has_overtime_request_permission(doc, user=None, permission_type=None):
	return _employee_or_approver_permission(doc, DIRECT_MANAGER_FIELDS, user)


def get_salary_adjustment_query(user=None):
	return _employee_or_approver_query("Salary Adjustment", DIRECT_MANAGER_FIELDS, user)


def has_salary_adjustment_permission(doc, user=None, permission_type=None):
	return _employee_or_approver_permission(doc, DIRECT_MANAGER_FIELDS, user)


def get_maternity_paternity_leave_query(user=None):
	return _employee_query("Maternity Paternity Leave", user)


def has_maternity_paternity_leave_permission(doc, user=None, permission_type=None):
	return _employee_permission(doc, user)


def get_special_leave_query(user=None):
	return _employee_query("Special Leave", user)


def has_special_leave_permission(doc, user=None, permission_type=None):
	return _employee_permission(doc, user)


def get_attendance_location_query(user=None):
	return _branch_query("Attendance Location", user)


def has_attendance_location_permission(doc, user=None, permission_type=None):
	return _branch_permission(doc, user)