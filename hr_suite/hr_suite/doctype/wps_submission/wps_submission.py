import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


REJECTED_WPS_STATUSES = {"Rejected", "Corrective Action Required"}


class WPSSubmission(Document):
	def validate(self):
		self._validate_payroll_document()
		self._normalize_defaults()
		self._validate_dates()
		self._validate_status_requirements()

	def on_update(self):
		self._sync_corrective_action_log()

	def _validate_payroll_document(self):
		if not self.payroll_document:
			return

		payroll = frappe.get_doc("Monthly Payroll", self.payroll_document)
		if payroll.docstatus != 1:
			frappe.throw(
				_("WPS Submission requires a submitted Monthly Payroll document."),
				title=_("Submitted Payroll Required"),
			)

		self.company = payroll.company

	def _normalize_defaults(self):
		if not self.status:
			self.status = "Draft"
		if self.status in {"Submitted", "Rejected", "Accepted"} and not self.submission_date:
			self.submission_date = nowdate()

	def _validate_dates(self):
		submission_date = getdate(self.submission_date) if self.submission_date else None
		rejection_date = getdate(self.rejection_date) if self.rejection_date else None
		correction_due_date = getdate(self.correction_due_date) if self.correction_due_date else None
		resubmission_date = getdate(self.resubmission_date) if self.resubmission_date else None
		accepted_on = getdate(self.accepted_on) if self.accepted_on else None

		if rejection_date and submission_date and rejection_date < submission_date:
			frappe.throw(_("Rejection Date cannot be before Submission Date."))

		if correction_due_date and rejection_date and correction_due_date < rejection_date:
			frappe.throw(_("Correction Due Date cannot be before Rejection Date."))

		if resubmission_date and rejection_date and resubmission_date < rejection_date:
			frappe.throw(_("Resubmission Date cannot be before Rejection Date."))

		if accepted_on and submission_date and accepted_on < submission_date:
			frappe.throw(_("Accepted On cannot be before Submission Date."))

		if accepted_on and resubmission_date and accepted_on < resubmission_date:
			frappe.throw(_("Accepted On cannot be before Resubmission Date."))

	def _validate_status_requirements(self):
		if self.status in REJECTED_WPS_STATUSES and not self.rejection_reason:
			frappe.throw(_("Rejection Reason is required when the WPS file is rejected or needs correction."))

		if self.status in REJECTED_WPS_STATUSES and not self.correction_due_date:
			frappe.throw(_("Correction Due Date is required when the WPS file is rejected or needs correction."))

		if self.status == "Rejected" and not self.rejection_date:
			frappe.throw(_("Rejection Date is required for rejected WPS submissions."))

		if self.status == "Resubmitted" and not self.resubmission_date:
			frappe.throw(_("Resubmission Date is required when the WPS file is re-submitted."))

		if self.status == "Accepted" and not self.accepted_on:
			frappe.throw(_("Accepted On is required when the WPS file is accepted."))

	def _sync_corrective_action_log(self):
		if self.status in REJECTED_WPS_STATUSES and not self.corrective_action_log:
			action = frappe.new_doc("HR Compliance Action Log")
			action.action_title = _("WPS correction for {0}").format(self.payroll_document)
			action.compliance_area = "Payroll"
			action.company = self.company
			action.action_date = self.rejection_date or self.submission_date or nowdate()
			action.priority = "High"
			action.assigned_to = self.responsible_user
			action.due_date = self.correction_due_date
			action.reference_doctype = self.doctype
			action.reference_name = self.name
			action.description = self.rejection_reason or self.notes or _("Follow up rejected WPS submission.")
			action.corrective_action = _("Correct the WPS file and resubmit it before the due date.")
			action.flags.ignore_permissions = True
			action.save()
			self.db_set("corrective_action_log", action.name)
			return

		if self.corrective_action_log and self.status == "Accepted":
			action = frappe.get_doc("HR Compliance Action Log", self.corrective_action_log)
			action.completed_on = self.accepted_on or nowdate()
			action.result_summary = _("WPS submission accepted after follow-up.")
			action.flags.ignore_permissions = True
			action.save()


@frappe.whitelist()
def create_wps_submission_from_payroll(payroll_document):
	payroll = frappe.get_doc("Monthly Payroll", payroll_document)
	frappe.has_permission("Monthly Payroll", "read", doc=payroll, throw=True)

	existing_name = frappe.db.get_value("WPS Submission", {"payroll_document": payroll_document}, "name")
	if existing_name:
		return frappe.get_doc("WPS Submission", existing_name).as_dict()

	doc = frappe.new_doc("WPS Submission")
	doc.payroll_document = payroll_document
	doc.company = payroll.company
	doc.responsible_user = frappe.session.user
	doc.insert()
	return doc.as_dict()