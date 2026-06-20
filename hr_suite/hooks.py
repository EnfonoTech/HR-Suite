from . import __version__ as app_version


app_name = "hr_suite"
app_title = "Hr Suite"
app_publisher = "siva@enfono.com"
app_description = "Hr Suite - Multi-Country HR Management System"
app_email = "siva@enfono.com"
app_license = "mit"
required_apps = ["frappe/erpnext"]

# Apps Screen
add_to_apps_screen = [
	{
		"name": "hr_suite",
		"logo": "/assets/hr_suite/images/logo.svg",
		"title": "Hr Suite",
		"route": "/app/hr-suite",
	},
]

app_include_css = ["/assets/hr_suite/css/hr_suite.css"]

# ─── Scheduled Tasks ───────────────────────────────────────────────────────────
scheduler_events = {
	"daily": [
		"hr_suite.hr_suite.salary_override_api.apply_pending_salary_overrides",
		"hr_suite.hr_suite.integrations.muqeem.sync_expiring_iqamas",
		"hr_suite.hr_suite.integrations.gosi_api.sync_monthly_gosi",
		"hr_suite.hr_suite.tasks.send_iqama_expiry_alerts",
		"hr_suite.hr_suite.tasks.send_contract_expiry_alerts",
		"hr_suite.hr_suite.tasks.send_work_permit_expiry_alerts",
		"hr_suite.hr_suite.tasks.send_sick_leave_threshold_alerts",
		"hr_suite.hr_suite.tasks.send_probation_end_alerts",
		"hr_suite.hr_suite.tasks.send_ministry_filing_due_alerts",
		"hr_suite.hr_suite.tasks.send_final_settlement_sla_alerts",
		"hr_suite.hr_suite.tasks.send_employee_document_custody_alerts",
		"hr_suite.hr_suite.tasks.send_inspection_fine_sla_alerts",
		"hr_suite.hr_suite.tasks.send_wps_correction_due_alerts",
		"hr_suite.hr_suite.tasks.send_work_regulation_review_alerts",
		"hr_suite.hr_suite.tasks.send_expat_authorization_due_alerts",
		"hr_suite.hr_suite.tasks.send_training_disclosure_due_alerts",
	],
	"monthly": [
		"hr_suite.hr_suite.tasks.send_gosi_due_alerts",
		"hr_suite.hr_suite.integrations.qiwa.sync_nitaqat_monthly",
		"hr_suite.hr_suite.integrations.mudad.sync_wps_monthly",
	],
	"weekly": [
		"hr_suite.hr_suite.tasks.send_iqama_expiry_alerts",
	],
}

# ─── Document Events ────────────────────────────────────────────────────────────
doc_events = {
	"Overtime Request": {
		"on_submit": "hr_suite.hr_suite.doctype.overtime_request.overtime_request.create_overtime_journal_entry",
	},
	"Employee Penalty": {
		"before_save": "hr_suite.hr_suite.doctype.employee_penalty.employee_penalty.before_save",
		"on_submit":   "hr_suite.hr_suite.doctype.employee_penalty.employee_penalty.on_submit",
		"on_cancel":   "hr_suite.hr_suite.doctype.employee_penalty.employee_penalty.on_cancel",
	},
	"GOSI Contribution": {
		"on_submit": "hr_suite.hr_suite.doctype.gosi_contribution.gosi_contribution.create_payroll_entries",
	},
	"Policy Acknowledgement": {
		"after_insert": "hr_suite.hr_suite.doctype.policy_acknowledgement.policy_acknowledgement.update_policy_acknowledgement_summary",
		"on_update":    "hr_suite.hr_suite.doctype.policy_acknowledgement.policy_acknowledgement.update_policy_acknowledgement_summary",
		"on_trash":     "hr_suite.hr_suite.doctype.policy_acknowledgement.policy_acknowledgement.update_policy_acknowledgement_summary",
	},
	"Termination Notice": {
		"on_submit": "hr_suite.hr_suite.compliance_controls.create_final_settlement_from_termination",
	},
	"Work Regulation": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Statutory HR Records Register": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Ministry Filing Tracker": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Disability Employment Compliance": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Final Settlement SLA": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Work Arrangement Control": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Working Time Compliance Check": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Inspection Fine SLA": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Special Employment Category Control": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Holiday Leave Overlap Rule": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Expat Work Authorization Control": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Training Disclosure Register": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Disciplinary Procedure": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Recruitment Service Provider Compliance": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Recruitment Provider Complaint": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},
	"Training Agreement": {
		"validate": "hr_suite.hr_suite.compliance_controls.validate_compliance_doc",
	},

	# ── Frappe HRMS integration ───────────────────────────────────────────────
	"Job Offer": {
		"on_submit": "hr_suite.hr_suite.integrations.hrms.on_job_offer_submit",
	},
	"Salary Slip": {
		"before_submit": "hr_suite.hr_suite.integrations.hrms.before_salary_slip_submit",
	},
	"Employee": {
		"after_insert": "hr_suite.hr_suite.integrations.hrms.on_employee_insert",
		"on_update":    "hr_suite.hr_suite.integrations.hrms.on_employee_update",
	},
	"Appraisal": {
		"on_submit": "hr_suite.hr_suite.integrations.hrms.on_appraisal_submit",
	},
}

doctype_js = {
	"Employee": "public/js/employee.js",
	"Salary Structure Assignment": "public/js/salary_structure_assignment.js",
	"Work Permit / Iqama": "public/js/work_permit_iqama.js",
	"Nitaqat Record": "public/js/nitaqat_record.js",
	"Payroll Entry": "public/js/wps_payroll.js",
}

# ─── Jinja ──────────────────────────────────────────────────────────────────────
jinja = {
	"methods": [
		"hr_suite.hr_suite.utils.get_eosb_amount",
		"hr_suite.hr_suite.utils.get_annual_leave_entitlement",
		"hr_suite.hr_suite.utils.get_gosi_rates",
	]
}

override_whitelisted_methods = {}

permission_query_conditions = {
	"Annual Leave":       "hr_suite.hr_suite.permissions.get_annual_leave_query",
	"Sick Leave":         "hr_suite.hr_suite.permissions.get_sick_leave_query",
	"Overtime Request":         "hr_suite.hr_suite.permissions.get_overtime_request_query",
	"Salary Adjustment":        "hr_suite.hr_suite.permissions.get_salary_adjustment_query",
	"Maternity Paternity Leave":"hr_suite.hr_suite.permissions.get_maternity_paternity_leave_query",
	"Special Leave":            "hr_suite.hr_suite.permissions.get_special_leave_query",
}

has_permission = {
	"Annual Leave":       "hr_suite.hr_suite.permissions.has_annual_leave_permission",
	"Sick Leave":         "hr_suite.hr_suite.permissions.has_sick_leave_permission",
	"Overtime Request":         "hr_suite.hr_suite.permissions.has_overtime_request_permission",
	"Salary Adjustment":        "hr_suite.hr_suite.permissions.has_salary_adjustment_permission",
	"Maternity Paternity Leave":"hr_suite.hr_suite.permissions.has_maternity_paternity_leave_permission",
	"Special Leave":            "hr_suite.hr_suite.permissions.has_special_leave_permission",
}

after_install = "hr_suite.install.after_install"

# ─── Fixtures ───────────────────────────────────────────────────────────────────
fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [["module", "=", "Hr Suite"]],
	},
	{
		"doctype": "Property Setter",
		"filters": [["module", "=", "Hr Suite"]],
	},
]

# ─── Migration Hooks ───────────────────────────────────────────────────────
after_migrate = ["hr_suite.install.after_migrate"]
