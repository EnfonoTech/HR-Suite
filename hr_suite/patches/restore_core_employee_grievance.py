"""Restore the HRMS `Employee Grievance` DocType and remap HR Suite's data onto it.

HR Suite shipped its own DocType of the same name, so every migrate overwrote the HRMS
definition and stripped its fields (`raised_by`, `subject`, `grievance_against`, …) — the
same defect that hit Employee Onboarding. HR Suite no longer ships it.

Because the name was shared, both definitions wrote to one table: the HR Suite columns still
sit next to the HRMS ones. So this reloads the HRMS definition, recreates HR Suite's
grievance-handling fields as Custom Fields, then copies the legacy values across row by row.
Legacy columns are left untouched — Frappe never drops columns, and keeping them makes a
re-run a no-op instead of a data loss.
"""

import frappe

DOCTYPE = "Employee Grievance"
STATUS_MAP = {"In Review": "Investigated", "Closed": "Resolved"}

# legacy fieldname -> HRMS / Custom Field fieldname
FIELD_MAP = {
	"employee": "raised_by",
	"grievance_date": "date",
	"grievance_summary": "description",
	"resolution_summary": "resolution_detail",
	"grievance_channel": "hrsuite_grievance_channel",
	"severity": "hrsuite_severity",
	"assigned_to": "hrsuite_assigned_to",
	"response_due_date": "hrsuite_response_due_date",
	"first_response_date": "hrsuite_first_response_date",
	"employee_requested_remedy": "hrsuite_requested_remedy",
	"investigation_notes": "hrsuite_investigation_notes",
}


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	if "hrms" not in frappe.get_installed_apps():
		frappe.log_error(
			f"HR Suite no longer ships {DOCTYPE} and hrms is not installed — install hrms to get "
			"the core definition back.",
			f"HR Suite: {DOCTYPE} not restored",
		)
		return

	from hr_suite.hr_suite.compliance_controls import sync_custom_fields
	from hr_suite.install import seed_grievance_types

	frappe.reload_doc("hr", "doctype", "grievance_type", force=True)
	frappe.reload_doc("hr", "doctype", DOCTYPE, force=True)
	frappe.clear_cache(doctype=DOCTYPE)

	seed_grievance_types()
	# Custom Fields are synced by after_migrate, which runs after patches — do it here so the
	# columns exist before the copy below.
	sync_custom_fields()

	columns = set(frappe.db.get_table_columns(DOCTYPE))
	copyable = {old: new for old, new in FIELD_MAP.items() if old in columns and new in columns}

	# The legacy columns are no longer part of the DocType, so the report/query layer would
	# reject them ("Field not permitted in query"). Query Builder reads the table directly.
	table = frappe.qb.DocType(DOCTYPE)
	fields = ["name", *sorted(set(columns) & _needed(copyable))]
	for row in (
		frappe.qb.from_(table).select(*[table[fieldname] for fieldname in fields]).run(as_dict=True)
	):
		updates = {}
		for old, new in copyable.items():
			if row.get(old) and not row.get(new):
				updates[new] = row.get(old)

		if "status" in columns and row.get("status") in STATUS_MAP:
			updates["status"] = STATUS_MAP[row["status"]]

		# subject and the grievance_against pair are mandatory on the HRMS DocType; legacy rows
		# have neither, so derive them instead of leaving rows that can never be saved again.
		if "subject" in columns and not row.get("subject"):
			updates["subject"] = f"Grievance — {row.get('employee_name') or row['name']}"
		needs_party = "grievance_against_party" in columns and not row.get("grievance_against_party")
		if needs_party and row.get("company"):
			updates["grievance_against_party"] = "Company"
			updates["grievance_against"] = row["company"]

		if updates:
			frappe.db.set_value(DOCTYPE, row["name"], updates, update_modified=False)

	frappe.db.commit()


def _needed(copyable):
	fields = set(copyable) | set(copyable.values())
	fields |= {"status", "subject", "employee_name", "company"}
	fields |= {"grievance_against_party", "grievance_against"}
	return fields
