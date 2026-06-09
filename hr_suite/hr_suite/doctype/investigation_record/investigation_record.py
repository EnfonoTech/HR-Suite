import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today

from hr_suite.hr_suite.utils import assert_doctype_permissions


class InvestigationRecord(Document):

	def validate(self):
		if self.investigation_start_date and self.allegation_date:
			if getdate(self.investigation_start_date) < getdate(self.allegation_date):
				frappe.throw(_("Investigation Start Date cannot be before Allegation Date"))

		if self.investigation_end_date and self.investigation_start_date:
			if getdate(self.investigation_end_date) < getdate(self.investigation_start_date):
				frappe.throw(_("Investigation End Date cannot be before Investigation Start Date"))

		if self.closure_date and self.investigation_end_date:
			if getdate(self.closure_date) < getdate(self.investigation_end_date):
				frappe.throw(_("Closure Date cannot be before Investigation End Date"))

		if self.closure_date:
			self.status = "Closed"
		elif self.investigation_end_date:
			self.status = "Findings Issued"
		elif self.investigation_start_date:
			self.status = "In Progress"


@frappe.whitelist()
def create_warning_notice(record_name: str):
	record = frappe.get_doc("Investigation Record", record_name)
	frappe.has_permission("Investigation Record", "read", doc=record, throw=True)
	if record.employee_warning_notice and frappe.db.exists("Employee Warning Notice", record.employee_warning_notice):
		return {"warning_notice": record.employee_warning_notice, "created": False}

	warning_notice = frappe.get_doc(
		{
			"doctype": "Employee Warning Notice",
			"employee": record.subject_employee,
			"company": record.company,
			"department": record.department,
			"warning_date": record.investigation_end_date or today(),
			"warning_level": "First Written Warning",
			"investigation_record": record.name,
			"legal_reference_matrix": record.legal_reference_matrix,
			"issue_reason": record.allegation_summary,
			"corrective_action": record.recommendation,
			"due_date": add_days(record.investigation_end_date or today(), 7),
		}
	)
	assert_doctype_permissions("Employee Warning Notice", "create", doc=warning_notice)
	warning_notice.insert()
	record.db_set("employee_warning_notice", warning_notice.name, update_modified=False)
	return {"warning_notice": warning_notice.name, "created": True}