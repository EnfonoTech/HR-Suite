import json
from io import BytesIO
from os.path import splitext

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt, getdate
from frappe.utils.file_manager import save_file
from frappe.utils.xlsxutils import make_xlsx
from openpyxl import load_workbook

from hrms.payroll.doctype.salary_structure.salary_structure import create_salary_structure_assignment

ALLOWED_WORKBOOK_EXTENSIONS = {".xlsx", ".xlsm"}
MAX_WORKBOOK_FILE_SIZE_BYTES = 5 * 1024 * 1024
SYNC_ROW_LIMIT = 50
REQUIRED_COLUMNS = {"employee", "salary structure"}


class SalaryStructureAssignmentImport(Document):
	pass


@frappe.whitelist()
def import_workbook(doc_name):
	doc = frappe.get_doc("Salary Structure Assignment Import", doc_name)
	frappe.has_permission(doc.doctype, "write", doc=doc, throw=True)

	if not doc.workbook:
		frappe.throw(_("Please attach a workbook first."))

	rows = _read_workbook_rows(doc.workbook)
	if not rows:
		frappe.throw(_("No data rows found in the workbook."))

	if len(rows) > SYNC_ROW_LIMIT:
		doc.db_set({"status": "Queued", "total_rows": len(rows)}, commit=True)
		frappe.enqueue(_process_workbook_rows, queue="long", timeout=3000, doc_name=doc.name)
		return {"queued": True, "total_rows": len(rows)}

	return _process_workbook_rows(doc_name=doc.name)


def _process_workbook_rows(doc_name):
	doc = frappe.get_doc("Salary Structure Assignment Import", doc_name)
	rows = _read_workbook_rows(doc.workbook)

	results = []
	success = skipped = failed = 0

	for idx, row in enumerate(rows, start=2):  # row 1 is the header
		employee_value = row.get("employee")
		structure_value = row.get("salary_structure")
		from_date = row.get("from_date") or doc.default_from_date
		base = row.get("base")
		variable = row.get("variable")

		row_result = {"row": idx, "employee": employee_value, "salary_structure": structure_value}

		if not employee_value or not structure_value:
			failed += 1
			row_result.update(status="Failed", message=_("Employee and Salary Structure are both required."))
			results.append(row_result)
			continue

		if not from_date:
			failed += 1
			row_result.update(
				status="Failed",
				message=_("From Date is required (set it on the row or as the Default From Date)."),
			)
			results.append(row_result)
			continue

		savepoint = f"ssai_row_{idx}"
		try:
			frappe.db.savepoint(savepoint)

			employee_id, employee_company = _resolve_employee(employee_value, doc.company)
			structure = _resolve_salary_structure(structure_value)

			if frappe.db.exists(
				"Salary Structure Assignment",
				{
					"employee": employee_id,
					"salary_structure": structure.name,
					"from_date": getdate(from_date),
					"docstatus": 1,
				},
			):
				skipped += 1
				row_result.update(status="Skipped", message=_("Already assigned for this From Date."))
				results.append(row_result)
				continue

			create_salary_structure_assignment(
				employee=employee_id,
				salary_structure=structure.name,
				company=employee_company,
				currency=structure.currency,
				from_date=getdate(from_date),
				base=flt(base) if base not in (None, "") else None,
				variable=flt(variable) if variable not in (None, "") else None,
			)
			success += 1
			row_result.update(status="Assigned", message="")
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			failed += 1
			row_result.update(status="Failed", message=cstr(e))
			frappe.log_error(
				title="Salary Structure Assignment Import Row Failed",
				message=frappe.get_traceback(),
			)
		results.append(row_result)

	doc.db_set(
		{
			"total_rows": len(rows),
			"success_count": success,
			"skipped_count": skipped,
			"failed_count": failed,
			"status": "Completed" if failed == 0 else "Completed with Errors",
			"import_log": json.dumps(results, indent=2, default=str),
		},
		commit=True,
	)

	summary = {
		"total_rows": len(rows),
		"success_count": success,
		"skipped_count": skipped,
		"failed_count": failed,
		"results": results,
	}
	frappe.publish_realtime("salary_structure_assignment_import_done", summary, user=frappe.session.user)
	return summary


def _resolve_employee(value, default_company):
	value = cstr(value).strip()
	employee_id = value if frappe.db.exists("Employee", value) else None

	if not employee_id:
		employee_id = frappe.db.get_value("Employee", {"user_id": value}, "name")
	if not employee_id:
		employee_id = frappe.db.get_value("Employee", {"employee_name": value}, "name")
	if not employee_id:
		frappe.throw(_("No Employee found matching {0}.").format(value))

	company = frappe.db.get_value("Employee", employee_id, "company") or default_company
	if not company:
		frappe.throw(_("Employee {0} has no Company set.").format(employee_id))
	return employee_id, company


def _resolve_salary_structure(value):
	value = cstr(value).strip()
	structure = frappe.db.get_value(
		"Salary Structure", value, ["name", "currency", "docstatus"], as_dict=True
	)
	if not structure:
		frappe.throw(_("No Salary Structure found named {0}.").format(value))
	if structure.docstatus != 1:
		frappe.throw(_("Salary Structure {0} is not submitted.").format(value))
	return structure


def _read_workbook_rows(file_url):
	file_row = frappe.db.get_value(
		"File", {"file_url": file_url}, ["name", "file_name", "file_size"], as_dict=True
	)
	if not file_row:
		frappe.throw(_("Unable to find the uploaded workbook."))

	extension = splitext(cstr(file_row.file_name or file_url).strip())[1].lower()
	if extension not in ALLOWED_WORKBOOK_EXTENSIONS:
		frappe.throw(_("Only .xlsx or .xlsm files are supported."), title=_("Invalid File Type"))
	if flt(file_row.file_size) > MAX_WORKBOOK_FILE_SIZE_BYTES:
		frappe.throw(
			_("The uploaded workbook is too large. Please keep it under {0} MB.").format(
				MAX_WORKBOOK_FILE_SIZE_BYTES // (1024 * 1024)
			),
			title=_("Workbook Too Large"),
		)

	content = frappe.get_doc("File", file_row.name).get_content()
	workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
	sheet = workbook.active

	header_cells = next(sheet.iter_rows(min_row=1, max_row=1), None)
	if not header_cells:
		frappe.throw(_("The workbook has no header row."))

	header_map = {}
	for i, cell in enumerate(header_cells):
		label = cstr(cell.value).strip().lower()
		if label:
			header_map[label] = i

	missing = REQUIRED_COLUMNS - set(header_map)
	if missing:
		frappe.throw(
			_("The workbook is missing required column(s): {0}.").format(", ".join(sorted(missing))),
			title=_("Missing Columns"),
		)

	def get(values, label):
		i = header_map.get(label)
		return values[i] if i is not None and i < len(values) else None

	rows = []
	for values in sheet.iter_rows(min_row=2, values_only=True):
		if not values or all(v in (None, "") for v in values):
			continue
		rows.append(
			{
				"employee": get(values, "employee"),
				"salary_structure": get(values, "salary structure"),
				"from_date": get(values, "from date"),
				"base": get(values, "base"),
				"variable": get(values, "variable"),
			}
		)
	return rows


@frappe.whitelist()
def download_template(doc_name):
	doc = frappe.get_doc("Salary Structure Assignment Import", doc_name)
	frappe.has_permission(doc.doctype, "read", doc=doc, throw=True)

	filters = {"status": "Active"}
	if doc.company:
		filters["company"] = doc.company

	employees = frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "employee_name"],
		order_by="employee_name asc",
	)

	rows = [["Employee", "Employee Name", "Salary Structure", "From Date", "Base", "Variable"]]
	for emp in employees:
		rows.append([emp.name, emp.employee_name, "", "", "", ""])

	file_name = f"salary-structure-assignment-template-{doc.name}.xlsx"
	file_doc = save_file(
		file_name,
		make_xlsx(rows, "Salary Structure Assignment").getvalue(),
		doc.doctype,
		doc.name,
		is_private=1,
	)
	return {"file_url": file_doc.file_url, "file_name": file_doc.file_name, "row_count": len(rows) - 1}
