"""Guard against HR Suite shipping a DocType that shadows another app's.

Frappe keys DocTypes by name, so two apps shipping `employee_onboarding/employee_onboarding.json`
means whichever syncs last wins and the other app's fields silently disappear from the meta —
queries for them then fail with "Field not permitted in query: <fieldname>".
"""

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

APP_ROOT = Path(__file__).resolve().parents[2]
DOCTYPE_ROOT = APP_ROOT / "hr_suite" / "hr_suite" / "doctype"

# `Employee Grievance` still shadows the HRMS DocType of the same name. It is wired into
# HR Suite's own workflow, number cards, dashboard chart and Compliance Case Tracker report,
# so renaming it needs its own patch — tracked separately.
KNOWN_SHADOWED_DOCTYPES = {"employee_grievance"}


class TestCoreDocTypeShadowing(FrappeTestCase):
	def test_shipped_doctypes_do_not_shadow_other_apps(self):
		shipped = {path.parent.name for path in DOCTYPE_ROOT.glob("*/*.json")}
		shadowed = set()

		for app in frappe.get_installed_apps():
			if app == "hr_suite":
				continue
			app_path = Path(frappe.get_app_path(app))
			for name in shipped:
				if list(app_path.glob(f"*/doctype/{name}/{name}.json")):
					shadowed.add(name)

		self.assertEqual(shadowed - KNOWN_SHADOWED_DOCTYPES, set())

	def test_employee_onboarding_is_the_hrms_doctype(self):
		if "hrms" not in frappe.get_installed_apps():
			self.skipTest("hrms is not installed")

		self.assertEqual(frappe.db.get_value("DocType", "Employee Onboarding", "module"), "HR")

		meta = frappe.get_meta("Employee Onboarding")
		for fieldname in ("boarding_status", "date_of_joining", "boarding_begins_on", "job_applicant"):
			self.assertTrue(meta.has_field(fieldname), fieldname)
