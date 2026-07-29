import frappe
from frappe.tests.utils import FrappeTestCase


class TestCandidateProfile(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.company = frappe.get_all("Company", pluck="name", limit_page_length=1)[0]

	def tearDown(self):
		frappe.db.rollback()
		super().tearDown()

	def _accept_candidate(self, label):
		suffix = frappe.generate_hash(length=8).lower()
		return frappe.get_doc({
			"doctype": "Candidate Profile",
			"candidate_name": f"HR Suite {label} {suffix}",
			"first_name": "HR Suite",
			"last_name": f"{label} {suffix}",
			"email_address": f"hr.suite.{label.lower()}.{suffix}@example.com",
			"mobile_number": "0500000000",
			"expected_joining_date": frappe.utils.nowdate(),
			"status": "Accepted",
		}).insert(ignore_permissions=True)

	def test_accepted_candidate_creates_employee_and_hrms_onboarding(self):
		candidate = self._accept_candidate("Alpha")
		candidate.reload()

		self.assertTrue(candidate.linked_employee)
		self.assertEqual(candidate.status, "Onboarded")

		if "hrms" not in frappe.get_installed_apps():
			self.skipTest("hrms is not installed")

		onboarding = frappe.db.get_value(
			"Employee Onboarding",
			{"custom_candidate_profile": candidate.name},
			["name", "job_applicant", "boarding_status", "employee"],
			as_dict=True,
		)
		self.assertIsNotNone(onboarding)
		# HRMS rejects an onboarding without a Job Applicant on the second candidate and
		# builds the boarding project name from it, so it must always be set.
		self.assertTrue(onboarding.job_applicant)
		self.assertEqual(onboarding.boarding_status, "Pending")
		self.assertEqual(onboarding.employee, candidate.linked_employee)

	def test_second_accepted_candidate_gets_its_own_onboarding(self):
		if "hrms" not in frappe.get_installed_apps():
			self.skipTest("hrms is not installed")

		first = self._accept_candidate("Beta")
		second = self._accept_candidate("Gamma")

		onboardings = frappe.get_all(
			"Employee Onboarding",
			filters={"custom_candidate_profile": ("in", [first.name, second.name])},
			pluck="job_applicant",
		)
		self.assertEqual(len(onboardings), 2)
		self.assertEqual(len(set(onboardings)), 2)
