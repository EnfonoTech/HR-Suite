"""
install.py — Executed when the application is first installed.
Creates: Saudi leave types, EOSB rules, default GOSI settings.
"""

import json
from pathlib import Path

import frappe


def _get_existing_employee_approver_fields():
	return [
		fieldname
		for fieldname in ("leave_approver", "expense_approver")
		if frappe.db.has_column("Employee", fieldname)
	]


def after_install():
	create_workflow_states()
	sync_workflow_configs()
	sync_compliance_controls()
	ensure_department_approver_role()
	sync_department_approver_role_assignments()
	sync_department_approver_company_permissions()
	sync_dashboard_chart_configs()
	sync_notification_configs()
	create_default_saudi_shift_type()
	create_default_settings()
	ensure_employee_custom_fields()
	frappe.db.commit()


def after_migrate():
	"""Called after every bench migrate — ensures workflow states always exist."""
	create_workflow_states()
	sync_workflow_configs()
	sync_compliance_controls()
	ensure_department_approver_role()
	sync_department_approver_role_assignments()
	sync_department_approver_company_permissions()
	sync_dashboard_chart_configs()
	sync_notification_configs()
	create_default_saudi_shift_type()
	migrate_legacy_shift_data()
	migrate_legacy_annual_leave()
	migrate_legacy_employee_loans()
	ensure_employee_custom_fields()
	remove_obsolete_reports()


def ensure_department_approver_role():
	"""Ensure the custom workflow role for line managers exists."""
	if frappe.db.exists("Role", "Department Approver"):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "Department Approver",
			"desk_access": 1,
		}
	).insert(ignore_permissions=True)


def sync_department_approver_role_assignments():
	"""Assign the Department Approver role to users already configured as approvers."""
	if not frappe.db.exists("Role", "Department Approver"):
		return

	from frappe.utils.user import add_role

	for user in _get_department_approver_users():
		add_role(user, "Department Approver")


def sync_department_approver_company_permissions():
	"""Keep approver users aligned with the companies of employees they approve."""
	approver_fields = _get_existing_employee_approver_fields()
	if not approver_fields:
		return

	from frappe.permissions import add_user_permission

	for user in _get_department_approver_users():
		conditions = " OR ".join(f"{fieldname} = %(user)s" for fieldname in approver_fields)
		companies = frappe.db.sql(
			"""
				SELECT DISTINCT company
				FROM `tabEmployee`
				WHERE ({conditions})
				  AND IFNULL(company, '') != ''
			""".format(conditions=conditions),
			{"user": user},
			as_dict=True,
		)

		for row in companies:
			if not frappe.db.exists(
				"User Permission",
				{"user": user, "allow": "Company", "for_value": row.company},
			):
				add_user_permission("Company", row.company, user, ignore_permissions=True)


def _get_department_approver_users():
	approver_users = set()
	for fieldname in _get_existing_employee_approver_fields():
		approver_users.update(
			user
			for user in frappe.get_all("Employee", filters={fieldname: ["!=", ""]}, pluck=fieldname)
			if user and frappe.db.exists("User", user)
		)

	if frappe.db.exists("DocType", "Department Approver"):
		approver_users.update(
			user
			for user in frappe.get_all("Department Approver", filters={"approver": ["!=", ""]}, pluck="approver")
			if user and frappe.db.exists("User", user)
		)

	return approver_users


def sync_dashboard_chart_configs():
	"""Keep standard Hr Suite dashboard charts on the correct Frappe code path."""
	chart_updates = {
		"Nationality Distribution": {"chart_type": "Group By"},
		"Active Contracts by Type": {"chart_type": "Group By"},
	}

	for chart_name, values in chart_updates.items():
		if not frappe.db.exists("Dashboard Chart", chart_name):
			continue

		for fieldname, value in values.items():
			if frappe.db.get_value("Dashboard Chart", chart_name, fieldname) == value:
				continue

			frappe.db.set_value("Dashboard Chart", chart_name, fieldname, value, update_modified=False)


def sync_notification_configs():
	"""Keep GOSI notifications aligned with the scheduler-driven compliance flow."""
	old_name = "GOSI Due Alert"
	new_name = "GOSI Status Update Alert"

	if frappe.db.exists("Notification", old_name):
		event = frappe.db.get_value("Notification", old_name, "event")
		value_changed = frappe.db.get_value("Notification", old_name, "value_changed")

		if event == "Change" and value_changed == "payment_status":
			if frappe.db.exists("Notification", new_name):
				frappe.delete_doc("Notification", old_name, force=1, ignore_permissions=True)
			else:
				frappe.rename_doc("Notification", old_name, new_name, force=True, merge=False)


def sync_compliance_controls():
	"""Install and update the Saudi Labor Regulations compliance layer."""
	from hr_suite.hr_suite.compliance_controls import sync_compliance_controls as sync_controls

	sync_controls()


# ─── Workflow States ──────────────────────────────────────────────────────────

def create_workflow_states():
        """Create workflow states required for all hr_suite workflows."""
        states = [
		("Draft",                                      "Warning"),
                ("Draft",                              "Warning"),
		("Open",                                       "Warning"),
                ("Open",                               "Warning"),
		("Under Review",                               "Primary"),
                ("Under Review",                "Primary"),
		("In Progress",                                "Primary"),
                ("In Progress",                  "Primary"),
                ("In Progress",                  "Primary"),
		("Pending HR",                                 "Primary"),
                ("Pending HR",                    "Primary"),
		("Pending HR Approval",                        "Primary"),
		("Pending Finance Approval",                   "Primary"),
		("Pending Manager",                            "Primary"),
		("Pending Manager Approval",                   "Primary"),
                ("Pending Manager",   "Primary"),
		("HR Review",                                  "Primary"),
                ("HR Review",                      "Primary"),
		("Management Approval",                        "Primary"),
                ("Management Approval",       "Primary"),
		("Notice Sent",                                "Primary"),
                ("Notice Sent",                   "Primary"),
		("Approved",                                   "Success"),
                ("Approved",                           "Success"),
		("Decided",                                    "Success"),
                ("Decided",                          "Success"),
		("Resolved",                                   "Success"),
                ("Resolved",                           "Success"),
		("Completed",                                  "Success"),
                ("Completed",                          "Success"),
		("Closed",                                     "Success"),
                ("Closed",                              "Success"),
		("Rejected",                                   "Danger"),
                ("Rejected",                           "Danger"),
		("Cancelled",                                  "Danger"),
                ("Cancelled",                           "Danger"),
        ]
        for state_name, style in states:
                if not frappe.db.exists("Workflow State", state_name):
                        frappe.get_doc({
                                "doctype": "Workflow State",
                                "workflow_state_name": state_name,
                                "style": style,
                        }).insert(ignore_permissions=True)


def sync_workflow_configs():
	workflow_dir = Path(frappe.get_app_path("hr_suite", "hr_suite", "workflow"))
	if not workflow_dir.exists():
		return

	for path in sorted(workflow_dir.glob("*/*.json")):
		with path.open(encoding="utf-8") as workflow_file:
			workflow_data = json.load(workflow_file)

		if workflow_data.get("doctype") != "Workflow":
			continue

		for constant_field in ("creation", "modified", "modified_by", "owner", "idx"):
			workflow_data.pop(constant_field, None)

		workflow_name = workflow_data.get("name") or workflow_data.get("workflow_name")
		if not workflow_name:
			continue

		workflow_data["name"] = workflow_name
		workflow_data["workflow_name"] = workflow_name
		workflow_data.setdefault("module", "Hr Suite")
		ensure_workflow_actions(workflow_data)

		try:
			if frappe.db.exists("Workflow", workflow_name):
				workflow = frappe.get_doc("Workflow", workflow_name)
				workflow.update(workflow_data)
				workflow.save(ignore_permissions=True)
			else:
				frappe.get_doc(workflow_data).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Hr Suite Workflow Sync Failed: {workflow_name}")


def ensure_workflow_actions(workflow_data):
	for transition in workflow_data.get("transitions", []):
		action = transition.get("action")
		if not action or frappe.db.exists("Workflow Action Master", action):
			continue

		frappe.get_doc(
			{
				"doctype": "Workflow Action Master",
				"workflow_action_name": action,
			}
		).insert(ignore_permissions=True)


# ─── Saudi Shift Management ───────────────────────────────────────────────────

def create_default_saudi_shift_type():
	"""Create a local Hr Suite shift so attendance works without an external HR app."""
	if not frappe.db.exists("DocType", "Saudi Shift Type"):
		return
	if frappe.db.exists("Saudi Shift Type", "Day Shift"):
		return

	frappe.get_doc(
		{
			"doctype": "Saudi Shift Type",
			"shift_name": "Day Shift",
			"start_time": "08:00:00",
			"end_time": "17:00:00",
			"begin_check_in_before_shift_start_time": 60,
			"allow_check_out_after_shift_end_time": 60,
			"enable_late_entry_marking": 1,
			"late_entry_grace_period": 15,
			"enable_early_exit_marking": 1,
			"early_exit_grace_period": 15,
		}
	).insert(ignore_permissions=True)


def migrate_legacy_shift_data():
	"""Copy legacy shift records into Hr Suite-owned doctypes before removing the old app."""
	if not frappe.db.exists("DocType", "Saudi Shift Type"):
		return

	if frappe.db.exists("DocType", "Shift Type"):
		shift_type_fields = [
			"name",
			"start_time",
			"end_time",
			"begin_check_in_before_shift_start_time",
			"allow_check_out_after_shift_end_time",
			"enable_late_entry_marking",
			"late_entry_grace_period",
			"enable_early_exit_marking",
			"early_exit_grace_period",
		]
		if frappe.db.has_column("Shift Type", "disabled"):
			shift_type_fields.append("disabled")

		for row in frappe.get_all(
			"Shift Type",
			fields=shift_type_fields,
		):
			if frappe.db.exists("Saudi Shift Type", row.name):
				continue
			frappe.get_doc(
				{
					"doctype": "Saudi Shift Type",
					"shift_name": row.name,
					"start_time": row.start_time,
					"end_time": row.end_time,
					"begin_check_in_before_shift_start_time": row.begin_check_in_before_shift_start_time,
					"allow_check_out_after_shift_end_time": row.allow_check_out_after_shift_end_time,
					"enable_late_entry_marking": row.enable_late_entry_marking,
					"late_entry_grace_period": row.late_entry_grace_period,
					"enable_early_exit_marking": row.enable_early_exit_marking,
					"early_exit_grace_period": row.early_exit_grace_period,
					"disabled": row.get("disabled", 0),
				}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("DocType", "Saudi Shift Assignment") or not frappe.db.exists("DocType", "Shift Assignment"):
		return

	for row in frappe.get_all(
		"Shift Assignment",
		fields=["name", "employee", "shift_type", "start_date", "end_date", "status", "docstatus"],
	):
		if not frappe.db.exists("Saudi Shift Type", row.shift_type):
			continue
		if frappe.db.exists(
			"Saudi Shift Assignment",
			{
				"employee": row.employee,
				"shift_type": row.shift_type,
				"start_date": row.start_date,
				"end_date": row.end_date,
			},
		):
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Saudi Shift Assignment",
				"employee": row.employee,
				"shift_type": row.shift_type,
				"start_date": row.start_date,
				"end_date": row.end_date,
				"status": row.status or "Active",
				"notes": f"Migrated from legacy Shift Assignment {row.name}",
			}
		)
		doc.insert(ignore_permissions=True)
		if row.docstatus == 1:
			doc.submit()


# ─── Leave Types ───────────────────────────────────────────────────────────────

def migrate_legacy_annual_leave():
	"""Copy legacy annual leave requests into Saudi Annual Leave before removing the old app."""
	if not frappe.db.exists("DocType", "Saudi Annual Leave"):
		return
	if not frappe.db.exists("DocType", "Leave Application"):
		return

	annual_types = (
		"Saudi Annual Leave",
		"Annual Leave",
	)
	rows = frappe.get_all(
		"Leave Application",
		filters={"leave_type": ["in", list(annual_types)]},
		fields=[
			"name",
			"employee",
			"employee_name",
			"company",
			"department",
			"from_date",
			"to_date",
			"half_day",
			"description",
			"status",
			"docstatus",
			"creation",
		],
	)

	for row in rows:
		if frappe.db.exists("Saudi Annual Leave", {"legacy_reference": row.name}):
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Saudi Annual Leave",
				"employee": row.employee,
				"employee_name": row.employee_name,
				"company": row.company,
				"department": row.department,
				"leave_start_date": row.from_date,
				"leave_end_date": row.to_date,
				"half_day": row.half_day,
				"description": row.description,
				"legacy_reference": row.name,
			}
		)
		doc.insert(ignore_permissions=True)
		if row.docstatus == 1:
			doc.submit()
		elif row.docstatus == 2:
			doc.submit()
			doc.cancel()
		elif row.status:
			doc.db_set("status", row.status)


def migrate_legacy_employee_loans():
	"""Backfill approval states for loans created before the approval workflow existed."""
	if not frappe.db.exists("DocType", "Employee Loan"):
		return

	from hr_suite.hr_suite.doctype.employee_loan.employee_loan import reconcile_legacy_employee_loans

	reconcile_legacy_employee_loans()


# ─── Hr Suite Settings ──────────────────────────────────────────────────────────

def create_default_settings():
	"""Create default Hr Suite settings."""
	if frappe.db.exists("Hr Suite Settings", "Hr Suite Settings"):
		return

	settings = frappe.get_doc({
		"doctype": "Hr Suite Settings",
		"gosi_saudi_employee_rate": 10.0,
		"gosi_saudi_employer_rate": 12.0,
		"gosi_non_saudi_employee_rate": 0.0,
		"gosi_non_saudi_employer_rate": 2.0,
		"annual_leave_years_threshold": 5,
		"annual_leave_before_threshold": 21,
		"annual_leave_after_threshold": 30,
		"probation_period_days": 90,
		"max_probation_period_days": 180,
		"notice_period_monthly_days": 60,
		"notice_period_non_monthly_days": 30,
		"sick_leave_full_pay_days": 30,
		"sick_leave_partial_pay_days": 60,
		"sick_leave_partial_pay_percentage": 75,
		"iqama_expiry_alert_days": 90,
	})
	try:
		settings.insert(ignore_permissions=True)
		frappe.msgprint("Created Hr Suite default settings", alert=True)
	except Exception:
		pass


# ─── Employee Custom Fields ────────────────────────────────────────────────────

def ensure_employee_custom_fields():
	"""Add HR Suite custom fields to the Employee doctype if not already present."""
	fields = [
		# GOSI Contribution Base salary — shown in Overview after General Details
		{
			"dt": "Employee",
			"fieldname": "hr_suite_gosi_salary",
			"label": "GOSI Contribution Base",
			"fieldtype": "Currency",
			"insert_after": "custom_visa_designation",
			"module": "Hr Suite",
			"description": "Basic salary used for GOSI contribution calculation",
		},
		# Employee Type (Saudi National / Expatriate) — drives GOSI rates and Nitaqat
		{
			"dt": "Employee",
			"fieldname": "hr_suite_employee_type",
			"label": "Employee Type",
			"fieldtype": "Select",
			"options": "\nSaudi National\nExpatriate",
			"insert_after": "hr_suite_gosi_salary",
			"module": "Hr Suite",
			"description": "Determines GOSI contribution rates and Nitaqat classification",
			"in_list_view": 1,
			"search_index": 1,
		},
		# Employee Documents section header
		{
			"dt": "Employee",
			"fieldname": "hr_suite_documents_section",
			"label": "Employee Documents",
			"fieldtype": "Section Break",
			"insert_after": "hr_suite_employee_type",
			"module": "Hr Suite",
		},
		# Documents child table (Iqama, Passport, Health Insurance, etc.)
		{
			"dt": "Employee",
			"fieldname": "hr_suite_documents",
			"label": "Documents",
			"fieldtype": "Table",
			"options": "Employee Document",
			"insert_after": "hr_suite_documents_section",
			"module": "Hr Suite",
		},
	]
	for cf in fields:
		if frappe.db.exists("Custom Field", {"dt": cf["dt"], "fieldname": cf["fieldname"]}):
			continue
		try:
			frappe.get_doc({"doctype": "Custom Field", **cf}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"HR Suite: failed to create custom field {cf['fieldname']}")


# ─── Remove Obsolete Reports ───────────────────────────────────────────────────

def remove_obsolete_reports():
	"""Delete report DB records whose Python module files have been removed."""
	stale = [
		"Team Attendance Review",
	]
	for report_name in stale:
		if frappe.db.exists("Report", report_name):
			try:
				frappe.delete_doc("Report", report_name, force=1, ignore_permissions=True)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"HR Suite: could not delete stale report {report_name}")

	# Remove stale Saudi Employee Voice Profile doctype registration
	if frappe.db.exists("DocType", "Saudi Employee Voice Profile"):
		try:
			frappe.delete_doc("DocType", "Saudi Employee Voice Profile", force=1, ignore_permissions=True)
		except Exception:
			pass
