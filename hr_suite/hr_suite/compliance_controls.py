import json

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, getdate, today


HR_PERMISSIONS = [
	{
		"role": "HR Manager",
		"read": 1,
		"write": 1,
		"create": 1,
		"delete": 1,
		"print": 1,
		"email": 1,
		"report": 1,
		"export": 1,
		"share": 1,
	},
	{
		"role": "HR User",
		"read": 1,
		"write": 1,
		"create": 1,
		"print": 1,
		"email": 1,
		"report": 1,
		"export": 1,
	},
	{
		"role": "System Manager",
		"read": 1,
		"write": 1,
		"create": 1,
		"delete": 1,
		"print": 1,
		"email": 1,
		"report": 1,
		"export": 1,
		"share": 1,
	},
]


READ_ONLY_PERMISSIONS = [
	{"role": "HR Manager", "read": 1, "report": 1, "export": 1, "print": 1},
	{"role": "HR User", "read": 1, "report": 1, "export": 1, "print": 1},
	{"role": "System Manager", "read": 1, "report": 1, "export": 1, "print": 1},
]


PERMISSION_FLAGS = [
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
	"if_owner",
	"select",
]


OPEN_STATUSES = {
	"Draft",
	"Open",
	"In Progress",
	"Under Review",
	"Pending Submission",
	"Submitted",
	"Rejected",
	"Corrective Action Required",
	"Pending",
	"Overdue",
}


def field(fieldname, fieldtype, label=None, **kwargs):
	docfield = {"fieldname": fieldname, "fieldtype": fieldtype}
	if label:
		docfield["label"] = label
	docfield.update(kwargs)
	return docfield


def section(fieldname, label, description=None):
	docfield = field(fieldname, "Section Break", label)
	if description:
		docfield["description"] = description
	return docfield


def column(fieldname):
	return field(fieldname, "Column Break")


def make_doctype(name, fields, **kwargs):
	definition = {
		"doctype": "DocType",
		"name": name,
		"module": "Hr Suite",
		"custom": 1,
		"engine": "InnoDB",
		"field_order": [row["fieldname"] for row in fields],
		"fields": fields,
		"permissions": kwargs.pop("permissions", HR_PERMISSIONS),
		"allow_import": kwargs.pop("allow_import", 1),
		"track_changes": kwargs.pop("track_changes", 1),
		"sort_field": kwargs.pop("sort_field", "modified"),
		"sort_order": kwargs.pop("sort_order", "DESC"),
	}
	definition.update(kwargs)
	return definition


def make_child_doctype(name, fields):
	return make_doctype(
		name,
		fields,
		istable=1,
		permissions=[],
		allow_import=0,
		track_changes=0,
		sort_field="idx",
		sort_order="ASC",
	)


COMPLIANCE_DOCTYPES = [
	make_child_doctype(
		"Statutory HR Record Row",
		[
			field("record_type", "Select", "Record Type", reqd=1, in_list_view=1, options="\nEmployee Names Register"),
			field("legal_reference", "Data", "Legal Reference", default="Art.17 / Reg. Art.5"),
			column("column_break_1"),
			field("required", "Check", "Required", default=1),
			field("status", "Select", "Status", in_list_view=1, options="Missing", default="Missing"),
			section("ownership_section", "Ownership & Evidence"),
			field("owner_user", "Link", "Owner", options="User"),
			field("last_verified_on", "Date", "Last Verified On"),
			field("next_review_date", "Date", "Next Review Date"),
			column("column_break_2"),
			field("linked_doctype", "Link", "Linked DocType", options="DocType"),
			field("linked_report", "Data", "Linked Report"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("gap_description", "Small Text", "Gap Description"),
			field("action_log", "Link", "Compliance Action", options="HR Compliance Action Log"),
		],
	),
	make_child_doctype(
		"Disability Accommodation Row",
		[
			field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
			field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
			column("column_break_1"),
			field("certificate_reference", "Data", "Certificate Reference"),
			field("certificate_expiry", "Date", "Certificate Expiry"),
			section("accommodation_section", "Accommodation"),
			field("accommodation_type", "Select", "Accommodation Type", options="\nWorkspace Adjustment"),
			field("accommodation_status", "Select", "Accommodation Status", in_list_view=1, options="Required", default="Required"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("notes", "Small Text", "Notes"),
		],
	),
	make_child_doctype(
		"Safety Risk Control Item",
		[
			field("hazard", "Data", "Hazard", reqd=1, in_list_view=1),
			field("severity", "Select", "Severity", in_list_view=1, options="\nLow", reqd=1),
			column("column_break_1"),
			field("required_control", "Small Text", "Required Control"),
			field("status", "Select", "Status", in_list_view=1, options="Open", default="Open"),
			field("owner_user", "Link", "Owner", options="User"),
			field("due_date", "Date", "Due Date"),
			field("evidence_attachment", "Attach", "Evidence"),
		],
	),
	make_doctype(
		"Work Regulation",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-WR-.YYYY.-.####", reqd=1),
			field("regulation_title", "Data", "Regulation Title", reqd=1, in_list_view=1),
			field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
			column("column_break_1"),
			field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
			field("regulation_type", "Select", "Regulation Type", options="Unified Model", default="Unified Model"),
			section("approval_section", "Approval & Publication", "Tracks the approved work regulation required by Labor Law Art.12-13 and Executive Regulations Art.3-4."),
			field("version", "Data", "Version", default="1.0", reqd=1),
			field("effective_date", "Date", "Effective Date", reqd=1),
			field("approval_date", "Date", "Approval Date"),
			column("column_break_2"),
			field("next_review_date", "Date", "Next Review Date"),
			field("lawyer_or_approver", "Data", "Lawyer or Approver"),
			field("ministry_certificate_reference", "Data", "Ministry Certificate Reference"),
			field("ministry_certificate_attachment", "Attach", "Ministry Certificate"),
			section("announcement_section", "Announcement & Acknowledgement"),
			field("announcement_date", "Date", "Announcement Date"),
			field("published_location", "Small Text", "Published Location"),
			column("column_break_3"),
			field("acknowledgement_required", "Check", "Acknowledgement Required", default=1),
			field("acknowledgement_due_days", "Int", "Acknowledgement Due Days", default=7),
			field("linked_policy", "Link", "Linked Policy", options="HR Policy Document"),
			section("legal_section", "Legal Basis"),
			field("legal_reference", "Data", "Legal Reference", default="Labor Law Art.12-13; Executive Regulations Art.3-4; Annex 1"),
			field("approved_attachment", "Attach", "Approved Regulation"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="regulation_title",
		search_fields="regulation_title,company,ministry_certificate_reference",
		icon="fa fa-balance-scale",
	),
	make_doctype(
		"Statutory HR Records Register",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-SHRR-.YYYY.-.####", reqd=1),
			field("register_title", "Data", "Register Title", reqd=1, in_list_view=1),
			field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
			column("column_break_1"),
			field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
			field("responsible_user", "Link", "Responsible User", options="User"),
			section("period_section", "Audit Period"),
			field("period_start", "Date", "Period Start", reqd=1),
			field("period_end", "Date", "Period End", reqd=1),
			column("column_break_2"),
			field("legal_reference", "Data", "Legal Reference", default="Labor Law Art.17; Executive Regulations Art.5"),
			field("total_required", "Int", "Required Records", read_only=1),
			field("completed_count", "Int", "Available Records", read_only=1),
			field("gap_count", "Int", "Gaps", read_only=1),
			section("records_section", "Records Checklist"),
			field("records", "Table", "Records", options="Statutory HR Record Row"),
			field("report_attachment", "Attach", "Audit Evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="register_title",
		search_fields="register_title,company,status",
		icon="fa fa-archive",
	),
	make_doctype(
		"Ministry Filing Tracker",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-MFT-.YYYY.-.####", reqd=1),
			field("filing_title", "Data", "Filing Title", reqd=1, in_list_view=1),
			field("filing_type", "Select", "Filing Type", reqd=1, in_list_view=1, options="\nEstablishment Data Update"),
			field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
			column("column_break_1"),
			field("status", "Select", "Status", options="Pending Submission", default="Pending Submission", in_list_view=1),
			field("priority", "Select", "Priority", options="\nP0", default="P0"),
			section("deadline_section", "Deadlines"),
			field("trigger_date", "Date", "Trigger Date", reqd=1),
			field("due_date", "Date", "Due Date", reqd=1, in_list_view=1),
			column("column_break_2"),
			field("submitted_on", "Date", "Submitted On"),
			field("accepted_on", "Date", "Accepted On"),
			field("responsible_user", "Link", "Responsible User", options="User"),
			section("evidence_section", "Platform Evidence"),
			field("platform_name", "Data", "Platform", default="MHRSD"),
			field("platform_reference", "Data", "Platform Reference"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("legal_reference", "Data", "Legal Reference"),
			field("action_log", "Link", "Compliance Action", options="HR Compliance Action Log"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="filing_title",
		search_fields="filing_title,filing_type,platform_reference",
		icon="fa fa-upload",
	),
	make_doctype(
		"Employee Document Custody Log",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-DOC-CUS-.YYYY.-.####", reqd=1),
			field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
			field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
			column("column_break_1"),
			field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
			field("document_type", "Select", "Document Type", reqd=1, in_list_view=1, options="\nPassport"),
			field("custody_status", "Select", "Custody Status", options="Not Held", default="Not Held", in_list_view=1),
			section("custody_section", "Custody & Return"),
			field("original_document_held", "Check", "Original Document Held", default=0),
			field("custody_start_date", "Date", "Custody Start Date"),
			field("return_due_date", "Date", "Return Due Date"),
			column("column_break_2"),
			field("returned_on", "Date", "Returned On"),
			field("authorized_by", "Link", "Authorized By", options="User"),
			field("legal_reference", "Data", "Legal Reference", default="Executive Regulations Art.6"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="employee_name",
		search_fields="employee,employee_name,document_type",
		icon="fa fa-id-card",
	),
	make_doctype(
		"Disability Employment Compliance",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-DIS-.YYYY.-.####", reqd=1),
			field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
			field("period_start", "Date", "Period Start", reqd=1),
			column("column_break_1"),
			field("period_end", "Date", "Period End", reqd=1),
			field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
			section("ratio_section", "Ratio"),
			field("total_employees", "Int", "Total Employees", reqd=1),
			field("disabled_employees", "Int", "Qualified Disabled Employees", reqd=1),
			field("required_ratio", "Percent", "Required Ratio", default=4),
			column("column_break_2"),
			field("compliance_ratio", "Percent", "Compliance Ratio", read_only=1),
			field("gap_to_required", "Float", "Gap to Required", read_only=1),
			field("responsible_user", "Link", "Responsible User", options="User"),
			section("accommodation_section", "Employees & Accommodations"),
			field("accommodations", "Table", "Accommodations", options="Disability Accommodation Row"),
			field("legal_reference", "Data", "Legal Reference", default="Executive Regulations Art.9"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="company",
		search_fields="company,status",
		icon="fa fa-universal-access",
	),
	make_doctype(
		"Final Settlement SLA",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-FSLA-.YYYY.-.####", reqd=1),
			field("termination_notice", "Link", "Termination Notice", options="Termination Notice", in_list_view=1),
			field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
			field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
			column("column_break_1"),
			field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
			field("status", "Select", "Status", options="Open", default="Open", in_list_view=1),
			section("sla_section", "Settlement Deadlines"),
			field("last_working_day", "Date", "Last Working Day", reqd=1),
			field("settlement_due_date", "Date", "Settlement Due Date", reqd=1, in_list_view=1),
			column("column_break_2"),
			field("document_return_due_date", "Date", "Document Return Due Date"),
			field("responsible_user", "Link", "Responsible User", options="User"),
			section("completion_section", "Completion Evidence"),
			field("eosb_document", "Link", "EOSB Document", options="End of Service Benefit"),
			field("exit_clearance", "Link", "Exit Clearance", options="Exit Clearance"),
			field("payment_status", "Select", "Payment Status", options="Pending", default="Pending"),
			field("settlement_paid_on", "Date", "Settlement Paid On"),
			column("column_break_3"),
			field("documents_returned_on", "Date", "Documents Returned On"),
			field("legal_review_required", "Check", "Legal Review Required", default=1),
			field("risk_level", "Select", "Risk Level", options="\nLow\nMedium\nHigh", default="High"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="employee_name",
		search_fields="employee,employee_name,status",
		icon="fa fa-hourglass-end",
	),
	make_doctype(
		"Work Arrangement Control",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-WAC-.YYYY.-.####", reqd=1),
			field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
			field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
			column("column_break_1"),
			field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
			field("contract", "Link", "Saudi Employment Contract", options="Saudi Employment Contract"),
			field("arrangement_type", "Select", "Arrangement Type", reqd=1, in_list_view=1, options="\nFlexible Work"),
			field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
			section("period_section", "Period & Limits"),
			field("start_date", "Date", "Start Date", reqd=1),
			field("end_date", "Date", "End Date"),
			field("actual_days", "Int", "Actual Days", read_only=1),
			column("column_break_2"),
			field("conversion_due_date", "Date", "Conversion Due Date"),
			field("conversion_required", "Check", "Conversion Required", read_only=1),
			field("daily_hours_limit", "Float", "Daily Hours Limit"),
			field("weekly_hours_limit", "Float", "Weekly Hours Limit"),
			section("portal_section", "Portal Evidence"),
			field("saudi_only_applicable", "Check", "Saudi-only Rule Applies", default=0),
			field("platform_reference", "Data", "Platform Reference"),
			field("compensatory_leave_allowed", "Check", "Compensatory Leave Allowed", default=0),
			field("legal_reference", "Data", "Legal Reference"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="employee_name",
		search_fields="employee,employee_name,arrangement_type,status",
		icon="fa fa-random",
	),
	make_doctype(
		"Working Time Compliance Check",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-WTC-.YYYY.-.####", reqd=1),
			field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
			field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
			column("column_break_1"),
			field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
			field("check_date", "Date", "Check Date", reqd=1, in_list_view=1),
			field("week_start_date", "Date", "Week Start"),
			section("hours_section", "Hours"),
			field("actual_daily_hours", "Float", "Actual Daily Hours"),
			field("actual_weekly_hours", "Float", "Actual Weekly Hours"),
			column("column_break_2"),
			field("overtime_hours", "Float", "Overtime Hours"),
			field("status", "Select", "Status", options="Needs Review\nCompliant\nNon-Compliant", default="Needs Review", in_list_view=1),
			field("approval_reference", "Link", "Approval Reference", options="Overtime Request"),
			field("exception_reason", "Small Text", "Exception Reason"),
			field("legal_reference", "Data", "Legal Reference", default="Executive Regulations working-hours controls"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="employee_name",
		search_fields="employee,employee_name,status",
		icon="fa fa-clock-o",
	),
	make_doctype(
		"Safety Inspection and Risk Control",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-SAFE-.YYYY.-.####", reqd=1),
			field("inspection_title", "Data", "Inspection Title", reqd=1, in_list_view=1),
			field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
			column("column_break_1"),
			field("location", "Data", "Location"),
			field("inspection_date", "Date", "Inspection Date", reqd=1, in_list_view=1),
			field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
			section("control_section", "Preventive Controls"),
			field("inspector_user", "Link", "Inspector", options="User"),
			field("risk_level", "Select", "Risk Level", options="\nLow\nMedium\nHigh", default="Medium"),
			field("first_aid_available", "Check", "First Aid Available", default=0),
			column("column_break_2"),
			field("remote_site_controls_required", "Check", "Remote Site Controls Required", default=0),
			field("next_inspection_date", "Date", "Next Inspection Date"),
			field("action_log", "Link", "Compliance Action", options="HR Compliance Action Log"),
			section("risk_items_section", "Risk Items"),
			field("risk_items", "Table", "Risk Items", options="Safety Risk Control Item"),
			field("legal_reference", "Data", "Legal Reference", default="Executive Regulations occupational safety controls"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="inspection_title",
		search_fields="inspection_title,company,location,status",
		icon="fa fa-shield",
	),
	make_doctype(
		"Inspection Fine SLA",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-FINE-.YYYY.-.####", reqd=1),
			field("labor_inspection", "Link", "Labor Inspection", options="Labor Inspection", in_list_view=1),
			field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
			column("column_break_1"),
			field("fine_reference", "Data", "Fine Reference", in_list_view=1),
			field("fine_amount", "Currency", "Fine Amount"),
			field("status", "Select", "Status", options="Open", default="Open", in_list_view=1),
			section("deadline_section", "Deadlines"),
			field("notification_date", "Date", "Notification Date", reqd=1),
			field("payment_due_date", "Date", "Payment Due Date", reqd=1, in_list_view=1),
			column("column_break_2"),
			field("paid_on", "Date", "Paid On"),
			field("objection_status", "Select", "Objection Status", options="Not Filed", default="Not Filed"),
			field("objection_deadline", "Date", "Objection Deadline"),
			field("responsible_user", "Link", "Responsible User", options="User"),
			section("evidence_section", "Evidence"),
			field("action_log", "Link", "Compliance Action", options="HR Compliance Action Log"),
			field("payment_reference", "Data", "Payment Reference"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("legal_reference", "Data", "Legal Reference", default="Executive Regulations penalty collection; 60-day payment tracking"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="fine_reference",
		search_fields="fine_reference,company,status",
		icon="fa fa-money",
	),
	make_doctype(
		"Contract Portal Evidence",
		[
			field("naming_series", "Select", "Naming Series", options="SAU-CPE-.YYYY.-.####", reqd=1),
			field("contract", "Link", "Saudi Employment Contract", options="Saudi Employment Contract", reqd=1, in_list_view=1),
			field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
			field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
			column("column_break_1"),
			field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
			field("portal_name", "Data", "Portal", default="Qiwa"),
			field("submission_reference", "Data", "Submission Reference", in_list_view=1),
			section("status_section", "Portal Status"),
			field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
			field("submitted_on", "Date", "Submitted On"),
			column("column_break_2"),
			field("employee_acknowledged_on", "Date", "Employee Acknowledged On"),
			field("accepted_on", "Date", "Accepted On"),
			field("evidence_attachment", "Attach", "Evidence"),
			field("legal_reference", "Data", "Legal Reference", default="Executive Regulations contract models and platform evidence"),
			field("notes", "Text Editor", "Notes"),
		],
		autoname="naming_series:",
		title_field="submission_reference",
		search_fields="contract,employee,submission_reference",
		icon="fa fa-file-contract",
	),
]


COMPLIANCE_DOCTYPES.extend(
	[
		make_doctype(
			"Disciplinary Violation Catalog",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-DVC-.YYYY.-.####", reqd=1),
				field("violation_code", "Data", "Violation Code", reqd=1, unique=1, in_list_view=1),
				field("violation_name", "Data", "Violation Name", reqd=1, in_list_view=1),
				column("column_break_1"),
				field("category", "Select", "Category", reqd=1, in_list_view=1, options="\nAttendance\nWork Organization\nConduct\nIntegrity\nSafety"),
				field("status", "Select", "Status", in_list_view=1, options="Active", default="Active"),
				section("penalty_section", "Progressive Penalties"),
				field("penalty_first", "Small Text", "First Time", reqd=1),
				field("penalty_second", "Small Text", "Second Time"),
				column("column_break_2"),
				field("penalty_third", "Small Text", "Third Time"),
				field("penalty_fourth", "Small Text", "Fourth Time"),
				section("control_section", "Legal Controls"),
				field("max_deduction_days", "Int", "Max Deduction Days"),
				field("requires_termination_review", "Check", "Requires Termination Review"),
				column("column_break_3"),
				field("legal_reference", "Data", "Legal Reference", default="Annex 1 - Unified Work Regulation Violation Table"),
				field("source_page", "Data", "PDF Page"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="violation_name",
			search_fields="violation_code,violation_name,category",
			icon="fa fa-list-ol",
		),
		make_doctype(
			"Disability Accommodation Catalog",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-DAC-.YYYY.-.####", reqd=1),
				field("accommodation_code", "Data", "Accommodation Code", reqd=1, unique=1, in_list_view=1),
				field("disability_type", "Select", "Disability Type", reqd=1, in_list_view=1, options="\nPhysical\nVisual\nHearing\nPsychological\nMedical Condition\nGeneral"),
				field("job_family", "Select", "Job Family", reqd=1, in_list_view=1, options="\nOffice\nTechnical\nTeaching\nManual\nAll Jobs"),
				column("column_break_1"),
				field("accommodation_title", "Data", "Accommodation", reqd=1, in_list_view=1),
				field("priority", "Select", "Priority", options="Recommended\nMandatory Review", default="Recommended"),
				section("requirement_section", "Checklist Requirement"),
				field("requirement_details", "Text Editor", "Requirement Details", reqd=1),
				field("evidence_required", "Small Text", "Evidence Required"),
				column("column_break_2"),
				field("legal_reference", "Data", "Legal Reference", default="Annex 2 - Accommodation and Facilitation Table"),
				field("source_page", "Data", "PDF Page"),
				field("active", "Check", "Active", default=1),
			],
			autoname="naming_series:",
			title_field="accommodation_title",
			search_fields="accommodation_code,disability_type,job_family,accommodation_title",
			icon="fa fa-universal-access",
		),
		make_child_doctype(
			"Recruitment Provider Branch Row",
			[
				field("branch_name", "Data", "Branch Name", reqd=1, in_list_view=1),
				field("city", "Data", "City", in_list_view=1),
				column("column_break_1"),
				field("approval_reference", "Data", "Ministry Approval Reference"),
				field("status", "Select", "Status", options="Pending Approval", default="Pending Approval", in_list_view=1),
				field("evidence_attachment", "Attach", "Evidence"),
			],
		),
		make_child_doctype(
			"Recruitment Provider Violation Row",
			[
				field("violation_date", "Date", "Violation Date", reqd=1, in_list_view=1),
				field("violation_type", "Select", "Violation Type", reqd=1, in_list_view=1, options="\nLicense Breach"),
				column("column_break_1"),
				field("severity", "Select", "Severity", options="Low\nMedium\nHigh", default="Medium"),
				field("status", "Select", "Status", options="Open", default="Open", in_list_view=1),
				section("details_section", "Details"),
				field("description", "Small Text", "Description"),
				field("corrective_action", "Small Text", "Corrective Action"),
				field("evidence_attachment", "Attach", "Evidence"),
			],
		),
		make_doctype(
			"Recruitment Service Provider Compliance",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-RSP-.YYYY.-.####", reqd=1),
				field("provider_name", "Data", "Provider Name", reqd=1, in_list_view=1),
				field("company", "Link", "Internal Company", options="Company", in_list_view=1),
				column("column_break_1"),
				field("provider_type", "Select", "Provider Type", reqd=1, in_list_view=1, options="\nSaudi Recruitment Mediation"),
				field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
				section("license_section", "License"),
				field("license_number", "Data", "License Number", reqd=1, in_list_view=1),
				field("license_issue_date", "Date", "License Issue Date"),
				field("license_expiry_date", "Date", "License Expiry Date", in_list_view=1),
				column("column_break_2"),
				field("renewal_due_date", "Date", "Renewal Due Date", read_only=1),
				field("ministry_reference", "Data", "Ministry Reference"),
				field("license_attachment", "Attach", "License Attachment"),
				section("controls_section", "Mandatory Controls"),
				field("insurance_policy_reference", "Data", "Insurance Policy Reference"),
				field("insurance_expiry_date", "Date", "Insurance Expiry Date"),
				field("bank_account_documented", "Check", "Bank Account Documented"),
				field("complaint_channel_available", "Check", "Complaint Channel Available", default=1),
				column("column_break_3"),
				field("hr_unit_available", "Check", "Independent HR Unit"),
				field("compliance_unit_available", "Check", "Independent Compliance Unit"),
				field("policy_manual_attachment", "Attach", "Policy Manual"),
				field("last_ministry_visit_date", "Date", "Last Ministry Visit"),
				section("branches_section", "Branches & Violations"),
				field("branches", "Table", "Branches", options="Recruitment Provider Branch Row"),
				field("violations", "Table", "Violations", options="Recruitment Provider Violation Row"),
				field("legal_reference", "Data", "Legal Reference", default="Annex 3 and Annex 4 - Recruitment and Labor Services Controls"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="provider_name",
			search_fields="provider_name,license_number,provider_type,status",
			icon="fa fa-briefcase",
		),
		make_doctype(
			"Recruitment Provider Complaint",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-RPC-.YYYY.-.####", reqd=1),
				field("provider_compliance", "Link", "Provider Compliance", options="Recruitment Service Provider Compliance", in_list_view=1),
				field("complainant_type", "Select", "Complainant Type", options="\nWorker", reqd=1),
				field("complaint_subject", "Data", "Complaint Subject", reqd=1, in_list_view=1),
				column("column_break_1"),
				field("received_on", "Date", "Received On", reqd=1, in_list_view=1),
				field("response_due_date", "Date", "Response Due Date"),
				field("status", "Select", "Status", options="Open", default="Open", in_list_view=1),
				section("resolution_section", "Resolution"),
				field("complaint_details", "Text Editor", "Complaint Details"),
				field("resolution_summary", "Text Editor", "Resolution Summary"),
				field("platform_reference", "Data", "Platform Reference"),
				field("evidence_attachment", "Attach", "Evidence"),
				field("legal_reference", "Data", "Legal Reference", default="Annex 4 complaint channel and platform handling controls"),
			],
			autoname="naming_series:",
			title_field="complaint_subject",
			search_fields="complaint_subject,provider_compliance,status",
			icon="fa fa-comments",
		),
		make_doctype(
			"Training Agreement",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-TRAGR-.YYYY.-.####", reqd=1),
				field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
				field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
				column("column_break_1"),
				field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
				field("training_record", "Link", "Training Record", options="Training Record"),
				field("status", "Select", "Status", options="Draft", default="Draft", in_list_view=1),
				section("agreement_section", "Agreement Terms"),
				field("program_name", "Data", "Program Name", reqd=1, in_list_view=1),
				field("agreement_date", "Date", "Agreement Date", reqd=1),
				field("training_start_date", "Date", "Training Start"),
				field("training_end_date", "Date", "Training End"),
				column("column_break_2"),
				field("training_cost", "Currency", "Training Cost"),
				field("employer_paid_cost", "Currency", "Employer Paid Cost"),
				field("commitment_months", "Int", "Commitment Months"),
				field("commitment_end_date", "Date", "Commitment End Date"),
				section("recovery_section", "Recovery Controls"),
				field("recovery_applicable", "Check", "Recovery Applicable"),
				field("recovery_amount", "Currency", "Recovery Amount"),
				field("recovery_reason", "Small Text", "Recovery Reason"),
				column("column_break_3"),
				field("employee_acknowledgement", "Check", "Employee Acknowledgement"),
				field("agreement_attachment", "Attach", "Agreement Attachment"),
				field("legal_reference", "Data", "Legal Reference", default="Executive Regulations training and qualification controls"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="program_name",
			search_fields="employee,employee_name,program_name,status",
			icon="fa fa-graduation-cap",
		),
		make_doctype(
			"Special Employment Category Control",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-SECC-.YYYY.-.####", reqd=1),
				field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
				field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
				column("column_break_1"),
				field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
				field("category", "Select", "Category", reqd=1, in_list_view=1, options="\nYoung Worker"),
				field("status", "Select", "Status", in_list_view=1, options="Draft\nNeeds Review\nApproved\nClosed", default="Needs Review"),
				section("controls_section", "Controls"),
				field("job_risk_review_required", "Check", "Job Risk Review Required", default=1),
				field("prohibited_job_review", "Small Text", "Prohibited Job Review"),
				field("training_or_medical_requirement", "Small Text", "Training or Medical Requirement"),
				column("column_break_2"),
				field("daily_hours_limit", "Float", "Daily Hours Limit"),
				field("night_work_restriction", "Check", "Night Work Restriction", default=0),
				field("responsible_user", "Link", "Responsible User", options="User"),
				field("evidence_attachment", "Attach", "Evidence"),
				field("legal_reference", "Data", "Legal Reference", default="Executive Regulations special employment category controls"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="employee_name",
			search_fields="employee,employee_name,category,status",
			icon="fa fa-users",
		),
		make_doctype(
			"Holiday Leave Overlap Rule",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-HOL-.YYYY.-.####", reqd=1),
				field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
				field("employee", "Link", "Employee", options="Employee", in_list_view=1),
				field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
				column("column_break_1"),
				field("holiday_name", "Data", "Holiday", reqd=1, in_list_view=1),
				field("holiday_date", "Date", "Holiday Date", reqd=1),
				field("overlap_type", "Select", "Overlap Type", reqd=1, options="\nWeekly Rest"),
				section("action_section", "Required Action"),
				field("required_action", "Select", "Required Action", options="Extend Leave\nLegal Review\nCompensation\nNo Action", default="Legal Review", in_list_view=1),
				field("status", "Select", "Status", options="Open", default="Open", in_list_view=1),
				column("column_break_2"),
				field("leave_reference", "Dynamic Link", "Leave Reference", options="leave_reference_doctype"),
				field("leave_reference_doctype", "Link", "Leave Reference Type", options="DocType"),
				field("evidence_attachment", "Attach", "Evidence"),
				field("legal_reference", "Data", "Legal Reference", default="Executive Regulations official holiday overlap controls"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="holiday_name",
			search_fields="holiday_name,employee,status",
			icon="fa fa-calendar",
		),
		make_doctype(
			"Expat Work Authorization Control",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-EWAC-.YYYY.-.####", reqd=1),
				field("employee", "Link", "Employee", options="Employee", reqd=1, in_list_view=1),
				field("employee_name", "Data", "Employee Name", fetch_from="employee.employee_name", read_only=1),
				column("column_break_1"),
				field("company", "Link", "Company", options="Company", fetch_from="employee.company", in_list_view=1),
				field("authorization_type", "Select", "Authorization Type", reqd=1, in_list_view=1, options="\nWork Permit Renewal"),
				field("status", "Select", "Status", in_list_view=1, options="Draft", default="Draft"),
				section("deadline_section", "Deadline & Evidence"),
				field("request_date", "Date", "Request Date"),
				field("due_date", "Date", "Due Date"),
				field("approved_on", "Date", "Approved On"),
				column("column_break_2"),
				field("platform_reference", "Data", "Platform Reference"),
				field("linked_work_permit", "Link", "Work Permit/Iqama", options="Work Permit Iqama"),
				field("evidence_attachment", "Attach", "Evidence"),
				field("legal_reference", "Data", "Legal Reference", default="Executive Regulations non-Saudi work authorization controls"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="employee_name",
			search_fields="employee,employee_name,authorization_type,status",
			icon="fa fa-id-badge",
		),
		make_doctype(
			"Training Disclosure Register",
			[
				field("naming_series", "Select", "Naming Series", options="SAU-TDR-.YYYY.-.####", reqd=1),
				field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
				field("disclosure_year", "Int", "Disclosure Year", reqd=1, in_list_view=1),
				column("column_break_1"),
				field("status", "Select", "Status", in_list_view=1, options="Draft", default="Draft"),
				field("responsible_user", "Link", "Responsible User", options="User"),
				section("training_section", "Training Summary"),
				field("total_employees", "Int", "Total Employees"),
				field("trained_saudi_employees", "Int", "Trained Saudi Employees"),
				field("training_programs_count", "Int", "Training Programs"),
				column("column_break_2"),
				field("disclosure_due_date", "Date", "Disclosure Due Date"),
				field("submitted_on", "Date", "Submitted On"),
				field("platform_reference", "Data", "Platform Reference"),
				field("evidence_attachment", "Attach", "Evidence"),
				field("legal_reference", "Data", "Legal Reference", default="Executive Regulations Art.43 training disclosure controls"),
				field("notes", "Text Editor", "Notes"),
			],
			autoname="naming_series:",
			title_field="company",
			search_fields="company,disclosure_year,status",
			icon="fa fa-graduation-cap",
		),
	]
)


CUSTOM_FIELDS = {
	"End of Service Benefit": [
		{
			"fieldname": "wage_basis_section",
			"fieldtype": "Section Break",
			"label": "EOSB Wage Basis Review",
			"insert_after": "last_basic_salary",
			"description": "Legal review marker because EOSB may require the last wage rather than basic salary only.",
		},
		{
			"fieldname": "eosb_wage_basis",
			"fieldtype": "Select",
			"label": "EOSB Wage Basis",
			"insert_after": "wage_basis_section",
			"options": "Basic Salary",
			"default": "Basic Salary",
			"reqd": 1,
		},
		{
			"fieldname": "last_total_salary",
			"fieldtype": "Currency",
			"label": "Last Total Wage",
			"insert_after": "eosb_wage_basis",
			"description": "Auto-filled from Saudi Employment Contract total salary when available.",
		},
		{
			"fieldname": "legal_review_required",
			"fieldtype": "Check",
			"label": "Legal Review Required",
			"insert_after": "last_total_salary",
			"default": 1,
		},
		{
			"fieldname": "legal_review_notes",
			"fieldtype": "Small Text",
			"label": "Legal Review Notes",
			"insert_after": "legal_review_required",
		},
	],
	"Labor Inspection Violation": [
		{
			"fieldname": "fine_payment_due_date",
			"fieldtype": "Date",
			"label": "Fine Payment Due Date",
			"insert_after": "fine_amount",
			"description": "Use for the 60-day penalty payment tracking when a fine notification date is known.",
		},
		{
			"fieldname": "fine_payment_status",
			"fieldtype": "Select",
			"label": "Fine Payment Status",
			"insert_after": "fine_payment_due_date",
			"options": "Not Applicable",
			"default": "Not Applicable",
		},
	],
	"Saudi Employment Contract": [
		{
			"fieldname": "contract_variant_section",
			"fieldtype": "Section Break",
			"label": "Regulatory Contract Variant",
			"insert_after": "contract_type",
		},
		{
			"fieldname": "regulatory_contract_variant",
			"fieldtype": "Select",
			"label": "Regulatory Contract Variant",
			"insert_after": "contract_variant_section",
			"options": "Standard",
			"default": "Standard",
		},
		{
			"fieldname": "portal_evidence_reference",
			"fieldtype": "Link",
			"label": "Portal Evidence",
			"insert_after": "regulatory_contract_variant",
			"options": "Contract Portal Evidence",
		},
	],
	"Disciplinary Procedure": [
		{
			"fieldname": "violation_catalog_section",
			"fieldtype": "Section Break",
			"label": "Annex 1 Violation Catalog",
			"insert_after": "violation_type",
			"description": "Use the unified work regulation violation table before issuing the penalty decision.",
		},
		{
			"fieldname": "violation_catalog",
			"fieldtype": "Link",
			"label": "Violation Catalog",
			"insert_after": "violation_catalog_section",
			"options": "Disciplinary Violation Catalog",
		},
		{
			"fieldname": "occurrence_number",
			"fieldtype": "Int",
			"label": "Occurrence Number",
			"insert_after": "violation_catalog",
			"default": 1,
			"description": "1 to 4 based on repeated violation history.",
		},
		{
			"fieldname": "recommended_penalty",
			"fieldtype": "Small Text",
			"label": "Recommended Penalty",
			"insert_after": "occurrence_number",
			"read_only": 1,
		},
		{
			"fieldname": "catalog_legal_reference",
			"fieldtype": "Data",
			"label": "Catalog Legal Reference",
			"insert_after": "recommended_penalty",
			"read_only": 1,
		},
		{
			"fieldname": "catalog_requires_review",
			"fieldtype": "Check",
			"label": "Catalog Requires Review",
			"insert_after": "catalog_legal_reference",
			"read_only": 1,
		},
	],
	"Disability Accommodation Row": [
		{
			"fieldname": "accommodation_catalog",
			"fieldtype": "Link",
			"label": "Accommodation Catalog",
			"insert_after": "accommodation_type",
			"options": "Disability Accommodation Catalog",
		},
		{
			"fieldname": "catalog_requirement_details",
			"fieldtype": "Small Text",
			"label": "Catalog Requirement",
			"insert_after": "accommodation_catalog",
			"read_only": 1,
		},
	],
	"Job Requisition": [
		{
			"fieldname": "hrsuite_section",
			"fieldtype": "Section Break",
			"label": "HR Suite",
			"insert_after": "reason_for_requesting",
		},
		{
			"fieldname": "hrsuite_saudization_priority",
			"fieldtype": "Check",
			"label": "Saudization Priority",
			"insert_after": "hrsuite_section",
			"description": "Flag this role as requiring a Saudi national hire to meet Nitaqat compliance.",
		},
		{
			"fieldname": "hrsuite_budgeted_monthly_salary",
			"fieldtype": "Currency",
			"label": "Budgeted Monthly Salary",
			"insert_after": "hrsuite_saudization_priority",
		},
		{
			"fieldname": "hrsuite_key_requirements",
			"fieldtype": "Small Text",
			"label": "Key Requirements",
			"insert_after": "hrsuite_budgeted_monthly_salary",
		},
		{
			"fieldname": "hrsuite_business_reason",
			"fieldtype": "Small Text",
			"label": "Business Reason",
			"insert_after": "hrsuite_key_requirements",
		},
	],
	"Appraisal": [
		{
			"fieldname": "hrsuite_section",
			"fieldtype": "Section Break",
			"label": "HR Suite",
			"insert_after": "remarks",
		},
		{
			"fieldname": "hrsuite_compliance_rating",
			"fieldtype": "Float",
			"label": "Compliance Rating",
			"insert_after": "hrsuite_section",
			"description": "HR Suite compliance score (0–5). Auto-computed from compliance behaviour during the period.",
		},
		{
			"fieldname": "hrsuite_promotion_recommended",
			"fieldtype": "Check",
			"label": "Promotion Recommended",
			"insert_after": "hrsuite_compliance_rating",
		},
		{
			"fieldname": "hrsuite_promotion_transfer",
			"fieldtype": "Link",
			"label": "Promotion / Transfer",
			"insert_after": "hrsuite_promotion_recommended",
			"options": "Promotion Transfer",
		},
		{
			"fieldname": "hrsuite_salary_adjustment_recommended",
			"fieldtype": "Check",
			"label": "Salary Adjustment Recommended",
			"insert_after": "hrsuite_promotion_transfer",
		},
		{
			"fieldname": "hrsuite_salary_adjustment",
			"fieldtype": "Link",
			"label": "Salary Adjustment",
			"insert_after": "hrsuite_salary_adjustment_recommended",
			"options": "Salary Adjustment",
		},
	],
	"Exit Interview": [
		{
			"fieldname": "hrsuite_section",
			"fieldtype": "Section Break",
			"label": "HR Suite Exit Details",
			"insert_after": "interview_summary",
		},
		{
			"fieldname": "hrsuite_termination_notice",
			"fieldtype": "Link",
			"label": "Termination Notice",
			"insert_after": "hrsuite_section",
			"options": "Termination Notice",
		},
		{
			"fieldname": "hrsuite_exit_clearance",
			"fieldtype": "Link",
			"label": "Exit Clearance",
			"insert_after": "hrsuite_termination_notice",
			"options": "Exit Clearance",
		},
		{
			"fieldname": "hrsuite_interview_mode",
			"fieldtype": "Select",
			"label": "Interview Mode",
			"insert_after": "hrsuite_exit_clearance",
			"options": "\nIn Person\nVideo Call\nPhone",
		},
		{
			"fieldname": "hrsuite_primary_exit_reason",
			"fieldtype": "Select",
			"label": "Primary Exit Reason",
			"insert_after": "hrsuite_interview_mode",
			"options": "\nBetter Opportunity\nRelocation\nPersonal Reasons\nCompensation\nWork Environment\nManagement Issues\nCareer Growth\nEnd of Contract\nRetirement\nOther",
		},
		{
			"fieldname": "hrsuite_rehire_eligible",
			"fieldtype": "Check",
			"label": "Eligible for Rehire",
			"insert_after": "hrsuite_primary_exit_reason",
			"default": "1",
		},
		{
			"fieldname": "hrsuite_overall_experience_rating",
			"fieldtype": "Select",
			"label": "Overall Experience",
			"insert_after": "hrsuite_rehire_eligible",
			"options": "\nExcellent\nGood\nAverage\nPoor",
		},
		{
			"fieldname": "hrsuite_final_recommendation",
			"fieldtype": "Select",
			"label": "Final Recommendation",
			"insert_after": "hrsuite_overall_experience_rating",
			"options": "\nRehire\nDo Not Rehire\nCase by Case",
		},
		{
			"fieldname": "hrsuite_immediate_follow_up_required",
			"fieldtype": "Check",
			"label": "Immediate Follow-up Required",
			"insert_after": "hrsuite_final_recommendation",
		},
		{
			"fieldname": "hrsuite_what_worked_well",
			"fieldtype": "Text Editor",
			"label": "What Worked Well",
			"insert_after": "hrsuite_immediate_follow_up_required",
		},
		{
			"fieldname": "hrsuite_improvement_suggestions",
			"fieldtype": "Text Editor",
			"label": "Improvement Suggestions",
			"insert_after": "hrsuite_what_worked_well",
		},
		{
			"fieldname": "hrsuite_retention_opportunity",
			"fieldtype": "Text Editor",
			"label": "Retention Opportunity",
			"insert_after": "hrsuite_improvement_suggestions",
		},
		{
			"fieldname": "hrsuite_follow_up_actions",
			"fieldtype": "Text Editor",
			"label": "Follow-up Actions",
			"insert_after": "hrsuite_retention_opportunity",
		},
		{
			"fieldname": "hrsuite_final_comments",
			"fieldtype": "Text Editor",
			"label": "Final Comments",
			"insert_after": "hrsuite_follow_up_actions",
		},
	],
}


WORKSPACE_COMPLIANCE_GROUPS = [
	{
		"id": "hr_suite_card_regulation_records",
		"label": "Compliance Regulations and Records",
		"links": [
			("Work Regulation", "Work Regulation", "DocType"),
			("Disciplinary Violation Catalog", "Disciplinary Violation Catalog", "DocType"),
			("Disability Accommodation Catalog", "Disability Accommodation Catalog", "DocType"),
			("Statutory HR Records Register", "Statutory HR Records Register", "DocType"),
			("Ministry Filing Tracker", "Ministry Filing Tracker", "DocType"),
			("Training Disclosure Register", "Training Disclosure Register", "DocType"),
		],
	},
	{
		"id": "hr_suite_card_employee_evidence",
		"label": "Employee Documentation and Contracts",
		"links": [
			("Employee Document Custody Log", "Employee Document Custody Log", "DocType"),
			("Contract Portal Evidence", "Contract Portal Evidence", "DocType"),
			("Training Agreement", "Training Agreement", "DocType"),
			("Disability Employment Compliance", "Disability Employment Compliance", "DocType"),
			("Expat Work Authorization Control", "Expat Work Authorization Control", "DocType"),
		],
	},
	{
		"id": "hr_suite_card_recruitment_providers",
		"label": "Recruitment and Staffing Agencies",
		"links": [
			("Recruitment Service Provider Compliance", "Recruitment Service Provider Compliance", "DocType"),
			("Recruitment Provider Complaint", "Recruitment Provider Complaint", "DocType"),
		],
	},
	{
		"id": "hr_suite_card_working_controls",
		"label": "Work Patterns and Hours",
		"links": [
			("Work Arrangement Control", "Work Arrangement Control", "DocType"),
			("Working Time Compliance Check", "Working Time Compliance Check", "DocType"),
			("Holiday Leave Overlap Rule", "Holiday Leave Overlap Rule", "DocType"),
			("Special Employment Category Control", "Special Employment Category Control", "DocType"),
		],
	},
	{
		"id": "hr_suite_card_safety_inspection",
		"label": "Safety, Inspection, and Penalties",
		"links": [
			("Safety Inspection and Risk Control", "Safety Inspection and Risk Control", "DocType"),
			("Inspection Fine SLA", "Inspection Fine SLA", "DocType"),
			("Labor Inspection", "Labor Inspection", "DocType"),
			("Work Injury", "Work Injury", "DocType"),
		],
	},
]

WORKSPACE_REPORT_LINKS = [
	(
		"Saudi Compliance Obligation Backlog",
		"Saudi Compliance Obligation Backlog",
		"Report",
	),
	(
		"Saudi Legal Review Queue",
		"Saudi Legal Review Queue",
		"Report",
	),
]

WORKSPACE_EXIT_LINK = ("Final Settlement SLA", "Final Settlement SLA", "DocType")
VALID_WORKSPACE_LINK_TYPES = {"DocType", "Page", "Report"}

DISCIPLINARY_CATALOG_DEFAULTS = [
	("ATT-001", "Attendance", "Late up to 15 minutes without disruption", "Written warning", "5% daily wage", "10% daily wage", "20% daily wage", 40),
	("ATT-002", "Attendance", "Late up to 15 minutes with disruption", "Written warning", "15% daily wage", "25% daily wage", "50% daily wage", 40),
	("ATT-003", "Attendance", "Late more than 15 up to 30 minutes without disruption", "10% daily wage", "15% daily wage", "25% daily wage", "50% daily wage", 40),
	("ATT-004", "Attendance", "Late more than 15 up to 30 minutes with disruption", "25% daily wage", "50% daily wage", "75% daily wage", "One day", 40),
	("ATT-005", "Attendance", "Late more than 30 up to 60 minutes without disruption", "25% daily wage", "50% daily wage", "75% daily wage", "One day", 40),
	("ATT-006", "Attendance", "Late more than 30 up to 60 minutes with disruption", "30% daily wage", "50% daily wage", "One day", "Two days plus late-time deduction", 40),
	("ATT-007", "Attendance", "Late more than one hour", "Written warning", "One day", "Two days", "Three days plus late-time deduction", 40),
	("ATT-008", "Attendance", "Leaving work up to 15 minutes early", "Written warning", "10% daily wage", "25% daily wage", "One day plus time deduction", 40),
	("ATT-009", "Attendance", "Leaving work more than 15 minutes early", "10% daily wage", "25% daily wage", "50% daily wage", "One day plus time deduction", 40),
	("ATT-010", "Attendance", "Remaining at workplace after hours without permission", "Written warning", "10% daily wage", "25% daily wage", "One day", 40),
	("ATT-011", "Attendance", "Absence one day without written permission", "50% daily wage", "One day", "Two days", "Three days", 41),
	("ATT-012", "Attendance", "Continuous absence two to six days", "Two days", "Three days", "Four days", "Promotion delay or one allowance denial plus absence deduction", 41),
	("ATT-013", "Attendance", "Continuous absence seven to ten days", "Four days", "Five days", "Promotion delay or one allowance denial", "Termination with EOSB if absence total does not exceed 30 days", 41),
	("ATT-014", "Attendance", "Continuous absence eleven to fourteen days", "Five days", "Promotion delay or one allowance denial with termination warning", "Termination under Article 80", "Legal review", 41),
	("ATT-015", "Attendance", "Continuous absence more than fifteen days", "Termination without EOSB after written warning", "", "", "", 41),
	("ATT-016", "Attendance", "Intermittent absence exceeding thirty days", "Termination without EOSB after written warning", "", "", "", 41),
	("ORG-001", "Work Organization", "Being outside assigned workplace during work time", "10% daily wage", "25% daily wage", "50% daily wage", "One day", 41),
	("ORG-002", "Work Organization", "Receiving non-work visitors without permission", "Written warning", "10% daily wage", "15% daily wage", "25% daily wage", 41),
	("ORG-003", "Work Organization", "Using company tools for private purposes", "Written warning", "10% daily wage", "25% daily wage", "50% daily wage", 41),
	("ORG-004", "Work Organization", "Interfering in work outside assignment", "50% daily wage", "One day", "Two days", "Three days", 41),
	("ORG-005", "Work Organization", "Entering or exiting from unauthorized place", "Written warning", "10% daily wage", "15% daily wage", "25% daily wage", 42),
	("ORG-006", "Work Organization", "Neglecting cleaning or maintenance of machines", "50% daily wage", "One day", "Two days", "Three days", 42),
	("ORG-007", "Work Organization", "Not returning tools to assigned places", "Written warning", "25% daily wage", "50% daily wage", "One day", 42),
	("ORG-008", "Work Organization", "Tearing or damaging company announcements", "Two days", "Three days", "Five days", "Termination with EOSB", 42),
	("ORG-009", "Work Organization", "Neglecting employee custody items", "Two days", "Three days", "Five days", "Termination with EOSB", 42),
	("ORG-010", "Work Organization", "Eating in unauthorized place or time", "Written warning", "10% daily wage", "15% daily wage", "25% daily wage", 42),
	("ORG-011", "Work Organization", "Sleeping during work", "Written warning", "10% daily wage", "25% daily wage", "50% daily wage", 42),
	("ORG-012", "Work Organization", "Sleeping where continuous alertness is required", "50% daily wage", "One day", "Two days", "Three days", 42),
	("ORG-013", "Work Organization", "Loitering or being outside work area", "10% daily wage", "25% daily wage", "50% daily wage", "One day", 42),
	("ORG-014", "Work Organization", "Tampering with attendance evidence", "One day", "Two days", "Promotion delay or one allowance denial", "Termination with EOSB", 42),
	("ORG-015", "Work Organization", "Disobeying normal work orders", "25% daily wage", "50% daily wage", "One day", "Two days", 42),
	("ORG-016", "Work Organization", "Inciting violation of written work instructions", "Two days", "Three days", "Five days", "Termination with EOSB", 42),
	("ORG-017", "Safety", "Smoking in prohibited places", "Two days", "Three days", "Five days", "Termination with EOSB", 42),
	("ORG-018", "Safety", "Neglect causing health, safety, material, or equipment harm", "Two days", "Three days", "Five days", "Termination with EOSB", 42),
	("CON-001", "Conduct", "Fighting or creating disturbances", "One day", "Two days", "Three days", "Five days", 42),
	("CON-002", "Conduct", "False work injury claim", "One day", "Two days", "Three days", "Five days", 42),
	("CON-003", "Conduct", "Refusing medical examination or treatment instructions", "One day", "Two days", "Three days", "Five days", 42),
	("CON-004", "Safety", "Violating health instructions", "50% daily wage", "One day", "Two days", "Five days", 43),
	("CON-005", "Conduct", "Writing on walls or posting announcements", "Written warning", "10% daily wage", "25% daily wage", "50% daily wage", 43),
	("CON-006", "Conduct", "Refusing administrative inspection on leaving", "25% daily wage", "50% daily wage", "One day", "Two days", 43),
	("CON-007", "Integrity", "Not delivering collected funds on time", "Two days", "Three days", "Five days", "Termination with EOSB", 43),
	("CON-008", "Safety", "Refusing protective clothing or safety devices", "Written warning", "One day", "Two days", "Five days", 43),
	("CON-009", "Conduct", "Intentional seclusion with other gender at work", "Two days", "Three days", "Five days", "Termination with EOSB", 43),
	("CON-010", "Conduct", "Indecent verbal or physical insinuation", "Two days", "Three days", "Five days", "Termination with EOSB", 43),
	("CON-011", "Conduct", "Insulting coworkers verbally, by gesture, or electronically", "Two days", "Three days", "Five days", "Termination with EOSB", 43),
	("CON-012", "Conduct", "Physical assault of coworkers or others indecently", "Termination without EOSB under Article 80", "", "", "", 43),
	("CON-013", "Conduct", "Assault against employer, manager, or supervisor", "Termination without EOSB under Article 80", "", "", "", 43),
	("CON-014", "Conduct", "Malicious report or complaint", "Three days", "Five days", "Termination with EOSB", "", 43),
	("CON-015", "Conduct", "Not complying with investigation committee attendance", "Two days", "Three days", "Five days", "Termination with EOSB", 43),
	("CON-016", "Conduct", "Not complying with approved official uniform", "One day", "Two days", "Three days", "Five days", 43),
]

DISABILITY_ACCOMMODATION_DEFAULTS = [
	("DAC-PHY-001", "Physical", "Office", "Wheelchair accessible office workspace", "Ramps, accessible toilets, adjusted desk height, shelf reach, and safe emergency exit route.", "Annex 2 pp.45"),
	("DAC-PHY-002", "Physical", "Technical", "Adjusted examination, pharmacy, or training equipment", "Adjusted beds, shelf heights, training tools, and room layout for movement access.", "Annex 2 pp.45"),
	("DAC-PHY-003", "Physical", "Teaching", "Accessible classroom or lecture room", "Ground-floor rooms or accessible elevators, lowered boards, and adequate spacing.", "Annex 2 pp.45"),
	("DAC-PHY-004", "Physical", "Manual", "Adapted manual tools and lifting support", "Adapted machinery handles, simple lifting aids, and suitable counters or worktops.", "Annex 2 pp.45"),
	("DAC-UPR-001", "Physical", "Office", "Upper-limb assistive workstation", "Modified keyboard, speech-to-text tools, adjustable chair and desk, and reachable controls.", "Annex 2 pp.45"),
	("DAC-SHO-001", "Physical", "All Jobs", "Short stature access adjustment", "Appropriate heights for devices, furniture, door handles, elevator buttons, movable steps, and vehicle adaptation when needed.", "Annex 2 pp.45"),
	("DAC-VIS-001", "Visual", "Office", "Screen reader and Braille support", "Arabic and English screen reader, Braille display, magnifier, OCR, Braille printer when needed, and safe audio emergency route.", "Annex 2 pp.46"),
	("DAC-VIS-002", "Visual", "Technical", "Accessible technical systems", "Portable screen reader, talking calculators or counting tools, accounting software support, and personal assistance when needed.", "Annex 2 pp.46"),
	("DAC-VIS-003", "Visual", "Teaching", "Accessible teaching materials", "Floor/wall navigation signs, Braille or electronic curricula, large-print materials, and assistant when necessary.", "Annex 2 pp.46"),
	("DAC-HEA-001", "Hearing", "Office", "Sign-language and visual alert support", "Sign-language interpreter or trained coworker, visual emergency alert, video-call phone, vibration and sign dictionary where available.", "Annex 2 pp.46"),
	("DAC-HEA-002", "Hearing", "Technical", "Visual monitoring and alerts", "Visual monitoring screens and light alerts in clinics, pharmacies, laboratories, and machines.", "Annex 2 pp.46"),
	("DAC-PSY-001", "Psychological", "Office", "Low-stimulation workspace and flexible schedule", "Comfortable wall colors, non-stimulating environment, flexible work and rest schedule, and computerized scheduling when needed.", "Annex 2 pp.47"),
	("DAC-MED-001", "Medical Condition", "Manual", "High-safety tools for diabetes or bleeding conditions", "Use safe tools, machines, and equipment that reduce cuts, wounds, and injury risk for workers with diabetes or blood-fluidity conditions.", "Annex 2 pp.48"),
	("DAC-GEN-001", "General", "All Jobs", "Workforce awareness and attitude adjustment", "Awareness and conduct adjustment for coworkers and supervisors to enable inclusive work environment.", "Annex 2 pp.45-48"),
]


def sync_compliance_controls():
	for doctype_def in COMPLIANCE_DOCTYPES:
		sync_doctype(doctype_def)
	sync_custom_fields()
	ensure_compliance_default_rows()
	sync_compliance_workspace()


def sync_compliance_workspace():
	if not frappe.db.exists("Workspace", "Hr Suite"):
		return

	workspace = frappe.get_doc("Workspace", "Hr Suite")
	content = _get_workspace_content(workspace)
	_sync_workspace_content_cards(content)
	_sync_workspace_links(workspace)
	workspace.content = json.dumps(content, ensure_ascii=False)
	workspace.flags.ignore_links = True
	workspace.flags.ignore_version = True
	workspace.save(ignore_permissions=True)
	frappe.clear_cache()


def _get_workspace_content(workspace):
	try:
		content = json.loads(workspace.content or "[]")
	except Exception:
		content = []
	return content if isinstance(content, list) else []


def _sync_workspace_content_cards(content):
	existing_ids = {row.get("id") for row in content if isinstance(row, dict)}
	insert_at = _find_content_index(content, "hr_suite_card_compliance_legal")
	if insert_at is None:
		insert_at = _find_content_index(content, "hr_suite_section_governance")
	if insert_at is None:
		insert_at = len(content) - 1

	offset = 1
	for group in WORKSPACE_COMPLIANCE_GROUPS:
		if group["id"] in existing_ids:
			continue
		content.insert(
			insert_at + offset,
			{
				"id": group["id"],
				"type": "card",
				"data": {"card_name": group["label"], "col": 4},
			},
		)
		offset += 1


def _find_content_index(content, item_id):
	for index, row in enumerate(content):
		if isinstance(row, dict) and row.get("id") == item_id:
			return index
	return None


def _sync_workspace_links(workspace):
	group_rows = []
	for group in WORKSPACE_COMPLIANCE_GROUPS:
		group_rows.append(_workspace_card_break(group["label"], len(group["links"])))
		group_rows.extend(_workspace_link(label, link_to, link_type) for label, link_to, link_type in group["links"])

	target_keys = {_workspace_row_key(row) for row in group_rows}
	for report_link in WORKSPACE_REPORT_LINKS:
		target_keys.add(_workspace_row_key(_workspace_link(*report_link)))
	target_keys.add(_workspace_row_key(_workspace_link(*WORKSPACE_EXIT_LINK)))

	new_links = []
	inserted_groups = False
	inserted_reports = False
	inserted_exit = False

	for row in workspace.links:
		cleaned = _clean_workspace_row(row)
		if not cleaned:
			continue
		if _workspace_row_key(cleaned) in target_keys:
			continue

		if not inserted_groups and cleaned.get("type") == "Card Break" and cleaned.get("label") == "Reports and Analytics":
			new_links.extend(group_rows)
			inserted_groups = True

		new_links.append(cleaned)

		if not inserted_exit and cleaned.get("type") == "Link" and cleaned.get("link_to") == "Termination Notice":
			new_links.append(_workspace_link(*WORKSPACE_EXIT_LINK))
			inserted_exit = True

		if not inserted_reports and cleaned.get("type") == "Link" and cleaned.get("link_to") == "Saudi Labor Coverage Matrix":
			new_links.extend(_workspace_link(*report_link) for report_link in WORKSPACE_REPORT_LINKS)
			inserted_reports = True

	if not inserted_groups:
		new_links.extend(group_rows)
	if not inserted_exit:
		new_links.append(_workspace_link(*WORKSPACE_EXIT_LINK))
	if not inserted_reports:
		new_links.extend(_workspace_link(*report_link) for report_link in WORKSPACE_REPORT_LINKS)

	_recalculate_workspace_link_counts(new_links)
	new_links = _drop_empty_workspace_cards(new_links)
	_recalculate_workspace_link_counts(new_links)
	workspace.set("links", new_links)


def _workspace_card_break(label, link_count):
	return {
		"type": "Card Break",
		"label": label,
		"hidden": 0,
		"is_query_report": 0,
		"link_count": link_count,
		"link_type": "DocType",
		"onboard": 0,
	}


def _workspace_link(label, link_to, link_type):
	return {
		"type": "Link",
		"label": label,
		"link_to": link_to,
		"link_type": link_type,
		"hidden": 0,
		"is_query_report": 1 if link_type == "Report" else 0,
		"link_count": 0,
		"onboard": 0,
	}


def _workspace_row_key(row):
	if row.get("type") == "Card Break":
		return ("Card Break", row.get("label"))
	return ("Link", row.get("label"), row.get("link_to"), row.get("link_type"))


def _clean_workspace_row(row):
	if row.get("type") == "Link" and row.get("link_type") not in VALID_WORKSPACE_LINK_TYPES:
		return None
	allowed = {
		"description",
		"hidden",
		"is_query_report",
		"label",
		"link_count",
		"link_to",
		"link_type",
		"onboard",
		"type",
	}
	cleaned = {key: row.get(key) for key in allowed if row.get(key) is not None}
	if cleaned.get("link_type") == "Report":
		cleaned["is_query_report"] = 1
	return cleaned


def _drop_empty_workspace_cards(rows):
	return [row for row in rows if row.get("type") != "Card Break" or row.get("link_count")]


def _recalculate_workspace_link_counts(rows):
	card_index = None
	for index, row in enumerate(rows):
		if row.get("type") == "Card Break":
			card_index = index
			row["link_count"] = 0
		elif row.get("type") == "Link" and card_index is not None:
			rows[card_index]["link_count"] = rows[card_index].get("link_count", 0) + 1


def sync_doctype(doctype_def):
	name = doctype_def["name"]
	if frappe.db.exists("DocType", name):
		doc = frappe.get_doc("DocType", name)
		update_doctype(doc, doctype_def)
		doc.save(ignore_permissions=True, ignore_version=True)
		return

	doc = frappe.get_doc(doctype_def)
	doc.flags.ignore_version = True
	doc.insert(ignore_permissions=True)


def update_doctype(doc, doctype_def):
	for key, value in doctype_def.items():
		if key in {"doctype", "fields", "permissions"}:
			continue
		setattr(doc, key, value)

	existing_fields = {row.fieldname: row for row in doc.fields}
	for field_def in doctype_def.get("fields", []):
		existing = existing_fields.get(field_def["fieldname"])
		if existing:
			for key, value in field_def.items():
				setattr(existing, key, value)
		else:
			doc.append("fields", field_def)

	if doctype_def.get("field_order"):
		doc.field_order = doctype_def["field_order"]

	if doctype_def.get("permissions") is not None:
		sync_permissions(doc, doctype_def.get("permissions", []))


def sync_permissions(doc, permission_defs):
	allowed_roles = {permission_def.get("role") for permission_def in permission_defs if permission_def.get("role")}
	for row in list(doc.permissions):
		if row.role not in allowed_roles:
			doc.remove(row)

	existing = {row.role: row for row in doc.permissions}
	for permission_def in permission_defs:
		role = permission_def.get("role")
		if not role:
			continue
		row = existing.get(role)
		if not row:
			row = doc.append("permissions", {"role": role})
		for key in PERMISSION_FLAGS:
			setattr(row, key, cint(permission_def.get(key, 0)))


def sync_custom_fields():
	for doctype, fields in CUSTOM_FIELDS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for field_def in fields:
			fieldname = field_def["fieldname"]
			custom_field_name = f"{doctype}-{fieldname}"
			values = dict(field_def)
			values.update({"doctype": "Custom Field", "dt": doctype})
			if frappe.db.exists("Custom Field", custom_field_name):
				continue
			else:
				values["name"] = custom_field_name
				frappe.get_doc(values).insert(ignore_permissions=True)


def ensure_compliance_default_rows():
	ensure_disciplinary_violation_catalog()
	ensure_disability_accommodation_catalog()


def ensure_disciplinary_violation_catalog():
	if not frappe.db.exists("DocType", "Disciplinary Violation Catalog"):
		return

	for code, category, name, first, second, third, fourth, source_page in DISCIPLINARY_CATALOG_DEFAULTS:
		if frappe.db.exists("Disciplinary Violation Catalog", {"violation_code": code}):
			continue
		frappe.get_doc(
			{
				"doctype": "Disciplinary Violation Catalog",
				"naming_series": "SAU-DVC-.YYYY.-.####",
				"violation_code": code,
				"violation_name": name,
				"category": category,
				"status": "Active",
				"penalty_first": first,
				"penalty_second": second,
				"penalty_third": third,
				"penalty_fourth": fourth,
				"requires_termination_review": 1 if "Termination" in fourth or "Termination" in first else 0,
				"legal_reference": "Annex 1 - Unified Work Regulation Violation Table",
				"source_page": str(source_page),
			}
		).insert(ignore_permissions=True)


def ensure_disability_accommodation_catalog():
	if not frappe.db.exists("DocType", "Disability Accommodation Catalog"):
		return

	for code, disability_type, job_family, title, details, source_page in DISABILITY_ACCOMMODATION_DEFAULTS:
		if frappe.db.exists("Disability Accommodation Catalog", {"accommodation_code": code}):
			continue
		frappe.get_doc(
			{
				"doctype": "Disability Accommodation Catalog",
				"naming_series": "SAU-DAC-.YYYY.-.####",
				"accommodation_code": code,
				"disability_type": disability_type,
				"job_family": job_family,
				"accommodation_title": title,
				"priority": "Recommended",
				"requirement_details": details,
				"evidence_required": "Medical/disability certificate, workplace review, and implementation evidence.",
				"legal_reference": "Annex 2 - Accommodation and Facilitation Table",
				"source_page": source_page,
				"active": 1,
			}
		).insert(ignore_permissions=True)


def calculate_disability_ratio(doc):
	total = flt(doc.total_employees)
	disabled = flt(doc.disabled_employees)
	doc.compliance_ratio = round((disabled / total) * 100, 2) if total else 0
	required_count = (total * flt(doc.required_ratio or 4)) / 100
	doc.gap_to_required = max(0, round(required_count - disabled, 2))

	if total and total < 25:
		doc.status = "Not Applicable"
	elif doc.compliance_ratio >= flt(doc.required_ratio or 4):
		doc.status = "Compliant"
	elif doc.status not in {"Needs Accommodation Review"}:
		doc.status = "Below Required Ratio"


def calculate_final_settlement_dates(doc):
	if doc.last_working_day and not doc.settlement_due_date:
		doc.settlement_due_date = add_days(doc.last_working_day, 14)
	if doc.last_working_day and not doc.document_return_due_date:
		doc.document_return_due_date = add_days(doc.last_working_day, 7)

	if doc.status in {"Settled", "Cancelled"}:
		return
	if doc.settlement_due_date and getdate(doc.settlement_due_date) < getdate(today()):
		doc.status = "Overdue"


def calculate_work_arrangement_dates(doc):
	if doc.start_date and doc.end_date:
		doc.actual_days = max(0, (getdate(doc.end_date) - getdate(doc.start_date)).days + 1)

	if doc.arrangement_type in {"Temporary Work", "Casual Work"}:
		doc.conversion_due_date = add_days(doc.start_date, 90) if doc.start_date else None
		doc.conversion_required = 1 if flt(doc.actual_days) > 90 else 0
		if doc.conversion_required and doc.status not in {"Closed", "Cancelled"}:
			doc.status = "Needs Conversion"


def calculate_working_time_status(doc):
	if flt(doc.actual_daily_hours) > 10:
		doc.status = "Daily Limit Exceeded"
	elif flt(doc.actual_weekly_hours) > 60:
		doc.status = "Weekly Limit Exceeded"
	elif doc.status == "Needs Review":
		doc.status = "Compliant"


def calculate_statutory_record_counts(doc):
	required_rows = [row for row in doc.records if row.required and row.status != "Not Applicable"]
	available_rows = [row for row in required_rows if row.status == "Available"]
	doc.total_required = len(required_rows)
	doc.completed_count = len(available_rows)
	doc.gap_count = max(0, len(required_rows) - len(available_rows))
	if doc.gap_count:
		doc.status = "Gaps Found"
	elif doc.total_required:
		doc.status = "Compliant"


def calculate_inspection_fine_dates(doc):
	if doc.notification_date and not doc.payment_due_date:
		doc.payment_due_date = add_days(doc.notification_date, 60)
	if doc.status in {"Paid", "Waived", "Closed"}:
		return
	if doc.payment_due_date and getdate(doc.payment_due_date) < getdate(today()):
		doc.status = "Overdue"


def calculate_ministry_filing_status(doc):
	if doc.status in {"Accepted", "Cancelled"}:
		return
	if doc.due_date and getdate(doc.due_date) < getdate(today()):
		doc.status = "Overdue"


def apply_disciplinary_catalog_recommendation(doc):
	if not getattr(doc, "violation_catalog", None) or not frappe.db.exists(
		"DocType", "Disciplinary Violation Catalog"
	):
		return

	catalog = frappe.db.get_value(
		"Disciplinary Violation Catalog",
		doc.violation_catalog,
		[
			"penalty_first",
			"penalty_second",
			"penalty_third",
			"penalty_fourth",
			"legal_reference",
			"requires_termination_review",
			"status",
		],
		as_dict=True,
	)
	if not catalog:
		return

	occurrence_number = min(max(cint(doc.occurrence_number or 1), 1), 4)
	penalty_field = {
		1: "penalty_first",
		2: "penalty_second",
		3: "penalty_third",
		4: "penalty_fourth",
	}[occurrence_number]
	doc.recommended_penalty = catalog.get(penalty_field)
	doc.catalog_legal_reference = catalog.get("legal_reference")
	doc.catalog_requires_review = 1 if catalog.get("requires_termination_review") or catalog.get("status") == "Needs Legal Review" else 0


def apply_disability_accommodation_catalog(doc):
	if not frappe.db.exists("DocType", "Disability Accommodation Catalog"):
		return

	for row in getattr(doc, "accommodations", []) or []:
		if not getattr(row, "accommodation_catalog", None):
			continue
		requirement_details = frappe.db.get_value(
			"Disability Accommodation Catalog",
			row.accommodation_catalog,
			"requirement_details",
		)
		if requirement_details:
			row.catalog_requirement_details = requirement_details


def calculate_provider_compliance_status(doc):
	if doc.license_expiry_date and not doc.renewal_due_date:
		doc.renewal_due_date = add_days(doc.license_expiry_date, -60)

	if doc.status in {"Suspended", "Closed"}:
		return
	if doc.license_expiry_date and getdate(doc.license_expiry_date) < getdate(today()):
		doc.status = "Expired"
	elif doc.renewal_due_date and getdate(doc.renewal_due_date) <= getdate(today()) and doc.status == "Active":
		doc.status = "Renewal Due"


def calculate_provider_complaint_status(doc):
	if doc.received_on and not doc.response_due_date:
		doc.response_due_date = add_days(doc.received_on, 15)

	if doc.status in {"Resolved", "Closed"}:
		return
	if doc.response_due_date and getdate(doc.response_due_date) < getdate(today()):
		doc.status = "Overdue"


def calculate_training_agreement_status(doc):
	if doc.training_end_date and doc.commitment_months and not doc.commitment_end_date:
		doc.commitment_end_date = add_months(doc.training_end_date, cint(doc.commitment_months))

	if doc.status in {"Waived", "Cancelled"}:
		return
	if doc.recovery_applicable and flt(doc.recovery_amount) > 0:
		doc.status = "Recovery Due"
	elif doc.commitment_end_date and getdate(doc.commitment_end_date) < getdate(today()):
		doc.status = "Completed"


def validate_compliance_doc(doc, method=None):
	if doc.doctype == "Disability Employment Compliance":
		calculate_disability_ratio(doc)
		apply_disability_accommodation_catalog(doc)
	elif doc.doctype == "Final Settlement SLA":
		calculate_final_settlement_dates(doc)
	elif doc.doctype == "Work Arrangement Control":
		calculate_work_arrangement_dates(doc)
	elif doc.doctype == "Working Time Compliance Check":
		calculate_working_time_status(doc)
	elif doc.doctype == "Statutory HR Records Register":
		calculate_statutory_record_counts(doc)
	elif doc.doctype == "Inspection Fine SLA":
		calculate_inspection_fine_dates(doc)
	elif doc.doctype == "Ministry Filing Tracker":
		calculate_ministry_filing_status(doc)
	elif doc.doctype == "Disciplinary Procedure":
		apply_disciplinary_catalog_recommendation(doc)
	elif doc.doctype == "Recruitment Service Provider Compliance":
		calculate_provider_compliance_status(doc)
	elif doc.doctype == "Recruitment Provider Complaint":
		calculate_provider_complaint_status(doc)
	elif doc.doctype == "Training Agreement":
		calculate_training_agreement_status(doc)


def create_final_settlement_from_termination(doc, method=None):
	if not frappe.db.exists("DocType", "Final Settlement SLA") or doc.doctype != "Termination Notice":
		return
	if frappe.db.exists("Final Settlement SLA", {"termination_notice": doc.name}):
		return

	settlement_due = add_days(doc.notice_end_date, 14) if doc.notice_end_date else None
	document_due = add_days(doc.notice_end_date, 7) if doc.notice_end_date else None
	frappe.get_doc(
		{
			"doctype": "Final Settlement SLA",
			"termination_notice": doc.name,
			"employee": doc.employee,
			"company": doc.company,
			"last_working_day": doc.notice_end_date,
			"settlement_due_date": settlement_due,
			"document_return_due_date": document_due,
			"status": "Open",
			"risk_level": "High",
			"legal_review_required": 1,
			"notes": _("Auto-created from approved Termination Notice {0}.").format(doc.name),
		}
	).insert(ignore_permissions=True)
