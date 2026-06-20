import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate


class CountryEmploymentContract(Document):

    def validate(self):
        self._calculate_probation_end_date()
        self._calculate_total_salary()
        self._validate_dates()

    def on_submit(self):
        self._activate_contract()

    def on_cancel(self):
        frappe.db.set_value("Country Employment Contract", self.name, "contract_status", "Terminated")

    def _calculate_probation_end_date(self):
        if self.start_date and self.probation_period_days:
            days = int(self.probation_period_days or 0)
            if self.probation_extended and self.extended_probation_days:
                days += int(self.extended_probation_days)
            self.probation_end_date = add_days(self.start_date, days)

    def _calculate_total_salary(self):
        self.total_salary = flt(self.basic_salary) + flt(self.housing_allowance) + \
            flt(self.transport_allowance) + flt(self.other_allowances)

    def _validate_dates(self):
        if self.contract_type == "Limited" and self.end_date:
            if getdate(self.end_date) <= getdate(self.start_date):
                frappe.throw(_("End Date must be after Start Date."))

    def _activate_contract(self):
        # Deactivate any other active contracts for this employee
        frappe.db.set_value(
            "Country Employment Contract",
            {"employee": self.employee, "contract_status": "Active", "name": ["!=", self.name]},
            "contract_status",
            "Expired",
        )
        frappe.db.set_value("Country Employment Contract", self.name, "contract_status", "Active")

        # Sync work_country to Employee record
        if self.work_country and frappe.db.has_column("Employee", "work_country"):
            frappe.db.set_value("Employee", self.employee, "work_country", self.work_country)


@frappe.whitelist()
def get_country_config_for_employee(employee: str) -> dict:
    """Return the Country Config for the employee's work country."""
    from hr_suite.hr_suite.utils import get_employee_work_country, get_country_config
    country = get_employee_work_country(employee)
    cfg = get_country_config(country)
    if not cfg:
        return {}
    return {
        "work_country": country,
        "statutory_scheme": cfg.statutory_scheme,
        "settlement_formula": cfg.settlement_formula,
        "wps_mandatory": cfg.wps_mandatory,
        "notice_period_days_monthly": cfg.notice_period_days_monthly,
        "max_probation_days": cfg.max_probation_days,
    }
