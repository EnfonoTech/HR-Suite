"""Tick "Forfeited On Disciplinary Dismissal" on the Saudi Country Config, once.

Saudi Arabia pays no end-of-service award on a disciplinary dismissal (Labour Law Art. 80),
and the old hardcoded formula returned 0 for it. That rule now lives on Country Config as a
tick-box, which arrives unticked everywhere — so without this patch a site that upgrades
would start paying a full award to dismissed Saudi employees.

A one-shot patch, not a top-up: an administrator who deliberately unticks it must find it
still unticked next month.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Country Config"):
		return
	if "gratuity_forfeited_on_dismissal" not in set(frappe.db.get_table_columns("Country Config")):
		return
	name = frappe.db.get_value("Country Config", {"country_code": "SA"}, "name")
	if name:
		frappe.db.set_value("Country Config", name, "gratuity_forfeited_on_dismissal", 1, update_modified=False)
