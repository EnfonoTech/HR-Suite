import frappe
from frappe import _

from hr_suite import hooks as app_hooks


IMPLEMENTED = "Implemented"
PARTIAL = "Partial"
GAP = "Gap"


def execute(filters=None):
	data = get_data(filters or {})
	return get_columns(), data, None, get_chart(data), get_report_summary(data)


def get_columns():
	return [
		{"fieldname": "coverage_area", "label": _("Coverage Area"), "fieldtype": "Data", "width": 150},
		{"fieldname": "legal_reference", "label": _("Legal Reference"), "fieldtype": "Data", "width": 160},
		{"fieldname": "requirement", "label": _("Requirement"), "fieldtype": "Data", "width": 260},
		{"fieldname": "component_type", "label": _("Component Type"), "fieldtype": "Data", "width": 150},
		{"fieldname": "component_name", "label": _("Component"), "fieldtype": "Data", "width": 220},
		{"fieldname": "implementation_status", "label": _("Implementation Status"), "fieldtype": "Data", "width": 145},
		{"fieldname": "evidence", "label": _("Evidence"), "fieldtype": "Small Text", "width": 250},
		{"fieldname": "notes", "label": _("Notes"), "fieldtype": "Small Text", "width": 340},
	]


def get_data(filters):
	rows = []
	for item in get_coverage_items():
		status = evaluate_item(item)
		row = {
			"coverage_area": item["coverage_area"],
			"legal_reference": item["legal_reference"],
			"requirement": item["requirement"],
			"component_type": item["component_type"],
			"component_name": item["component_name"],
			"implementation_status": status,
			"evidence": resolve_copy(item, status, "evidence"),
			"notes": resolve_copy(item, status, "notes"),
		}
		if filters.get("implementation_status") and row["implementation_status"] != filters["implementation_status"]:
			continue
		if filters.get("coverage_area") and row["coverage_area"] != filters["coverage_area"]:
			continue
		rows.append(row)

	rows.sort(key=lambda row: (status_rank(row["implementation_status"]), row["coverage_area"], row["legal_reference"]))
	return rows


def evaluate_item(item):
	if item.get("implementation_status"):
		return item["implementation_status"]

	validator_name = item.get("validator")
	if validator_name:
		validator = globals().get(validator_name)
		if validator:
			return validator(item)

	checks = item.get("checks", [])
	if not checks:
		return GAP

	if all(run_check(check) for check in checks):
		return item.get("implemented_status", IMPLEMENTED)

	return GAP


def resolve_copy(item, status, fieldname):
	status_key = status.lower().split(" /")[0].replace(" ", "_")
	return item.get(f"{status_key}_{fieldname}", item.get(fieldname, ""))


def run_check(check):
	kind = check["kind"]
	name = check.get("name")

	if kind == "doctype":
		return bool(frappe.db.exists("DocType", name))
	if kind == "report":
		return bool(frappe.db.exists("Report", name))
	if kind == "workflow":
		return bool(frappe.db.exists("Workflow", name))
	if kind == "notification":
		return bool(frappe.db.exists("Notification", name))
	if kind == "print_format":
		return bool(frappe.db.exists("Print Format", name))
	if kind == "scheduler":
		return scheduler_method_exists(name)

	return False


def scheduler_method_exists(method_path):
	for event_group in app_hooks.scheduler_events.values():
		if isinstance(event_group, list) and method_path in event_group:
			return True
	return False


def validate_annual_leave_coverage(item):
	if not all(run_check(check) for check in item.get("checks", [])):
		return GAP

	return IMPLEMENTED if frappe.db.exists("DocType", "Annual Leave") else PARTIAL


def validate_special_leave_coverage(item):
	if not all(run_check(check) for check in item.get("checks", [])):
		return GAP

	options = frappe.db.get_value(
		"DocField",
		{"parent": "Special Leave", "fieldname": "leave_type"},
		"options",
	) or ""

	expected_options = (
		"Hajj Leave",
		"Bereavement Leave",
		"Marriage Leave",
	)
	return IMPLEMENTED if all(option in options for option in expected_options) else PARTIAL


def validate_gosi_coverage(item):
	if not all(run_check(check) for check in item.get("checks", [])):
		return GAP

	if scheduler_method_exists("hr_suite.hr_suite.tasks.send_gosi_due_alerts") and frappe.db.exists(
		"Notification", "GOSI Status Update Alert"
	):
		return IMPLEMENTED

	notification = frappe.db.get_value(
		"Notification",
		"GOSI Status Update Alert",
		["event", "value_changed"],
		as_dict=True,
	) or {}

	if notification.get("event") == "Change" and notification.get("value_changed") == "payment_status":
		return PARTIAL

	return IMPLEMENTED


def validate_wps_coverage(item):
	if not run_check({"kind": "report", "name": "WPS Export Report"}):
		return GAP

	if frappe.db.exists("DocType", "WPS Submission"):
		return IMPLEMENTED

	return PARTIAL


def status_rank(status):
	return {
		GAP: 0,
		PARTIAL: 1,
		IMPLEMENTED: 2,
	}.get(status, 99)


def get_chart(data):
	implemented_count = sum(1 for row in data if row["implementation_status"] == IMPLEMENTED)
	partial_count = sum(1 for row in data if row["implementation_status"] == PARTIAL)
	gap_count = sum(1 for row in data if row["implementation_status"] == GAP)

	return {
		"data": {
			"labels": [IMPLEMENTED, PARTIAL, GAP],
			"datasets": [{"name": _("Coverage Status"), "values": [implemented_count, partial_count, gap_count]}],
		},
		"type": "bar",
		"colors": ["#2F9E44", "#F08C00", "#C92A2A"],
	}


def get_report_summary(data):
	total = len(data)
	implemented_count = sum(1 for row in data if row["implementation_status"] == IMPLEMENTED)
	partial_count = sum(1 for row in data if row["implementation_status"] == PARTIAL)
	gap_count = sum(1 for row in data if row["implementation_status"] == GAP)

	return [
		{
			"label": _("Implemented"),
			"value": implemented_count,
			"indicator": "Green",
			"datatype": "Int",
		},
		{
			"label": _("Partial"),
			"value": partial_count,
			"indicator": "Orange",
			"datatype": "Int",
		},
		{
			"label": _("Gap"),
			"value": gap_count,
			"indicator": "Red",
			"datatype": "Int",
		},
		{
			"label": _("Coverage Ratio"),
			"value": f"{round((implemented_count / total) * 100, 1) if total else 0}%",
			"indicator": "Blue",
			"datatype": "Data",
		},
	]


def get_coverage_items():
	return [
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Art. 37-46",
			"requirement": _("Employment contracts and terms"),
			"component_type": "DocType",
			"component_name": "Country Employment Contract",
			"checks": [{"kind": "doctype", "name": "Country Employment Contract"}],
			"evidence": _("Contract DocType with probation, hours, and expiry tracking."),
			"notes": _("Core contract coverage is implemented in the employment lifecycle."),
		},
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Art. 53",
			"requirement": _("Probation controls and alerts"),
			"component_type": "Scheduler + DocType",
			"component_name": "Country Employment Contract + Probation End Alert",
			"checks": [
				{"kind": "doctype", "name": "Country Employment Contract"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_probation_end_alerts"},
			],
			"evidence": _("Probation validation in contract plus scheduled reminder before end date."),
			"notes": _("Covers probation cap, end-date calculation, and proactive reminders."),
		},
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Art. 60-64",
			"requirement": _("Training records and compliance"),
			"component_type": "DocType",
			"component_name": "Training Record",
			"checks": [{"kind": "doctype", "name": "Training Record"}],
			"evidence": _("Dedicated training register for mandatory and planned training."),
			"notes": _("Training compliance is modeled as a standalone HR record."),
		},
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Executive Regulations training agreement controls",
			"requirement": _("Training agreement and cost recovery evidence"),
			"component_type": "DocType",
			"component_name": "Training Agreement",
			"checks": [{"kind": "doctype", "name": "Training Agreement"}],
			"evidence": _("Training agreement record tracks program dates, cost, commitment period, acknowledgement, and recovery controls."),
			"notes": _("Adds the specific training-agreement layer that was previously only covered by general training records."),
		},
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Art. 65-80",
			"requirement": _("Disciplinary process and appeals"),
			"component_type": "DocType + Workflow",
			"component_name": "Disciplinary Procedure + Disciplinary Appeal",
			"checks": [
				{"kind": "doctype", "name": "Disciplinary Procedure"},
				{"kind": "doctype", "name": "Disciplinary Appeal"},
			],
			"evidence": _("Progressive discipline record plus appeal tracking with committee notes."),
			"notes": _("Operational coverage exists for both disciplinary action and appeal review."),
		},
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Annex 1 violation table",
			"requirement": _("Disciplinary violation and penalty catalog"),
			"component_type": "DocType + Defaults",
			"component_name": "Disciplinary Violation Catalog",
			"checks": [{"kind": "doctype", "name": "Disciplinary Violation Catalog"}],
			"evidence": _("Seeded catalog covers attendance, work-organization, safety, conduct, and integrity violations from the unified regulation table."),
			"notes": _("Disciplinary Procedure can link to the catalog and display the recommended penalty by occurrence number."),
		},
		{
			"coverage_area": _("Employment"),
			"legal_reference": "Art. 75-76",
			"requirement": _("Termination notice approvals"),
			"component_type": "DocType + Workflow",
			"component_name": "Termination Notice + Termination Approval Workflow",
			"checks": [
				{"kind": "doctype", "name": "Termination Notice"},
				{"kind": "workflow", "name": "Termination Approval Workflow"},
			],
			"evidence": _("Termination notice document with approval routing and notice-period handling."),
			"notes": _("Covers structured termination notice processing and approvals."),
		},
		{
			"coverage_area": _("Payroll & Benefits"),
			"legal_reference": "Art. 84",
			"requirement": _("End of service benefit"),
			"component_type": "DocType + Report",
			"component_name": "End of Service Benefit + EOSB Calculation Report",
			"checks": [
				{"kind": "doctype", "name": "End of Service Benefit"},
				{"kind": "report", "name": "EOSB Calculation Report"},
			],
			"evidence": _("EOSB computation record with supporting calculation report."),
			"notes": _("Benefit calculation and analytical reporting are both implemented."),
		},
		{
			"coverage_area": _("Payroll & Benefits"),
			"legal_reference": "Art. 90-102",
			"requirement": _("Payroll, attendance, and official records"),
			"component_type": "DocType",
			"component_name": "Monthly Payroll + Monthly Attendance Record",
			"checks": [
				{"kind": "doctype", "name": "Monthly Payroll"},
				{"kind": "doctype", "name": "Monthly Attendance Record"},
			],
			"evidence": _("Monthly payroll batch plus official attendance register with daily details."),
			"notes": _("Core wage and attendance registers are present in the app."),
		},
		{
			"coverage_area": _("Payroll & Benefits"),
			"legal_reference": "Art. 107",
			"requirement": _("Overtime compensation and approval"),
			"component_type": "DocType + Workflow",
			"component_name": "Overtime Request + Overtime Approval Workflow",
			"checks": [
				{"kind": "doctype", "name": "Overtime Request"},
				{"kind": "workflow", "name": "Overtime Approval Workflow"},
			],
			"evidence": _("Overtime request flow with approval routing and payroll integration."),
			"notes": _("Overtime is modeled as a controlled request with approval states."),
		},
		{
			"coverage_area": _("Leave Management"),
			"legal_reference": "Art. 109",
			"requirement": _("Annual leave entitlement"),
			"component_type": "DocType",
			"component_name": "Annual Leave Disbursement",
			"checks": [{"kind": "doctype", "name": "Annual Leave Disbursement"}],
			"validator": "validate_annual_leave_coverage",
			"evidence": _("Annual leave disbursement and entitlement tracking."),
			"notes": _("Annual leave coverage exists as an operational leave component."),
			"partial_evidence": _("Annual leave processing exists, but coverage also depends on the supported annual leave type being available on the site."),
			"partial_notes": _("The component is present, but the site is only partially compliant until a recognized annual leave type is installed."),
		},
		{
			"coverage_area": _("Leave Management"),
			"legal_reference": "Art. 113",
			"requirement": _("Special leave events"),
			"component_type": "DocType",
			"component_name": "Special Leave",
			"checks": [{"kind": "doctype", "name": "Special Leave"}],
			"validator": "validate_special_leave_coverage",
			"evidence": _("Special leave register for Hajj, bereavement, marriage, and similar events."),
			"notes": _("Special leave categories are represented in a dedicated record."),
			"partial_evidence": _("The Special Leave record exists, but the configured entitlement options do not fully match the expected statutory setup."),
			"partial_notes": _("Review the leave-type options and entitlement values before treating this article as fully implemented."),
		},
		{
			"coverage_area": _("Leave Management"),
			"legal_reference": "Art. 117",
			"requirement": _("Sick leave thresholds and pay tiers"),
			"component_type": "DocType + Scheduler",
			"component_name": "Sick Leave + Sick Leave Alerts",
			"checks": [
				{"kind": "doctype", "name": "Sick Leave"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_sick_leave_threshold_alerts"},
			],
			"evidence": _("Sick leave record plus threshold alerts and pay-rate handling."),
			"notes": _("Sick leave coverage includes operational tracking and alerts."),
		},
		{
			"coverage_area": _("Leave Management"),
			"legal_reference": "Art. 151 & 160",
			"requirement": _("Parental leave"),
			"component_type": "DocType",
			"component_name": "Maternity Paternity Leave",
			"checks": [{"kind": "doctype", "name": "Maternity Paternity Leave"}],
			"evidence": _("Dedicated parental leave record for maternity and paternity cases."),
			"notes": _("Parental leave is modeled as a dedicated leave component."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": "Art. 148-156",
			"requirement": _("Work injuries and GOSI reporting"),
			"component_type": "DocType",
			"component_name": "Work Injury",
			"checks": [{"kind": "doctype", "name": "Work Injury"}],
			"evidence": _("Work injury record with Form 25 and deadline controls."),
			"notes": _("Reactive injury compliance is implemented and linked to GOSI timing."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": "Art. 218-221",
			"requirement": _("Labor disputes and escalation"),
			"component_type": "DocType",
			"component_name": "Labor Dispute",
			"checks": [{"kind": "doctype", "name": "Labor Dispute"}],
			"evidence": _("Labor dispute register for ministry and court escalation tracking."),
			"notes": _("Dispute handling exists as a separate compliance record."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": _("GOSI"),
			"requirement": _("Monthly social insurance processing"),
			"component_type": "DocType + Report + Notification + Scheduler",
			"component_name": "GOSI Contribution + GOSI Monthly Report + Status Alert",
			"checks": [
				{"kind": "doctype", "name": "GOSI Contribution"},
				{"kind": "report", "name": "GOSI Monthly Report"},
				{"kind": "notification", "name": "GOSI Status Update Alert"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_gosi_due_alerts"},
			],
			"validator": "validate_gosi_coverage",
			"evidence": _("Contribution record, monthly report, and due alert notification."),
			"notes": _("GOSI processing is implemented across transaction, reporting, and notification layers."),
			"partial_evidence": _("Core GOSI transaction and reporting exist, but the current due alert is still tied to payment-status changes rather than a monthly due cycle."),
			"partial_notes": _("Treat this area as partially implemented until the due alert models the intended monthly compliance reminder."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": _("Nitaqat"),
			"requirement": _("Saudization ratio monitoring"),
			"component_type": "DocType + Report",
			"component_name": "Nitaqat Record + Nitaqat Compliance Report",
			"checks": [
				{"kind": "doctype", "name": "Nitaqat Record"},
				{"kind": "report", "name": "Nitaqat Compliance Report"},
			],
			"evidence": _("Saudization compliance record and analytical report."),
			"notes": _("Nitaqat monitoring is implemented for tracking and reporting."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": _("WPS"),
			"requirement": _("Wage protection file generation"),
			"component_type": "Report + DocType",
			"component_name": "WPS Export Report + WPS Submission",
			"checks": [{"kind": "report", "name": "WPS Export Report"}],
			"validator": "validate_wps_coverage",
			"evidence": _("SIF export exists together with a WPS submission lifecycle record for submission, rejection, correction, and acceptance tracking."),
			"notes": _("WPS export and submission follow-up are now modeled inside Hr Suite."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": _("Internal Compliance"),
			"requirement": _("Policy and legal obligation mapping"),
			"component_type": "DocType + Report",
			"component_name": "HR Policy Document + Legal Reference Matrix",
			"checks": [
				{"kind": "doctype", "name": "HR Policy Document"},
				{"kind": "doctype", "name": "Legal Reference Matrix"},
				{"kind": "report", "name": "Policy Compliance Register"},
			],
			"evidence": _("Policy register, legal reference matrix, and compliance register report."),
			"notes": _("Internal compliance layer is operational and tied to the Hr Suite workspace."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": _("Executive Regulations"),
			"requirement": _("Labor inspection and violations"),
			"component_type": "DocType + Report",
			"component_name": "Labor Inspection + Labor Inspection Tracker",
			"checks": [
				{"kind": "doctype", "name": "Labor Inspection"},
				{"kind": "doctype", "name": "Labor Inspection Violation"},
				{"kind": "report", "name": "Labor Inspection Tracker"},
			],
			"evidence": _("Dedicated inspection register with violation rows, fines, and corrective follow-up reporting."),
			"notes": _("Inspection findings are now tracked operationally and linked to compliance actions for remediation."),
			"gap_evidence": _("No dedicated inspection, violation, fine, or corrective-order entity was found."),
			"gap_notes": _("This is the highest-value next compliance module to implement after the coverage matrix."),
		},
		{
			"coverage_area": _("Work Regulations"),
			"legal_reference": _("Art.12-13; Executive Reg. Art.3-4; Annex 1"),
			"requirement": _("Approved work regulation and acknowledgement evidence"),
			"component_type": "DocType + Scheduler",
			"component_name": "Work Regulation",
			"checks": [
				{"kind": "doctype", "name": "Work Regulation"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_work_regulation_review_alerts"},
			],
			"evidence": _("Dedicated regulation record with approval, publication, certificate, and review tracking."),
			"notes": _("Covers the highest-risk policy gap identified from the official annex."),
		},
		{
			"coverage_area": _("Official Records"),
			"legal_reference": _("Art.17; Executive Reg. Art.5"),
			"requirement": _("Statutory workplace registers"),
			"component_type": "DocType",
			"component_name": "Statutory HR Records Register",
			"checks": [{"kind": "doctype", "name": "Statutory HR Records Register"}],
			"evidence": _("Single audit register for worker names, wages, fines, attendance, Saudi training, medical exams, and employee files."),
			"notes": _("Turns scattered evidence into an auditable compliance package."),
		},
		{
			"coverage_area": _("Government Filings"),
			"legal_reference": _("Art.15; Executive Reg. Art.4 repeated; hiring disclosures"),
			"requirement": _("Ministry filing deadlines and platform evidence"),
			"component_type": "DocType + Scheduler",
			"component_name": "Ministry Filing Tracker",
			"checks": [
				{"kind": "doctype", "name": "Ministry Filing Tracker"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_ministry_filing_due_alerts"},
			],
			"evidence": _("Tracks establishment data updates, vacancy filings, candidate responses, and annual disclosures."),
			"notes": _("Addresses mandatory deadlines such as the 10-day establishment-data update."),
		},
		{
			"coverage_area": _("Document Custody"),
			"legal_reference": _("Executive Reg. Art.6"),
			"requirement": _("No retention of non-Saudi passport, iqama, or medical insurance originals"),
			"component_type": "DocType + Scheduler",
			"component_name": "Employee Document Custody Log",
			"checks": [
				{"kind": "doctype", "name": "Employee Document Custody Log"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_employee_document_custody_alerts"},
			],
			"evidence": _("Records custody exceptions, return due dates, and evidence attachments."),
			"notes": _("Provides internal evidence without encouraging permanent original-document retention."),
		},
		{
			"coverage_area": _("Saudization & Inclusion"),
			"legal_reference": _("Executive Reg. Art.9"),
			"requirement": _("Qualified disability employment and accommodation evidence"),
			"component_type": "DocType",
			"component_name": "Disability Employment Compliance",
			"checks": [{"kind": "doctype", "name": "Disability Employment Compliance"}],
			"evidence": _("Tracks required ratio, qualified employees, and accommodations by period."),
			"notes": _("Complements Nitaqat with a specific disability-employment compliance layer."),
		},
		{
			"coverage_area": _("Saudization & Inclusion"),
			"legal_reference": _("Annex 2 accommodation table"),
			"requirement": _("Accommodation catalog by disability type and job family"),
			"component_type": "DocType + Defaults",
			"component_name": "Disability Accommodation Catalog",
			"checks": [{"kind": "doctype", "name": "Disability Accommodation Catalog"}],
			"evidence": _("Seeded catalog maps physical, visual, hearing, psychological, medical, and general accommodations to job families."),
			"notes": _("Disability Employment Compliance rows can link to a catalog item and inherit its checklist requirement."),
		},
		{
			"coverage_area": _("Exit"),
			"legal_reference": _("Unified contract model and Art.75-76, 84"),
			"requirement": _("Final settlement, document return, and EOSB wage-basis legal review"),
			"component_type": "DocType + Scheduler + Custom Fields",
			"component_name": "Final Settlement SLA + EOSB Wage Basis Review",
			"checks": [
				{"kind": "doctype", "name": "Final Settlement SLA"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_final_settlement_sla_alerts"},
			],
			"evidence": _("Tracks settlement due date, document-return due date, EOSB link, and legal review flag."),
			"notes": _("Reduces the risk that termination is approved without a timed closure package."),
		},
		{
			"coverage_area": _("Alternative Work"),
			"legal_reference": _("Executive Regulations and contract annexes"),
			"requirement": _("Flexible, part-time, remote, temporary, casual, and seasonal work controls"),
			"component_type": "DocType",
			"component_name": "Work Arrangement Control",
			"checks": [{"kind": "doctype", "name": "Work Arrangement Control"}],
			"evidence": _("Dedicated record for arrangement type, portal reference, dates, hours, and 90-day conversion tracking."),
			"notes": _("Implements the former Work Arrangement Controls gap."),
		},
		{
			"coverage_area": _("Working Time"),
			"legal_reference": _("Executive Regulations working-hours controls"),
			"requirement": _("Daily and weekly hour guardrails"),
			"component_type": "DocType",
			"component_name": "Working Time Compliance Check",
			"checks": [{"kind": "doctype", "name": "Working Time Compliance Check"}],
			"evidence": _("Flags 10-hour daily and 60-hour weekly overages for review or exception approval."),
			"notes": _("Complements shifts and overtime with statutory guardrails."),
		},
		{
			"coverage_area": _("Compliance"),
			"legal_reference": _("Executive Regulations penalty collection"),
			"requirement": _("Inspection fine payment and objection SLA"),
			"component_type": "DocType + Scheduler",
			"component_name": "Inspection Fine SLA",
			"checks": [
				{"kind": "doctype", "name": "Inspection Fine SLA"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_inspection_fine_sla_alerts"},
			],
			"evidence": _("Tracks notification date, payment deadline, objection state, and payment evidence."),
			"notes": _("Adds the 60-day fine payment follow-up missing from inspection tracking."),
		},
		{
			"coverage_area": _("Safety"),
			"legal_reference": _("Executive Regulations occupational safety controls"),
			"requirement": _("Preventive occupational safety controls"),
			"component_type": "DocType",
			"component_name": "Safety Inspection and Risk Control",
			"checks": [{"kind": "doctype", "name": "Safety Inspection and Risk Control"}],
			"evidence": _("Preventive inspection record with risk controls, first-aid evidence, and remote-site controls."),
			"notes": _("Implements the former preventive safety gap and complements Work Injury."),
		},
		{
			"coverage_area": _("Contract Evidence"),
			"legal_reference": _("Contract models and platform evidence"),
			"requirement": _("Portal reference and employee acknowledgement for contract documentation"),
			"component_type": "DocType",
			"component_name": "Contract Portal Evidence",
			"checks": [{"kind": "doctype", "name": "Contract Portal Evidence"}],
			"evidence": _("Tracks submission reference, employee acknowledgement, acceptance date, and attachment."),
			"notes": _("Supports standard, part-time, flexible, remote, temporary, casual, and seasonal contract evidence."),
		},
		{
			"coverage_area": _("Contract Evidence"),
			"legal_reference": _("Annex 5 unified contract models"),
			"requirement": _("Official print formats for standard, part-time, temporary/casual, and seasonal contracts"),
			"component_type": "Print Formats",
			"component_name": "Standard/Part Time/Temporary/Seasonal Contract Official",
			"checks": [
				{"kind": "print_format", "name": "Standard Contract Official"},
				{"kind": "print_format", "name": "Part Time Contract Official"},
				{"kind": "print_format", "name": "Temporary Casual Contract Official"},
				{"kind": "print_format", "name": "Seasonal Contract Official"},
			],
			"evidence": _("Print formats for the per-country official contract models."),
			"notes": _(
				"Open gap: the country-specific contract-model print formats are not shipped yet — "
				"the previous ones were empty placeholders and were removed."
			),
		},
		{
			"coverage_area": _("Recruitment Providers"),
			"legal_reference": _("Annex 3 and Annex 4"),
			"requirement": _("Licensed recruitment and labor-services provider compliance"),
			"component_type": "DocType",
			"component_name": "Recruitment Service Provider Compliance",
			"checks": [{"kind": "doctype", "name": "Recruitment Service Provider Compliance"}],
			"evidence": _("Tracks license, renewal, insurance, bank documentation, complaint channel, branches, violations, and ministry evidence."),
			"notes": _("This is marked operational even when the employer is not a provider, because the optional provider module now exists."),
		},
		{
			"coverage_area": _("Recruitment Providers"),
			"legal_reference": _("Annex 4 complaint channel controls"),
			"requirement": _("Provider complaint tracking and SLA"),
			"component_type": "DocType",
			"component_name": "Recruitment Provider Complaint",
			"checks": [{"kind": "doctype", "name": "Recruitment Provider Complaint"}],
			"evidence": _("Complaint record tracks complainant type, received date, response due date, status, resolution, and platform evidence."),
			"notes": _("Complements provider compliance with an auditable complaint workflow."),
		},
		{
			"coverage_area": _("Special Categories"),
			"legal_reference": _("Executive Regulations special category controls"),
			"requirement": _("Women, young workers, disability, pregnancy, and nursing controls"),
			"component_type": "DocType",
			"component_name": "Special Employment Category Control",
			"checks": [{"kind": "doctype", "name": "Special Employment Category Control"}],
			"evidence": _("Tracks category, job-risk review, prohibited-job review, medical/training requirements, and evidence."),
			"notes": _("Implements the former Women & Young Workers Controls gap as a general protected-category control."),
		},
		{
			"coverage_area": _("Leave Management"),
			"legal_reference": _("Executive Regulations official holiday overlap controls"),
			"requirement": _("Official holiday overlap with weekly rest, annual leave, and sick leave"),
			"component_type": "DocType",
			"component_name": "Holiday Leave Overlap Rule",
			"checks": [{"kind": "doctype", "name": "Holiday Leave Overlap Rule"}],
			"evidence": _("Tracks overlap type, required action, leave reference, and evidence."),
			"notes": _("Provides a legal-review record before turning overlap scenarios into fully automated payroll/leave rules."),
		},
		{
			"coverage_area": _("Government Relations"),
			"legal_reference": _("Executive Regulations non-Saudi authorization controls"),
			"requirement": _("Work permit, iqama, profession change, service transfer, and restricted occupation evidence"),
			"component_type": "DocType + Scheduler",
			"component_name": "Expat Work Authorization Control",
			"checks": [
				{"kind": "doctype", "name": "Expat Work Authorization Control"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_expat_authorization_due_alerts"},
			],
			"evidence": _("Adds platform action tracking on top of expiry-only Work Permit/Iqama records."),
			"notes": _("Useful where the obligation is an external platform action but the employer needs internal evidence."),
		},
		{
			"coverage_area": _("Training"),
			"legal_reference": _("Executive Reg. Art.43"),
			"requirement": _("Annual training disclosure and supporting evidence"),
			"component_type": "DocType + Scheduler",
			"component_name": "Training Disclosure Register",
			"checks": [
				{"kind": "doctype", "name": "Training Disclosure Register"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_training_disclosure_due_alerts"},
			],
			"evidence": _("Summarizes yearly training counts and platform submission evidence."),
			"notes": _("Complements Training Record with a ministry-disclosure package."),
		},
	]
