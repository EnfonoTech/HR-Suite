"""Two seeded values that contradicted the policy spec, corrected once.

1. Resignation factors seeded as 33.33 and 66.67 lose a few halalas against the spec's exact
   one third and two thirds (3 years, 6,000 a month: 2,999.70 instead of 3,000.00). Only rows
   still holding the old seeded figures are touched.
2. Saudi Country Config carried the UAE figure (21) in the legacy "Days/Year (Below Threshold)"
   field. Nothing reads it any more, but it is what a tester sees on the form. Corrected to 15
   only where it still holds the wrong seed.

A one-shot patch: an administrator who later edits either value must find it unchanged.
"""

import frappe
from frappe.utils import flt


def execute():
	if not frappe.db.exists("DocType", "Country Resignation Factor"):
		return
	rows = frappe.get_all(
		"Country Resignation Factor",
		filters={"parenttype": "Country Config"},
		fields=["name", "payable_percent"],
	)
	for row in rows:
		for old, new in ((33.33, 33.333333), (66.67, 66.666667), (33.3333, 33.333333), (66.6667, 66.666667)):
			if abs(flt(row.payable_percent) - old) < 0.0001:
				frappe.db.set_value("Country Resignation Factor", row.name, "payable_percent", new, update_modified=False)

	if "days_per_year_below_threshold" in set(frappe.db.get_table_columns("Country Config")):
		name = frappe.db.get_value(
			"Country Config", {"country_code": "SA", "days_per_year_below_threshold": 21}, "name"
		)
		if name:
			frappe.db.set_value("Country Config", name, "days_per_year_below_threshold", 15, update_modified=False)
	frappe.clear_cache()
