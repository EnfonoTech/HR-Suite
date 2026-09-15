"""Give every existing Country Config its statutory overtime rates.

``seed_country_configs()`` deliberately skips a Country Config that already
exists, so that an administrator's edits survive a migrate. That is right, and
it also means the overtime fields added with this release land unset on every
site installed before them — and an unset rate falls back to the module default
of 1.5, which is wrong for Bahrain (1.25 by day), the UAE (1.25), Oman (2.0 on
a rest day) and India (2.0 flat, over a 26-day month).

**Why "unset" is not simply "falsy".** The first cut of these fields carried a
DocType `default` of 1.5 (and 240 hours). Adding a column with a DDL default
writes that default onto every existing row, so the rates arrived looking
deliberately set to 1.5 and a plain `if not value` test skipped all of them —
BH and IN silently kept the Saudi rate. Those defaults are gone from the DocType
now, but the sites that already migrated carry the value, so this patch treats
"equal to the old DDL default" as unset too. At the moment this patch first
runs, nobody can have chosen 1.5 on purpose: the field did not exist before it.

A field holding any other figure is an administrator's answer and is never
touched, and re-running the patch writes nothing new.
"""

import frappe
from frappe.utils import flt

# What the removed DocType defaults used to write. A value still equal to one of
# these was put there by the schema migration, not by a person.
LEGACY_DDL_DEFAULTS = {
	"overtime_hours_per_month": 240.0,
	"overtime_weekday_rate": 1.5,
	"overtime_rest_day_rate": 1.5,
	"overtime_holiday_rate": 1.5,
}

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


def _is_unset(field: str, value) -> bool:
	if value in (None, ""):
		return True
	if field in LEGACY_DDL_DEFAULTS:
		return not flt(value) or flt(value) == LEGACY_DDL_DEFAULTS[field]
	return False


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
		updates = {
			field: defaults[field]
			for field in fields
			if field in defaults and _is_unset(field, current.get(field))
		}

		if updates:
			frappe.db.set_value("Country Config", name, updates, update_modified=False)
			frappe.logger().info(
				f"HR Suite: seeded overtime terms on Country Config {code}: {sorted(updates)}"
			)
