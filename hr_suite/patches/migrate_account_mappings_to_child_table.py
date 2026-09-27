"""Move the three global leave-salary / settlement accounts into the per-company table.

Those were Link fields on Hr Suite Settings, which is a Single — so the whole site got
ONE leave salary expense account, ONE payable, ONE settlement advance. An Account belongs
to exactly one company, so on any site running a second company at most one of them could
ever be right, and the other company silently fell through to matching account NAMES in
its chart. UAT runs four companies.

The mapping now lives in the `hr_account_mappings` child table keyed by (company, purpose).

Which company does an old value belong to? Not a guess: read it off the account itself.
`Account.company` is exactly the answer, and an account that has since been deleted or
turned into a group is dropped rather than migrated into a row that could not post.

By the time this runs the three fields are gone from the DocType (patches in
[post_model_sync] run after the schema sync), so `frappe.db.get_single_value` would
throw "Field ... does not exist" — database.py:845. The values are still sitting in
`tabSingles`, which is what this reads, the same way frappe reads it internally.
"""

import frappe

FIELD_TO_PURPOSE = {
	"leave_salary_expense_account": ("Leave Salary Expense", "Expense"),
	"leave_salary_payable_account": ("Leave Salary Payable", "Liability"),
	"settlement_advance_account": ("Settlement Advance", "Asset"),
}


def execute():
	if not frappe.db.exists("DocType", "HR Suite Account Row"):
		return
	if not frappe.db.exists("DocType", "Hr Suite Settings"):
		return

	rows = frappe.qb.get_query(
		table="Singles",
		filters={"doctype": "Hr Suite Settings", "field": ["in", list(FIELD_TO_PURPOSE)]},
		fields=["field", "value"],
	).run(as_dict=True)

	legacy = {r["field"]: (r["value"] or "").strip() for r in rows if (r.get("value") or "").strip()}
	if not legacy:
		_drop_legacy_singles()
		return

	settings = frappe.get_doc("Hr Suite Settings")
	existing = {
		(r.company, r.purpose) for r in (settings.get("hr_account_mappings") or [])
	}

	added = []
	for field, account in legacy.items():
		purpose, root_type = FIELD_TO_PURPOSE[field]

		detail = frappe.db.get_value(
			"Account", account, ["company", "is_group", "root_type"], as_dict=True
		)
		if not detail or detail.is_group or detail.root_type != root_type:
			frappe.logger().info(
				f"HR Suite: dropping legacy {field}={account!r} — it is not a postable "
				f"{root_type} account any more, so it could not have posted."
			)
			continue

		if (detail.company, purpose) in existing:
			continue

		settings.append("hr_account_mappings", {
			"company": detail.company,
			"purpose": purpose,
			"account": account,
		})
		existing.add((detail.company, purpose))
		added.append(f"{detail.company}/{purpose}={account}")

	if added:
		# flags.ignore_permissions: migrate runs as Administrator with no session user.
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.logger().info(f"HR Suite: migrated account mappings -> {added}")

	_drop_legacy_singles()


def _drop_legacy_singles():
	"""Remove the orphaned tabSingles rows so a re-run cannot resurrect them.

	Frappe does not clean tabSingles when a field is removed from a Single's DocType,
	so without this the old values sit there forever, invisible and misleading to
	anyone reading the table directly.
	"""
	frappe.db.delete("Singles", {
		"doctype": "Hr Suite Settings",
		"field": ["in", list(FIELD_TO_PURPOSE)],
	})
	frappe.clear_cache(doctype="Hr Suite Settings")
