import frappe
from frappe.model.document import Document


class CountryConfig(Document):
    def validate(self):
        self.country_code = (self.country_code or "").strip().upper()
        if self.settlement_ceiling_applicable and not self.settlement_ceiling_amount:
            frappe.throw("Settlement ceiling amount is required when ceiling applies.")

    @staticmethod
    def get_for(country_code: str):
        """Return a Country Config doc for the given code, or None."""
        if not country_code:
            return None
        name = frappe.db.get_value("Country Config", {"country_code": country_code.upper()}, "name")
        return frappe.get_doc("Country Config", name) if name else None
