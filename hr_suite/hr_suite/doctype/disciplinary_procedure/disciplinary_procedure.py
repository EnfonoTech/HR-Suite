import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import today

from hr_suite.hr_suite.utils import assert_doctype_permissions


class DisciplinaryProcedure(Document):

    def validate(self):
        self._validate_dates()
        self._sync_from_investigation()
        self._check_prior_warnings()

    def on_submit(self):
        if not self.penalty_type:
            frappe.throw(_("Penalty Type must be set before submitting (Art.65 Saudi Labor Law)"))
        if not self.hr_manager_approval:
            frappe.throw(_("HR Manager Approval is required before submitting"))
        self.status = "Decision Issued"
        self.db_set("status", self.status)

    def _validate_dates(self):
        if self.investigation_date and self.incident_date:
            if self.investigation_date < self.incident_date:
                frappe.throw(_("Investigation Date cannot be before Incident Date"))
        if self.penalty_start_date and self.penalty_end_date:
            if self.penalty_end_date < self.penalty_start_date:
                frappe.throw(_("Penalty End Date cannot be before Penalty Start Date"))
        if self.penalty_type and "Suspension" in self.penalty_type:
            if not self.penalty_days or self.penalty_days <= 0:
                frappe.throw(_("Penalty Days must be specified for Suspension (Art.65)"))

            if self.penalty_days > 5:
                frappe.msgprint(
                    _("Warning: Saudi Labor Law Art.65 limits single suspension to 5 days per month"),
                    indicator="orange",
                    title=_("Saudi Labor Law Warning")
                )

    def _check_prior_warnings(self):
        """Count prior warnings to enforce progressive discipline Art.65"""
        if not self.employee or not self.penalty_type:
            return
        prior_count = frappe.db.count(
            "Disciplinary Procedure",
            filters={
                "employee": self.employee,
                "docstatus": 1,
                "name": ["!=", self.name or ""],
            }
        )
        if prior_count == 0 and self.penalty_type and "Termination" in self.penalty_type:
            frappe.msgprint(
                _(
                    "No prior disciplinary records found for this employee. "
                    "Saudi Labor Law Art.65 requires progressive discipline before termination."
                ),
                indicator="orange",
                title=_("Progressive Discipline Warning")
            )

    def _sync_from_investigation(self):
        if not self.investigation_record:
            return

        record = frappe.db.get_value(
            "Investigation Record",
            self.investigation_record,
            ["subject_employee", "company", "department", "allegation_date", "legal_reference_matrix", "employee_warning_notice"],
            as_dict=True,
        ) or {}

        self.employee = self.employee or record.get("subject_employee")
        self.company = self.company or record.get("company")
        self.department = self.department or record.get("department")
        self.incident_date = self.incident_date or record.get("allegation_date")
        self.legal_reference_matrix = self.legal_reference_matrix or record.get("legal_reference_matrix")
        self.employee_warning_notice = self.employee_warning_notice or record.get("employee_warning_notice")


@frappe.whitelist()
def create_decision_log(doc_name):
    doc = frappe.get_doc("Disciplinary Procedure", doc_name)
    frappe.has_permission("Disciplinary Procedure", "read", doc=doc, throw=True)
    if doc.disciplinary_decision_log and frappe.db.exists("Disciplinary Decision Log", doc.disciplinary_decision_log):
        return {"decision_log": doc.disciplinary_decision_log, "created": False}

    article_reference = None
    legal_reference = None
    if doc.legal_reference_matrix:
        reference = frappe.db.get_value(
            "Legal Reference Matrix",
            doc.legal_reference_matrix,
            ["article_number", "law_name"],
            as_dict=True,
        ) or {}
        article_reference = reference.get("article_number")
        legal_reference = reference.get("law_name")

    decision_log = frappe.get_doc(
        {
            "doctype": "Disciplinary Decision Log",
            "disciplinary_procedure": doc.name,
            "employee": doc.employee,
            "company": doc.company,
            "department": doc.department,
            "investigation_record": doc.investigation_record,
            "employee_warning_notice": doc.employee_warning_notice,
            "decision_status": "Issued" if doc.docstatus == 1 else "Draft",
            "decision_type": doc.penalty_type,
            "decision_date": doc.penalty_start_date or today(),
            "effective_from": doc.penalty_start_date,
            "effective_to": doc.penalty_end_date,
            "decided_by": frappe.session.user,
            "article_reference": article_reference,
            "legal_reference": legal_reference,
            "decision_summary": doc.decision_notes or doc.incident_description,
            "appeal_deadline": doc.appeal_date,
        }
    )
    assert_doctype_permissions("Disciplinary Decision Log", "create", doc=decision_log)
    decision_log.insert()
    doc.db_set("disciplinary_decision_log", decision_log.name, update_modified=False)
    return {"decision_log": decision_log.name, "created": True}


@frappe.whitelist()
def get_prior_warnings(employee):
    """Return count and list of prior disciplinary records for an employee"""
    records = frappe.get_all(
        "Disciplinary Procedure",
        filters={"employee": employee, "docstatus": 1},
        fields=["name", "incident_date", "violation_type", "penalty_type", "status"],
        order_by="incident_date desc",
        limit=10,
    )
    return {"count": len(records), "records": records}
