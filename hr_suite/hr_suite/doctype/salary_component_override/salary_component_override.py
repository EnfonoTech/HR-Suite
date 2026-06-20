import frappe
from frappe.model.document import Document


class SalaryComponentOverride(Document):
    def before_insert(self):
        self.modified_by_user = frappe.session.user

    def validate(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw("Effective Until cannot be before Effective From.")
