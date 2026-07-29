import frappe
from frappe.model.document import Document
from frappe import _

from hr_suite.hr_suite.utils import assert_employee_access, get_employee_nationality


class TrainingRecord(Document):
    def validate(self):
        self._validate_dates()
        self._set_nationality()
        self._set_mandatory_flag()

    def _validate_dates(self):
        if self.training_end_date and self.training_start_date:
            if self.training_end_date < self.training_start_date:
                frappe.throw(_("End Date cannot be before Start Date"))

    def _set_mandatory_flag(self):
        if self.training_type and "Saudization" in self.training_type:
            self.is_saudization_related = 1

    def _set_nationality(self):
        if self.employee and not self.nationality:
            self.nationality = get_employee_nationality(self.employee)

    def on_submit(self):
        if not self.result:
            frappe.throw(_("Please set the Training Result before submitting"))


@frappe.whitelist()
def get_employee_training_summary(employee):
    """Return training statistics for the given employee."""
    assert_employee_access(employee)
    data = frappe.db.sql("""
        SELECT
            COUNT(*) as total_trainings,
            SUM(CASE WHEN result LIKE 'Pass%%' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN certificate_obtained = 1 THEN 1 ELSE 0 END) as certificates,
            SUM(COALESCE(training_hours, 0)) as total_hours,
            SUM(COALESCE(training_cost, 0)) as total_cost
        FROM `tabTraining Record`
        WHERE employee = %s AND docstatus = 1
    """, (employee,), as_dict=True)
    return data[0] if data else {}
