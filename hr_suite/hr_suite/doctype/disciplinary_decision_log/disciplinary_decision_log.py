import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class DisciplinaryDecisionLog(Document):
	def validate(self):
		self._sync_from_procedure()
		self._validate_dates()
		self._sync_status()

	def _sync_from_procedure(self):
		if not self.disciplinary_procedure:
			return

		procedure = frappe.db.get_value(
			"Disciplinary Procedure",
			self.disciplinary_procedure,
			["employee", "employee_name", "company", "department", "investigation_record", "employee_warning_notice", "penalty_type", "decision_notes"],
			as_dict=True,
		) or {}

		self.employee = self.employee or procedure.get("employee")
		self.employee_name = self.employee_name or procedure.get("employee_name")
		self.company = self.company or procedure.get("company")
		self.department = self.department or procedure.get("department")
		self.investigation_record = self.investigation_record or procedure.get("investigation_record")
		self.employee_warning_notice = self.employee_warning_notice or procedure.get("employee_warning_notice")
		self.decision_type = self.decision_type or procedure.get("penalty_type")
		self.decision_summary = self.decision_summary or procedure.get("decision_notes")

	def _validate_dates(self):
		if self.effective_to and self.effective_from and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From"))

		if self.appeal_received_on and self.decision_date and getdate(self.appeal_received_on) < getdate(self.decision_date):
			frappe.throw(_("Appeal Received On cannot be before Decision Date"))

	def _sync_status(self):
		if self.appeal_received_on:
			self.decision_status = "Appealed"
		elif not self.decision_status:
			self.decision_status = "Draft"