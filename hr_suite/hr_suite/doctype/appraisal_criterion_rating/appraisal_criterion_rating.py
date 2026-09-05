import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

# The Steel Force Performance Appraisal Form 2025 scores every criterion on a whole-number
# 1-5 scale (5 Excellent / 4 Very Good / 3 Good / 2 Average / 1 Poor). A blank score is
# allowed while the form is still being drafted — it only has to be filled in before submit.
MIN_SCORE = 1
MAX_SCORE = 5


def validate_criterion_row(row) -> None:
	"""Validate one Appraisal Criterion Rating row and refresh its variance.

	Frappe does not run a child DocType's ``validate`` automatically — only the parent's
	is invoked — so this helper is shared between this controller (for direct/child-level
	use) and ``hr_suite.hr_suite.performance.validate_appraisal`` which is what actually
	fires through the ``Appraisal`` ``validate`` doc event.
	"""
	for fieldname, label in (
		("appraiser_rating", _("Appraiser")),
		("reviewer_rating", _("Reviewer")),
	):
		value = row.get(fieldname)
		# A blank / zero score means "not scored yet" and is permitted while drafting.
		if value in (None, "", 0):
			row.set(fieldname, None)
			continue

		score = cint(value)
		if score < MIN_SCORE or score > MAX_SCORE:
			frappe.throw(
				_("Row #{0}: {1} score for {2} must be between {3} and {4}").format(
					row.idx, label, row.criterion or _("criterion"), MIN_SCORE, MAX_SCORE
				),
				title=_("Invalid Score"),
			)
		row.set(fieldname, score)

	set_variance(row)


def set_variance(row) -> None:
	"""Variance = Reviewer score - Appraiser score. Zero when either side is unscored."""
	appraiser = cint(row.get("appraiser_rating"))
	reviewer = cint(row.get("reviewer_rating"))
	row.variance = (reviewer - appraiser) if (appraiser and reviewer) else 0


class AppraisalCriterionRating(Document):
	def validate(self):
		validate_criterion_row(self)
