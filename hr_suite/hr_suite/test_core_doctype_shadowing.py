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

# No DocType may shadow another app's. Employee Onboarding and Employee Grievance were both
# removed in favour of the HRMS originals; keep this empty.
KNOWN_SHADOWED_DOCTYPES = set()


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

	def test_hrms_doctypes_kept_their_own_definitions(self):
		if "hrms" not in frappe.get_installed_apps():
			self.skipTest("hrms is not installed")

		expected = {
			"Employee Onboarding": (
				"boarding_status",
				"date_of_joining",
				"boarding_begins_on",
				"job_applicant",
			),
			"Employee Grievance": ("raised_by", "subject", "grievance_against", "status"),
		}
		for doctype, fieldnames in expected.items():
			self.assertEqual(frappe.db.get_value("DocType", doctype, "module"), "HR", doctype)
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				self.assertTrue(meta.has_field(fieldname), f"{doctype}.{fieldname}")

	def test_attendance_features_use_the_hrms_doctypes(self):
		"""HR Suite must not invent its own copies of DocTypes HRMS already ships."""
		if "hrms" not in frappe.get_installed_apps():
			self.skipTest("hrms is not installed")

		for doctype in ("Shift Type", "Shift Assignment", "Attendance", "Shift Location", "Employee Checkin"):
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

		for doctype in (
			"HR Shift Type",
			"HR Shift Assignment",
			"HR Daily Attendance",
			"HR Employee Checkin",
			"Attendance Location",
			"Monthly Attendance Record",
		):
			self.assertFalse(frappe.db.exists("DocType", doctype), f"{doctype} should not exist")

	def test_no_saudi_specific_doctypes_ship(self):
		"""HR Suite is multi-country — a DocType must not be named for one country."""
		shipped = {path.parent.name for path in DOCTYPE_ROOT.glob("*/*.json")}
		self.assertEqual({name for name in shipped if "saudi" in name}, set())
