import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class PolicyAcknowledgement(Document):

	def validate(self):
		self._validate_dates()
		self._sync_from_policy()
		self._sync_status()
		self._prevent_duplicates()

	def _validate_dates(self):
		if self.due_date and self.assigned_on and getdate(self.due_date) < getdate(self.assigned_on):
			frappe.throw(_("Due Date cannot be before Assigned On"))

		if self.acknowledged_on and self.assigned_on and getdate(self.acknowledged_on) < getdate(self.assigned_on):
			frappe.throw(_("Acknowledged On cannot be before Assigned On"))

	def _sync_from_policy(self):
		if not self.policy_document:
			return

		policy = frappe.db.get_value(
			"HR Policy Document",
			self.policy_document,
			["policy_title", "policy_version", "article_reference", "legal_reference", "company"],
			as_dict=True,
		) or {}

		self.policy_title = self.policy_title or policy.get("policy_title")
		self.policy_version = self.policy_version or policy.get("policy_version")
		self.article_reference = self.article_reference or policy.get("article_reference")
		self.legal_reference = self.legal_reference or policy.get("legal_reference")
		self.company = self.company or policy.get("company")

	def _sync_status(self):
		if self.acknowledged_on:
			self.acknowledgement_status = "Acknowledged"
			if not self.acknowledgement_channel:
				self.acknowledgement_channel = "Manual"
		else:
			self.acknowledgement_status = self.acknowledgement_status or "Pending"

	def _prevent_duplicates(self):
		if not all((self.policy_document, self.policy_version, self.employee)):
			return

		existing = frappe.db.exists(
			"Policy Acknowledgement",
			{
				"policy_document": self.policy_document,
				"policy_version": self.policy_version,
				"employee": self.employee,
				"name": ["!=", self.name or ""],
			},
		)
		if existing:
			frappe.throw(_("A policy acknowledgement already exists for this employee and policy version"))


def update_policy_acknowledgement_summary(doc, method=None):
	if not getattr(doc, "policy_document", None):
		return

	rows = frappe.get_all(
		"Policy Acknowledgement",
		filters={"policy_document": doc.policy_document},
		fields=["acknowledgement_status"],
	)
	acknowledged = sum(1 for row in rows if row.acknowledgement_status == "Acknowledged")
	pending = sum(1 for row in rows if row.acknowledgement_status != "Acknowledged")

	frappe.db.set_value("HR Policy Document", doc.policy_document, "acknowledged_count", acknowledged, update_modified=False)
	frappe.db.set_value(
		"HR Policy Document",
		doc.policy_document,
		"pending_acknowledgement_count",
		pending,
		update_modified=False,
	)
	frappe.db.set_value(
		"HR Policy Document",
		doc.policy_document,
		"last_acknowledgement_sync_on",
		now_datetime(),
		update_modified=False,
	)