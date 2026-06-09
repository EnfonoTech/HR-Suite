import frappe


def execute():
	frappe.reload_doc("hr_suite", "workflow", "annual_leave_approval_workflow")
