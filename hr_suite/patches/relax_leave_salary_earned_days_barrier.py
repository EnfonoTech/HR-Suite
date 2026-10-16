"""Drop the seeded 30-day earned-balance barrier on leave salary, once.

The policy spec pays leave salary once the minimum service is met (12 months by default) for
every day accrued since joining. The first build also demanded 30 earned days, which a 21-day
employee (1.75 a month) reaches only after about 17 months, so someone with 12 months'
service was still refused. Only a Country Config still holding the seeded 30 is changed;
the field stays for a client that wants the second barrier.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Country Config"):
		return
	if "leave_salary_min_earned_days" not in set(frappe.db.get_table_columns("Country Config")):
		return
	for name in frappe.get_all("Country Config", filters={"leave_salary_min_earned_days": 30}, pluck="name"):
		frappe.db.set_value("Country Config", name, "leave_salary_min_earned_days", 0, update_modified=False)
	frappe.clear_cache()
