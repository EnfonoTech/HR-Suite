"""Give every existing Work Permit Iqama a work_country, and name Bahrain's fee authority.

`work_country` is new, so every record written before this patch holds NULL. The form now
uses it to decide which blocks are relevant, so a NULL would leave a Saudi record showing
its Iqama block only because of the "or the field already has a value" arms in the
depends_on expressions. Backfilling makes the classification explicit instead of implied.

Two things this patch deliberately does not do:
  * It does not touch a record whose work_country is already set — HR's own answer wins.
  * It writes only the LMRA *label* and the *note* onto Country Config BH. The monthly
    fee and its applicability are statutory figures nobody has confirmed, so they stay
    unset and the register reports "not configured" until the client enters them.
"""

import frappe

from hr_suite.hr_suite.utils import get_employee_work_country_map

_LMRA_NOTE = (
	"LMRA charges a recurring monthly fee per work-permit holder. Enter the rate "
	"currently in force and choose who it applies to before relying on the LMRA Work "
	"Permit Register liability figures. Confirm with the client: the monthly amount, "
	"whether it is charged for every permit holder or only expatriates, and any "
	"exemption or SME discount that applies to this establishment."
)


def execute():
	backfill_permit_work_country()
	extend_permit_naming_series()
	name_bahrain_fee_authority()
	frappe.db.commit()


def backfill_permit_work_country():
	if not frappe.db.table_exists("Work Permit Iqama"):
		return
	if "work_country" not in frappe.db.get_table_columns("Work Permit Iqama"):
		return

	rows = frappe.get_all(
		"Work Permit Iqama",
		filters={"work_country": ["in", ["", None]]},
		fields=["name", "employee"],
		limit_page_length=0,
	)
	if not rows:
		return

	resolved = get_employee_work_country_map([r.employee for r in rows if r.employee])

	for row in rows:
		country = resolved.get(row.employee)
		if not country:
			continue
		# Direct column write: these records are submitted, and work_country is a
		# classification the document's own validate() would set identically. Going
		# through save() would re-run status calculations and rewrite `modified` on
		# every historical record.
		frappe.db.set_value(
			"Work Permit Iqama", row.name, "work_country", country, update_modified=False
		)


def name_bahrain_fee_authority():
	if not frappe.db.exists("DocType", "Country Config"):
		return
	if "recurring_permit_fee_authority" not in frappe.db.get_table_columns("Country Config"):
		return

	name = frappe.db.get_value("Country Config", {"country_code": "BH"}, "name")
	if not name:
		return

	current = frappe.db.get_value(
		"Country Config", name,
		["recurring_permit_fee_authority", "recurring_permit_fee_notes"],
		as_dict=True,
	) or {}

	updates = {}
	if not (current.get("recurring_permit_fee_authority") or "").strip():
		updates["recurring_permit_fee_authority"] = "LMRA"
	if not (current.get("recurring_permit_fee_notes") or "").strip():
		updates["recurring_permit_fee_notes"] = _LMRA_NOTE

	if updates:
		frappe.db.set_value("Country Config", name, updates)


# The country-neutral naming series added to the DocType do not reach a site where
# someone has opened Document Naming Settings for this DocType: that page writes a
# `<DocType>-naming_series-options` Property Setter, and a Property Setter shadows the
# DocField for good. Append what is missing rather than replacing the value, so any
# series the client added by hand survives.
_PERMIT_SERIES = ("WP-.YYYY.-.####", "BH-WP-.YYYY.-.####")


def extend_permit_naming_series():
	name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Work Permit Iqama", "field_name": "naming_series", "property": "options"},
		"name",
	)
	if not name:
		return

	current = frappe.db.get_value("Property Setter", name, "value") or ""
	existing = [line.strip() for line in current.split("\n") if line.strip()]
	missing = [s for s in _PERMIT_SERIES if s not in existing]
	if not missing:
		return

	frappe.db.set_value("Property Setter", name, "value", "\n".join(missing + existing))
	frappe.clear_cache(doctype="Work Permit Iqama")
