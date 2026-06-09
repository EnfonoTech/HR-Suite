import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class SaudiRegulatoryTask(Document):

	def validate(self):
		self._validate_dates()
		self._sync_from_reference()
		self._sync_status()

	def _validate_dates(self):
		if self.due_date and self.task_date and getdate(self.due_date) < getdate(self.task_date):
			frappe.throw(_("Due Date cannot be before Task Date"))

		if self.completed_on and self.task_date and getdate(self.completed_on) < getdate(self.task_date):
			frappe.throw(_("Completed On cannot be before Task Date"))

	def _sync_from_reference(self):
		if not self.legal_reference_matrix:
			return

		reference = frappe.db.get_value(
			"Legal Reference Matrix",
			self.legal_reference_matrix,
			["article_number", "obligation_summary", "linked_policy", "reference_topic", "risk_level"],
			as_dict=True,
		) or {}

		self.article_reference = self.article_reference or reference.get("article_number")
		self.obligation_summary = self.obligation_summary or reference.get("obligation_summary")
		self.policy_document = self.policy_document or reference.get("linked_policy")
		self.task_title = self.task_title or reference.get("reference_topic")
		self.priority = self.priority or _map_risk_to_priority(reference.get("risk_level"))

	def _sync_status(self):
		if self.completed_on:
			self.status = "Completed"
			self.progress_percentage = 100
		elif self.progress_percentage and self.progress_percentage > 0 and self.status == "Open":
			self.status = "In Progress"


def _map_risk_to_priority(risk_level):
	mapping = {
		"Critical": "Urgent",
		"High": "High",
		"Medium": "Medium",
		"Low": "Low",
	}
	return mapping.get(risk_level or "", "Medium")