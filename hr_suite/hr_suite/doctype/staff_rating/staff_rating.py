import re
import frappe
from frappe import _
from frappe.model.document import Document
from hr_suite.hr_suite.utils import assert_employee_access


class StaffRating(Document):

	def before_insert(self):
		if not self.rated_by_employee:
			emp = _get_employee_for_user(frappe.session.user)
			if not emp:
				frappe.throw(_("No Employee record found for the current user. Cannot submit a rating."))
			self.rated_by_employee = emp

	def validate(self):
		self._validate_period_format()
		self._prevent_self_rating()
		self._validate_rater_relationship()
		self._prevent_duplicate()

	def _validate_period_format(self):
		if not re.match(r"^\d{4}-\d{2}$", self.rating_period or ""):
			frappe.throw(_("Rating Period must be in YYYY-MM format (e.g. 2026-06)."))

	def _prevent_self_rating(self):
		if self.rated_by_employee == self.employee:
			frappe.throw(_("An employee cannot rate themselves."))

	def _validate_rater_relationship(self):
		if self.rating_direction == "Downward":
			reports_to = frappe.db.get_value("Employee", self.employee, "reports_to")
			if reports_to != self.rated_by_employee:
				frappe.throw(
					_("Downward rating: {0} is not the direct manager of {1}.").format(
						self.rated_by_employee, self.employee
					)
				)
		elif self.rating_direction == "Upward":
			rater_reports_to = frappe.db.get_value("Employee", self.rated_by_employee, "reports_to")
			if rater_reports_to != self.employee:
				frappe.throw(
					_("Upward rating: {0} does not directly report to {1}.").format(
						self.rated_by_employee, self.employee
					)
				)

	def _prevent_duplicate(self):
		filters = {
			"employee": self.employee,
			"rated_by_employee": self.rated_by_employee,
			"rating_period": self.rating_period,
			"rating_direction": self.rating_direction,
			"docstatus": ["!=", 2],
		}
		if not self.is_new():
			filters["name"] = ["!=", self.name]
		if frappe.db.exists("Staff Rating", filters):
			frappe.throw(
				_("A {0} rating for {1} in {2} already exists from this rater.").format(
					self.rating_direction, self.employee, self.rating_period
				)
			)


@frappe.whitelist()
def submit_rating(employee, rating_direction, rating_period, rating, review=""):
	assert_employee_access(employee)
	frappe.has_permission("Staff Rating", "create", throw=True)
	rater_emp = _get_employee_for_user(frappe.session.user)
	if not rater_emp:
		frappe.throw(_("No Employee record found for your user account."))

	doc = frappe.get_doc({
		"doctype": "Staff Rating",
		"employee": employee,
		"rated_by_employee": rater_emp,
		"rating_direction": rating_direction,
		"rating_period": rating_period,
		"rating": float(rating),
		"review": review,
	})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


@frappe.whitelist()
def get_rating_summary(employee):
	frappe.has_permission("Employee", "read", doc=employee, throw=True)
	return frappe.db.sql("""
		SELECT
			rating_period,
			rating_direction,
			ROUND(AVG(rating), 2)  AS avg_rating,
			COUNT(*)               AS review_count
		FROM `tabStaff Rating`
		WHERE employee = %s
		  AND docstatus = 1
		GROUP BY rating_period, rating_direction
		ORDER BY rating_period DESC
		LIMIT 36
	""", employee, as_dict=True)


@frappe.whitelist()
def get_rateable_relationship(employee):
	assert_employee_access(employee)
	me = _get_employee_for_user(frappe.session.user)
	if not me or me == employee:
		return {"can_rate": False, "directions": []}

	directions = []
	reports_to = frappe.db.get_value("Employee", employee, "reports_to")
	if reports_to == me:
		directions.append("Downward")

	my_manager = frappe.db.get_value("Employee", me, "reports_to")
	if my_manager == employee:
		directions.append("Upward")

	return {"can_rate": bool(directions), "directions": directions}


def _get_employee_for_user(user):
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
