"""Validation for the leave / sick / gratuity policy tables on Country Config."""

import frappe
from frappe import _
from frappe.utils import cint, flt


def validate_policy(doc):
	_validate_annual_bands(doc)
	_validate_sick_tiers(doc)
	_validate_year_ranges(doc, "gratuity_slabs", "from_years", "to_years", _("Gratuity slab"))
	_validate_year_ranges(
		doc, "gratuity_resignation_factors", "from_years", "to_years", _("Resignation factor")
	)
	_validate_percents(doc)
	if flt(doc.gratuity_cap_months) < 0:
		frappe.throw(_("The gratuity cap cannot be negative."))
	if cint(doc.annual_leave_eligible_after_months) < 0 or cint(doc.sick_leave_eligible_after_months) < 0:
		frappe.throw(_("Eligibility months cannot be negative."))


def _validate_annual_bands(doc):
	seen = set()
	for row in doc.get("annual_leave_bands") or []:
		start = cint(row.service_from_months)
		if start < 0:
			frappe.throw(_("Annual leave band row {0}: service months cannot be negative.").format(row.idx))
		if start in seen:
			frappe.throw(
				_("Annual leave band row {0}: another band already starts at {1} months.").format(row.idx, start)
			)
		seen.add(start)
		if flt(row.leave_days_per_year) < 0 or flt(row.salary_days_per_year) < 0:
			frappe.throw(_("Annual leave band row {0}: days cannot be negative.").format(row.idx))
		if flt(row.leave_days_per_year) > 366 or flt(row.salary_days_per_year) > 366:
			frappe.throw(_("Annual leave band row {0}: more than 366 days a year is not possible.").format(row.idx))


def _validate_sick_tiers(doc):
	total = 0
	for row in doc.get("sick_leave_tiers") or []:
		if cint(row.tier_days) <= 0:
			frappe.throw(_("Sick leave tier row {0}: days must be more than zero.").format(row.idx))
		total += cint(row.tier_days)
	declared = cint(doc.sick_leave_days_per_year)
	if total and declared and total != declared:
		frappe.throw(
			_("The sick leave tiers add up to {0} days but Sick Days / Year is {1}. They must match.").format(
				total, declared
			),
			title=_("Sick leave tiers do not add up"),
		)


def _validate_year_ranges(doc, table, from_field, to_field, label):
	"""Rows must be ordered, non-overlapping year ranges; only the last may be open-ended."""
	rows = sorted(doc.get(table) or [], key=lambda r: flt(r.get(from_field)))
	previous_to = None
	for position, row in enumerate(rows):
		start, end = flt(row.get(from_field)), flt(row.get(to_field))
		if start < 0:
			frappe.throw(_("{0} row {1}: years cannot be negative.").format(label, row.idx))
		if end and end <= start:
			frappe.throw(_("{0} row {1}: 'To' must be greater than 'From' (or 0 for no limit).").format(label, row.idx))
		if previous_to is not None and start < previous_to:
			frappe.throw(_("{0} row {1} overlaps the row before it.").format(label, row.idx))
		if not end and position != len(rows) - 1:
			frappe.throw(_("{0} row {1} has no upper limit, so it must be the last row.").format(label, row.idx))
		previous_to = end


def _validate_percents(doc):
	for table, field in (("sick_leave_tiers", "pay_percent"), ("gratuity_resignation_factors", "payable_percent")):
		for row in doc.get(table) or []:
			if not 0 <= flt(row.get(field)) <= 100:
				frappe.throw(_("Row {0}: a percentage must be between 0 and 100.").format(row.idx))
	for row in doc.get("gratuity_slabs") or []:
		if flt(row.rate_value) < 0:
			frappe.throw(_("Gratuity slab row {0}: the rate cannot be negative.").format(row.idx))
