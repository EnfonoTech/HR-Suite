import frappe
from frappe import _


CATALOG_VERSION = "2026-06-21-multi-country-global"


CATEGORIES = [
	{"id": "daily", "title": "Daily Command", "tone": "Operations"},
	{"id": "setup", "title": "Setup and Governance", "tone": "Foundation"},
	{"id": "workflow", "title": "Workflow Control", "tone": "Control"},
	{"id": "recruitment", "title": "Recruitment", "tone": "Talent"},
	{"id": "onboarding", "title": "Onboarding and Contracts", "tone": "Lifecycle"},
	{"id": "time", "title": "Leave and Payroll", "tone": "Payroll"},
	{"id": "statutory", "title": "Statutory Contributions", "tone": "Compliance"},
	{"id": "performance", "title": "Performance and Growth", "tone": "Growth"},
	{"id": "relations", "title": "Employee Relations", "tone": "People"},
	{"id": "compliance", "title": "Compliance and Legal", "tone": "Risk"},
	{"id": "exit", "title": "Exit and Settlement", "tone": "Closure"},
	{"id": "components", "title": "System Components", "tone": "Structure"},
	{"id": "reports", "title": "Reports and Analytics", "tone": "Insights"},
]


FEATURES = [
	# ── Daily Command ────────────────────────────────────────────────────────
	{"id": "employee-org-tree", "category": "daily", "title": "Employee Org Tree", "summary": "Visual organization map for departments, managers, and employee scope.", "target_type": "Page", "target": "employee-org-tree", "priority": "Primary"},

	# ── Setup and Governance ─────────────────────────────────────────────────
	{"id": "hr-suite-settings", "category": "setup", "title": "Hr Suite Settings", "summary": "Central control for Hr Suite policies, rates, alerts, and operating preferences.", "target_type": "DocType", "target": "Hr Suite Settings", "priority": "Primary", "allow_entry": False, "action_label": "Open Settings"},
	{"id": "country-config", "category": "setup", "title": "Country Config", "summary": "Configure statutory rates, settlement formulas, leave entitlements, and compliance rules per country.", "target_type": "DocType", "target": "Country Config", "priority": "Primary"},
	{"id": "hr-policy-document", "category": "setup", "title": "HR Policy Document", "summary": "Maintain policy documents, versions, and acknowledgement governance.", "target_type": "DocType", "target": "HR Policy Document"},
	{"id": "legal-reference-matrix", "category": "setup", "title": "Legal Reference Matrix", "summary": "Reference labor rules per country and connect them to operational HR controls.", "target_type": "DocType", "target": "Legal Reference Matrix"},
	{"id": "regulatory-task", "category": "setup", "title": "Regulatory Task", "summary": "Track statutory HR tasks, due dates, owners, and closure evidence.", "target_type": "DocType", "target": "Regulatory Task"},
	{"id": "policy-acknowledgement", "category": "setup", "title": "Policy Acknowledgement", "summary": "Record employee acknowledgement of HR policies and policy updates.", "target_type": "DocType", "target": "Policy Acknowledgement"},
	{"id": "hr-letter-template", "category": "setup", "title": "HR Letter Template", "summary": "Create reusable templates for official HR letters and correspondence.", "target_type": "DocType", "target": "HR Letter Template"},
	{"id": "hr-letter", "category": "setup", "title": "HR Letter", "summary": "Generate and track official HR letters issued to employees.", "target_type": "DocType", "target": "HR Letter"},

	# ── Workflow Control ─────────────────────────────────────────────────────
	{"id": "workflow", "category": "workflow", "title": "Workflow", "summary": "Configure approval paths for HR documents and operational controls.", "target_type": "DocType", "target": "Workflow"},
	{"id": "workflow-state", "category": "workflow", "title": "Workflow State", "summary": "Maintain workflow states used by HR approval processes.", "target_type": "DocType", "target": "Workflow State"},
	{"id": "workflow-action", "category": "workflow", "title": "Workflow Action", "summary": "Monitor pending and completed approval actions across HR flows.", "target_type": "DocType", "target": "Workflow Action"},
	{"id": "overtime-approval-workflow", "category": "workflow", "title": "Overtime Approval Workflow", "summary": "Open the configured workflow record for overtime request approvals.", "target_type": "URL", "target": "/app/workflow/Overtime%20Approval%20Workflow"},
	{"id": "annual-leave-approval-workflow", "category": "workflow", "title": "Annual Leave Approval Workflow", "summary": "Open the configured workflow record for annual leave approvals.", "target_type": "URL", "target": "/app/workflow/Annual%20Leave%20Approval%20Workflow"},
	{"id": "sick-leave-approval-workflow", "category": "workflow", "title": "Sick Leave Approval Workflow", "summary": "Open the configured workflow record for sick leave approvals.", "target_type": "URL", "target": "/app/workflow/Sick%20Leave%20Approval%20Workflow"},
	{"id": "salary-adjustment-workflow", "category": "workflow", "title": "Salary Adjustment Workflow", "summary": "Open the configured workflow record for salary adjustment approvals.", "target_type": "URL", "target": "/app/workflow/Salary%20Adjustment%20Workflow"},

	# ── Recruitment ──────────────────────────────────────────────────────────
	{"id": "job-requisition", "category": "recruitment", "title": "Job Requisition", "summary": "Request, approve, and track headcount needs before recruitment starts.", "target_type": "DocType", "target": "Job Requisition", "priority": "Primary"},
	{"id": "candidate-profile", "category": "recruitment", "title": "Candidate Profile", "summary": "Maintain candidate information and recruitment pipeline records.", "target_type": "DocType", "target": "Candidate Profile"},

	# ── Onboarding and Contracts ─────────────────────────────────────────────
	{"id": "employee-onboarding", "category": "onboarding", "title": "Employee Onboarding", "summary": "Coordinate onboarding tasks, owners, and readiness before joining.", "target_type": "DocType", "target": "Employee Onboarding", "priority": "Primary"},
	{"id": "employee-profile", "category": "onboarding", "title": "Employee Profile", "summary": "Open the employee master profile for core employment data.", "target_type": "DocType", "target": "Employee", "priority": "Primary"},
	{"id": "country-employment-contract", "category": "onboarding", "title": "Country Employment Contract", "summary": "Manage multi-country employment contracts, terms, expiry, and renewals.", "target_type": "DocType", "target": "Country Employment Contract", "priority": "Primary"},
	{"id": "medical-examination", "category": "onboarding", "title": "Medical Examination", "summary": "Track pre-employment and periodic medical examination requirements and results.", "target_type": "DocType", "target": "Medical Examination"},
	{"id": "work-permit-iqama", "category": "onboarding", "title": "Work Permit Iqama", "summary": "Track work permit and residency records, expiry dates, and renewals.", "target_type": "DocType", "target": "Work Permit Iqama", "priority": "Primary"},
	{"id": "employee-document", "category": "onboarding", "title": "Employee Document", "summary": "Track employee documents, custodians, and document expiry dates.", "target_type": "DocType", "target": "Employee Document"},
	{"id": "employee-document-type", "category": "onboarding", "title": "Employee Document Type", "summary": "Configure document types available for employee document tracking.", "target_type": "DocType", "target": "Employee Document Type"},

	# ── Leave and Payroll ────────────────────────────────────────────────────
	{"id": "monthly-payroll", "category": "time", "title": "Monthly Payroll", "summary": "Run monthly payroll with deductions, contributions, and settlement context.", "target_type": "DocType", "target": "Monthly Payroll", "priority": "Primary"},
	{"id": "wps-submission", "category": "time", "title": "WPS Submission", "summary": "Prepare and track WPS payroll submissions for the Gulf region.", "target_type": "DocType", "target": "WPS Submission", "priority": "Primary"},
	{"id": "overtime-request", "category": "time", "title": "Overtime Request", "summary": "Request, approve, and post overtime based on HR policy.", "target_type": "DocType", "target": "Overtime Request"},
	{"id": "annual-leave", "category": "time", "title": "Annual Leave", "summary": "Manage annual leave requests, balances, approvals, and disbursement context.", "target_type": "DocType", "target": "Annual Leave", "priority": "Primary"},
	{"id": "sick-leave", "category": "time", "title": "Sick Leave", "summary": "Track sick leave rules, pay tiers, thresholds, and approval workflow.", "target_type": "DocType", "target": "Sick Leave"},
	{"id": "maternity-paternity-leave", "category": "time", "title": "Maternity Paternity Leave", "summary": "Manage family-related statutory leave records.", "target_type": "DocType", "target": "Maternity Paternity Leave"},
	{"id": "special-leave", "category": "time", "title": "Special Leave", "summary": "Track special leave cases and approvals.", "target_type": "DocType", "target": "Special Leave"},
	{"id": "employee-loan", "category": "time", "title": "Employee Loan", "summary": "Manage employee loans and payroll recovery installments.", "target_type": "DocType", "target": "Employee Loan"},
	{"id": "salary-component-override", "category": "time", "title": "Salary Override", "summary": "Queue one-time salary adjustments and bonuses for the next payroll cycle.", "target_type": "DocType", "target": "Salary Component Override"},

	# ── Statutory Contributions ──────────────────────────────────────────────
	{"id": "gosi-contribution", "category": "statutory", "title": "GOSI Contribution", "summary": "Track Saudi GOSI contributions and payroll accounting impact.", "target_type": "DocType", "target": "GOSI Contribution", "priority": "Primary"},
	{"id": "dews-contribution", "category": "statutory", "title": "DEWS Contribution", "summary": "Track UAE DEWS end-of-service fund contributions for expatriate employees.", "target_type": "DocType", "target": "DEWS Contribution"},
	{"id": "epf-esi-contribution", "category": "statutory", "title": "EPF / ESI Contribution", "summary": "Track India EPF and ESI statutory contributions and employer liability.", "target_type": "DocType", "target": "EPF ESI Contribution"},
	{"id": "statutory-contribution", "category": "statutory", "title": "Statutory Contribution", "summary": "Record statutory contributions for Bahrain, Oman, and multi-country operations.", "target_type": "DocType", "target": "Statutory Contribution"},
	{"id": "nitaqat-record", "category": "statutory", "title": "Nitaqat Record", "summary": "Track Saudization and Nitaqat compliance records and band position.", "target_type": "DocType", "target": "Nitaqat Record"},

	# ── Performance and Growth ───────────────────────────────────────────────
	{"id": "appraisal", "category": "performance", "title": "Appraisal", "summary": "Manage employee performance reviews, ratings, and development outcomes.", "target_type": "DocType", "target": "Appraisal", "priority": "Primary"},
	{"id": "salary-adjustment", "category": "performance", "title": "Salary Adjustment", "summary": "Request and approve salary adjustments with governance controls.", "target_type": "DocType", "target": "Salary Adjustment", "priority": "Primary"},
	{"id": "promotion-transfer", "category": "performance", "title": "Promotion Transfer", "summary": "Manage promotions, transfers, and position movement decisions.", "target_type": "DocType", "target": "Promotion Transfer", "priority": "Primary"},
	{"id": "staff-rating", "category": "performance", "title": "Staff Rating", "summary": "Capture multi-rater staff performance scores and structured feedback.", "target_type": "DocType", "target": "Staff Rating"},
	{"id": "training-record", "category": "performance", "title": "Training Record", "summary": "Track employee training participation and development evidence.", "target_type": "DocType", "target": "Training Record"},

	# ── Employee Relations ───────────────────────────────────────────────────
	{"id": "employee-grievance", "category": "relations", "title": "Employee Grievance", "summary": "Record and resolve employee grievance cases.", "target_type": "DocType", "target": "Employee Grievance"},
	{"id": "investigation-record", "category": "relations", "title": "Investigation Record", "summary": "Document employee investigations, findings, and actions.", "target_type": "DocType", "target": "Investigation Record"},
	{"id": "employee-warning-notice", "category": "relations", "title": "Employee Warning Notice", "summary": "Issue and track warning notices with HR governance.", "target_type": "DocType", "target": "Employee Warning Notice"},
	{"id": "employee-penalty", "category": "relations", "title": "Employee Penalty", "summary": "Issue employee penalties and route deductions to the next payroll cycle.", "target_type": "DocType", "target": "Employee Penalty"},
	{"id": "absence-case", "category": "relations", "title": "Absence Case", "summary": "Track absence cases, justification, and resolution.", "target_type": "DocType", "target": "Absence Case"},
	{"id": "work-injury", "category": "relations", "title": "Work Injury", "summary": "Record workplace injuries, follow-up actions, and medical examination links.", "target_type": "DocType", "target": "Work Injury"},

	# ── Compliance and Legal ─────────────────────────────────────────────────
	{"id": "disciplinary-procedure", "category": "compliance", "title": "Disciplinary Procedure", "summary": "Manage disciplinary procedures aligned with policy and labor law.", "target_type": "DocType", "target": "Disciplinary Procedure"},
	{"id": "disciplinary-decision-log", "category": "compliance", "title": "Disciplinary Decision Log", "summary": "Track disciplinary decisions, evidence, and execution status.", "target_type": "DocType", "target": "Disciplinary Decision Log"},
	{"id": "disciplinary-appeal", "category": "compliance", "title": "Disciplinary Appeal", "summary": "Manage employee appeals against disciplinary decisions.", "target_type": "DocType", "target": "Disciplinary Appeal"},
	{"id": "labor-dispute", "category": "compliance", "title": "Labor Dispute", "summary": "Track labor disputes, milestones, and settlement actions.", "target_type": "DocType", "target": "Labor Dispute"},
	{"id": "labor-inspection", "category": "compliance", "title": "Labor Inspection", "summary": "Record labor inspections, findings, and corrective actions.", "target_type": "DocType", "target": "Labor Inspection"},
	{"id": "hr-compliance-action-log", "category": "compliance", "title": "HR Compliance Action Log", "summary": "Central log for HR compliance actions and closure evidence.", "target_type": "DocType", "target": "HR Compliance Action Log"},
	{"id": "work-regulation", "category": "compliance", "title": "Work Regulation", "summary": "Maintain work regulations and labor law compliance control records.", "target_type": "DocType", "target": "Work Regulation"},
	{"id": "statutory-hr-records-register", "category": "compliance", "title": "Statutory HR Records Register", "summary": "Track mandatory HR registers required by labor authorities.", "target_type": "DocType", "target": "Statutory HR Records Register"},
	{"id": "ministry-filing-tracker", "category": "compliance", "title": "Ministry Filing Tracker", "summary": "Monitor ministry filing obligations, deadlines, and completion evidence.", "target_type": "DocType", "target": "Ministry Filing Tracker"},
	{"id": "disability-employment-compliance", "category": "compliance", "title": "Disability Employment Compliance", "summary": "Track disability employment quota requirements and accommodation records.", "target_type": "DocType", "target": "Disability Employment Compliance"},
	{"id": "work-arrangement-control", "category": "compliance", "title": "Work Arrangement Control", "summary": "Monitor remote work, flexible arrangements, and compliance controls.", "target_type": "DocType", "target": "Work Arrangement Control"},
	{"id": "working-time-compliance-check", "category": "compliance", "title": "Working Time Compliance Check", "summary": "Verify working hours, rest periods, and overtime compliance.", "target_type": "DocType", "target": "Working Time Compliance Check"},
	{"id": "inspection-fine-sla", "category": "compliance", "title": "Inspection Fine SLA", "summary": "Track labor inspection fines, payment deadlines, and appeal status.", "target_type": "DocType", "target": "Inspection Fine SLA"},
	{"id": "special-employment-category-control", "category": "compliance", "title": "Special Employment Category Control", "summary": "Manage compliance for minors, women, and protected employee categories.", "target_type": "DocType", "target": "Special Employment Category Control"},
	{"id": "holiday-leave-overlap-rule", "category": "compliance", "title": "Holiday Leave Overlap Rule", "summary": "Configure rules for leave that overlaps with official public holidays.", "target_type": "DocType", "target": "Holiday Leave Overlap Rule"},
	{"id": "expat-work-authorization-control", "category": "compliance", "title": "Expat Work Authorization Control", "summary": "Monitor authorization requirements and validity for expatriate employees.", "target_type": "DocType", "target": "Expat Work Authorization Control"},
	{"id": "training-disclosure-register", "category": "compliance", "title": "Training Disclosure Register", "summary": "Track training disclosure obligations and statutory training requirements.", "target_type": "DocType", "target": "Training Disclosure Register"},
	{"id": "recruitment-service-provider-compliance", "category": "compliance", "title": "Recruitment Provider Compliance", "summary": "Monitor compliance with registered recruitment agencies and provider contracts.", "target_type": "DocType", "target": "Recruitment Service Provider Compliance"},
	{"id": "safety-inspection-and-risk-control", "category": "compliance", "title": "Safety Inspection and Risk Control", "summary": "Track workplace safety inspections, risk items, and mitigation actions.", "target_type": "DocType", "target": "Safety Inspection and Risk Control"},

	# ── Exit and Settlement ──────────────────────────────────────────────────
	{"id": "termination-notice", "category": "exit", "title": "Termination Notice", "summary": "Issue and track termination notices with required dates and reasons.", "target_type": "DocType", "target": "Termination Notice"},
	{"id": "exit-clearance", "category": "exit", "title": "Exit Clearance", "summary": "Coordinate clearance items and unblock final settlement.", "target_type": "DocType", "target": "Exit Clearance", "priority": "Primary"},
	{"id": "exit-interview", "category": "exit", "title": "Exit Interview", "summary": "Capture exit interview feedback, retention signals, and rehire eligibility.", "target_type": "DocType", "target": "Exit Interview"},
	{"id": "end-of-service-benefit", "category": "exit", "title": "End of Service Benefit", "summary": "Calculate and track EOSB entitlement using country-specific settlement formulas.", "target_type": "DocType", "target": "End of Service Benefit", "priority": "Primary"},
	{"id": "annual-leave-disbursement", "category": "exit", "title": "Annual Leave Disbursement", "summary": "Manage annual leave balance disbursement during final settlement.", "target_type": "DocType", "target": "Annual Leave Disbursement"},
	{"id": "final-settlement-sla", "category": "exit", "title": "Final Settlement SLA", "summary": "Monitor final settlement payment deadlines and legal SLA compliance.", "target_type": "DocType", "target": "Final Settlement SLA"},

	# ── System Components ────────────────────────────────────────────────────
	{"id": "branch-employee-directory-row", "category": "components", "title": "Branch Employee Directory Row", "summary": "Internal employee directory line used inside branch and organizational views.", "target_type": "DocType", "target": "Branch Employee Directory Row", "allow_entry": False, "route_target_type": "Page", "route_target": "employee-org-tree", "action_label": "Open Parent View"},
	{"id": "employee-loan-installment", "category": "components", "title": "Employee Loan Installment", "summary": "Installment schedule component used inside employee loan recovery records.", "target_type": "DocType", "target": "Employee Loan Installment", "allow_entry": False, "route_target_type": "DocType", "route_target": "Employee Loan", "action_label": "Open Parent Records"},
	{"id": "labor-inspection-violation", "category": "components", "title": "Labor Inspection Violation", "summary": "Violation detail component captured within labor inspection records.", "target_type": "DocType", "target": "Labor Inspection Violation", "allow_entry": False, "route_target_type": "DocType", "route_target": "Labor Inspection", "action_label": "Open Parent Records"},
	{"id": "payroll-adjustment-item", "category": "components", "title": "Payroll Adjustment Item", "summary": "Payroll adjustment line component used inside monthly payroll processing.", "target_type": "DocType", "target": "Payroll Adjustment Item", "allow_entry": False, "route_target_type": "DocType", "route_target": "Monthly Payroll", "action_label": "Open Parent Records"},
	{"id": "monthly-payroll-employee", "category": "components", "title": "Monthly Payroll Employee", "summary": "Employee payroll line component generated within monthly payroll runs.", "target_type": "DocType", "target": "Monthly Payroll Employee", "allow_entry": False, "route_target_type": "DocType", "route_target": "Monthly Payroll", "action_label": "Open Parent Records"},
	{"id": "country-leave-type-row", "category": "components", "title": "Country Leave Type Row", "summary": "Leave entitlement row used inside Country Config records per leave type.", "target_type": "DocType", "target": "Country Leave Type Row", "allow_entry": False, "route_target_type": "DocType", "route_target": "Country Config", "action_label": "Open Parent Records"},
	{"id": "statutory-hr-record-row", "category": "components", "title": "Statutory HR Records Row", "summary": "Record detail row used inside Statutory HR Records Register.", "target_type": "DocType", "target": "Statutory HR Records Register", "allow_entry": False, "route_target_type": "DocType", "route_target": "Statutory HR Records Register", "action_label": "Open Parent Records"},

	# ── Reports and Analytics ────────────────────────────────────────────────
	{"id": "labor-coverage-matrix", "category": "reports", "title": "Labor Coverage Matrix", "summary": "Report coverage of labor law requirements across HR controls for each country.", "target_type": "Report", "target": "Labor Coverage Matrix"},
	{"id": "policy-compliance-register", "category": "reports", "title": "Policy Compliance Register", "summary": "Review policy compliance status and gaps.", "target_type": "Report", "target": "Policy Compliance Register"},
	{"id": "compliance-case-tracker", "category": "reports", "title": "Compliance Case Tracker", "summary": "Track compliance cases across ownership and status.", "target_type": "Report", "target": "Compliance Case Tracker"},
	{"id": "labor-inspection-tracker", "category": "reports", "title": "Labor Inspection Tracker", "summary": "Monitor inspection findings and corrective actions.", "target_type": "Report", "target": "Labor Inspection Tracker"},
	{"id": "gosi-monthly-report", "category": "reports", "title": "GOSI Monthly Report", "summary": "Monthly report for GOSI contribution review.", "target_type": "Report", "target": "GOSI Monthly Report"},
	{"id": "eosb-calculation-report", "category": "reports", "title": "EOSB Calculation Report", "summary": "Review EOSB calculations and settlement values.", "target_type": "Report", "target": "EOSB Calculation Report"},
	{"id": "contract-expiry-report", "category": "reports", "title": "Contract Expiry Report", "summary": "Monitor contract expiry dates and renewal pipeline.", "target_type": "Report", "target": "Contract Expiry Report"},
	{"id": "work-permit-expiry-report", "category": "reports", "title": "Work Permit Expiry Report", "summary": "Monitor work permit and residency expiry risks.", "target_type": "Report", "target": "Work Permit Expiry Report"},
	{"id": "nitaqat-compliance-report", "category": "reports", "title": "Nitaqat Compliance Report", "summary": "Review Nitaqat compliance and Saudization band position.", "target_type": "Report", "target": "Nitaqat Compliance Report"},
	{"id": "leave-balance-report", "category": "reports", "title": "Leave Balance Report", "summary": "Review leave balances and accrued liabilities across all countries.", "target_type": "Report", "target": "Leave Balance Report"},
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
