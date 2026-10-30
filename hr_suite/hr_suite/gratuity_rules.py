"""HRMS Gratuity Rules made from the Country Config gratuity slabs.

The HRMS Gratuity document asks for a Gratuity Rule, and a site that only had the UAE and Indian
rules left Saudi Arabia out of that list even though the Saudi slabs are on Country Config. This
creates, for each country whose slabs HRMS can express exactly, a rule named
"<Country> - Termination / End Of Contract" (marginal slabs, "Sum of all previous slabs", exact
fractional years), so a Saudi employee can be settled from the standard Gratuity form.

Left out on purpose, because HRMS cannot say them and an approximate rule would pay the wrong
amount: the resignation reduction (a factor on the WHOLE gratuity that steps with service), caps
in months of wage, and Bahrain's employer scheme that ends in March 2024. Those stay in HR Suite's
own calculation (Gratuity Liability report, end-of-service benefit), which reads the same slabs.

A rule that already exists is never touched, so an edit made on the site survives. Nothing here
builds SQL from strings.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from hr_suite.hr_suite.gratuity import _months_of_wage_per_year

SUFFIX = "Termination / End Of Contract"
COMPONENTS = ("Basic Salary", "Basic")


def rule_name(country_name):
	return "{0} - {1}".format(country_name, SUFFIX)


def _expressible(policy):
	"""Why HRMS cannot hold this country's slabs exactly, or "" when it can."""
	if not policy.gratuity_slabs:
		return _("no gratuity slabs")
	if flt(policy.gratuity_cap_months):
		return _("a cap of {0} months of wage").format(policy.gratuity_cap_months)
	if policy.get("gratuity_scheme_end_date"):
		return _("the employer scheme ends on {0}").format(policy.gratuity_scheme_end_date)
	for slab in policy.gratuity_slabs:
		if flt(slab.get("from_years")) != int(flt(slab.get("from_years"))) or flt(slab.get("to_years")) != int(flt(slab.get("to_years"))):
			return _("slab boundaries that are not whole years")
	return ""


def sync_gratuity_rules():
	"""Create the missing rules. Called after every migrate; safe to repeat."""
	if not frappe.db.exists("DocType", "Gratuity Rule"):
		return
	component = next((c for c in COMPONENTS if frappe.db.exists("Salary Component", c)), None)
	if not component:
		return

	from hr_suite.hr_suite.policy import get_country_policy

	for code in frappe.get_all("Country Config", filters={"is_active": 1}, pluck="country_code"):
		policy = get_country_policy(code)
		if not policy or _expressible(policy):
			continue
		name = rule_name(policy.country_name)
		if frappe.db.exists("Gratuity Rule", name):
			continue
		try:
			rule = frappe.get_doc(
				{
					"doctype": "Gratuity Rule",
					"calculate_gratuity_amount_based_on": "Sum of all previous slabs",
					"work_experience_calculation_function": "Take Exact Completed Years",
					"total_working_days_per_year": 365,
					"minimum_year_for_gratuity": cint(flt(policy.gratuity_min_service_years)),
					"applicable_earnings_component": [{"salary_component": component}],
					"gratuity_rule_slabs": [
						{
							"from_year": cint(slab.get("from_years")),
							"to_year": cint(slab.get("to_years")),
							"fraction_of_applicable_earnings": flt(
								_months_of_wage_per_year(
									slab.get("rate_unit"), flt(slab.get("rate_value")), policy.get("gratuity_days_per_month")
								),
								6,
							),
						}
						for slab in sorted(policy.gratuity_slabs, key=lambda s: flt(s.get("from_years")))
					],
				}
			)
			rule.__newname = name  # the DocType names itself by prompt
			rule.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "HR Suite: could not create Gratuity Rule " + name)


def validate_one_gratuity_per_employee(doc, method=None):
	"""Gratuity is paid once per employment: refuse to submit a second one while another is live.

	HRMS lets any number of Gratuity documents be submitted for one employee, so a settled
	employee could be paid again. Drafts are left alone, and a cancelled one does not count,
	which keeps Amend working.
	"""
	existing = frappe.db.get_value(
		"Gratuity",
		{"employee": doc.employee, "docstatus": 1, "name": ["!=", doc.name]},
		"name",
	)
	if existing:
		frappe.throw(
			_("Gratuity {0} is already submitted for {1}. Cancel it before submitting this one.").format(
				frappe.bold(existing), frappe.bold(doc.employee)
			),
			title=_("Gratuity Already Exists"),
		)
