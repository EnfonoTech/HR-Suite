import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from hr_suite.hr_suite.policy_validation import validate_policy


class CountryConfig(Document):
    def validate(self):
        self.country_code = (self.country_code or "").strip().upper()
        if self.settlement_ceiling_applicable and not self.settlement_ceiling_amount:
            frappe.throw("Settlement ceiling amount is required when ceiling applies.")
        self._validate_overtime()
        validate_policy(self)

    def _validate_overtime(self):
        """A night window that prices nothing is the failure this doctype keeps producing.

        The rate columns are NOT NULL DEFAULT 0, so a record can end up carrying a
        perfectly good 19:00-07:00 window next to a rate of zero — and overtime then
        quietly falls back to the weekday rate with nothing on screen to say so. A saved window
        without a rate is refused (a new one has simply not been given a window), and a
        rate without a complete window is refused.
        """
        if not flt(self.overtime_night_rate):
            if self.is_new():
                # A NEW Country Config with no night rate has no night window. Frappe stamps
                # an unset Time field with the current time on a new document, so "a window
                # is set" is true of every country that simply has none — and both window
                # fields are hidden (depends_on night rate) in exactly that state, so the
                # administrator could neither see nor clear what a throw would ask for.
                # That refused to seed Saudi Arabia and India on a fresh install.
                self.overtime_night_start = None
                self.overtime_night_end = None
            elif self.overtime_night_start or self.overtime_night_end:
                # A SAVED config genuinely carrying a window next to a zero rate is the
                # failure this guard exists for.
                frappe.throw(
                    _("A night window is set for {0} but the Night Rate is 0, so the window "
                      "would price nothing and overtime would fall back to the weekday rate. "
                      "Enter the night rate, or clear the window.").format(self.country_code or _("this country")),
                    title=_("Night rate missing"),
                )
        else:
            if not (self.overtime_night_start and self.overtime_night_end):
                frappe.throw(
                    _("The night window needs both a start and an end time."),
                    title=_("Night window incomplete"),
                )

        for fieldname, label in (
            ("overtime_rest_day_rate", _("Weekly Rest Day Rate")),
            ("overtime_holiday_rate", _("Public Holiday Rate")),
        ):
            rate = flt(self.get(fieldname))
            if rate and rate < flt(self.overtime_weekday_rate):
                frappe.throw(
                    _("{0} ({1}) is below the Weekday Rate ({2}). No labour law prices a rest "
                      "day or a holiday lower than an ordinary day — check the figures.").format(
                        label, rate, flt(self.overtime_weekday_rate)),
                    title=_("Rate lower than a working day"),
                )

    @staticmethod
    def get_for(country_code: str):
        """Return a Country Config doc for the given code, or None."""
        if not country_code:
            return None
        name = frappe.db.get_value("Country Config", {"country_code": country_code.upper()}, "name")
        return frappe.get_doc("Country Config", name) if name else None
