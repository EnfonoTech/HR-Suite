"""Fold `Saudi Employment Contract` into the global `Country Employment Contract`.

HR Suite shipped both DocTypes: the Saudi one plus the country-neutral successor that
`install.rename_saudi_doctypes` was meant to rename it into. Because both shipped, the
rename never fired and the two lived side by side, with code referencing each. Only the
country-neutral DocType ships now, so existing rows are copied across (same document name
where it is free, so the patch is safe to re-run) and the Saudi DocType is removed.

Records are copied at DB level: re-submitting them would re-fire on_submit and rewrite
Employee records that are already correct.
"""

import frappe

OLD = "Saudi Employment Contract"
NEW = "Country Employment Contract"

# old fieldname -> new fieldname
FIELD_MAP = {
	"employee": "employee",
	"employee_name": "employee_name",
	"company": "company",
	"department": "department",
	"designation": "designation",
	"contract_status": "contract_status",
	"start_date": "start_date",
	"end_date": "end_date",
	"probation_period_days": "probation_period_days",
	"probation_end_date": "probation_end_date",
	"probation_extended": "probation_extended",
	"extended_probation_days": "extended_probation_days",
	"basic_salary": "basic_salary",
	"housing_allowance": "housing_allowance",
	"transport_allowance": "transport_allowance",
	"other_allowances": "other_allowances",
	"total_salary": "total_salary",
	"working_hours_per_day": "working_hours_per_day",
	"ramadan_hours_per_day": "ramadan_hours_per_day",
	"weekly_rest_day": "weekly_rest_day",
	"outdoor_work_prohibition": "outdoor_work_restriction",
	"nationality": "nationality",
	"iqama_number": "permit_number",
	"passport_number": "passport_number",
	"visa_type": "visa_type",
	"terms_and_conditions": "terms_and_conditions",
}

CONTRACT_TYPE_MAP = {"Fixed Term": "Limited", "Open Ended": "Unlimited"}
WEEKLY_REST_DAYS = {"Friday", "Saturday", "Sunday", "Friday-Saturday"}


def execute():
	if not frappe.db.table_exists(OLD):
		return

	old_meta_fields = set(frappe.db.get_table_columns(OLD))
	readable = [fieldname for fieldname in FIELD_MAP if fieldname in old_meta_fields]

	rows = frappe.get_all(
		OLD,
		fields=["name", "contract_type", "docstatus", "owner", "creation", *readable],
		limit_page_length=0,
	)

	migrated = 0
	for row in rows:
		if frappe.db.exists(NEW, row.name):
			continue

		values = {FIELD_MAP[fieldname]: row.get(fieldname) for fieldname in readable}
		values["contract_type"] = CONTRACT_TYPE_MAP.get(row.contract_type, "Unlimited")
		if row.get("iqama_number"):
			values["permit_type"] = "Iqama"
		if values.get("weekly_rest_day") not in WEEKLY_REST_DAYS:
			values["weekly_rest_day"] = None
		# work_country is mandatory on the global DocType; every legacy row is Saudi.
		values["work_country"] = "SA"

		doc = frappe.get_doc({"doctype": NEW, **values})
		doc.name = row.name
		doc.flags.name_set = True
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

		if row.docstatus:
			frappe.db.set_value(NEW, doc.name, "docstatus", row.docstatus, update_modified=False)
		frappe.db.set_value(NEW, doc.name, "owner", row.owner, update_modified=False)
		migrated += 1

	pending = [row.name for row in rows if not frappe.db.exists(NEW, row.name)]
	if pending:
		frappe.log_error(
			f"{len(pending)} {OLD} record(s) could not be copied to {NEW}: {pending[:20]}. "
			f"The {OLD} DocType was left in place — migrate them before removing it.",
			"HR Suite: Saudi Employment Contract migration incomplete",
		)
		return

	frappe.db.commit()
	if frappe.db.exists("DocType", OLD):
		frappe.delete_doc("DocType", OLD, ignore_permissions=True, force=True)
	frappe.clear_cache()
	if migrated:
		print(f"HR Suite: migrated {migrated} contract(s) from {OLD} to {NEW}")
