import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate


class CountryEmploymentContract(Document):

    def validate(self):
        self._validate_probation_period()
        self._calculate_probation_end_date()
        self._calculate_total_salary()
        self._validate_dates()

    def on_submit(self):
        self._activate_contract()
        self._sync_employee_fields()

    def _validate_probation_period(self):
        """Probation is capped per work country (Country Config.max_probation_days)."""
        from hr_suite.hr_suite.utils import get_country_config

        total_probation = cint(self.probation_period_days) + cint(self.extended_probation_days)
        if not total_probation:
            return

        config = get_country_config(self.work_country)
        max_days = cint(config.max_probation_days) if config else 0
        if max_days and total_probation > max_days:
            frappe.throw(
                _("Total probation period cannot exceed {0} days for {1}.").format(
                    max_days, (config.country_name if config else self.work_country)
                ),
                title=_("Probation Period Exceeded"),
            )

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
        if self.contract_type == "Limited" and not self.end_date:
            frappe.throw(_("End Date is required for Limited contracts."), title=_("End Date Required"))
        if self.end_date and self.start_date:
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

    def _sync_employee_fields(self):
        """Push the contract's statutory base and key details onto the Employee record."""
        from hr_suite.hr_suite.utils import get_employee_is_national

        updates = {}
        if self.basic_salary:
            updates["hr_suite_gosi_salary"] = self.basic_salary
        if self.designation:
            updates["designation"] = self.designation
        if self.department:
            updates["department"] = self.department
        if self.start_date and not frappe.db.get_value("Employee", self.employee, "date_of_joining"):
            updates["date_of_joining"] = self.start_date
        if self.work_country and frappe.db.has_column("Employee", "hr_suite_employee_type"):
            # Employee Type options are National / Expatriate — never a country-specific label.
            is_national = get_employee_is_national(self.employee, self.work_country)
            updates["hr_suite_employee_type"] = "National" if is_national else "Expatriate"
        if updates:
            frappe.db.set_value("Employee", self.employee, updates)


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
