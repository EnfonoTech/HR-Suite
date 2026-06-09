import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today, add_days


class WorkInjury(Document):

	def validate(self):
		self._validate_reporting_deadline()
		self._warn_if_gosi_overdue()

	def _validate_reporting_deadline(self):
		"""Art.150: Injury must be reported to GOSI within 3 working days."""
		if not self.injury_date:
			return
		days_elapsed = date_diff(today(), self.injury_date)
		if days_elapsed > 3 and not self.gosi_form_25_submitted:
			frappe.msgprint(
				_(f"⚠ Injury occurred {days_elapsed} days ago. GOSI Form 25 must be submitted within 3 working days per Article 150.<br>"
				  f"Warning: {days_elapsed} days have passed since the injury. GOSI Form 25 must be submitted within 3 working days per Article 150."),
				title=_("GOSI Reporting Overdue"),
				indicator="red",
			)

	def _warn_if_gosi_overdue(self):
		if self.gosi_form_25_submitted and not self.gosi_submission_date:
			self.gosi_submission_date = today()

	def on_submit(self):
		if not self.gosi_form_25_submitted:
			frappe.throw(
				_("GOSI Form 25 must be submitted before finalising the injury record.<br>"
				  "GOSI Form 25 must be submitted before completing the injury record."),
				title=_("GOSI Form Required"),
			)
		self.db_set("status", "Reported to GOSI")


@frappe.whitelist()
def get_gosi_deadline(injury_date: str) -> str:
	"""Return the 3-working-day GOSI reporting deadline."""
	return add_days(injury_date, 3)
