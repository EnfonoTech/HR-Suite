"""Rename fields that named a single country on otherwise country-neutral DocTypes.

HR Suite is multi-country (Country Config drives SA / AE / BH / IN / OM), so a generic
compliance DocType must not carry a Saudi-only fieldname. `rename_field` moves the column
and its data; without it the renamed definition would create a second, empty column.
"""

import frappe
from frappe.model.utils.rename_field import rename_field

RENAMES = [
	("Work Arrangement Control", "saudi_only_applicable", "country_rule_applicable"),
]


def execute():
	for doctype, old, new in RENAMES:
		if not frappe.db.table_exists(doctype):
			continue

		columns = frappe.db.get_table_columns(doctype)
		if old not in columns or new in columns:
			continue

		try:
			rename_field(doctype, old, new)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), f"HR Suite: rename {doctype}.{old} -> {new} failed"
			)

	rename_reports()
	frappe.db.commit()


REPORT_RENAMES = [
	("Saudi Compliance Obligation Backlog", "Compliance Obligation Backlog"),
	("Saudi Labor Coverage Matrix", "Labor Coverage Matrix"),
	("Saudi Leave Balance Report", "Leave Balance Report"),
	("Saudi Legal Review Queue", "Legal Review Queue"),
]


def rename_reports():
	"""These reports cover every configured country, so they no longer carry one country's name."""
	for old, new in REPORT_RENAMES:
		if not frappe.db.exists("Report", old) or frappe.db.exists("Report", new):
			continue
		try:
			frappe.rename_doc("Report", old, new, force=True, ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"HR Suite: rename Report {old} -> {new} failed")
