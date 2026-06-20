import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from hr_suite.hr_suite.utils import assert_doctype_permissions


class LegalReferenceMatrix(Document):

	def validate(self):
		self._set_defaults()
		if self.next_review_date and self.effective_from:
			if getdate(self.next_review_date) < getdate(self.effective_from):
				frappe.throw(_("Next Review Date cannot be before Effective From"))

		if self.status == "Retired" and not self.retirement_reason:
			frappe.throw(_("Retirement Reason is required when the reference is retired"))

		self._update_task_summary()

	def _set_defaults(self):
		if not self.lifecycle_stage:
			self.lifecycle_stage = "Strategy & Setup"
		if not self.task_category:
			self.task_category = "Policy" if self.required_control else "Workflow"

	def _update_task_summary(self):
		if not self.name or self.is_new():
			self.latest_regulatory_task = None
			self.open_regulatory_tasks = 0
			return

		rows = frappe.get_all(
			"Regulatory Task",
			filters={"legal_reference_matrix": self.name},
			fields=["name", "status", "modified"],
			order_by="modified desc",
		)
		self.latest_regulatory_task = rows[0].name if rows else None
		self.open_regulatory_tasks = sum(
			1
			for row in rows
			if row.status not in ("Completed", "Cancelled")
		)

	def create_regulatory_task(self):
		created_names = []
		latest_name = None
		for payload in self._get_task_blueprints():
			existing = frappe.db.get_value(
				"Regulatory Task",
				{
					"legal_reference_matrix": self.name,
					"task_title": payload["task_title"],
					"status": ["in", ["Open", "In Progress", "Blocked"]],
				},
				"name",
			)
			if existing:
				latest_name = existing
				continue

			task = frappe.get_doc(payload)
			assert_doctype_permissions("Regulatory Task", "create", doc=task)
			task.insert()
			latest_name = task.name
			created_names.append(task.name)

		if latest_name:
			self.db_set("latest_regulatory_task", latest_name, update_modified=False)
		self.db_set(
			"open_regulatory_tasks",
			frappe.db.count(
				"Regulatory Task",
				filters={
					"legal_reference_matrix": self.name,
					"status": ["not in", ["Completed", "Cancelled"]],
				},
			),
			update_modified=False,
		)
		return created_names or ([latest_name] if latest_name else []), bool(created_names)

	def _get_task_blueprints(self):
		base = {
			"doctype": "Regulatory Task",
			"company": self.company,
			"legal_reference_matrix": self.name,
			"article_reference": self.article_number,
			"policy_document": self.linked_policy,
			"lifecycle_stage": self.lifecycle_stage,
			"source_type": "Regulation Review",
			"source_reference": self.name,
			"priority": _map_risk_to_priority(self.risk_level),
			"assigned_to": self.control_owner,
		}
		blueprints = [
			{
				**base,
				"task_title": self.reference_topic,
				"task_category": self.task_category,
				"obligation_summary": self.obligation_summary,
			}
		]

		if self.evidence_requirement:
			blueprints.append(
				{
					**base,
					"task_title": _("Evidence Readiness: {0}").format(self.reference_topic),
					"task_category": "Document",
					"obligation_summary": self.evidence_requirement,
				}
			)

		if self.linked_policy:
			blueprints.append(
				{
					**base,
					"task_title": _("Policy Alignment: {0}").format(self.reference_topic),
					"task_category": "Policy",
					"obligation_summary": _("Review and align policy {0} with article {1}.").format(self.linked_policy, self.article_number),
				}
			)

		return blueprints


def _map_risk_to_priority(risk_level):
	mapping = {
		"Critical": "Urgent",
		"High": "High",
		"Medium": "Medium",
		"Low": "Low",
	}
	return mapping.get(risk_level or "", "Medium")


@frappe.whitelist()
def create_regulatory_task(reference_name: str):
	reference = frappe.get_doc("Legal Reference Matrix", reference_name)
	task_names, created = reference.create_regulatory_task()
	return {"task_name": task_names[0] if task_names else None, "task_names": task_names, "created": created}