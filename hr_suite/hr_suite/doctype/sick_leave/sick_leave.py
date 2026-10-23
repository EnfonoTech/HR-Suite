import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, date_diff, getdate, flt, get_first_day_of_week

from hr_suite.hr_suite.policy import get_policy
from hr_suite.hr_suite.sick_leave_tiers import split_days
from hr_suite.hr_suite.utils import assert_employee_access, get_employee_basic_salary


class SickLeave(Document):

	def validate(self):
		self._refuse_on_auto_split()
		self._calculate_total_days()
		self._calculate_cumulative_days()
		self._validate_max_sick_days()
		self._calculate_pay()
		self._set_alerts()

	def _policy(self):
		"""The employee's country policy (cached on the document for this save)."""
		if not hasattr(self, "_policy_cache"):
			self._policy_cache = get_policy(self.employee, on_date=self.from_date) if self.employee else {}
		return self._policy_cache

	def _tiers(self):
		policy = self._policy()
		return policy.sick_leave_tiers if policy.get("has_policy") and policy.get("sick_leave_tiers") else []

	def _refuse_on_auto_split(self):
		"""A NEW Sick Leave document is not raised for a country that splits sick leave automatically.

		That country records sick leave as a Leave Application for "Sick Leave" and the pay tiers are
		applied there. This document stays for existing records and for countries not switched over.
		"""
		if not self.is_new() or not self.employee:
			return
		policy = self._policy()
		if policy.get("has_policy") and cint(policy.sick_leave_auto_split):
			frappe.throw(
				_("{0}'s country splits sick leave into pay tiers automatically. Record it as a Leave "
				  "Application for {1} instead.").format(self.employee_name or self.employee, policy.sick_leave_type),
				title=_("Use Leave Application"),
			)

	def _calculate_total_days(self):
		if self.from_date and self.to_date:
			self.total_days = date_diff(self.to_date, self.from_date) + 1
			if self.total_days <= 0:
				frappe.throw(_("To Date must be after From Date"))

	def _get_sick_days_this_year(self, exclude_current=True):
		"""Total sick days in the current contract year (excluding the current document)."""
		filters = {
			"employee": self.employee,
			"docstatus": 1,
			"from_date": [">=", f"{getdate(self.from_date).year}-01-01"],
			"to_date": ["<=", f"{getdate(self.from_date).year}-12-31"],
		}
		if exclude_current and self.name:
			filters["name"] = ["!=", self.name]

		rows = frappe.get_all("Sick Leave", filters=filters, fields=["total_days"])
		return sum(r.total_days or 0 for r in rows)

	def _calculate_cumulative_days(self):
		self.sick_days_this_year_before = self._get_sick_days_this_year()
		self.sick_days_this_year_after = self.sick_days_this_year_before + (self.total_days or 0)

	def _validate_max_sick_days(self):
		"""The country's sick days a year; Saudi Arabia's 120 (Art. 117) where no policy exists."""
		policy = self._policy()
		limit = cint(policy.get("sick_leave_days_per_year")) if policy.get("has_policy") else 0
		if limit:
			where = policy.get("country_name") or policy.get("country_code")
			basis = _("the {0} sick leave policy").format(where)
		else:
			limit, basis = 120, _("Saudi Labor Law Art. 117")
		if self.sick_days_this_year_after > limit:
			frappe.throw(
				_("Total sick days in the year cannot exceed {0} under {1}.").format(limit, basis),
				title=_("Sick Leave Limit Exceeded"),
			)

	def _calculate_pay(self):
		"""Pay by the country's tiers; Hr Suite Settings' three Saudi figures where it has none."""
		monthly = get_employee_basic_salary(self.employee)
		self.daily_salary = round(monthly / 30, 2)
		used_before = self.sick_days_this_year_before
		new_days = self.total_days or 0

		tiers = self._tiers()
		if tiers:
			days = [(add_days(self.from_date, i), 1.0) for i in range(int(new_days))]
			segments, _used = split_days(tiers, used_before, days)
			self.leave_pay_amount = round(
				sum(seg["weight"] * self.daily_salary * flt(seg["pay_percent"]) / 100.0 for seg in segments), 2
			)
			current = split_days(tiers, used_before, [(self.from_date, 1.0)])[0]
			self.pay_rate = flt(current[0]["pay_percent"]) if current else 0.0
			self.pay_label = current[0]["label"] if current else "No Pay"
			return

		settings = frappe.get_single("Hr Suite Settings")
		full_days = int(settings.sick_leave_full_pay_days or 30)
		partial_days = int(settings.sick_leave_partial_pay_days or 60)
		partial_pct = flt(settings.sick_leave_partial_pay_percentage or 75) / 100

		if used_before < full_days:
			full_day_quota = min(new_days, full_days - used_before)
			partial_quota = 0
			if new_days > full_day_quota:
				remaining = new_days - full_day_quota
				partial_quota = min(remaining, partial_days - max(0, used_before - full_days))
		else:
			full_day_quota = 0
			partial_from = max(0, used_before - full_days)
			partial_quota = min(new_days, max(0, partial_days - partial_from))

		self.leave_pay_amount = round(
			full_day_quota * self.daily_salary + partial_quota * self.daily_salary * partial_pct, 2
		)

		if used_before < full_days:
			self.pay_rate = 100.0
			self.pay_label = "Full Pay"
		elif used_before < full_days + partial_days:
			self.pay_rate = partial_pct * 100
			self.pay_label = "Partial Pay"
		else:
			self.pay_rate = 0.0
			self.pay_label = "No Pay"

	def _set_alerts(self):
		"""alert_30_days: past the full-pay tier. alert_90_days: into unpaid sick days.

		Field names are the old Saudi thresholds (30 and 30+60); they now follow the country's tiers.
		"""
		after = self.sick_days_this_year_after or 0
		tiers = self._tiers()
		if tiers:
			full_days = flt(tiers[0]["tier_days"]) if flt(tiers[0]["pay_percent"]) >= 100 else 0
			paid_days = sum(flt(t["tier_days"]) for t in tiers if flt(t["pay_percent"]) > 0)
		else:
			settings = frappe.get_single("Hr Suite Settings")
			full_days = int(settings.sick_leave_full_pay_days or 30)
			paid_days = full_days + int(settings.sick_leave_partial_pay_days or 60)

		self.alert_30_days = 1 if after > full_days else 0
		self.alert_90_days = 1 if after > paid_days else 0

		if self.alert_90_days and (self._policy().get("country_code") or "SA") == "SA":
			frappe.msgprint(
				_("The employee has used more than {0} paid sick days this year. Termination is permitted "
				  "under Article 117 of the Saudi Labor Law.").format(int(paid_days)),
				title=_("Sick Leave Alert"),
				indicator="red",
			)
		elif self.alert_90_days:
			frappe.msgprint(
				_("The employee has used more than {0} paid sick days this year; the rest is unpaid.").format(int(paid_days)),
				title=_("Sick Leave Alert"),
				indicator="orange",
			)


@frappe.whitelist()
def get_sick_days_this_year(employee, exclude_doc=""):
	"""
	Return the total approved sick days for *employee* in the current year,
	optionally excluding a specific document (used during editing).
	"""
	assert_employee_access(employee)
	from frappe.utils import getdate, nowdate

	current_year = getdate(nowdate()).year
	filters = {
		"employee": employee,
		"docstatus": 1,
		"from_date": [">=", f"{current_year}-01-01"],
		"to_date": ["<=", f"{current_year}-12-31"],
	}
	if exclude_doc:
		filters["name"] = ["!=", exclude_doc]

	rows = frappe.get_all("Sick Leave", filters=filters, fields=["total_days"])
	return sum(flt(r.total_days) for r in rows)


@frappe.whitelist()
def get_daily_salary(employee):
	"""Return daily salary (monthly_basic / 30) for the employee."""
	assert_employee_access(employee)
	monthly = get_employee_basic_salary(employee)
	return round(monthly / 30, 2)
