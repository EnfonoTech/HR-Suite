from urllib.parse import unquote

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.professional_hr_catalog import get_professional_hr_catalog, get_professional_hr_feature


class TestProfessionalHrCatalog(FrappeTestCase):
	def test_catalog_contains_full_feature_navigation(self):
		catalog = get_professional_hr_catalog()

		self.assertGreaterEqual(catalog["total_features"], 70)
		self.assertTrue(catalog["version"])
		self.assertGreaterEqual(len(catalog["categories"]), 10)
		self.assertTrue(all(feature.get("detail_route") for feature in catalog["features"]))
		self.assertTrue(all(feature.get("route") for feature in catalog["features"]))
		self.assertTrue(all("?feature=" not in feature.get("detail_route", "") for feature in catalog["features"]))

	def test_doctype_features_have_professional_entry_routes(self):
		catalog = get_professional_hr_catalog()
		doctype_features = [
			feature
			for feature in catalog["features"]
			if feature["target_type"] == "DocType" and feature.get("allow_entry") is not False
		]
		component_features = [feature for feature in catalog["features"] if feature.get("allow_entry") is False]
		report_features = [feature for feature in catalog["features"] if feature["target_type"] == "Report"]

		self.assertTrue(doctype_features)
		self.assertTrue(all(feature.get("entry_route") for feature in doctype_features))
		self.assertTrue(component_features)
		self.assertTrue(all(not feature.get("entry_route") for feature in component_features))
		self.assertTrue(all(feature.get("action_label") for feature in component_features))
		self.assertTrue(all(not feature.get("entry_route") for feature in report_features))
		settings = next(feature for feature in catalog["features"] if feature["id"] == "saudi-hr-settings")
		self.assertFalse(settings.get("entry_route"))
		self.assertEqual(settings.get("action_label"), "Open Settings")

	def test_component_features_route_to_parent_surfaces(self):
		catalog = get_professional_hr_catalog()
		features = {feature["id"]: feature for feature in catalog["features"]}

		self.assertEqual(features["labor-inspection-violation"]["route"], "/app/labor-inspection")
		self.assertEqual(features["employee-loan-installment"]["route"], "/app/employee-loan")
		self.assertEqual(features["saudi-monthly-payroll-employee"]["route"], "/app/saudi-monthly-payroll")
		self.assertEqual(features["branch-employee-directory-row"]["route"], "/app/employee-org-tree")

	def test_feature_detail_returns_related_features(self):
		result = get_professional_hr_feature("saudi-monthly-payroll")

		self.assertEqual(result["feature"]["title"], "Saudi Monthly Payroll")
		self.assertEqual(result["category"]["id"], "time")
		self.assertTrue(result["related"])
		self.assertGreaterEqual(result["catalog_summary"]["total_features"], 70)

	def test_every_feature_has_a_valid_target_and_staged_routes(self):
		catalog = get_professional_hr_catalog()
		category_ids = {category["id"] for category in catalog["categories"]}
		feature_ids = [feature["id"] for feature in catalog["features"]]

		self.assertEqual(len(feature_ids), len(set(feature_ids)))

		for feature in catalog["features"]:
			self.assertIn(feature["category"], category_ids)
			self.assertEqual(feature["detail_route"], f"/app/professional-hr-feature/{feature['id']}")

			if feature["target_type"] == "DocType" and feature.get("allow_entry") is not False:
				self.assertEqual(feature["entry_route"], f"/app/professional-hr-entry/{feature['id']}")
			else:
				self.assertNotIn("entry_route", feature)

			target_type = feature.get("route_target_type") or feature["target_type"]
			target = feature.get("route_target") or feature["target"]
			if target_type == "DocType":
				self.assertTrue(frappe.db.exists("DocType", target), feature["id"])
			elif target_type == "Page":
				self.assertTrue(frappe.db.exists("Page", target), feature["id"])
			elif target_type == "Report":
				self.assertTrue(frappe.db.exists("Report", target), feature["id"])
			else:
				self.assertTrue(feature["route"].startswith("/"), feature["id"])

			if feature["target_type"] == "URL" and feature["route"].startswith("/app/workflow/"):
				workflow_name = unquote(feature["route"].split("/app/workflow/", 1)[1])
				self.assertTrue(frappe.db.exists("Workflow", workflow_name), feature["id"])
