import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import date_diff, getdate, flt

from hr_suite.hr_suite.utils import get_annual_leave_days_taken, get_annual_leave_entitlement, get_employee_salary_components


class AnnualLeaveDisbursement(Document):

    def validate(self):
        self._load_salary_data()
        self._calculate_entitlement()
        self._calculate_pay()

    def on_submit(self):

        self.status = "Approved"
        self.db_set("status", self.status)

    # ------------------------------------------------------------------

    def _load_salary_data(self):
        if not self.employee:
            return

        salary = get_employee_salary_components(self.employee)
        basic = salary["basic_salary"]
        if not self.monthly_basic_salary:
            self.monthly_basic_salary = basic

        housing = salary["housing_allowance"]
        transport = salary["transport_allowance"]
        self.monthly_gross_salary = (self.monthly_basic_salary or 0) + housing + transport
        self.daily_basic_rate = (self.monthly_basic_salary or 0) / 30

    def _calculate_entitlement(self):
        """Article 109: 21 days/year for first 5 years, 30 days/year after"""
        if not self.employee or not self.leave_year:
            return

        # Years of service
        join_date = frappe.db.get_value("Employee", self.employee, "date_of_joining")
        if not join_date:
            return

        reference_date = f"{self.leave_year}-12-31"
        years_service = (getdate(reference_date) - getdate(join_date)).days / 365.25
        entitled = get_annual_leave_entitlement(self.employee, reference_date)
        self.leave_days_entitled = entitled

        # Days already taken this year from Saudi Annual Leave requests
        taken = get_annual_leave_days_taken(self.employee, self.leave_year)
        self.leave_days_taken = taken
        self.leave_days_balance = entitled - taken

        if not self.leave_days_to_pay:
            # Default to leave period duration
            if self.leave_from_date and self.leave_to_date:
                self.leave_days_to_pay = date_diff(self.leave_to_date, self.leave_from_date) + 1

    def _calculate_pay(self):
        if not self.daily_basic_rate or not self.leave_days_to_pay:
            return

        days = self.leave_days_to_pay
        basic_pay = self.daily_basic_rate * days
        self.basic_leave_pay = basic_pay

        if self.disbursement_type and "Full" in self.disbursement_type:
            # Pro-rate housing and transport too
            salary = get_employee_salary_components(self.employee)
            housing_daily = salary["housing_allowance"] / 30
            transport_daily = salary["transport_allowance"] / 30
            self.housing_allowance_pay = housing_daily * days
            self.transport_allowance_pay = transport_daily * days
        else:
            self.housing_allowance_pay = 0
            self.transport_allowance_pay = 0

        ticket = self.ticket_amount if self.ticket_entitled else 0
        self.total_leave_pay = (
            (self.basic_leave_pay or 0)
            + (self.housing_allowance_pay or 0)
            + (self.transport_allowance_pay or 0)
            + ticket
        )


@frappe.whitelist()
def get_leave_balance(employee, leave_year):
    """Return leave entitlement, taken and balance for UI"""
    join_date = frappe.db.get_value("Employee", employee, "date_of_joining")
    if not join_date:
        return {}

    reference_date = f"{leave_year}-12-31"
    years_service = (getdate(reference_date) - getdate(join_date)).days / 365.25
    entitled = get_annual_leave_entitlement(employee, reference_date)
    taken = get_annual_leave_days_taken(employee, leave_year)

    return {
        "entitled": entitled,
        "taken": taken,
        "balance": entitled - taken,
        "years_service": round(years_service, 1),
    }

