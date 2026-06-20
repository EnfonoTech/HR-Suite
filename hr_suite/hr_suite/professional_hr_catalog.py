import frappe
from frappe import _


CATALOG_VERSION = "2026-05-08-component-parent-routes"


CATEGORIES = [
	{"id": "daily", "title": "Daily Command", "tone": "Operations"},
	{"id": "setup", "title": "Setup and Governance", "tone": "Foundation"},
	{"id": "workflow", "title": "Workflow Control", "tone": "Control"},
	{"id": "recruitment", "title": "Recruitment", "tone": "Talent"},
	{"id": "onboarding", "title": "Onboarding and Contracts", "tone": "Lifecycle"},
	{"id": "time", "title": "Leave and Payroll", "tone": "Payroll"},
	{"id": "performance", "title": "Performance and Growth", "tone": "Growth"},
	{"id": "relations", "title": "Employee Relations", "tone": "People"},
	{"id": "compliance", "title": "Compliance and Legal", "tone": "Risk"},
	{"id": "exit", "title": "Exit and Settlement", "tone": "Closure"},
	{"id": "components", "title": "System Components", "tone": "Structure"},
	{"id": "reports", "title": "Reports and Analytics", "tone": "Insights"},
]


FEATURES = [
	{"id": "employee-org-tree", "category": "daily", "title": "Employee Org Tree", "summary": "Visual organization map for departments, managers, and employee scope.", "target_type": "Page", "target": "employee-org-tree", "priority": "Primary"},
	{"id": "saudi-hr-settings", "category": "setup", "title": "Hr Suite Settings", "summary": "Central control for Hr Suite policies, rates, alerts, and operating preferences.", "target_type": "DocType", "target": "Hr Suite Settings", "priority": "Primary", "allow_entry": False, "action_label": "Open Settings"},
	{"id": "hr-policy-document", "category": "setup", "title": "HR Policy Document", "summary": "Maintain policy documents, versions, and acknowledgement governance.", "target_type": "DocType", "target": "HR Policy Document"},
	{"id": "legal-reference-matrix", "category": "setup", "title": "Legal Reference Matrix", "summary": "Reference Saudi labor rules and connect them to operational HR controls.", "target_type": "DocType", "target": "Legal Reference Matrix"},
	{"id": "saudi-regulatory-task", "category": "setup", "title": "Regulatory Task", "summary": "Track statutory HR tasks, due dates, owners, and closure evidence.", "target_type": "DocType", "target": "Regulatory Task"},
	{"id": "policy-acknowledgement", "category": "setup", "title": "Policy Acknowledgement", "summary": "Record employee acknowledgement of HR policies and policy updates.", "target_type": "DocType", "target": "Policy Acknowledgement"},
	{"id": "workflow", "category": "workflow", "title": "Workflow", "summary": "Configure approval paths for HR documents and operational controls.", "target_type": "DocType", "target": "Workflow"},
	{"id": "workflow-state", "category": "workflow", "title": "Workflow State", "summary": "Maintain workflow states used by HR approval processes.", "target_type": "DocType", "target": "Workflow State"},
	{"id": "workflow-action", "category": "workflow", "title": "Workflow Action", "summary": "Monitor pending and completed approval actions across HR flows.", "target_type": "DocType", "target": "Workflow Action"},
	{"id": "overtime-approval-workflow", "category": "workflow", "title": "Overtime Approval Workflow", "summary": "Open the configured workflow record for overtime request approvals.", "target_type": "URL", "target": "/app/workflow/Overtime%20Approval%20Workflow"},
	{"id": "annual-leave-approval-workflow", "category": "workflow", "title": "Annual Leave Approval Workflow", "summary": "Open the configured workflow record for annual leave approvals.", "target_type": "URL", "target": "/app/workflow/Annual%20Leave%20Approval%20Workflow"},
	{"id": "sick-leave-approval-workflow", "category": "workflow", "title": "Sick Leave Approval Workflow", "summary": "Open the configured workflow record for sick leave approvals.", "target_type": "URL", "target": "/app/workflow/Sick%20Leave%20Approval%20Workflow"},
	{"id": "salary-adjustment-workflow", "category": "workflow", "title": "Salary Adjustment Workflow", "summary": "Open the configured workflow record for salary adjustment approvals.", "target_type": "URL", "target": "/app/workflow/Salary%20Adjustment%20Workflow"},
	{"id": "hiring-requisition", "category": "recruitment", "title": "Hiring Requisition", "summary": "Request, approve, and track headcount needs before recruitment starts.", "target_type": "DocType", "target": "Hiring Requisition", "priority": "Primary"},
	{"id": "candidate-profile", "category": "recruitment", "title": "Candidate Profile", "summary": "Maintain candidate information and recruitment pipeline records.", "target_type": "DocType", "target": "Candidate Profile"},
	{"id": "employee-onboarding", "category": "onboarding", "title": "Employee Onboarding", "summary": "Coordinate onboarding tasks, owners, and readiness before joining.", "target_type": "DocType", "target": "Employee Onboarding", "priority": "Primary"},
	{"id": "employee-profile", "category": "onboarding", "title": "Employee Profile", "summary": "Open the employee master profile for core employment data.", "target_type": "DocType", "target": "Employee", "priority": "Primary"},
	{"id": "saudi-employment-contract", "category": "onboarding", "title": "Saudi Employment Contract", "summary": "Manage Saudi employment contracts, terms, expiry, and renewals.", "target_type": "DocType", "target": "Saudi Employment Contract", "priority": "Primary"},
	{"id": "medical-examination", "category": "onboarding", "title": "Medical Examination", "summary": "Track medical examination requirements and results for employees.", "target_type": "DocType", "target": "Medical Examination"},
	{"id": "work-permit-iqama", "category": "onboarding", "title": "Work Permit Iqama", "summary": "Track work permit and Iqama records, expiry dates, and renewals.", "target_type": "DocType", "target": "Work Permit Iqama", "priority": "Primary"},
	{"id": "saudi-monthly-payroll", "category": "time", "title": "Monthly Payroll", "summary": "Run monthly Saudi payroll with deductions, contributions, and settlement context.", "target_type": "DocType", "target": "Monthly Payroll", "priority": "Primary"},
	{"id": "wps-submission", "category": "time", "title": "WPS Submission", "summary": "Prepare and track WPS payroll submissions.", "target_type": "DocType", "target": "WPS Submission", "priority": "Primary"},
	{"id": "overtime-request", "category": "time", "title": "Overtime Request", "summary": "Request, approve, and post overtime based on HR policy.", "target_type": "DocType", "target": "Overtime Request"},
	{"id": "saudi-annual-leave", "category": "time", "title": "Annual Leave", "summary": "Manage annual leave requests, balances, approvals, and disbursement context.", "target_type": "DocType", "target": "Annual Leave", "priority": "Primary"},
	{"id": "saudi-sick-leave", "category": "time", "title": "Sick Leave", "summary": "Track sick leave rules, thresholds, and approval workflow.", "target_type": "DocType", "target": "Sick Leave"},
	{"id": "maternity-paternity-leave", "category": "time", "title": "Maternity Paternity Leave", "summary": "Manage family-related statutory leave records.", "target_type": "DocType", "target": "Maternity Paternity Leave"},
	{"id": "special-leave", "category": "time", "title": "Special Leave", "summary": "Track special leave cases and approvals.", "target_type": "DocType", "target": "Special Leave"},
	{"id": "employee-loan", "category": "time", "title": "Employee Loan", "summary": "Manage employee loans and payroll recovery.", "target_type": "DocType", "target": "Employee Loan"},
	{"id": "gosi-contribution", "category": "time", "title": "GOSI Contribution", "summary": "Track GOSI contributions and payroll accounting impact.", "target_type": "DocType", "target": "GOSI Contribution"},
	{"id": "nitaqat-record", "category": "time", "title": "Nitaqat Record", "summary": "Track Saudization and Nitaqat compliance records.", "target_type": "DocType", "target": "Nitaqat Record"},
	{"id": "performance-review", "category": "performance", "title": "Performance Review", "summary": "Manage employee performance reviews and development outcomes.", "target_type": "DocType", "target": "Performance Review", "priority": "Primary"},
	{"id": "salary-adjustment", "category": "performance", "title": "Salary Adjustment", "summary": "Request and approve salary adjustments with governance controls.", "target_type": "DocType", "target": "Salary Adjustment", "priority": "Primary"},
	{"id": "promotion-transfer", "category": "performance", "title": "Promotion Transfer", "summary": "Manage promotions, transfers, and position movement decisions.", "target_type": "DocType", "target": "Promotion Transfer", "priority": "Primary"},
	{"id": "training-record", "category": "performance", "title": "Training Record", "summary": "Track employee training participation and development evidence.", "target_type": "DocType", "target": "Training Record"},
	{"id": "employee-grievance", "category": "relations", "title": "Employee Grievance", "summary": "Record and resolve employee grievance cases.", "target_type": "DocType", "target": "Employee Grievance"},
	{"id": "investigation-record", "category": "relations", "title": "Investigation Record", "summary": "Document employee investigations, findings, and actions.", "target_type": "DocType", "target": "Investigation Record"},
	{"id": "employee-warning-notice", "category": "relations", "title": "Employee Warning Notice", "summary": "Issue and track warning notices with HR governance.", "target_type": "DocType", "target": "Employee Warning Notice"},
	{"id": "absence-case", "category": "relations", "title": "Absence Case", "summary": "Track absence cases, justification, and resolution.", "target_type": "DocType", "target": "Absence Case"},
	{"id": "work-injury", "category": "relations", "title": "Work Injury", "summary": "Record workplace injuries and follow-up actions.", "target_type": "DocType", "target": "Work Injury"},
	{"id": "disciplinary-procedure", "category": "compliance", "title": "Disciplinary Procedure", "summary": "Manage disciplinary procedures aligned with policy and labor law.", "target_type": "DocType", "target": "Disciplinary Procedure"},
	{"id": "disciplinary-decision-log", "category": "compliance", "title": "Disciplinary Decision Log", "summary": "Track disciplinary decisions, evidence, and execution status.", "target_type": "DocType", "target": "Disciplinary Decision Log"},
	{"id": "disciplinary-appeal", "category": "compliance", "title": "Disciplinary Appeal", "summary": "Manage employee appeals against disciplinary decisions.", "target_type": "DocType", "target": "Disciplinary Appeal"},
	{"id": "labor-dispute", "category": "compliance", "title": "Labor Dispute", "summary": "Track labor disputes, milestones, and settlement actions.", "target_type": "DocType", "target": "Labor Dispute"},
	{"id": "labor-inspection", "category": "compliance", "title": "Labor Inspection", "summary": "Record labor inspections, findings, and corrective actions.", "target_type": "DocType", "target": "Labor Inspection"},
	{"id": "hr-compliance-action-log", "category": "compliance", "title": "HR Compliance Action Log", "summary": "Central log for HR compliance actions and closure evidence.", "target_type": "DocType", "target": "HR Compliance Action Log"},
	{"id": "termination-notice", "category": "exit", "title": "Termination Notice", "summary": "Issue and track termination notices with required dates and reasons.", "target_type": "DocType", "target": "Termination Notice"},
	{"id": "exit-clearance", "category": "exit", "title": "Exit Clearance", "summary": "Coordinate clearance items before final settlement.", "target_type": "DocType", "target": "Exit Clearance", "priority": "Primary"},
	{"id": "exit-interview", "category": "exit", "title": "Exit Interview", "summary": "Capture exit interview feedback and retention signals.", "target_type": "DocType", "target": "Exit Interview"},
	{"id": "end-of-service-benefit", "category": "exit", "title": "End of Service Benefit", "summary": "Calculate and track EOSB entitlement and settlement details.", "target_type": "DocType", "target": "End of Service Benefit"},
	{"id": "annual-leave-disbursement", "category": "exit", "title": "Annual Leave Disbursement", "summary": "Manage annual leave balance disbursement during settlement.", "target_type": "DocType", "target": "Annual Leave Disbursement"},
	{"id": "branch-employee-directory-row", "category": "components", "title": "Branch Employee Directory Row", "summary": "Internal employee directory line used inside branch and organizational views.", "target_type": "DocType", "target": "Branch Employee Directory Row", "allow_entry": False, "route_target_type": "Page", "route_target": "employee-org-tree", "action_label": "Open Parent View"},
	{"id": "employee-loan-installment", "category": "components", "title": "Employee Loan Installment", "summary": "Installment schedule component used inside employee loan recovery records.", "target_type": "DocType", "target": "Employee Loan Installment", "allow_entry": False, "route_target_type": "DocType", "route_target": "Employee Loan", "action_label": "Open Parent Records"},
	{"id": "labor-inspection-violation", "category": "components", "title": "Labor Inspection Violation", "summary": "Violation detail component captured within labor inspection records.", "target_type": "DocType", "target": "Labor Inspection Violation", "allow_entry": False, "route_target_type": "DocType", "route_target": "Labor Inspection", "action_label": "Open Parent Records"},
	{"id": "payroll-adjustment-item", "category": "components", "title": "Payroll Adjustment Item", "summary": "Payroll adjustment line component used inside monthly payroll processing.", "target_type": "DocType", "target": "Payroll Adjustment Item", "allow_entry": False, "route_target_type": "DocType", "route_target": "Monthly Payroll", "action_label": "Open Parent Records"},
	{"id": "saudi-monthly-payroll-employee", "category": "components", "title": "Monthly Payroll Employee", "summary": "Employee payroll line component generated within Saudi monthly payroll runs.", "target_type": "DocType", "target": "Monthly Payroll Employee", "allow_entry": False, "route_target_type": "DocType", "route_target": "Monthly Payroll", "action_label": "Open Parent Records"},
	{"id": "saudi-labor-coverage-matrix", "category": "reports", "title": "Saudi Labor Coverage Matrix", "summary": "Report coverage of Saudi labor requirements across HR controls.", "target_type": "Report", "target": "Saudi Labor Coverage Matrix"},
	{"id": "policy-compliance-register", "category": "reports", "title": "Policy Compliance Register", "summary": "Review policy compliance status and gaps.", "target_type": "Report", "target": "Policy Compliance Register"},
	{"id": "compliance-case-tracker", "category": "reports", "title": "Compliance Case Tracker", "summary": "Track compliance cases across ownership and status.", "target_type": "Report", "target": "Compliance Case Tracker"},
	{"id": "labor-inspection-tracker", "category": "reports", "title": "Labor Inspection Tracker", "summary": "Monitor inspection findings and corrective actions.", "target_type": "Report", "target": "Labor Inspection Tracker"},
	{"id": "gosi-monthly-report", "category": "reports", "title": "GOSI Monthly Report", "summary": "Monthly report for GOSI contribution review.", "target_type": "Report", "target": "GOSI Monthly Report"},
	{"id": "eosb-calculation-report", "category": "reports", "title": "EOSB Calculation Report", "summary": "Review EOSB calculations and settlement values.", "target_type": "Report", "target": "EOSB Calculation Report"},
	{"id": "contract-expiry-report", "category": "reports", "title": "Contract Expiry Report", "summary": "Monitor contract expiry dates and renewal pipeline.", "target_type": "Report", "target": "Contract Expiry Report"},
	{"id": "work-permit-expiry-report", "category": "reports", "title": "Work Permit Expiry Report", "summary": "Monitor work permit and Iqama expiry risks.", "target_type": "Report", "target": "Work Permit Expiry Report"},
	{"id": "nitaqat-compliance-report", "category": "reports", "title": "Nitaqat Compliance Report", "summary": "Review Nitaqat compliance and Saudization position.", "target_type": "Report", "target": "Nitaqat Compliance Report"},
	{"id": "saudi-leave-balance-report", "category": "reports", "title": "Saudi Leave Balance Report", "summary": "Review leave balances and liabilities.", "target_type": "Report", "target": "Saudi Leave Balance Report"},
	{"id": "outstanding-employee-loans", "category": "reports", "title": "Outstanding Employee Loans", "summary": "Report outstanding employee loan balances.", "target_type": "Report", "target": "Outstanding Employee Loans"},
	{"id": "loan-deduction-register", "category": "reports", "title": "Loan Deduction Register", "summary": "Review payroll loan deductions.", "target_type": "Report", "target": "Loan Deduction Register"},
	{"id": "monthly-loan-recovery-summary", "category": "reports", "title": "Monthly Loan Recovery Summary", "summary": "Summarize monthly employee loan recovery.", "target_type": "Report", "target": "Monthly Loan Recovery Summary"},
	{"id": "wps-export-report", "category": "reports", "title": "WPS Export Report", "summary": "Review WPS export output before submission.", "target_type": "Report", "target": "WPS Export Report"},
	{"id": "wps-submission-tracker", "category": "reports", "title": "WPS Submission Tracker", "summary": "Track WPS submission status, files, and follow-up.", "target_type": "Report", "target": "WPS Submission Tracker", "priority": "Primary"},
]


def _route_for_target(target_type, target):
	if not target:
		return ""
	if target_type == "URL":
		return target
	if target_type == "Page":
		return f"/app/{target}"
	if target_type == "Report":
		return f"/app/query-report/{target}"
	return f"/app/{frappe.scrub(target).replace('_', '-')}"


def _route_for_feature(feature):
	return _route_for_target(
		feature.get("route_target_type") or feature.get("target_type"),
		feature.get("route_target") or feature.get("target"),
	)


def _feature_with_route(feature):
	item = dict(feature)
	item["route"] = _route_for_feature(feature)
	item["detail_route"] = f"/app/professional-hr-feature/{feature['id']}"
	if feature.get("target_type") == "DocType" and feature.get("allow_entry") is not False:
		item["entry_route"] = f"/app/professional-hr-entry/{feature['id']}"
	return item


@frappe.whitelist()
def get_professional_hr_catalog():
	features = [_feature_with_route(feature) for feature in FEATURES]
	category_counts = {category["id"]: 0 for category in CATEGORIES}
	for feature in features:
		category_counts[feature["category"]] = category_counts.get(feature["category"], 0) + 1

	return {
		"version": CATALOG_VERSION,
		"categories": [dict(category, count=category_counts.get(category["id"], 0)) for category in CATEGORIES],
		"features": features,
		"total_features": len(features),
		"primary_features": len([feature for feature in features if feature.get("priority") == "Primary"]),
	}


@frappe.whitelist()
def get_professional_hr_feature(feature_id):
	catalog = get_professional_hr_catalog()
	feature = next((item for item in catalog["features"] if item["id"] == feature_id), None)
	if not feature:
		frappe.throw(_("Professional HR feature not found."), frappe.DoesNotExistError)

	category = next((item for item in catalog["categories"] if item["id"] == feature["category"]), None)
	related = [
		item
		for item in catalog["features"]
		if item["category"] == feature["category"] and item["id"] != feature["id"]
	][:6]

	return {
		"feature": feature,
		"category": category,
		"related": related,
		"catalog_summary": {
			"total_features": catalog["total_features"],
			"category_features": category.get("count") if category else 0,
		},
	}
