"""Country-awareness of the work-permit record (client ticket 3.1 — Bahrain LMRA).

The regression these guard against is a Saudi-shaped compliance record being the only
one HR Suite can produce: an Iqama number that is mandatory everywhere, an expiry window
taken from Saudi Arabia, and a recurring fee invented rather than configured.
"""

import frappe
from frappe.utils import add_days, today

from hr_suite.hr_suite.report.lmra_work_permit_register.lmra_work_permit_register import (
	execute as run_lmra_register,
)
from hr_suite.hr_suite.utils import (
	get_employee_work_country_map,
	get_employees_is_national_map,
	get_permit_labels,
	get_recurring_permit_fee_config,
)
from frappe.tests.utils import FrappeTestCase


class TestWorkPermitCountry(FrappeTestCase):

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {"country": "Bahrain"}, "name")
		cls.employee = frappe.db.get_value(
			"Employee", {"company": cls.company, "status": "Active"}, "name"
		)

	# ─── Labels come from Country Config, never from code ─────────────────────

	def test_bahrain_labels_come_from_country_config(self):
		if not frappe.db.exists("Country Config", {"country_code": "BH"}):
			self.skipTest("No Country Config for BH on this site")

		labels = get_permit_labels("BH")
		config = frappe.db.get_value(
			"Country Config", {"country_code": "BH"},
			["primary_permit_label", "national_id_label", "permit_expiry_alert_days"],
			as_dict=True,
		)
		self.assertEqual(labels["permit_label"], config.primary_permit_label)
		self.assertEqual(labels["national_id_label"], config.national_id_label)
		self.assertEqual(labels["alert_days"], config.permit_expiry_alert_days)
		self.assertNotIn("Iqama", labels["permit_label"])

	def test_unknown_country_falls_back_without_inventing_a_country(self):
		labels = get_permit_labels("ZZ")
		self.assertFalse(labels["configured"])
		self.assertEqual(labels["permit_label"], "Work Permit")

	# ─── The statutory rule: an unconfigured fee is never a number ────────────

	def test_recurring_fee_is_unset_until_the_client_configures_it(self):
		"""A fee rate that nobody confirmed must never reach a liability figure."""
		fee = get_recurring_permit_fee_config("BH")
		configured_rate = frappe.db.get_value(
			"Country Config", {"country_code": "BH"}, "monthly_permit_fee_per_worker"
		)
		if not configured_rate:
			self.assertFalse(fee["is_configured"])
			self.assertEqual(fee["monthly_fee"], 0.0)

	# ─── A Bahrain permit record must be creatable ────────────────────────────

	def test_bahrain_permit_saves_without_an_iqama_number(self):
		if not self.employee:
			self.skipTest("No active employee on a Bahrain company")

		doc = frappe.get_doc({
			"doctype": "Work Permit Iqama",
			"naming_series": "WP-.YYYY.-.####",
			"employee": self.employee,
			"company": self.company,
			"work_country": "BH",
			"work_permit_number": "LMRA-TEST-0001",
			"work_permit_expiry_date": add_days(today(), 30),
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Work Permit Iqama", doc.name, force=True)

		self.assertFalse(doc.iqama_number)
		self.assertEqual(doc.work_permit_status, "Expiring Soon")
		self.assertEqual(doc.days_to_permit_expiry, 30)

	def test_saudi_permit_still_requires_the_iqama_number(self):
		if not self.employee:
			self.skipTest("No active employee on a Bahrain company")

		doc = frappe.get_doc({
			"doctype": "Work Permit Iqama",
			"naming_series": "WP-.YYYY.-.####",
			"employee": self.employee,
			"company": self.company,
			"work_country": "SA",
			"work_permit_number": "SA-TEST-0001",
			"work_permit_expiry_date": add_days(today(), 30),
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_work_country_defaults_from_the_employee(self):
		if not self.employee:
			self.skipTest("No active employee on a Bahrain company")

		doc = frappe.get_doc({
			"doctype": "Work Permit Iqama",
			"naming_series": "WP-.YYYY.-.####",
			"employee": self.employee,
			"company": self.company,
			"work_permit_number": "LMRA-TEST-0002",
			"work_permit_expiry_date": add_days(today(), 400),
		}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Work Permit Iqama", doc.name, force=True)

		self.assertEqual(doc.work_country, "BH")
		# 400 days out is beyond Bahrain's 60-day window, so it must not read as expiring.
		self.assertEqual(doc.work_permit_status, "Active")

	# ─── Batch resolvers must agree with the single-employee ones ─────────────

	def test_batch_work_country_matches_the_single_employee_resolver(self):
		from hr_suite.hr_suite.utils import get_employee_work_country

		names = [
			r.name for r in frappe.get_all("Employee", fields=["name"], limit_page_length=8)
		]
		if not names:
			self.skipTest("No employees on this site")

		batched = get_employee_work_country_map(names)
		for name in names:
			self.assertEqual(batched.get(name), get_employee_work_country(name), msg=name)

	def test_batch_national_map_matches_the_single_employee_resolver(self):
		from hr_suite.hr_suite.utils import get_employee_is_national

		names = [
			r.name for r in frappe.get_all("Employee", fields=["name"], limit_page_length=8)
		]
		if not names:
			self.skipTest("No employees on this site")

		batched = get_employees_is_national_map(names, "BH")
		for name in names:
			self.assertEqual(
				bool(batched.get(name)), get_employee_is_national(name, "BH"), msg=name
			)

	# ─── The register ─────────────────────────────────────────────────────────

	def test_register_lists_employees_with_no_permit_on_file(self):
		columns, rows, message, chart, summary = run_lmra_register(
			{"company": self.company, "work_country": "BH", "employee_status": "Active"}
		)

		self.assertTrue(columns)
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("monthly_permit_fee", fieldnames)
		self.assertIn("currency", fieldnames)

		# BHD is 3-decimal: the Currency column must resolve its currency per row.
		fee_col = next(c for c in columns if c["fieldname"] == "monthly_permit_fee")
		self.assertEqual(fee_col["options"], "currency")

		# Every active Bahrain employee appears, permit record or not — that is the
		# compliance question LMRA asks.
		active = frappe.db.count(
			"Employee", {"company": self.company, "status": "Active"}
		)
		self.assertLessEqual(len(rows), active)
		if rows:
			self.assertTrue(all(r["currency"] for r in rows))

		labels = {s["label"] for s in summary}
		self.assertIn("No permit on file", labels)

	def test_register_reports_an_unconfigured_fee_rather_than_a_number(self):
		configured_rate = frappe.db.get_value(
			"Country Config", {"country_code": "BH"}, "monthly_permit_fee_per_worker"
		)
		if configured_rate:
			self.skipTest("A fee rate has been configured on this site")

		_, rows, message, _chart, summary = run_lmra_register(
			{"company": self.company, "work_country": "BH", "employee_status": "Active"}
		)
		self.assertIn("NOT configured", message)
		self.assertTrue(all(r["monthly_permit_fee"] is None for r in rows))
		self.assertTrue(any(s["value"] == "Not configured" for s in summary))
