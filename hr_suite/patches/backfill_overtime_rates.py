"""Give every existing Country Config its statutory overtime rates.

``seed_country_configs()`` deliberately skips a Country Config that already
exists, so that an administrator's edits survive a migrate. That is right, and
it also means the overtime fields added with this release land empty on every
site that was installed before them — and an empty rate silently falls back to
the module default of 1.5, which is wrong for Bahrain (1.25 by day), the UAE
(1.25), Oman (2.0 on a rest day) and India (2.0 flat).

So: fill only what is still empty. A field an administrator has already set to
a real figure is never touched, and re-running the patch writes nothing.
"""

import frappe
from frappe.utils import flt

OVERTIME_FIELDS = (
	"overtime_hours_per_month",
	"overtime_weekday_rate",
	"overtime_night_rate",
	"overtime_night_start",
	"overtime_night_end",
	"overtime_rest_day_rate",
	"overtime_holiday_rate",
	"overtime_notes",
)


def execute():
	if not frappe.db.exists("DocType", "Country Config"):
		return

	columns = set(frappe.db.get_table_columns("Country Config"))
	fields = [f for f in OVERTIME_FIELDS if f in columns]
	if not fields:
		return

	from hr_suite.install import _COUNTRY_CONFIGS

	for defaults in _COUNTRY_CONFIGS:
		code = defaults.get("country_code")
		name = frappe.db.get_value("Country Config", {"country_code": code}, "name")
		if not name:
			continue

		current = frappe.db.get_value("Country Config", name, fields, as_dict=True) or {}
		updates = {}
		for field in fields:
			if field not in defaults:
				continue
			value = current.get(field)
			# "Still empty" means blank for a time/text field and zero for a rate —
			# a rate of 0 cannot be a deliberate answer, it just means never set.
			if value in (None, "") or (isinstance(defaults[field], (int, float)) and not flt(value)):
				updates[field] = defaults[field]

		if updates:
			frappe.db.set_value("Country Config", name, updates, update_modified=False)
			frappe.logger().info(f"HR Suite: seeded overtime terms on Country Config {code}: {sorted(updates)}")
