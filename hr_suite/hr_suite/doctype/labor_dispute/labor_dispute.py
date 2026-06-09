import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import getdate, date_diff


class LaborDispute(Document):

    def validate(self):
        self._validate_dates()
        self._update_status_from_data()

    def on_submit(self):
        # Once submitted, lock to prevent casual edits
        if self.status in ("Open",):
            self.status = "Internal Mediation"
            self.db_set("status", self.status)

    def _validate_dates(self):
        if self.mlsd_hearing_date and self.mlsd_submission_date:
            if getdate(self.mlsd_hearing_date) < getdate(self.mlsd_submission_date):
                frappe.throw(_("MLSD Hearing Date cannot be before MLSD Submission Date"))
        if self.court_decision_date and self.court_submission_date:
            if getdate(self.court_decision_date) < getdate(self.court_submission_date):
                frappe.throw(_("Court Decision Date cannot be before Court Submission Date"))

    def _update_status_from_data(self):
        """Auto-advance status based on filled sections"""
        if self.court_decision:
            if self.status not in ("Resolved", "Closed"):
                self.status = "Resolved"
        elif self.court_case_number:
            self.status = "Labour Court"
        elif self.mlsd_decision:
            self.status = "Resolved"
        elif self.mlsd_case_number:
            self.status = "MLSD Mediation"
        elif self.mlsd_submission_date:
            self.status = "Referred to MLSD"
        elif self.internal_resolution:
            self.status = "Resolved"
