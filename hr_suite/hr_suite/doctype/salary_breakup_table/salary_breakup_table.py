from io import BytesIO
from os.path import splitext

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt, now_datetime
from openpyxl import load_workbook

from hr_suite.hr_suite.utils import assert_doctype_permissions

ALLOWED_IMPORT_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
MAX_IMPORT_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_HEADER_SCAN_ROWS = 5


class SalaryBreakupTable(Document):
	def validate(self):
		if not self.breakup_workbook:
			self.set("rows", [])
			self.last_imported_on = None
			self.imported_row_count = 0


def _classify_header(label):
	label = cstr(label).strip().lower()
	if not label:
		return None
	if "total" in label and "salary" in label:
		return "total_salary"
	if "total" in label and ("basic" in label or "allowance" in label):
		# The sheet's own "Total Basic & Allowances" check column — not a split value.
		return None
	if "basic" in label:
		return "basic"
	if "hra" in label or "living" in label:
		return "hra"
	if "transport" in label or "food" in label:
		return "transport"
	if "other" in label:
		return "other_allowance"
	return None


def _get_file_bytes(file_url):
	file_row = frappe.db.get_value(
		"File", {"file_url": file_url}, ["name", "file_name", "file_size"], as_dict=True
	)
	if not file_row:
		frappe.throw(_("Unable to find the uploaded workbook."))
	extension = splitext(cstr(file_row.file_name or file_url).strip())[1].lower()
	if extension not in ALLOWED_IMPORT_EXTENSIONS:
		frappe.throw(_("Only Excel workbook files are supported."), title=_("Invalid File Type"))
	if flt(file_row.file_size) > MAX_IMPORT_FILE_SIZE_BYTES:
		frappe.throw(
			_("The uploaded workbook is too large. Please keep it under {0} MB.").format(
				MAX_IMPORT_FILE_SIZE_BYTES // (1024 * 1024)
			),
			title=_("Workbook Too Large"),
		)
	return frappe.get_doc("File", file_row.name).get_content()


def _find_header_row(sheet):
	"""Scan the first few rows for the real header (skips merged title rows like 'Salary Breakup')."""
	for row_idx, row in enumerate(
		sheet.iter_rows(min_row=1, max_row=MAX_HEADER_SCAN_ROWS), start=1
	):
		header_map = {}
		for col_idx, cell in enumerate(row):
			key = _classify_header(cell.value)
			if key and key not in header_map:
				header_map[key] = col_idx
		if {"total_salary", "basic"}.issubset(header_map):
			return row_idx, header_map
	return None, {}


def _read_breakup_rows(file_url):
	content = _get_file_bytes(file_url)
	workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
	sheet = workbook.active

	header_row_idx, header_map = _find_header_row(sheet)
	if header_row_idx is None:
		frappe.throw(
			_("Could not find a header row with Total Salary and Basic columns in the workbook."),
			title=_("Missing Columns"),
		)

	def get(values, key):
		i = header_map.get(key)
		return values[i] if i is not None and i < len(values) else None

	rows = []
	for values in sheet.iter_rows(min_row=header_row_idx + 1, values_only=True):
		if not values or all(v in (None, "") for v in values):
			continue
		total_salary = get(values, "total_salary")
		if total_salary in (None, ""):
			continue
		rows.append(
			{
				"total_salary": flt(total_salary),
				"basic": flt(get(values, "basic")),
				"hra": flt(get(values, "hra")),
				"transport": flt(get(values, "transport")),
				"other_allowance": flt(get(values, "other_allowance")),
			}
		)
	return rows


@frappe.whitelist()
def import_breakup_table(file_url=None):
	doc = frappe.get_single("Salary Breakup Table")
	assert_doctype_permissions(doc.doctype, "write", doc=doc)

	file_url = file_url or doc.breakup_workbook
	if not file_url:
		frappe.throw(_("Attach a Salary Breakup Workbook first."))

	rows = _read_breakup_rows(file_url)
	if not rows:
		frappe.throw(_("No usable rows found in the workbook."))

	doc.breakup_workbook = file_url
	doc.set("rows", [])
	for row in rows:
		doc.append("rows", row)
	doc.last_imported_on = now_datetime()
	doc.imported_row_count = len(rows)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"row_count": len(rows)}


def get_breakup_for_total_salary(total_salary):
	"""Exact-match lookup used by the Salary Structure Assignment 'Apply Salary Breakup' button."""
	total_salary = flt(total_salary)
	doc = frappe.get_single("Salary Breakup Table")
	for row in doc.rows or []:
		if flt(row.total_salary) == total_salary:
			return {
				"basic": flt(row.basic),
				"hra": flt(row.hra),
				"transport": flt(row.transport),
				"other_allowance": flt(row.other_allowance),
			}
	return None
