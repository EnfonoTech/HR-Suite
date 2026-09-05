"""
performance_setup.py — provisioning for HR Suite Performance Management.

Creates the Custom Fields that turn the stock HRMS ``Appraisal`` into the
Steel Force Performance Appraisal Form 2025, and seeds the criteria /
appraisal template that form is built on.

Everything here is idempotent and is wired into BOTH ``after_install`` and
``after_migrate`` (see ``hr_suite/install.py``).

Design notes / constraints that must not be broken:
  * ``Appraisal.start_date`` / ``end_date`` are NEVER written to. Core's
    ``Appraisal.validate_duplicate()`` rejects a second appraisal whose dates
    overlap, so populating them would make a Mid-Term and an Annual appraisal
    for the same employee mutually exclusive. We carry our own
    ``custom_period_from`` / ``custom_period_to`` instead.
  * No Custom Field is added to ``Employee Feedback Rating`` — that child table
    is shared by ``Appraisal.self_ratings``, ``Appraisal Template.rating_criteria``
    and ``Employee Performance Feedback.feedback_ratings``, and hrms scoring code
    reads it in all three places. Scores live in our own
    ``Appraisal Criterion Rating`` child table.
  * Scores are ``Int`` 1-5, never ``Rating`` — Frappe's ``Rating`` fieldtype is a
    normalised 0..1 float that accepts half-star clicks.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

APPRAISAL_TEMPLATE_NAME = "Steel Force Annual Appraisal"
DEFAULT_KRA_TITLE = "Overall Job Performance"

# The 15 criteria of the printed form, in the printed order. The order is
# load-bearing: ``load_criteria`` seeds the grid with it and the print format
# relies on the grid idx.
STEEL_FORCE_CRITERIA = [
	"Job Knowledge",
	"Technical Skills",
	"Work Quality",
	"Work Consistency",
	"Initiative",
	"Communication Skills",
	"Customer Interaction & Service",
	"Productivity",
	"Attitude",
	"Cooperation",
	"Punctuality & Attendance",
	"Self-Development",
	"Discipline",
	"Accountability",
	"Leadership",
]

_GRADE_OPTIONS = "\nExcellent\nVery Good\nGood\nAverage\nPoor"

# ─── Custom Fields on Appraisal ────────────────────────────────────────────────
# Anchored on ``final_score``, i.e. at the end of the stock "Employee Details" tab
# and before the "KRA" tab. hr_suite's compliance_controls block anchors itself on
# ``remarks`` (inside the KRA tab), so the two chains never collide.
APPRAISAL_CUSTOM_FIELDS = [
	# ── Header ────────────────────────────────────────────────────────────────
	{
		"fieldname": "custom_steel_force_section",
		"fieldtype": "Section Break",
		"label": "Steel Force Appraisal",
		"insert_after": "final_score",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_report_type",
		"fieldtype": "Select",
		"label": "Type of Report",
		"options": "\nDuring Probation\nAfter Probation\nMid-Term Appraisal\nAnnual Appraisal\nOthers",
		"reqd": 1,
		"insert_after": "custom_steel_force_section",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_report_type_other",
		"fieldtype": "Data",
		"label": "Specify Type of Report",
		"depends_on": 'eval:doc.custom_report_type=="Others"',
		"mandatory_depends_on": 'eval:doc.custom_report_type=="Others"',
		"insert_after": "custom_report_type",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_branch",
		"fieldtype": "Link",
		"label": "Branch / Unit",
		"options": "Branch",
		"fetch_from": "employee.branch",
		"read_only": 1,
		"insert_after": "custom_report_type_other",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_period_from",
		"fieldtype": "Date",
		"label": "Evaluation Period From",
		"insert_after": "custom_branch",
		"module": "Hr Suite",
		"description": "Deliberately separate from Appraisal.start_date, which core uses for duplicate detection.",
	},
	{
		"fieldname": "custom_period_to",
		"fieldtype": "Date",
		"label": "Evaluation Period To",
		"insert_after": "custom_period_from",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_sf_header_col_break",
		"fieldtype": "Column Break",
		"insert_after": "custom_period_to",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_date_of_review",
		"fieldtype": "Date",
		"label": "Date of Review",
		"insert_after": "custom_sf_header_col_break",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_years_in_current_role",
		"fieldtype": "Float",
		"label": "Years of Experience in Current Role",
		"precision": "1",
		"read_only": 1,
		"insert_after": "custom_date_of_review",
		"module": "Hr Suite",
		"description": "Derived from the latest designation change (Employee Promotion / Employee Transfer), else Date of Joining.",
	},
	{
		"fieldname": "custom_appraiser",
		"fieldtype": "Link",
		"label": "Appraiser",
		"options": "Employee",
		# NOT reqd at field level. AppraisalCycle.create_appraisals_for_cycle()
		# (appraisal_cycle.py:163-195) inserts Appraisals programmatically with only
		# company / template / employee / cycle, and its except clause catches ONLY
		# frappe.DuplicateEntryError — so a MandatoryError here escapes and aborts the
		# whole "Create Appraisals" run, leaving the remaining appraisees with nothing.
		# hr_suite.hr_suite.performance.validate_appraisal enforces it at submit instead.
		"reqd": 0,
		"insert_after": "custom_years_in_current_role",
		"module": "Hr Suite",
		"description": "Required before submitting.",
	},
	{
		"fieldname": "custom_appraiser_designation",
		"fieldtype": "Data",
		"label": "Appraiser Designation",
		"fetch_from": "custom_appraiser.designation",
		"read_only": 1,
		"insert_after": "custom_appraiser",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer",
		"fieldtype": "Link",
		"label": "Reviewer",
		"options": "Employee",
		"insert_after": "custom_appraiser_designation",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_designation",
		"fieldtype": "Data",
		"label": "Reviewer Designation",
		"fetch_from": "custom_reviewer.designation",
		"read_only": 1,
		"insert_after": "custom_reviewer",
		"module": "Hr Suite",
	},
	# ── Criteria grid ─────────────────────────────────────────────────────────
	{
		"fieldname": "custom_ratings_section",
		"fieldtype": "Section Break",
		"label": "Performance Criteria",
		"insert_after": "custom_reviewer_designation",
		"module": "Hr Suite",
		"description": "5 Excellent (exceeds expectations) | 4 Very Good (meets) | 3 Good (meets most) | 2 Average (needs improvement) | 1 Poor (unsatisfactory)",
	},
	{
		"fieldname": "custom_criterion_ratings",
		"fieldtype": "Table",
		"label": "Criterion Ratings",
		"options": "Appraisal Criterion Rating",
		"insert_after": "custom_ratings_section",
		"module": "Hr Suite",
	},
	# ── Totals ────────────────────────────────────────────────────────────────
	{
		"fieldname": "custom_totals_section",
		"fieldtype": "Section Break",
		"label": "Total Rating",
		"insert_after": "custom_criterion_ratings",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_total",
		"fieldtype": "Int",
		"label": "Appraiser: Total Rating",
		"read_only": 1,
		"insert_after": "custom_totals_section",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_grade",
		"fieldtype": "Select",
		"label": "Appraiser Grade",
		"options": _GRADE_OPTIONS,
		"read_only": 1,
		"insert_after": "custom_appraiser_total",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_totals_col_break",
		"fieldtype": "Column Break",
		"insert_after": "custom_appraiser_grade",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_total",
		"fieldtype": "Int",
		"label": "Reviewer: Total Rating",
		"read_only": 1,
		"insert_after": "custom_totals_col_break",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_performance_grade",
		"fieldtype": "Select",
		"label": "Performance Grade",
		"options": _GRADE_OPTIONS,
		"read_only": 1,
		"insert_after": "custom_reviewer_total",
		"module": "Hr Suite",
		"description": "The official grade. Follows the Reviewer total once the Reviewer has scored every criterion the Appraiser scored, otherwise the Appraiser total.",
	},
	{
		"fieldname": "custom_totals_col_break_2",
		"fieldtype": "Column Break",
		"insert_after": "custom_performance_grade",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_max_total",
		"fieldtype": "Int",
		"label": "Maximum Total",
		"read_only": 1,
		"insert_after": "custom_totals_col_break_2",
		"module": "Hr Suite",
	},
	# ── Appraiser feedback ────────────────────────────────────────────────────
	{
		"fieldname": "custom_appraiser_feedback_section",
		"fieldtype": "Section Break",
		"label": "Appraiser: General Feedback",
		"insert_after": "custom_max_total",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_feedback",
		"fieldtype": "Small Text",
		"label": "Appraiser Feedback / Comments",
		"insert_after": "custom_appraiser_feedback_section",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_training_recommendations",
		"fieldtype": "Small Text",
		"label": "Appraiser Training Recommendations",
		"insert_after": "custom_appraiser_feedback",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_sign_col_break",
		"fieldtype": "Column Break",
		"insert_after": "custom_appraiser_training_recommendations",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_signature",
		"fieldtype": "Signature",
		"label": "Appraiser Signature",
		"insert_after": "custom_appraiser_sign_col_break",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_appraiser_signed_on",
		"fieldtype": "Date",
		"label": "Appraiser Signed On",
		"insert_after": "custom_appraiser_signature",
		"module": "Hr Suite",
	},
	# ── Reviewer feedback ─────────────────────────────────────────────────────
	{
		"fieldname": "custom_reviewer_feedback_section",
		"fieldtype": "Section Break",
		"label": "Reviewer: General Feedback",
		"insert_after": "custom_appraiser_signed_on",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_feedback",
		"fieldtype": "Small Text",
		"label": "Reviewer Feedback / Comments",
		"insert_after": "custom_reviewer_feedback_section",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_training_recommendations",
		"fieldtype": "Small Text",
		"label": "Reviewer Training Recommendations",
		"insert_after": "custom_reviewer_feedback",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_sign_col_break",
		"fieldtype": "Column Break",
		"insert_after": "custom_reviewer_training_recommendations",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_signature",
		"fieldtype": "Signature",
		"label": "Reviewer Signature",
		"insert_after": "custom_reviewer_sign_col_break",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_reviewer_signed_on",
		"fieldtype": "Date",
		"label": "Reviewer Signed On",
		"insert_after": "custom_reviewer_signature",
		"module": "Hr Suite",
	},
	# ── Employee acknowledgement ──────────────────────────────────────────────
	# Acknowledgement happens AFTER submit, so every field in this block carries
	# allow_on_submit (the Section / Column Break included, so the block stays
	# rendered and editable on a submitted document).
	{
		"fieldname": "custom_acknowledgement_section",
		"fieldtype": "Section Break",
		"label": "Performance Review Acknowledgement",
		"allow_on_submit": 1,
		"insert_after": "custom_reviewer_signed_on",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_employee_acknowledged",
		"fieldtype": "Check",
		"label": "Employee Acknowledged",
		"allow_on_submit": 1,
		"insert_after": "custom_acknowledgement_section",
		"module": "Hr Suite",
		"description": "The review was explained to the employee and the employee accepts it.",
	},
	{
		"fieldname": "custom_acknowledged_on",
		"fieldtype": "Datetime",
		"label": "Acknowledged On",
		"allow_on_submit": 1,
		"insert_after": "custom_employee_acknowledged",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_ack_col_break",
		"fieldtype": "Column Break",
		"allow_on_submit": 1,
		"insert_after": "custom_acknowledged_on",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_employee_signature",
		"fieldtype": "Signature",
		"label": "Employee Signature",
		"allow_on_submit": 1,
		"insert_after": "custom_ack_col_break",
		"module": "Hr Suite",
	},
	{
		"fieldname": "custom_employee_comments",
		"fieldtype": "Small Text",
		"label": "Employee Comments",
		"allow_on_submit": 1,
		"insert_after": "custom_employee_signature",
		"module": "Hr Suite",
	},
	# ── Attendance & disciplinary history panel ───────────────────────────────
	{
		"fieldname": "custom_history_section",
		"fieldtype": "Section Break",
		"label": "Attendance & Disciplinary History",
		"collapsible": 1,
		"insert_after": "custom_employee_comments",
		"module": "Hr Suite",
		"description": "Punctuality, attendance and discipline must be scored strictly from this historical data.",
	},
	{
		"fieldname": "custom_history_html",
		"fieldtype": "HTML",
		"label": "History",
		"read_only": 1,
		"insert_after": "custom_history_section",
		"module": "Hr Suite",
	},
]


def ensure_performance_custom_fields() -> None:
	"""Create / refresh the Steel Force Appraisal Custom Fields. Idempotent."""
	if not frappe.db.exists("DocType", "Appraisal"):
		return

	try:
		create_custom_fields({"Appraisal": APPRAISAL_CUSTOM_FIELDS}, ignore_validate=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: Appraisal custom field setup failed")


def seed_appraisal_criteria() -> None:
	"""Seed the 15 Employee Feedback Criteria of the printed form. Idempotent.

	``Employee Feedback Criteria`` autonames by its ``criteria`` field, so the record
	name is the criterion text itself.
	"""
	if not frappe.db.exists("DocType", "Employee Feedback Criteria"):
		return

	existing = set(
		frappe.get_all(
			"Employee Feedback Criteria",
			filters={"name": ["in", STEEL_FORCE_CRITERIA]},
			pluck="name",
		)
	)
	for criterion in STEEL_FORCE_CRITERIA:
		if criterion in existing:
			continue
		try:
			frappe.get_doc({"doctype": "Employee Feedback Criteria", "criteria": criterion}).insert(
				ignore_permissions=True
			)
		except frappe.DuplicateEntryError:
			pass
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"HR Suite: failed to seed Employee Feedback Criteria",
			)


def _ensure_default_kra() -> str | None:
	"""``Appraisal Template.goals`` is reqd, so the template needs at least one KRA."""
	if not frappe.db.exists("DocType", "KRA"):
		return None
	if frappe.db.exists("KRA", DEFAULT_KRA_TITLE):
		return DEFAULT_KRA_TITLE
	try:
		# KRA autonames by field:title, so name == title.
		frappe.get_doc(
			{
				"doctype": "KRA",
				"title": DEFAULT_KRA_TITLE,
				"description": _("Overall performance against the Steel Force appraisal criteria."),
			}
		).insert(ignore_permissions=True)
		return DEFAULT_KRA_TITLE
	except frappe.DuplicateEntryError:
		return DEFAULT_KRA_TITLE
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: failed to seed default KRA")
		return None


def _equal_weightages(count: int) -> list:
	"""Split 100% across ``count`` rows so the total is EXACTLY 100 at 2 decimals.

	``AppraisalMixin.validate_total_weightage`` compares ``flt(total, 2) != 100.0``,
	so for 15 rows we use 14 x 6.67 + 1 x 6.62 = 100.00.
	"""
	if count <= 0:
		return []
	base = flt(round(100.0 / count, 2), 2)
	weightages = [base] * (count - 1)
	weightages.append(flt(round(100.0 - base * (count - 1), 2), 2))
	return weightages


def seed_appraisal_template() -> None:
	"""Seed the 'Steel Force Annual Appraisal' Appraisal Template. Idempotent."""
	if not frappe.db.exists("DocType", "Appraisal Template"):
		return
	if frappe.db.exists("Appraisal Template", APPRAISAL_TEMPLATE_NAME):
		return

	kra = _ensure_default_kra()
	if not kra:
		return

	criteria = frappe.get_all(
		"Employee Feedback Criteria",
		filters={"name": ["in", STEEL_FORCE_CRITERIA]},
		pluck="name",
	)
	# Preserve the printed order — get_all does not guarantee it.
	criteria = [c for c in STEEL_FORCE_CRITERIA if c in set(criteria)]
	if not criteria:
		return

	weightages = _equal_weightages(len(criteria))

	try:
		template = frappe.get_doc(
			{
				"doctype": "Appraisal Template",
				"template_title": APPRAISAL_TEMPLATE_NAME,
				"description": _("Steel Force Performance Appraisal Form 2025 — 15 criteria scored 1-5."),
				# goals is reqd; one generic KRA at the full 100% keeps the mixin happy
				# without pretending the paper form has KRA-based goals.
				"goals": [{"key_result_area": kra, "per_weightage": 100.0}],
				"rating_criteria": [
					{"criteria": name, "per_weightage": weightage}
					for name, weightage in zip(criteria, weightages, strict=False)
				],
			}
		)
		template.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		pass
	except Exception:
		frappe.log_error(frappe.get_traceback(), "HR Suite: failed to seed Appraisal Template")


def setup_performance_management() -> None:
	"""Single entry point wired into after_install() and after_migrate()."""
	ensure_performance_custom_fields()
	seed_appraisal_criteria()
	seed_appraisal_template()
