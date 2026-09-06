"""Work Permit Iqama — the single work-authorisation record for every country.

This DocType is deliberately NOT duplicated per country. `tasks.send_work_permit_expiry_alerts`,
`report/work_permit_expiry_report`, `Expat Work Authorization Control.linked_work_permit`,
`integrations/muqeem.py`, `integrations/gosi_api.py`, `report/wps_export_report` and
`doctype/monthly_payroll` all read this one table; a Bahrain sibling DocType would have to be
wired into every one of them and would give HR two places to record the same expiry date.
What was Saudi-shaped here was the LABELLING and the unconditional `reqd` on the Iqama fields,
not the model — so those are what changed.

`work_country` decides which blocks are shown and what the generic permit fields are called;
the labels themselves come from `Country Config` (primary_permit_label / national_id_label) so
they are the client's own configured wording, never hardcoded here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, date_diff, today

from hr_suite.hr_suite.utils import (
	get_country_config,
	get_employee_nationality,
	get_employee_work_country,
	get_permit_labels,
)


class WorkPermitIqama(Document):

	def validate(self):
		self._set_work_country()
		self._set_nationality()
		self._validate_saudi_fields()
		self._calculate_iqama_status()
		self._calculate_permit_status()

	def on_update_after_submit(self):
		"""`work_country` is allow_on_submit, and it is what makes the Iqama fields
		mandatory. Frappe runs `validate` only up to submit, so without this a submitted
		Bahrain permit could be switched to Saudi Arabia after the fact and keep an empty
		Iqama number. Re-run the same guard on the update-after-submit path."""
		self._validate_saudi_fields()

	def _set_work_country(self):
		"""Resolve the work country from the Employee when HR has not set one.

		Uses utils.get_employee_work_country, so the answer is the same one payroll,
		settlement and the statutory scheme use: active Country Employment Contract ->
		Employee.work_country -> Company country -> Hr Suite Settings default.
		"""
		if self.work_country or not self.employee:
			return
		self.work_country = get_employee_work_country(self.employee) or ""

	def _set_nationality(self):
		if self.employee and not self.nationality:
			self.nationality = get_employee_nationality(self.employee)

	def _validate_saudi_fields(self):
		"""`mandatory_depends_on` is enforced by the form only.

		`BaseDocument._get_missing_mandatory_fields` reads `reqd` and nothing else, so a
		record inserted over the REST API or by a script would bypass it. Repeat the rule
		here so the Iqama number stays mandatory for Saudi Arabia on every write path,
		without making it mandatory for Bahrain.
		"""
		if cstr(self.work_country).upper() != "SA":
			return

		missing = []
		if not self.iqama_number:
			missing.append(_("Iqama Number"))
		if not self.iqama_expiry_date:
			missing.append(_("Iqama Expiry Date"))
		if missing:
			frappe.throw(
				_("{0} is required when the Work Country is Saudi Arabia.").format(", ".join(missing)),
				title=_("Missing Iqama Details"),
			)

	def _alert_days(self) -> int:
		"""Days-before-expiry window for this record's country.

		Country Config.permit_expiry_alert_days is the per-country value the client
		configured (Bahrain 60, Saudi Arabia 90); Hr Suite Settings is the global
		fallback for a country with no config row.
		"""
		config = get_country_config(cstr(self.work_country).upper())
		days = cint(config.permit_expiry_alert_days) if config else 0
		if days > 0:
			return days
		days = cint(frappe.db.get_single_value("Hr Suite Settings", "work_permit_expiry_alert_days"))
		return days if days > 0 else 90

	@staticmethod
	def _status_for(expiry_date, alert_days: int) -> str:
		days = date_diff(expiry_date, today())
		if days < 0:
			return "Expired"
		if days <= alert_days:
			return "Expiring Soon"
		return "Active"

	def _calculate_iqama_status(self):
		if not self.iqama_expiry_date:
			self.days_to_iqama_expiry = 0
			self.iqama_status = None
			return

		self.days_to_iqama_expiry = date_diff(self.iqama_expiry_date, today())
		# cint, not int(): iqama_expiry_alert_days is user input and int("") raises.
		alert_days = cint(frappe.db.get_single_value("Hr Suite Settings", "iqama_expiry_alert_days")) or 90
		self.iqama_status = self._status_for(self.iqama_expiry_date, alert_days)

	def _calculate_permit_status(self):
		if not self.work_permit_expiry_date:
			self.work_permit_status = "N/A"
			self.days_to_permit_expiry = 0
			return

		self.days_to_permit_expiry = date_diff(self.work_permit_expiry_date, today())
		self.work_permit_status = self._status_for(self.work_permit_expiry_date, self._alert_days())


@frappe.whitelist()
def get_country_permit_labels(work_country: str | None = None) -> dict:
	"""Labels and the expiry window for a work country, for the client script.

	Read-only master data, but Country Config is still permission-checked because it
	carries the client's statutory configuration.
	"""
	frappe.has_permission("Country Config", "read", throw=True)
	return get_permit_labels(cstr(work_country).strip().upper())
