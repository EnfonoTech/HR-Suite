from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from hr_suite.hr_suite.report.wps_export_report import wps_export_report


class TestWpsExportReport(FrappeTestCase):
	def test_report_opens_without_required_filter(self):
		columns, data = wps_export_report.execute({})

		self.assertTrue(columns)
		self.assertEqual(data, [])

	def test_employee_lookup_skips_missing_optional_employee_fields(self):
		rows = [frappe._dict(employee="EMP-001")]

		with self._patch_sparse_employee_meta():
			details = wps_export_report._get_employee_details_lookup(rows)

		self.assertEqual(details["EMP-001"].employee_name, "Demo Employee")
		self.assertEqual(details["EMP-001"].iqama_number, "2089300780")
		self.assertEqual(details["EMP-001"].nationality, "Saudi")

	def test_identity_lookup_uses_available_contract_fields(self):
		rows = [frappe._dict(employee="EMP-001", national_id="", iqama_number="", passport_number="")]

		with self._patch_sparse_employee_meta():
			lookup = wps_export_report._get_identity_lookup(rows)

		self.assertEqual(lookup["EMP-001"], "2089300780")

	@contextmanager
	def _patch_sparse_employee_meta(self):
		def exists(doctype, name=None, *args, **kwargs):
			return doctype == "DocType" and name in {"Employee", "Saudi Employment Contract"}

		def get_meta(doctype):
			field_map = {
				"Employee": {"employee_name"},
				"Saudi Employment Contract": {"employee", "iqama_number", "nationality"},
			}
			return frappe._dict(has_field=lambda fieldname: fieldname in field_map.get(doctype, set()))

		def get_all(doctype, **kwargs):
			if doctype == "Employee":
				self.assertEqual(kwargs["fields"], ["name", "employee_name"])
				return [frappe._dict(name="EMP-001", employee_name="Demo Employee")]
			if doctype == "Saudi Employment Contract":
				return [
					frappe._dict(
						employee="EMP-001",
						iqama_number="2089300780",
						nationality="Saudi",
					)
				]
			return []

		with patch.multiple(
			wps_export_report.frappe,
			get_all=get_all,
			get_meta=get_meta,
		), patch.object(wps_export_report.frappe.db, "exists", side_effect=exists):
			yield
