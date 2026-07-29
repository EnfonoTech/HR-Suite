"""Restore the HRMS `Employee Onboarding` DocType.

HR Suite used to ship its own DocType named `Employee Onboarding` (module "Hr Suite",
checklist based). Frappe keys DocTypes by name, so on every migrate that JSON
overwrote the HRMS definition and stripped its fields — `boarding_status`,
`date_of_joining`, `boarding_begins_on`, `activities`. Any query for those fields
then failed with "Field not permitted in query: boarding_status", and HRMS's own
onboarding flow (Job Applicant -> Job Offer -> Onboarding -> Employee) was dead.

The shipped DocType is removed from the app; this patch reloads the HRMS definition
so existing sites get the core fields back. Columns the old definition created
(`joining_date`, `completion_percentage`, the checklist checks) are left in the table
— they are no longer in the meta and are harmless, and dropping them would destroy
data on any site that did use them.
"""

import frappe

DOCTYPE = "Employee Onboarding"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	if frappe.db.get_value("DocType", DOCTYPE, "module") == "HR":
		# Already the HRMS definition — nothing to restore.
		return

	if "hrms" not in frappe.get_installed_apps():
		frappe.log_error(
			f"{DOCTYPE} is owned by module "
			f"{frappe.db.get_value('DocType', DOCTYPE, 'module')} and hrms is not installed — "
			"HR Suite no longer ships this DocType, install hrms to get the core definition.",
			"HR Suite: Employee Onboarding not restored",
		)
		return

	rows = frappe.db.count(DOCTYPE)
	if rows:
		frappe.log_error(
			f"{rows} existing {DOCTYPE} record(s) were created against HR Suite's old "
			"checklist definition. They are retained, but their checklist fields are no "
			"longer part of the DocType — review them against the HRMS fields.",
			"HR Suite: Employee Onboarding records predate the HRMS definition",
		)

	frappe.reload_doc("hr", "doctype", "employee_onboarding", force=True)
	frappe.clear_cache(doctype=DOCTYPE)
