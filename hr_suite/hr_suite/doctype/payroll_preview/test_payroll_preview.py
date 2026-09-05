# Copyright (c) 2026, Enfono Technologies and contributors
# See license.txt

"""Tests for Payroll Preview.

The point of this DocType is that it is READ-ONLY, so the tests defend that contract
first: nothing here may write a payroll figure, and every amount must be marked
read_only so a user cannot type one in either.
"""

import json
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from hr_suite.hr_suite.doctype.payroll_preview import payroll_preview as preview_module

DOCTYPE_DIR = os.path.dirname(os.path.abspath(preview_module.__file__))
CHILD_DIR = os.path.join(os.path.dirname(DOCTYPE_DIR), "payroll_preview_employee")
ALLOCATION_DIR = os.path.join(os.path.dirname(DOCTYPE_DIR), "payroll_preview_allocation")


def load_schema(directory, name):
	with open(os.path.join(directory, name + ".json")) as f:
		return json.load(f)


class TestPayrollPreviewContract(FrappeTestCase):
	"""Structural guarantees. These run without any payroll data."""

	def test_preview_is_not_submittable(self):
		schema = load_schema(DOCTYPE_DIR, "payroll_preview")
		self.assertFalse(schema.get("is_submittable"))

	def test_every_amount_field_is_read_only(self):
		for directory, name in (
			(DOCTYPE_DIR, "payroll_preview"),
			(CHILD_DIR, "payroll_preview_employee"),
			(ALLOCATION_DIR, "payroll_preview_allocation"),
		):
			schema = load_schema(directory, name)
			for field in schema["fields"]:
				if field["fieldtype"] in ("Currency", "Float") and field["fieldname"] != "currency":
					self.assertTrue(
						field.get("read_only"),
						msg=f"{name}.{field['fieldname']} is an amount and must be read_only",
					)

	def test_child_tables_are_read_only(self):
		schema = load_schema(DOCTYPE_DIR, "payroll_preview")
		tables = [f for f in schema["fields"] if f["fieldtype"] == "Table"]
		self.assertEqual(len(tables), 2)
		for field in tables:
			self.assertTrue(field.get("read_only"), msg=f"{field['fieldname']} must be read_only")

	def test_controller_never_writes_a_source_document(self):
		"""No insert / submit / db_set / delete anywhere in the controller.

		`self.save()` is the only persistence, and it writes the preview's own mirror rows.
		"""
		with open(os.path.join(DOCTYPE_DIR, "payroll_preview.py")) as f:
			source = f.read()

		for forbidden in (".insert(", ".submit(", ".db_set(", "frappe.db.set_value", "frappe.delete_doc"):
			self.assertNotIn(forbidden, source, msg=f"{forbidden} must not appear in a read-only preview")

	def test_currency_fields_reference_the_currency_field(self):
		for directory, name in (
			(DOCTYPE_DIR, "payroll_preview"),
			(CHILD_DIR, "payroll_preview_employee"),
			(ALLOCATION_DIR, "payroll_preview_allocation"),
		):
			schema = load_schema(directory, name)
			for field in schema["fields"]:
				if field["fieldtype"] == "Currency":
					self.assertEqual(
						field.get("options"),
						"currency",
						msg=f"{name}.{field['fieldname']} must honour the company currency",
					)


class TestPayrollPreviewLogic(FrappeTestCase):
	"""Behaviour of the pure helpers, exercised without payroll fixtures."""

	def make_preview(self):
		preview = frappe.new_doc("Payroll Preview")
		preview.company = frappe.defaults.get_defaults().get("company") or "_Test Company"
		preview.payroll_frequency = "Monthly"
		preview.start_date = "2026-01-01"
		preview.end_date = "2026-01-31"
		return preview

	def test_period_is_clamped_to_joining_and_relieving(self):
		preview = self.make_preview()

		employee = frappe._dict(
			{"date_of_joining": getdate("2026-01-10"), "relieving_date": getdate("2026-01-20")}
		)
		start_date, end_date = preview._get_period_for_employee(employee)
		self.assertEqual(start_date, getdate("2026-01-10"))
		self.assertEqual(end_date, getdate("2026-01-20"))

		employee = frappe._dict({"date_of_joining": getdate("2025-01-01"), "relieving_date": None})
		start_date, end_date = preview._get_period_for_employee(employee)
		self.assertEqual(start_date, getdate("2026-01-01"))
		self.assertEqual(end_date, getdate("2026-01-31"))

	def test_end_date_before_start_date_is_rejected(self):
		preview = self.make_preview()
		preview.end_date = add_days(preview.start_date, -1)
		self.assertRaises(frappe.ValidationError, preview.validate_period)

	def test_totals_are_a_plain_sum_of_the_employee_rows(self):
		preview = self.make_preview()
		preview.append(
			"employees",
			{"employee": "EMP-A", "earnings": 100, "deductions": 25, "net_estimate": 575, "has_issues": 0},
		)
		preview.append(
			"employees",
			{"employee": "EMP-B", "earnings": 50, "deductions": 10, "net_estimate": 340, "has_issues": 1},
		)

		preview.recalculate_totals()

		self.assertEqual(preview.number_of_employees, 2)
		self.assertEqual(preview.employees_with_issues, 1)
		self.assertEqual(preview.total_earnings, 150)
		self.assertEqual(preview.total_deductions, 35)
		self.assertEqual(preview.net_estimate, 915)

	def test_allocation_row_updates_only_its_own_entry_type_bucket(self):
		preview = self.make_preview()
		employees = {"EMP-A": frappe._dict({"employee_name": "A", "earnings": 0.0, "deductions": 0.0})}

		preview._append_allocation(employees, "EMP-A", entry_type="Earning", amount=100)
		preview._append_allocation(employees, "EMP-A", entry_type="Deduction", amount=30)
		# Information rows are booked elsewhere and must not move the estimate
		preview._append_allocation(employees, "EMP-A", entry_type="Information", amount=999)

		self.assertEqual(employees["EMP-A"].earnings, 100)
		self.assertEqual(employees["EMP-A"].deductions, 30)
		self.assertEqual(len(preview.allocations), 3)

	def test_blocking_issues_cover_every_documented_case(self):
		preview = self.make_preview()
		employee = frappe._dict(
			{"iban": None, "bank_ac_no": None, "identity_number": "", "has_identity_field": True}
		)
		counts = frappe._dict({"lwp_days": 0, "absent_days": 0, "unmarked_days": 3})

		issues = preview._collect_blocking_issues(
			employee=employee,
			assignment=None,
			counts=counts,
			net_estimate=-5,
			is_withheld=True,
			unmapped={"Basic"},
		)

		self.assertEqual(len(issues), 6)
		joined = " ".join(issues)
		for fragment in ("Salary Structure Assignment", "IBAN", "identity", "unmarked", "Basic", "negative"):
			self.assertIn(fragment, joined)

	def test_clean_employee_has_no_blocking_issues(self):
		preview = self.make_preview()
		employee = frappe._dict(
			{"iban": "BH00X", "bank_ac_no": None, "identity_number": None, "has_identity_field": False}
		)
		counts = frappe._dict({"lwp_days": 0, "absent_days": 0, "unmarked_days": 0})

		issues = preview._collect_blocking_issues(
			employee=employee,
			assignment=frappe._dict({"base": 500}),
			counts=counts,
			net_estimate=500,
			is_withheld=False,
			unmapped=set(),
		)

		self.assertEqual(issues, [])

	def test_hr_suite_sources_are_guarded_by_doctype_existence(self):
		preview = self.make_preview()
		with patch.object(preview_module.frappe.db, "exists", return_value=None):
			self.assertEqual(preview._get_loan_installments(["EMP-A"]), [])
			self.assertEqual(preview._get_employee_penalties(["EMP-A"], []), [])
			self.assertEqual(preview._get_overtime_requests(["EMP-A"]), [])
			self.assertEqual(preview._get_salary_adjustments(["EMP-A"]), [])


class TestMakePayrollEntry(FrappeTestCase):
	def test_refuses_a_preview_with_blocking_issues(self):
		preview = frappe.new_doc("Payroll Preview")
		preview.company = frappe.defaults.get_defaults().get("company") or "_Test Company"
		preview.payroll_frequency = "Monthly"
		preview.start_date = "2026-01-01"
		preview.end_date = "2026-01-31"
		preview.append(
			"employees",
			{
				"employee": "EMP-A",
				"employee_name": "A",
				"has_issues": 1,
				"blocking_issues": "No submitted Salary Structure Assignment",
			},
		)

		with patch.object(preview_module.frappe, "get_doc", return_value=preview), patch.object(
			preview_module.frappe, "has_permission", return_value=True
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				preview_module.make_payroll_entry("PPRV-TEST")

		self.assertIn("blocking issues", str(ctx.exception))

	def test_refuses_an_empty_preview(self):
		preview = frappe.new_doc("Payroll Preview")
		preview.company = frappe.defaults.get_defaults().get("company") or "_Test Company"

		with patch.object(preview_module.frappe, "get_doc", return_value=preview), patch.object(
			preview_module.frappe, "has_permission", return_value=True
		):
			self.assertRaises(frappe.ValidationError, preview_module.make_payroll_entry, "PPRV-TEST")

	def test_rejects_a_non_string_reference(self):
		self.assertRaises(frappe.ValidationError, preview_module.make_payroll_entry, {"evil": 1})
