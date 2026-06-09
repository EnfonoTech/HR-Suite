import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import add_months, add_days


class MedicalExamination(Document):
    def validate(self):
        self._set_valid_until()
        self._set_next_examination()
        self._check_unfit_alert()

    def _set_valid_until(self):
        """Set validity to 1 year from examination date if not already set."""
        if self.examination_date and not self.valid_until:
            self.valid_until = add_months(self.examination_date, 12)

    def _set_next_examination(self):
        """Auto-set next periodic examination date if not set."""
        if self.examination_date and not self.next_examination_date:
            if "Periodic" in (self.examination_type or ""):
                self.next_examination_date = add_months(self.examination_date, 12)

    def _check_unfit_alert(self):
        if self.fitness_result and "Unfit" in self.fitness_result:
            if not self.restrictions_notes:
                frappe.throw(
                    _("Please provide Restrictions/Notes when the result is Unfit")
                )

    def on_submit(self):
        # Link back to Work Injury if referenced
        if self.work_injury_reference:
            frappe.db.set_value(
                "Work Injury",
                self.work_injury_reference,
                "medical_examination_done",
                1,
                update_modified=False
            )
