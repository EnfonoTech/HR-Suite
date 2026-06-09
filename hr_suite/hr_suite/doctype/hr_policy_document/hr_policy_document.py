import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, getdate, today

from hr_suite.hr_suite.utils import assert_doctype_permissions


class HRPolicyDocument(Document):

	def validate(self):
		self._validate_dates()
		self._validate_target_scope()
		self._sync_status()
		self._set_defaults()
		self._update_acknowledgement_summary()

	def _validate_dates(self):
		if self.review_date and self.effective_date:
			if getdate(self.review_date) < getdate(self.effective_date):
				frappe.throw(_("Review Date cannot be before Effective Date"))

	def _validate_target_scope(self):
		if self.target_scope == "Department Employees" and not self.target_department:
			frappe.throw(_("Target Department is required when the policy applies to a specific department"))

	def _sync_status(self):
		if self.status == "Archived":
			return

		if self.review_date and getdate(self.review_date) < getdate(today()):
			self.status = "Under Review"
		elif self.effective_date and getdate(self.effective_date) <= getdate(today()):
			self.status = "Active"
		else:
			self.status = self.status or "Draft"

	def _set_defaults(self):
		if not self.policy_version:
			self.policy_version = "1.0"
		if self.acknowledgement_due_days is None:
			self.acknowledgement_due_days = 7
		if not self.target_scope:
			self.target_scope = "Company Employees"

	def _update_acknowledgement_summary(self):
		if not self.name or self.is_new():
			self.acknowledged_count = 0
			self.pending_acknowledgement_count = 0
			return

		rows = frappe.get_all(
			"Policy Acknowledgement",
			filters={"policy_document": self.name},
			fields=["acknowledgement_status"],
		)
		self.acknowledged_count = sum(1 for row in rows if row.acknowledgement_status == "Acknowledged")
		self.pending_acknowledgement_count = sum(1 for row in rows if row.acknowledgement_status != "Acknowledged")

	def get_target_employees(self):
		filters = {"company": self.company, "status": "Active"}
		if self.target_scope == "Department Employees":
			filters["department"] = self.target_department

		return frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "company", "department"],
			order_by="employee_name asc",
		)

	def sync_policy_acknowledgements(self):
		if not self.acknowledgement_required:
			frappe.throw(_("This policy does not require acknowledgement records"))

		if self.status != "Active":
			frappe.throw(_("Policy acknowledgements can only be synced for active policies"))

		target_employees = self.get_target_employees()
		created = 0
		due_date = add_days(getdate(today()), self.acknowledgement_due_days or 0)

		for employee in target_employees:
			exists = frappe.db.exists(
				"Policy Acknowledgement",
				{
					"policy_document": self.name,
					"policy_version": self.policy_version,
					"employee": employee.name,
				},
			)
			if exists:
				continue

			acknowledgement = frappe.get_doc(
				{
					"doctype": "Policy Acknowledgement",
					"policy_document": self.name,
					"policy_title": self.policy_title,
					"policy_version": self.policy_version,
					"employee": employee.name,
					"employee_name": employee.employee_name,
					"company": employee.company,
					"department": employee.department,
					"article_reference": self.article_reference,
					"legal_reference": self.legal_reference,
					"assigned_on": today(),
					"due_date": due_date,
				}
			)
			assert_doctype_permissions("Policy Acknowledgement", "create", doc=acknowledgement)
			acknowledgement.insert()
			created += 1

		self.db_set("last_acknowledgement_sync_on", get_datetime(), update_modified=False)
		self.reload()
		self._update_acknowledgement_summary()
		self.db_set("acknowledged_count", self.acknowledged_count, update_modified=False)
		self.db_set("pending_acknowledgement_count", self.pending_acknowledgement_count, update_modified=False)
		return created


@frappe.whitelist()
def sync_policy_acknowledgements(policy_name: str):
	policy = frappe.get_doc("HR Policy Document", policy_name)
	frappe.has_permission("HR Policy Document", "read", doc=policy, throw=True)
	created = policy.sync_policy_acknowledgements()
	frappe.msgprint(
		_("Created {0} acknowledgement records for policy {1}").format(created, policy.policy_title),
		alert=True,
	)
	return {"created": created, "policy": policy.name}