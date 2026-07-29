"""
install.py — Executed when the application is first installed.
Creates: leave types, statutory defaults, and Country Config for all operating countries.
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
	create_default_shift_type()
	create_default_settings()
	ensure_employee_custom_fields()
	seed_country_configs()
	seed_employee_document_types()
	seed_grievance_types()
	frappe.db.commit()


def after_migrate():
	"""Called after every bench migrate — ensures workflow states always exist."""
	rename_saudi_doctypes()
	_cleanup_deprecated_doctypes()
	create_workflow_states()
	sync_workflow_configs()
	sync_compliance_controls()
	ensure_department_approver_role()
	sync_department_approver_role_assignments()
	sync_department_approver_company_permissions()
	sync_dashboard_chart_configs()
	sync_notification_configs()
	create_default_shift_type()
	migrate_legacy_annual_leave()
	migrate_legacy_employee_loans()
	ensure_employee_custom_fields()
	seed_country_configs()
	seed_employee_document_types()
	seed_grievance_types()
	remove_obsolete_reports()


def _cleanup_deprecated_doctypes():
	"""Remove DocType records for doctypes eliminated in favour of HRMS equivalents."""
	for dt in ("Hiring Requisition", "Performance Review"):
		if frappe.db.exists("DocType", dt):
			try:
				frappe.delete_doc("DocType", dt, ignore_permissions=True, force=True)
			except Exception:
				frappe.log_error(f"Could not delete deprecated DocType {dt}", "HR Suite cleanup")


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


# ─── Shift Management ───────────────────────────────────────────────────

def rename_saudi_doctypes():
	"""Idempotent migration: rename Saudi-prefixed generic DocTypes to country-neutral names."""
	renames = [
		("Saudi Monthly Payroll Employee", "Monthly Payroll Employee"),
		("Saudi Monthly Payroll", "Monthly Payroll"),
		("Saudi Annual Leave", "Annual Leave"),
		("Saudi Sick Leave", "Sick Leave"),
		("Saudi Regulatory Task", "Regulatory Task"),
		("Saudi Employment Contract", "Country Employment Contract"),
	]
	for old_name, new_name in renames:
		if frappe.db.exists("DocType", old_name) and not frappe.db.exists("DocType", new_name):
			try:
				frappe.rename_doc("DocType", old_name, new_name, force=True, ignore_permissions=True)
				frappe.db.commit()
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"HR Suite: rename DocType {old_name} → {new_name} failed")


def create_default_shift_type():
	"""Create a default HRMS Shift Type so mobile attendance works out of the box."""
	if not frappe.db.exists("DocType", "Shift Type"):
		return
	if frappe.db.exists("Shift Type", "Day Shift"):
		return

	frappe.get_doc(
		{
			"doctype": "Shift Type",
			"__newname": "Day Shift",
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


def migrate_legacy_annual_leave():
	"""Copy legacy annual leave requests into Annual Leave before removing the old app."""
	if not frappe.db.exists("DocType", "Annual Leave"):
		return
	if not frappe.db.exists("DocType", "Leave Application"):
		return

	annual_types = (
		"Annual Leave",
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
		if frappe.db.exists("Annual Leave", {"legacy_reference": row.name}):
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Annual Leave",
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
			"label": "Statutory Contribution Base",
			"fieldtype": "Currency",
			"insert_after": "custom_visa_designation",
			"module": "Hr Suite",
			"description": "Basic salary used for statutory contribution calculation (GOSI, GPSSA, SIO, PASI, EPF)",
		},
		# Employee Type (National / Expatriate) — drives statutory contribution rates
		{
			"dt": "Employee",
			"fieldname": "hr_suite_employee_type",
			"label": "Employee Type",
			"fieldtype": "Select",
			"options": "\nNational\nExpatriate",
			"insert_after": "hr_suite_gosi_salary",
			"module": "Hr Suite",
			"description": "Determines statutory contribution rates and nationalization quota classification",
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


# ─── Country Configuration Seed Data ──────────────────────────────────────────

_COUNTRY_CONFIGS = [
	{
		"country_code": "SA",
		"country_name": "Saudi Arabia",
		"currency": "SAR",
		"is_active": 1,
		# Statutory
		"statutory_scheme": "GOSI",
		"contribution_basis": "Basic Salary",
		"contribution_ceiling": 45000,
		"national_employee_rate": 10.0,
		"national_employer_rate": 12.0,
		"expat_employee_rate": 0.0,
		"expat_employer_rate": 2.0,
		# Settlement
		"settlement_formula": "EOSB-SA",
		"settlement_basis": "Basic Salary",
		"years_threshold": 5,
		"days_per_year_below_threshold": 21,
		"days_per_year_above_threshold": 30,
		"gratuity_eligibility_years": 2,
		"settlement_ceiling_applicable": 0,
		# Permits
		"primary_permit_label": "Iqama",
		"permit_expiry_alert_days": 90,
		"national_id_label": "National ID (Ahwal)",
		# WPS
		"wps_mandatory": 1,
		"wps_format": "SARIE (SA)",
		# Nationalization
		"nationalization_applies": 1,
		"nationalization_scheme_name": "Nitaqat",
		# Notice & Probation
		"notice_period_days_monthly": 60,
		"notice_period_days_others": 30,
		"max_probation_days": 180,
		# Leave types
		"leave_types": [
			{"leave_type_name": "Annual Leave", "days_per_year": 21, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 30, "frappe_leave_type_name": "Annual Leave"},
			{"leave_type_name": "Annual Leave (5+ Years)", "days_per_year": 30, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 30, "frappe_leave_type_name": "Annual Leave"},
			{"leave_type_name": "Sick Leave", "days_per_year": 120, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Sick Leave"},
			{"leave_type_name": "Maternity Leave", "days_per_year": 70, "gender_specific": "Female Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Maternity Leave"},
			{"leave_type_name": "Paternity Leave", "days_per_year": 3, "gender_specific": "Male Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Paternity Leave"},
			{"leave_type_name": "Hajj Leave", "days_per_year": 15, "gender_specific": "All", "is_optional": 0, "once_in_employment": 1, "max_carry_forward_days": 0, "frappe_leave_type_name": "Hajj Leave"},
			{"leave_type_name": "Iddah Leave", "days_per_year": 130, "gender_specific": "Female Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Iddah Leave"},
		],
	},
	{
		"country_code": "AE",
		"country_name": "United Arab Emirates",
		"currency": "AED",
		"is_active": 1,
		# Statutory (GPSSA for nationals; DEWS for DIFC; expats have no social insurance)
		"statutory_scheme": "GPSSA",
		"contribution_basis": "Basic Salary",
		"contribution_ceiling": 0,
		"national_employee_rate": 5.0,
		"national_employer_rate": 12.5,
		"expat_employee_rate": 0.0,
		"expat_employer_rate": 0.0,
		# Settlement
		"settlement_formula": "Gratuity-AE",
		"settlement_basis": "Basic Salary",
		"years_threshold": 5,
		"days_per_year_below_threshold": 21,
		"days_per_year_above_threshold": 30,
		"gratuity_eligibility_years": 1,
		"settlement_ceiling_applicable": 0,
		# Permits
		"primary_permit_label": "UAE Residence Visa",
		"permit_expiry_alert_days": 60,
		"national_id_label": "Emirates ID",
		# WPS
		"wps_mandatory": 1,
		"wps_format": "SIF-AE (UAE)",
		# Nationalization
		"nationalization_applies": 1,
		"nationalization_scheme_name": "Emiratisation (Nafis)",
		# Notice & Probation
		"notice_period_days_monthly": 30,
		"notice_period_days_others": 30,
		"max_probation_days": 180,
		# Leave types
		"leave_types": [
			{"leave_type_name": "Annual Leave", "days_per_year": 30, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 15, "frappe_leave_type_name": "Annual Leave"},
			{"leave_type_name": "Sick Leave", "days_per_year": 90, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Sick Leave"},
			{"leave_type_name": "Maternity Leave", "days_per_year": 60, "gender_specific": "Female Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Maternity Leave"},
			{"leave_type_name": "Paternity Leave", "days_per_year": 5, "gender_specific": "Male Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Paternity Leave"},
			{"leave_type_name": "Bereavement Leave", "days_per_year": 5, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Bereavement Leave"},
			{"leave_type_name": "Study Leave", "days_per_year": 10, "gender_specific": "All", "is_optional": 1, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Study Leave"},
		],
	},
	{
		"country_code": "BH",
		"country_name": "Bahrain",
		"currency": "BHD",
		"is_active": 1,
		# Statutory (SIO)
		"statutory_scheme": "SIO",
		"contribution_basis": "Basic Salary",
		"contribution_ceiling": 4000,
		"national_employee_rate": 7.0,
		"national_employer_rate": 12.0,
		"expat_employee_rate": 1.0,
		"expat_employer_rate": 3.0,
		# Settlement
		"settlement_formula": "Indemnity-BH",
		"settlement_basis": "Basic Salary",
		"years_threshold": 3,
		"days_per_year_below_threshold": 15,
		"days_per_year_above_threshold": 30,
		"gratuity_eligibility_years": 1,
		"settlement_ceiling_applicable": 0,
		# Permits
		"primary_permit_label": "CPR / Work Permit",
		"permit_expiry_alert_days": 60,
		"national_id_label": "CPR Number",
		# WPS
		"wps_mandatory": 1,
		"wps_format": "WPS-BH (Bahrain)",
		# Nationalization
		"nationalization_applies": 1,
		"nationalization_scheme_name": "Bahrainisation",
		# Notice & Probation
		"notice_period_days_monthly": 30,
		"notice_period_days_others": 30,
		"max_probation_days": 90,
		# Leave types
		"leave_types": [
			{"leave_type_name": "Annual Leave", "days_per_year": 30, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 30, "frappe_leave_type_name": "Annual Leave"},
			{"leave_type_name": "Sick Leave", "days_per_year": 55, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Sick Leave"},
			{"leave_type_name": "Maternity Leave", "days_per_year": 60, "gender_specific": "Female Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Maternity Leave"},
			{"leave_type_name": "Paternity Leave", "days_per_year": 1, "gender_specific": "Male Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Paternity Leave"},
			{"leave_type_name": "Hajj Leave", "days_per_year": 14, "gender_specific": "All", "is_optional": 0, "once_in_employment": 1, "max_carry_forward_days": 0, "frappe_leave_type_name": "Hajj Leave"},
		],
	},
	{
		"country_code": "IN",
		"country_name": "India",
		"currency": "INR",
		"is_active": 1,
		# Statutory (EPF + ESI — handled by dedicated EPF ESI Contribution doctype)
		"statutory_scheme": "EPF+ESI",
		"contribution_basis": "Basic Salary",
		"contribution_ceiling": 15000,
		"national_employee_rate": 12.0,
		"national_employer_rate": 12.0,
		"expat_employee_rate": 0.0,
		"expat_employer_rate": 0.0,
		# Settlement (Gratuity Act 1972: 15/26 × basic × years, 5yr min, ₹20L cap)
		"settlement_formula": "Gratuity-IN",
		"settlement_basis": "Basic Salary",
		"years_threshold": 5,
		"days_per_year_below_threshold": 15,
		"days_per_year_above_threshold": 15,
		"gratuity_eligibility_years": 5,
		"settlement_ceiling_applicable": 1,
		"settlement_ceiling_amount": 2000000,
		# Permits
		"primary_permit_label": "Work Permit / OCI",
		"permit_expiry_alert_days": 60,
		"national_id_label": "Aadhaar / PAN",
		# WPS
		"wps_mandatory": 0,
		"wps_format": "None",
		# Nationalization
		"nationalization_applies": 0,
		"nationalization_scheme_name": "",
		# Notice & Probation
		"notice_period_days_monthly": 30,
		"notice_period_days_others": 30,
		"max_probation_days": 180,
		# Leave types
		"leave_types": [
			{"leave_type_name": "Earned Leave", "days_per_year": 15, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 30, "frappe_leave_type_name": "Earned Leave"},
			{"leave_type_name": "Casual Leave", "days_per_year": 12, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Casual Leave"},
			{"leave_type_name": "Sick Leave", "days_per_year": 12, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Sick Leave"},
			{"leave_type_name": "Maternity Leave", "days_per_year": 182, "gender_specific": "Female Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Maternity Leave"},
			{"leave_type_name": "Paternity Leave", "days_per_year": 15, "gender_specific": "Male Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Paternity Leave"},
			{"leave_type_name": "Privilege Leave", "days_per_year": 15, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 45, "frappe_leave_type_name": "Privilege Leave"},
			{"leave_type_name": "Compensatory Off", "days_per_year": 0, "gender_specific": "All", "is_optional": 1, "once_in_employment": 0, "max_carry_forward_days": 5, "frappe_leave_type_name": "Compensatory Off"},
		],
	},
	{
		"country_code": "OM",
		"country_name": "Oman",
		"currency": "OMR",
		"is_active": 1,
		# Statutory (PASI)
		"statutory_scheme": "PASI",
		"contribution_basis": "Basic Salary",
		"contribution_ceiling": 5000,
		"national_employee_rate": 7.0,
		"national_employer_rate": 10.5,
		"expat_employee_rate": 0.0,
		"expat_employer_rate": 0.0,
		# Settlement
		"settlement_formula": "Indemnity-OM",
		"settlement_basis": "Basic Salary",
		"years_threshold": 3,
		"days_per_year_below_threshold": 15,
		"days_per_year_above_threshold": 30,
		"gratuity_eligibility_years": 1,
		"settlement_ceiling_applicable": 0,
		# Permits
		"primary_permit_label": "Oman Residence Card",
		"permit_expiry_alert_days": 60,
		"national_id_label": "Civil ID (Omani)",
		# WPS
		"wps_mandatory": 1,
		"wps_format": "WPS-OM (Oman)",
		# Nationalization
		"nationalization_applies": 1,
		"nationalization_scheme_name": "Omanisation",
		# Notice & Probation
		"notice_period_days_monthly": 30,
		"notice_period_days_others": 30,
		"max_probation_days": 180,
		# Leave types
		"leave_types": [
			{"leave_type_name": "Annual Leave", "days_per_year": 30, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 30, "frappe_leave_type_name": "Annual Leave"},
			{"leave_type_name": "Sick Leave", "days_per_year": 182, "gender_specific": "All", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Sick Leave"},
			{"leave_type_name": "Maternity Leave", "days_per_year": 50, "gender_specific": "Female Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Maternity Leave"},
			{"leave_type_name": "Paternity Leave", "days_per_year": 3, "gender_specific": "Male Only", "is_optional": 0, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Paternity Leave"},
			{"leave_type_name": "Hajj Leave", "days_per_year": 15, "gender_specific": "All", "is_optional": 0, "once_in_employment": 1, "max_carry_forward_days": 0, "frappe_leave_type_name": "Hajj Leave"},
			{"leave_type_name": "Study Leave", "days_per_year": 15, "gender_specific": "All", "is_optional": 1, "once_in_employment": 0, "max_carry_forward_days": 0, "frappe_leave_type_name": "Study Leave"},
		],
	},
]


def seed_country_configs():
	"""Seed Country Config master records for all 5 operating countries."""
	if not frappe.db.exists("DocType", "Country Config"):
		return

	for cfg_data in _COUNTRY_CONFIGS:
		code = cfg_data["country_code"]
		leave_types = cfg_data.pop("leave_types", [])

		existing = frappe.db.get_value("Country Config", {"country_code": code}, "name")
		if existing:
			cfg_data["leave_types"] = leave_types
			continue  # Don't overwrite admin-customised configs

		doc_data = dict(cfg_data)
		doc_data["doctype"] = "Country Config"
		doc_data["leave_types"] = [
			dict(lt, **{"doctype": "Country Leave Type Row"}) for lt in leave_types
		]

		try:
			frappe.get_doc(doc_data).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"HR Suite: failed to seed Country Config for {code}")

		# restore leave_types key in _COUNTRY_CONFIGS entry for idempotent re-runs
		cfg_data["leave_types"] = leave_types


# ─── Employee Document Types ────────────────────────────────────────────────────

def seed_grievance_types():
	"""HRMS keys Employee Grievance off Grievance Type records — seed the HR Suite set."""
	if not frappe.db.exists("DocType", "Grievance Type"):
		return

	for name in (
		"Pay",
		"Leave",
		"Attendance",
		"Manager Conduct",
		"Disciplinary Action",
		"Termination",
		"Harassment",
		"Other",
	):
		if frappe.db.exists("Grievance Type", name):
			continue
		try:
			frappe.get_doc({"doctype": "Grievance Type", "name": name}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"HR Suite: failed to seed Grievance Type {name}")


def seed_employee_document_types():
	defaults = [
		{"name": "Iqama", "description": "Saudi residency permit for expatriate employees", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Passport", "description": "International travel document", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "National ID", "description": "National identity card", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Health Insurance", "description": "Employee health insurance card or policy", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Driving License", "description": "Motor vehicle driving license", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Work Permit", "description": "Government-issued work authorization permit", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Visa", "description": "Entry or residency visa", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Employment Contract", "description": "Signed employment contract copy", "requires_expiry_date": 0, "requires_document_no": 0},
		{"name": "Educational Certificate", "description": "Degree, diploma, or certificate of qualification", "requires_expiry_date": 0, "requires_document_no": 1},
		{"name": "Professional License", "description": "Trade, professional, or occupational license", "requires_expiry_date": 1, "requires_document_no": 1},
		{"name": "Medical Certificate", "description": "Fitness-to-work or pre-employment medical report", "requires_expiry_date": 0, "requires_document_no": 0},
		{"name": "Police Clearance", "description": "Criminal background clearance certificate", "requires_expiry_date": 1, "requires_document_no": 0},
		{"name": "Bank Account Details", "description": "Salary payment bank account information", "requires_expiry_date": 0, "requires_document_no": 1},
		{"name": "Other", "description": "Any other employee document not listed above", "requires_expiry_date": 0, "requires_document_no": 0},
	]
	for doc in defaults:
		if not frappe.db.exists("Employee Document Type", doc["name"]):
			try:
				frappe.get_doc({"doctype": "Employee Document Type", **doc}).insert(ignore_permissions=True)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"HR Suite: failed to seed Employee Document Type '{doc['name']}'")


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
