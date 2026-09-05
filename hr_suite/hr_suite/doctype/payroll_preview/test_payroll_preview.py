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

	def test_only_conditions_that_break_payroll_are_blocking(self):
		"""Missing bank details, a missing ID and a withheld salary are shown, not blocking.

		hrms creates a Salary Slip perfectly well in all three cases, so holding the run on
		them would only teach people to work around the gate.
		"""
		preview = self.make_preview()
		employee = frappe._dict(
			{"iban": None, "bank_ac_no": None, "identity_number": "", "has_identity_field": True}
		)
		counts = frappe._dict({"lwp_days": 0, "absent_days": 0, "unmarked_days": 3})

		blocking, advisory = preview._collect_issues(
			employee=employee,
			assignment=None,
			counts=counts,
			net_estimate=-5,
			is_withheld=True,
			unmapped={"Basic"},
			is_timesheet_based=True,
			attendance_driven=False,
		)

		joined_blocking = " ".join(blocking)
		for fragment in ("Salary Structure Assignment", "Basic", "negative"):
			self.assertIn(fragment, joined_blocking)
		self.assertEqual(len(blocking), 3)

		joined_advisory = " ".join(advisory)
		for fragment in ("IBAN", "identity", "unmarked", "withheld", "Timesheet"):
			self.assertIn(fragment, joined_advisory)

	def test_unmarked_attendance_blocks_only_when_payroll_is_attendance_based(self):
		preview = self.make_preview()
		employee = frappe._dict(
			{"iban": "BH00X", "bank_ac_no": None, "identity_number": None, "has_identity_field": False}
		)
		counts = frappe._dict({"lwp_days": 0, "absent_days": 0, "unmarked_days": 3})
		args = dict(
			employee=employee,
			assignment=frappe._dict({"base": 500}),
			counts=counts,
			net_estimate=500,
			is_withheld=False,
			unmapped=set(),
		)

		blocking, advisory = preview._collect_issues(attendance_driven=True, **args)
		self.assertEqual(len(blocking), 1)
		self.assertIn("unmarked", blocking[0])
		self.assertEqual(advisory, [])

		blocking, advisory = preview._collect_issues(attendance_driven=False, **args)
		self.assertEqual(blocking, [])
		self.assertEqual(len(advisory), 1)
		self.assertIn("unmarked", advisory[0])

	def test_clean_employee_has_no_issues_at_all(self):
		preview = self.make_preview()
		employee = frappe._dict(
			{"iban": "BH00X", "bank_ac_no": None, "identity_number": None, "has_identity_field": False}
		)
		counts = frappe._dict({"lwp_days": 0, "absent_days": 0, "unmarked_days": 0})

		blocking, advisory = preview._collect_issues(
			employee=employee,
			assignment=frappe._dict({"base": 500}),
			counts=counts,
			net_estimate=500,
			is_withheld=False,
			unmapped=set(),
		)

		self.assertEqual(blocking, [])
		self.assertEqual(advisory, [])

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
		preview.last_refreshed_on = "2026-02-01 00:00:00"
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

	def test_refuses_a_preview_that_was_never_refreshed(self):
		"""An unrefreshed preview has employee rows only if someone put them there.

		`validate` clears the mirror whenever the scope changes, so `last_refreshed_on`
		being empty means nothing on this document was ever read from the sources.
		"""
		preview = frappe.new_doc("Payroll Preview")
		preview.company = frappe.defaults.get_defaults().get("company") or "_Test Company"
		preview.start_date = "2026-01-01"
		preview.end_date = "2026-01-31"
		preview.append("employees", {"employee": "EMP-A", "employee_name": "A", "has_issues": 0})

		with patch.object(preview_module.frappe, "get_doc", return_value=preview), patch.object(
			preview_module.frappe, "has_permission", return_value=True
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				preview_module.make_payroll_entry("PPRV-TEST")

		self.assertIn("not been refreshed", str(ctx.exception))

	def test_refuses_an_empty_preview(self):
		preview = frappe.new_doc("Payroll Preview")
		preview.company = frappe.defaults.get_defaults().get("company") or "_Test Company"

		with patch.object(preview_module.frappe, "get_doc", return_value=preview), patch.object(
			preview_module.frappe, "has_permission", return_value=True
		):
			self.assertRaises(frappe.ValidationError, preview_module.make_payroll_entry, "PPRV-TEST")

	def test_rejects_a_non_string_reference(self):
		# `@frappe.whitelist()` runs `transform_parameter_types` over the annotated
		# signature first, so a dict never reaches the isinstance guard: frappe rejects it
		# with FrappeTypeError, which is NOT a subclass of ValidationError. Both are
		# accepted here; what the test defends is that the call is refused, not which of
		# the two layers refuses it.
		self.assertRaises(
			(frappe.ValidationError, frappe.exceptions.FrappeTypeError),
			preview_module.make_payroll_entry,
			{"evil": 1},
		)


class TestPayrollPreviewLoanInstalments(FrappeTestCase):
	"""The double-count trap.

	A submitted Employee Loan now books each instalment as an `Additional Salary`, which
	`_add_additional_salary_rows` already lists AND already adds to the employee's
	deductions. If `_add_loan_installment_rows` listed the same instalment again the
	screen would show the loan twice while the payslip deducts it once - on a screen
	whose entire purpose is to state the figure the payslip will carry.
	"""

	def make_preview(self):
		preview = frappe.new_doc("Payroll Preview")
		preview.company = frappe.defaults.get_defaults().get("company") or "_Test Company"
		preview.payroll_frequency = "Monthly"
		preview.start_date = "2026-09-01"
		preview.end_date = "2026-09-30"
		return preview

	def employees(self):
		return {"EMP-A": frappe._dict({"employee_name": "A", "earnings": 0.0, "deductions": 0.0})}

	def instalment(self, **overrides):
		row = {
			"loan": "LOAN-1",
			"employee": "EMP-A",
			"employee_name": "A",
			"installment": "INST-1",
			"installment_number": 1,
			"due_date": getdate("2026-09-05"),
			"installment_amount": 100,
			"outstanding_amount": 100,
			"deduction_status": "Scheduled",
			"additional_salary": "HR-ADS-1",
		}
		row.update(overrides)
		return frappe._dict(row)

	def test_an_instalment_booked_into_this_period_is_not_counted_twice(self):
		preview = self.make_preview()
		employees = self.employees()
		additional_salaries = [frappe._dict({"name": "HR-ADS-1"})]

		with patch.object(preview, "_get_loan_component_setup_gap", return_value=""):
			unbooked = preview._add_loan_installment_rows(
				employees, [self.instalment()], additional_salaries
			)

		# The Additional Salary row carries it; nothing is added here, and no blocker.
		self.assertEqual(len(preview.get("allocations")), 0)
		self.assertEqual(unbooked, {})
		self.assertEqual(employees["EMP-A"].deductions, 0.0)

	def test_an_unbooked_instalment_is_listed_and_blocks(self):
		preview = self.make_preview()
		employees = self.employees()

		with patch.object(preview, "_get_loan_component_setup_gap", return_value=""):
			unbooked = preview._add_loan_installment_rows(
				employees,
				[self.instalment(deduction_status="Pending", additional_salary=None)],
				[],
			)

		rows = preview.get("allocations")
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].entry_type, preview_module.INFORMATION)
		# Information only: it states a gap, so it must not move the deduction total, and
		# it must carry no salary_component or `_get_components_without_account` would
		# raise a second, duplicate blocking issue about the same thing.
		self.assertEqual(employees["EMP-A"].deductions, 0.0)
		self.assertIsNone(rows[0].salary_component)
		self.assertIn("EMP-A", unbooked)
		self.assertIn("not booked into payroll", unbooked["EMP-A"][0])

	def test_the_reason_a_booking_is_impossible_is_carried_into_the_blocker(self):
		preview = self.make_preview()

		with patch.object(preview, "_get_loan_component_setup_gap", return_value="No account for X."):
			unbooked = preview._add_loan_installment_rows(
				self.employees(),
				[self.instalment(deduction_status="Pending", additional_salary=None)],
				[],
			)

		self.assertIn("No account for X.", unbooked["EMP-A"][0])

	def test_a_booking_in_a_future_period_is_information_only(self):
		preview = self.make_preview()
		employees = self.employees()
		booking = frappe._dict({"name": "HR-ADS-2", "docstatus": 1, "payroll_date": getdate("2026-10-05"), "amount": 100})

		with patch.object(preview, "_get_loan_component_setup_gap", return_value=""), patch.object(
			preview_module.frappe, "get_all", return_value=[booking]
		):
			unbooked = preview._add_loan_installment_rows(
				employees,
				[self.instalment(installment_number=2, due_date=getdate("2026-10-05"), additional_salary="HR-ADS-2")],
				[],
			)

		self.assertEqual(unbooked, {})
		self.assertEqual(len(preview.get("allocations")), 1)
		self.assertEqual(employees["EMP-A"].deductions, 0.0)

	def test_a_booking_in_a_period_that_has_already_run_blocks(self):
		preview = self.make_preview()
		booking = frappe._dict({"name": "HR-ADS-3", "docstatus": 1, "payroll_date": getdate("2026-04-01"), "amount": 300})

		with patch.object(preview, "_get_loan_component_setup_gap", return_value=""), patch.object(
			preview_module.frappe, "get_all", return_value=[booking]
		):
			unbooked = preview._add_loan_installment_rows(
				self.employees(),
				[self.instalment(installment_number=3, due_date=getdate("2026-04-01"), additional_salary="HR-ADS-3")],
				[],
			)

		self.assertIn("EMP-A", unbooked)
		self.assertIn("already passed", unbooked["EMP-A"][0])

	def test_unbooked_loans_reach_collect_issues_as_blocking(self):
		preview = self.make_preview()

		blocking, advisory = preview._collect_issues(
			employee=frappe._dict({"iban": "BH00X", "has_identity_field": False, "identity_number": None}),
			assignment=frappe._dict({"base": 500}),
			counts=frappe._dict({"lwp_days": 0, "absent_days": 0, "unmarked_days": 0}),
			net_estimate=500,
			is_withheld=False,
			unmapped=set(),
			unbooked_loans=["Loan instalment 1 due 2026-09-05 is not booked into payroll."],
		)

		self.assertEqual(len(blocking), 1)
		self.assertEqual(advisory, [])
