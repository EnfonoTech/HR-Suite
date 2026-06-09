import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days



ARTICLE_MAP = {
	"Resignation by Employee": (
		"Article 75 — Employee Resignation",
		"Art. 75 — The employee must notify the employer before leaving based on pay type: "
		"60 days for monthly, 30 days for others.",
	),
	"Termination by Employer": (
		"Article 76 — Termination by Employer",
		"Art. 76 — The employer must notify the employee before termination: "
		"60 days for monthly, 30 days for others.",
	),
	"End of Fixed Term": (
		"Article 84 — End of Service Benefit",
		"Fixed-term contract expiry — full EOSB entitlement per Article 84.",
	),
	"Mutual Agreement": (
		"Art.75 / Art.76 — Mutual Agreement",
		"Termination by mutual consent — rights of both parties determined by agreement.",
	),
	"Dismissal Without Notice": (
		"Art.80 — Contract Termination Without Notice",
		"Art. 80 — Employer may terminate without notice or EOSB in cases listed under Art. 80.",
	),
}


class TerminationNotice(Document):

	def validate(self):
		self._calculate_notice_period()
		self._set_legal_reference()

	def _calculate_notice_period(self):
		"""
		Art.75/Art.76: 60 days for monthly salary, 30 days for others.
		During probation or (Art.80): 0 days.
		"""
		reason = self.termination_reason or ""
		settings = frappe.get_single("Hr Suite Settings")


		if "Art.80" in reason or "Dismissal" in reason or self.during_probation:
			self.notice_required_days = 0
		elif self.salary_payment_type == "Monthly":
			self.notice_required_days = int(settings.notice_period_monthly_days or 60)
		else:
			self.notice_required_days = int(settings.notice_period_non_monthly_days or 30)


		if self.notice_start_date and self.notice_required_days is not None:
			self.notice_end_date = add_days(self.notice_start_date, self.notice_required_days)

	def _set_legal_reference(self):
		"""Determine the legal article, description, and EOSB applicability."""
		reason = self.termination_reason or ""
		article, description = ARTICLE_MAP.get(reason, ("—", ""))

		self.termination_article = article
		self.article_description = description


		no_eosb_reasons = {
			"Dismissal Without Notice",
		}
		self.eosb_applicable = 0 if reason in no_eosb_reasons else 1

	def on_submit(self):
		self._auto_create_exit_documents()

	def _auto_create_exit_documents(self):
		last_day = self.notice_end_date or frappe.utils.nowdate()

		# Exit Interview
		if not frappe.db.exists("Exit Interview", {"employee": self.employee, "docstatus": ["!=", 2]}):
			frappe.get_doc({
				"doctype": "Exit Interview",
				"employee": self.employee,
				"employee_name": self.employee_name,
				"company": self.company,
				"department": self.department,
				"termination_notice": self.name,
				"interview_date": last_day,
				"status": "Scheduled",
			}).insert(ignore_permissions=True)

		# Exit Clearance
		ec_name = frappe.db.get_value(
			"Exit Clearance", {"employee": self.employee, "docstatus": ["!=", 2]}, "name"
		)
		if not ec_name:
			ec = frappe.get_doc({
				"doctype": "Exit Clearance",
				"employee": self.employee,
				"employee_name": self.employee_name,
				"company": self.company,
				"department": self.department,
				"termination_notice": self.name,
				"last_working_day": last_day,
				"status": "Open",
			})
			ec.insert(ignore_permissions=True)
			ec_name = ec.name

		# EOSB — only when applicable
		if self.eosb_applicable and not frappe.db.exists(
			"End of Service Benefit", {"employee": self.employee, "docstatus": ["!=", 2]}
		):
			emp = frappe.get_doc("Employee", self.employee)
			basic = (
				frappe.db.get_value(
					"Saudi Employment Contract",
					{"employee": self.employee, "contract_status": "Active"},
					"basic_salary",
				)
				or frappe.db.get_value("Employee", self.employee, "hr_suite_gosi_salary")
				or 0
			)
			eosb = frappe.get_doc({
				"doctype": "End of Service Benefit",
				"employee": self.employee,
				"employee_name": self.employee_name,
				"company": self.company,
				"department": self.department,
				"joining_date": emp.date_of_joining,
				"termination_date": last_day,
				"termination_reason": self.termination_reason,
				"last_basic_salary": basic,
			})
			eosb.insert(ignore_permissions=True)
			# Back-link EOSB on this termination notice
			self.db_set("eosb_reference", eosb.name)
			# Link EOSB on exit clearance
			frappe.db.set_value("Exit Clearance", ec_name, "end_of_service_benefit", eosb.name)

		frappe.msgprint(
			_("Exit Interview, Exit Clearance{0} created automatically.").format(
				_(" and EOSB") if self.eosb_applicable else ""
			),
			title=_("Exit Process Initiated"),
			indicator="green",
		)
