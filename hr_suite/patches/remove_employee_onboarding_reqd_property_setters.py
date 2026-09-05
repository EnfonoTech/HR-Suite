"""Restore `job_applicant` / `job_offer` as mandatory on HRMS `Employee Onboarding`.

hr_suite used to ship two Property Setters (`fixtures/property_setter.json`) that made
`Employee Onboarding.job_applicant` and `Employee Onboarding.job_offer` non-mandatory, so
that `Candidate Profile` could create an onboarding without a Job Applicant. That broke
core HRMS onboarding site-wide:

* `EmployeeOnboarding.set_employee`
  (hrms/hr/doctype/employee_onboarding/employee_onboarding.py:22-24) resolves the employee
  with `frappe.db.get_value("Employee", {"job_applicant": self.job_applicant}, "name")`.
  With `job_applicant` blank that filter becomes `job_applicant IS NULL` and binds the
  onboarding to an arbitrary employee.
* `validate_duplicate_employee_onboarding` (:26-34) then matches every OTHER onboarding
  whose `job_applicant` is blank, so only ONE such record can exist on the whole site.

`Candidate Profile._create_onboarding` now always goes through a real Job Applicant and a
real (draft) Job Offer, so the core fields can stay mandatory. The fixtures are gone, but
removing a fixture never deletes the record from a site that already has it — this patch
does that. It is idempotent and safe to replay: Property Setters hold no data, and the
patch is a no-op once the records are absent.
"""

import frappe
from frappe.utils import cint

DOCTYPE = "Employee Onboarding"
PROPERTY_SETTERS = (
	"Employee Onboarding-job_applicant-reqd",
	"Employee Onboarding-job_offer-reqd",
)


def execute():
	removed = []

	for name in PROPERTY_SETTERS:
		row = frappe.db.get_value(
			"Property Setter",
			name,
			["doc_type", "field_name", "property", "value"],
			as_dict=True,
		)
		if not row:
			continue

		# Only the "make it optional" flavour is ours to remove. Anything else under the
		# same name was put there by the site and is left alone.
		if row.property != "reqd" or cint(row.value):
			continue

		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
		removed.append(name)

	if not removed:
		return

	frappe.clear_cache(doctype=DOCTYPE)

	if not frappe.db.table_exists(DOCTYPE):
		return

	# With the fields mandatory again, any onboarding created while they were optional can
	# no longer be saved. Surface them instead of letting HR find out on the next edit.
	orphans = frappe.get_all(
		DOCTYPE,
		filters={"docstatus": ["!=", 2]},
		or_filters=[
			["job_applicant", "in", ["", None]],
			["job_offer", "in", ["", None]],
		],
		pluck="name",
		limit=100,
	)
	if orphans:
		frappe.log_error(
			"Removed Property Setters "
			+ ", ".join(removed)
			+ ", so job_applicant and job_offer are mandatory on "
			+ DOCTYPE
			+ " again. These existing records have one of them blank and cannot be saved "
			"until it is filled in: " + ", ".join(orphans),
			"HR Suite: Employee Onboarding records missing Job Applicant / Job Offer",
		)
