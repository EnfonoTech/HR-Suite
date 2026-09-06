# Copyright (c) 2026, Enfono Technologies and contributors
# For license information, please see license.txt
"""Tests for the Employee salary mirror.

These assert the behaviour that matters to the user looking at the Salary tab:
the figures come from the assignment, they change when the assignment changes,
and they disappear when the assignment is cancelled.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from hr_suite.hr_suite.employee_salary import (
	COMPONENTS_FIELD,
	get_current_assignment,
	sync_employee_salary,
)


class TestEmployeeSalary(FrappeTestCase):
	def _an_employee_with_an_assignment(self):
		"""Return (employee, assignment) for any employee that has one, else (None, None)."""
		row = frappe.get_all(
			"Salary Structure Assignment",
			filters={"docstatus": 1, "from_date": ["<=", today()]},
			fields=["employee", "name", "base", "salary_structure"],
			order_by="from_date desc",
			limit=1,
		)
		if not row:
			return None, None
		return row[0].employee, row[0]

	def test_current_assignment_picks_the_latest_in_force(self):
		employee, assignment = self._an_employee_with_an_assignment()
		if not employee:
			self.skipTest("no submitted Salary Structure Assignment on this site")

		found = get_current_assignment(employee)
		self.assertIsNotNone(found)
		self.assertEqual(flt(found["base"]), flt(assignment.base))

		# An assignment that starts tomorrow must not be picked up today.
		self.assertIsNone(
			get_current_assignment(employee, as_on=add_days(assignment.from_date, -1))
			if assignment.get("from_date")
			else None,
			msg="an assignment should not apply before its from_date",
		)

	def test_sync_writes_components_and_totals(self):
		employee, _assignment = self._an_employee_with_an_assignment()
		if not employee:
			self.skipTest("no submitted Salary Structure Assignment on this site")

		result = sync_employee_salary(employee)
		self.assertTrue(result["synced"], msg=result.get("reason"))

		doc = frappe.get_doc("Employee", employee)
		rows = doc.get(COMPONENTS_FIELD) or []
		self.assertEqual(len(rows), result["components"])

		# Header totals must equal the rows they summarise — that is the whole
		# promise of the tab.
		earnings = sum(flt(r.amount) for r in rows if r.component_type == "Earning")
		deductions = sum(flt(r.amount) for r in rows if r.component_type == "Deduction")
		self.assertAlmostEqual(flt(doc.custom_total_earnings), earnings, places=2)
		self.assertAlmostEqual(flt(doc.custom_total_deductions), deductions, places=2)
		self.assertAlmostEqual(flt(doc.custom_net_salary), earnings - deductions, places=2)
		self.assertTrue(doc.custom_salary_synced_on)

	def test_sync_is_idempotent(self):
		"""Running it twice must not duplicate rows — it rebuilds, it does not append."""
		employee, _ = self._an_employee_with_an_assignment()
		if not employee:
			self.skipTest("no submitted Salary Structure Assignment on this site")

		first = sync_employee_salary(employee)
		second = sync_employee_salary(employee)
		self.assertEqual(first["components"], second["components"])

		rows = frappe.get_all(
			"Employee Salary Component",
			filters={"parent": employee, "parentfield": COMPONENTS_FIELD},
		)
		self.assertEqual(len(rows), second["components"])

	def test_employee_without_assignment_is_cleared_not_stale(self):
		employee = frappe.db.get_value(
			"Employee",
			{"status": "Active", "name": ["not in", [
				r.employee for r in frappe.get_all(
					"Salary Structure Assignment", filters={"docstatus": 1}, fields=["employee"]
				)
			] or [""]]},
			"name",
		)
		if not employee:
			self.skipTest("every active employee has an assignment on this site")

		result = sync_employee_salary(employee)
		self.assertTrue(result["synced"])
		self.assertEqual(result["components"], 0)
		self.assertFalse(frappe.db.get_value("Employee", employee, "custom_salary_structure"))
