import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import date_diff, getdate

from hr_suite.hr_suite.utils import get_employee_basic_salary



LEAVE_ENTITLEMENT = {
    "Hajj": 15,
    "Bereavement": 5,
    "Marriage": 5,
}

MIN_HAJJ_SERVICE_DAYS = 730


class SpecialLeave(Document):

    def validate(self):
        self._set_entitled_days()
        self._set_actual_days()
        self._check_eligibility()
        self._calculate_pay()

    def on_submit(self):
        if not self.is_eligible:
            frappe.throw(_("Employee is not eligible for this special leave. Check eligibility notes."))
        if not self.documentation_attached:
            frappe.msgprint(
                _("Reminder: Please attach supporting documentation for this special leave (Art.113)"),
                indicator="orange",
                title=_("Documentation Required")
            )
        self.status = "Approved"
        self.db_set("status", self.status)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_leave_key(self):
        if not self.leave_type:
            return None
        if "Hajj" in self.leave_type:
            return "Hajj"
        if "Bereavement" in self.leave_type:
            return "Bereavement"
        if "Marriage" in self.leave_type:
            return "Marriage"
        return None

    def _set_entitled_days(self):
        key = self._get_leave_key()
        if key:
            self.entitled_days = LEAVE_ENTITLEMENT[key]

    def _set_actual_days(self):
        if self.leave_start_date and self.leave_end_date:
            self.actual_days = date_diff(self.leave_end_date, self.leave_start_date) + 1
            if self.actual_days > self.entitled_days:
                frappe.throw(
                    _(
                        "Actual days ({0}) exceed the entitled days ({1}) for {2} per Art.113.<br>"
                        "Actual days ({0}) exceed entitled days ({1}) for leave type {2} per Article 113."
                    ).format(self.actual_days, self.entitled_days, self.leave_type),
                    title=_("Days Exceeded")
                )

    def _check_eligibility(self):
        key = self._get_leave_key()
        if not key or not self.employee:
            return

        self.is_eligible = 1
        self.eligibility_notes = ""

        if key == "Hajj":
            joining_date = frappe.db.get_value("Employee", self.employee, "date_of_joining")
            if joining_date:
                service_days = date_diff(getdate(self.leave_start_date or getdate()), getdate(joining_date))
                if service_days < MIN_HAJJ_SERVICE_DAYS:
                    self.is_eligible = 0
                    self.eligibility_notes = _(
                        "Hajj Leave requires at least 2 years of service. "
                        "Current length of service does not meet the minimum required for Hajj leave."
                    )

            prior = frappe.db.count(
                "Special Leave",
                filters={
                    "employee": self.employee,
                    "leave_type": ["like", "%Hajj%"],
                    "docstatus": 1,
                    "name": ["!=", self.name or ""],
                }
            )
            self.hajj_previously_taken = 1 if prior > 0 else 0
            if prior > 0:
                self.is_eligible = 0
                self.eligibility_notes = _(
                    "Hajj Leave is granted only once per employment (Art.113). "
                    "Prior Hajj leave found."
                )

        elif key == "Bereavement":
            if not self.relationship_to_deceased:
                self.eligibility_notes = _("Please specify relationship to deceased for Bereavement Leave")

        elif key == "Marriage":
            prior_marriage = frappe.db.count(
                "Special Leave",
                filters={
                    "employee": self.employee,
                    "leave_type": ["like", "%Marriage%"],
                    "docstatus": 1,
                    "name": ["!=", self.name or ""],
                }
            )
            if prior_marriage > 0:
                self.eligibility_notes = _(
                    "Note: Marriage Leave (Art.113) is typically granted once. "
                    "Prior marriage leave records found ({0})."
                ).format(prior_marriage)

    def _calculate_pay(self):
        if not self.daily_basic_salary:
            if self.employee:
                monthly = get_employee_basic_salary(self.employee)
                if monthly:
                    self.daily_basic_salary = monthly / 30
        if self.daily_basic_salary and self.actual_days:
            self.total_special_leave_pay = self.daily_basic_salary * self.actual_days


@frappe.whitelist()
def check_hajj_eligibility(employee):
    """Return True if employee has not previously taken Hajj leave"""
    joining_date = frappe.db.get_value("Employee", employee, "date_of_joining")
    minimum_service_met = True
    years_service = 0.0
    if joining_date:
        years_service = round(date_diff(getdate(), getdate(joining_date)) / 365.0, 2)
        minimum_service_met = date_diff(getdate(), getdate(joining_date)) >= MIN_HAJJ_SERVICE_DAYS

    prior = frappe.db.count(
        "Special Leave",
        filters={
            "employee": employee,
            "leave_type": ["like", "%Hajj%"],
            "docstatus": 1,
        }
    )
    return {
        "eligible": prior == 0 and minimum_service_met,
        "prior_count": prior,
        "minimum_service_met": minimum_service_met,
        "years_service": years_service,
    }
