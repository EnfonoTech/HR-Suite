"""Tick "May Be Paid In Advance" on the leave-type rows that accrue, once.

The field is new, so every existing Country Leave Type Row arrives at 0 — and 0 is the
answer that refuses a disbursement. Without this patch a site that has been paying leave
salary would find, after the upgrade, that no leave may be paid in advance at all.

Only rows that declare an accrual frequency are ticked: leave that is EARNED by serving
another month is the leave an employee can ask for early. Sick, maternity and Hajj leave
are paid by payroll for the month they fall in, and are deliberately left unticked — a
client who genuinely advances maternity pay ticks it themselves, and this patch never
runs again to untick it.

Deliberately a one-shot patch rather than a top-up on every migrate: an administrator who
unticks a box must find it still unticked next month.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Country Leave Type Row"):
		return

	columns = set(frappe.db.get_table_columns("Country Leave Type Row"))
	if not {"leave_salary_in_advance", "accrual_frequency"} <= columns:
		return

	rows = frappe.get_all(
		"Country Leave Type Row",
		filters={
			"parenttype": "Country Config",
			"leave_salary_in_advance": 0,
			"accrual_frequency": ["not in", ["", None, "None"]],
		},
		fields=["name", "parent", "leave_type_name"],
	)

	for row in rows:
		frappe.db.set_value(
			"Country Leave Type Row", row.name, "leave_salary_in_advance", 1, update_modified=False
		)

	if rows:
		frappe.logger().info(
			"HR Suite: leave salary may be paid in advance for {0} leave-type row(s): {1}".format(
				len(rows), ", ".join(sorted({r.leave_type_name for r in rows}))
			)
		)
