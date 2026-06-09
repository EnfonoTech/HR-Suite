import frappe
from frappe import _
from frappe.utils import getdate, today


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters), None, get_chart(filters), get_report_summary(filters)


def get_columns():
	return [
		{"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 90},
		{"fieldname": "obligation_area", "label": _("Area"), "fieldtype": "Data", "width": 180},
		{"fieldname": "legal_reference", "label": _("Legal Reference"), "fieldtype": "Data", "width": 170},
		{"fieldname": "requirement", "label": _("Requirement"), "fieldtype": "Small Text", "width": 260},
		{"fieldname": "component", "label": _("Component"), "fieldtype": "Data", "width": 220},
		{"fieldname": "component_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
		{"fieldname": "risk", "label": _("Risk"), "fieldtype": "Data", "width": 120},
		{"fieldname": "next_action", "label": _("Next Action"), "fieldtype": "Small Text", "width": 320},
	]


def get_data(filters):
	rows = []
	for item in get_backlog_items():
		status = get_component_status(item)
		row = {
			"priority": item["priority"],
			"obligation_area": item["obligation_area"],
			"legal_reference": item["legal_reference"],
			"requirement": item["requirement"],
			"component": item["component"],
			"component_type": item["component_type"],
			"status": status,
			"risk": item["risk"],
			"next_action": item["next_action"],
		}
		if filters.get("priority") and row["priority"] != filters["priority"]:
			continue
		if filters.get("status") and row["status"] != filters["status"]:
			continue
		rows.append(row)
	return rows


def get_component_status(item):
	checks = item.get("checks") or []
	if not checks:
		return _("Needs Legal Scope")
	if all(run_check(check) for check in checks):
		return _("Implemented")
	if any(run_check(check) for check in checks):
		return _("Partially Implemented")
	return _("Gap")


def run_check(check):
	if check["kind"] == "doctype":
		return bool(frappe.db.exists("DocType", check["name"]))
	if check["kind"] == "report":
		return bool(frappe.db.exists("Report", check["name"]))
	if check["kind"] == "workflow":
		return bool(frappe.db.exists("Workflow", check["name"]))
	if check["kind"] == "scheduler":
		from hr_suite import hooks as app_hooks

		return any(
			isinstance(methods, list) and check["name"] in methods
			for methods in app_hooks.scheduler_events.values()
		)
	return False


def get_backlog_items():
	return [
		{
			"priority": "P0",
			"obligation_area": _("Work Regulations"),
			"legal_reference": _("Labor Law Art.12-13; Executive Reg. Art.3-4; Annex 1"),
			"requirement": _("Approved work regulation, publication evidence, and employee acknowledgement."),
			"component": "Work Regulation",
			"component_type": "DocType",
			"risk": _("Critical"),
			"next_action": _("Register the approved regulation and attach ministry/legal approval evidence."),
			"checks": [{"kind": "doctype", "name": "Work Regulation"}],
		},
		{
			"priority": "P0",
			"obligation_area": _("Statutory Records"),
			"legal_reference": _("Labor Law Art.17; Executive Reg. Art.5"),
			"requirement": _("Worker names, wages, fines, attendance, Saudi training, medical examination, and employee files."),
			"component": "Statutory HR Records Register",
			"component_type": "DocType",
			"risk": _("Critical"),
			"next_action": _("Create one register per audit period and close missing record actions."),
			"checks": [{"kind": "doctype", "name": "Statutory HR Records Register"}],
		},
		{
			"priority": "P0",
			"obligation_area": _("Ministry Filings"),
			"legal_reference": _("Executive Reg. Art.4 repeated and hiring disclosure controls"),
			"requirement": _("Track 10-day establishment data updates, vacancy filings, candidate responses, and annual disclosures."),
			"component": "Ministry Filing Tracker",
			"component_type": "DocType + Scheduler",
			"risk": _("High"),
			"next_action": _("Create filings with due dates and platform references."),
			"checks": [
				{"kind": "doctype", "name": "Ministry Filing Tracker"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_ministry_filing_due_alerts"},
			],
		},
		{
			"priority": "P0",
			"obligation_area": _("Document Custody"),
			"legal_reference": _("Executive Reg. Art.6"),
			"requirement": _("Prevent or evidence return of original passport, iqama, and medical insurance documents."),
			"component": "Employee Document Custody Log",
			"component_type": "DocType + Scheduler",
			"risk": _("High"),
			"next_action": _("Record any temporary custody and return evidence."),
			"checks": [
				{"kind": "doctype", "name": "Employee Document Custody Log"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_employee_document_custody_alerts"},
			],
		},
		{
			"priority": "P0",
			"obligation_area": _("Disability Employment"),
			"legal_reference": _("Executive Reg. Art.9"),
			"requirement": _("Track required ratio, qualified employees, and reasonable accommodations."),
			"component": "Disability Employment Compliance",
			"component_type": "DocType",
			"risk": _("High"),
			"next_action": _("Maintain periodical records and accommodation evidence."),
			"checks": [{"kind": "doctype", "name": "Disability Employment Compliance"}],
		},
		{
			"priority": "P0",
			"obligation_area": _("End of Service"),
			"legal_reference": _("Labor Law Art.75-76, 84 and unified contract model"),
			"requirement": _("Termination approval workflow, final settlement deadline, document return, and EOSB wage-basis review."),
			"component": "Termination Approval Workflow + Final Settlement SLA",
			"component_type": "Workflow + DocType",
			"risk": _("Critical"),
			"next_action": _("Use the workflow, auto-create settlement SLA, and complete legal review for wage basis."),
			"checks": [
				{"kind": "workflow", "name": "Termination Approval Workflow"},
				{"kind": "doctype", "name": "Final Settlement SLA"},
			],
		},
		{
			"priority": "P1",
			"obligation_area": _("Work Arrangements"),
			"legal_reference": _("Executive Regulations and contract annexes"),
			"requirement": _("Flexible, part-time, remote, temporary, casual, and seasonal contract controls."),
			"component": "Work Arrangement Control",
			"component_type": "DocType",
			"risk": _("Medium"),
			"next_action": _("Create arrangement records and monitor temporary/casual 90-day conversion."),
			"checks": [{"kind": "doctype", "name": "Work Arrangement Control"}],
		},
		{
			"priority": "P1",
			"obligation_area": _("Working Time"),
			"legal_reference": _("Executive Regulations working-hours controls"),
			"requirement": _("Monitor daily and weekly working-hours ceilings and exceptions."),
			"component": "Working Time Compliance Check",
			"component_type": "DocType",
			"risk": _("High"),
			"next_action": _("Review exceptions and link them to overtime approvals."),
			"checks": [{"kind": "doctype", "name": "Working Time Compliance Check"}],
		},
		{
			"priority": "P1",
			"obligation_area": _("Inspection Fines"),
			"legal_reference": _("Executive Regulations penalty collection"),
			"requirement": _("Track penalty notification, payment due date, objection, and closure evidence."),
			"component": "Inspection Fine SLA",
			"component_type": "DocType + Scheduler",
			"risk": _("High"),
			"next_action": _("Create SLA records for inspection fines and attach payment/objection evidence."),
			"checks": [
				{"kind": "doctype", "name": "Inspection Fine SLA"},
				{"kind": "scheduler", "name": "hr_suite.hr_suite.tasks.send_inspection_fine_sla_alerts"},
			],
		},
		{
			"priority": "P2",
			"obligation_area": _("Preventive Safety"),
			"legal_reference": _("Executive Regulations occupational safety controls"),
			"requirement": _("Preventive safety inspections, risk controls, first-aid evidence, and remote-site controls."),
			"component": "Safety Inspection and Risk Control",
			"component_type": "DocType",
			"risk": _("Medium"),
			"next_action": _("Schedule preventive inspections and close open risk items."),
			"checks": [{"kind": "doctype", "name": "Safety Inspection and Risk Control"}],
		},
	]


def get_chart(filters):
	data = get_data(filters)
	counts = {}
	for row in data:
		counts[row["status"]] = counts.get(row["status"], 0) + 1
	return {
		"data": {
			"labels": list(counts),
			"datasets": [{"name": _("Obligations"), "values": list(counts.values())}],
		},
		"type": "bar",
	}


def get_report_summary(filters):
	data = get_data(filters)
	implemented = sum(1 for row in data if row["status"] == _("Implemented"))
	gaps = sum(1 for row in data if row["status"] == _("Gap"))
	partials = sum(1 for row in data if row["status"] == _("Partially Implemented"))
	return [
		{"label": _("Implemented"), "value": implemented, "indicator": "Green", "datatype": "Int"},
		{"label": _("Partial"), "value": partials, "indicator": "Orange", "datatype": "Int"},
		{"label": _("Gap"), "value": gaps, "indicator": "Red", "datatype": "Int"},
	]
