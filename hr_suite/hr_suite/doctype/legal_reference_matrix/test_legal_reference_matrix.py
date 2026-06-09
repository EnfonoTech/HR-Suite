import frappe
from frappe.tests.utils import FrappeTestCase


class TestLegalReferenceMatrix(FrappeTestCase):
	def test_get_task_blueprints_adds_evidence_and_policy_followups(self):
		doc = frappe.get_doc({
			"doctype": "Legal Reference Matrix",
			"reference_topic": "Disciplinary Control",
			"company": "amd",
			"article_number": "Art. 65",
			"linked_policy": "SAU-POL-2026-0001",
			"evidence_requirement": "Signed acknowledgement and committee report",
			"task_category": "Workflow",
			"lifecycle_stage": "Employee Relations & Legal",
			"risk_level": "High",
			"obligation_summary": "Document the disciplinary process.",
		})

		blueprints = doc._get_task_blueprints()

		self.assertEqual(len(blueprints), 3)
		self.assertEqual(blueprints[0]["task_title"], "Disciplinary Control")
		self.assertEqual(blueprints[1]["task_category"], "Document")
		self.assertEqual(blueprints[2]["task_category"], "Policy")