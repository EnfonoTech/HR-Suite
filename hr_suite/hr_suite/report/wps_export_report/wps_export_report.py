"""
WPS Export Report
Generates WPS-compliant CSV for MLSD (Ministry of Human Resources) submission.

MLSD SIF (Salary Information File) Format v2.0
Required monthly submission for businesses with 10+ employees.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate


MONTH_NUMBER_MAP = {
    "1": "01",
    "01": "01",
    "january": "01",
    "january": "01",
    "2": "02",
    "02": "02",
    "february": "02",
    "february": "02",
    "3": "03",
    "03": "03",
    "march": "03",
    "march": "03",
    "4": "04",
    "04": "04",
    "april": "04",
    "april": "04",
    "april": "04",
    "5": "05",
    "05": "05",
    "may": "05",
    "may": "05",
    "6": "06",
    "06": "06",
    "june": "06",
    "june": "06",
    "7": "07",
    "07": "07",
    "july": "07",
    "july": "07",
    "8": "08",
    "08": "08",
    "august": "08",
    "august": "08",
    "august": "08",
    "9": "09",
    "09": "09",
    "september": "09",
    "september": "09",
    "10": "10",
    "october": "10",
    "october": "10",
    "october": "10",
    "11": "11",
    "november": "11",
    "november": "11",
    "12": "12",
    "december": "12",
    "december": "12",
}


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Employer ID"),
            "fieldname": "employer_id",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Employee ID"),
            "fieldname": "employee_iqama",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": _("Employee Name"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("IBAN"),
            "fieldname": "iban",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Bank Name"),
            "fieldname": "bank_name",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Payment Date"),
            "fieldname": "payment_date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "label": _("Pay Period"),
            "fieldname": "pay_period",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Net Salary"),
            "fieldname": "net_salary",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Basic Salary"),
            "fieldname": "basic_salary",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Housing Allowance"),
            "fieldname": "housing_allowance",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": _("Nationality"),
            "fieldname": "nationality",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("WPS Status"),
            "fieldname": "wps_status",
            "fieldtype": "Data",
            "width": 100,
        },
    ]


def get_data(filters):
    payroll_name = filters.get("payroll_document")
    if not payroll_name:
        return []

    payroll = frappe.get_doc("Saudi Monthly Payroll", payroll_name)
    company = payroll.company
    pay_period = _get_pay_period_code(payroll)
    payment_date = _get_payment_date(payroll)

    # Get company CR number (used as Employer ID in WPS)
    employer_id = frappe.db.get_value("Company", company, "registration_details") or company
    employee_details = _get_employee_details_lookup(payroll.employees)
    identity_lookup = _get_identity_lookup(payroll.employees)

    rows = []
    for emp_row in payroll.employees:
        employee = emp_row.employee
        emp_data = employee_details.get(employee, {})
        iqama = identity_lookup.get(employee) or employee

        basic = flt(emp_row.get("basic_salary"))
        housing = flt(emp_row.get("housing_allowance"))
        net = flt(emp_row.get("net_salary"))

        # Validate IBAN - basic check
        iban = emp_data.get("iban") or ""
        wps_status = _get_wps_status(iban, iqama, net)

        rows.append({
            "employer_id": employer_id,
            "employee_iqama": iqama,
            "employee_name": emp_row.get("employee_name") or emp_data.get("employee_name") or employee,
            "iban": iban,
            "bank_name": emp_data.get("bank_name") or "",
            "payment_date": payment_date,
            "pay_period": pay_period,
            "net_salary": net,
            "basic_salary": basic,
            "housing_allowance": housing,
            "nationality": emp_data.get("nationality") or "",
            "wps_status": wps_status,
        })

    return rows


@frappe.whitelist()
def download_wps_sif(payroll_document):
    """
    Generate WPS SIF (Salary Information File) as CSV download.
    MLSD format: EDR record + EMP records + EOS record.
    """
    import csv
    import io

    filters = {"payroll_document": payroll_document}
    _, data = execute(filters)

    if not data:
        frappe.throw(_("No employee data found for this payroll document"))

    payroll = frappe.get_doc("Saudi Monthly Payroll", payroll_document)
    company = payroll.company
    employer_id = frappe.db.get_value("Company", company, "registration_details") or company
    pay_period = _get_pay_period_code(payroll)

    output = io.StringIO()
    writer = csv.writer(output)

    # SIF Header (EDR record)
    writer.writerow(["EDR", employer_id, company, pay_period, len(data)])

    # Employee records (EMP)
    for row in data:
        writer.writerow([
            "EMP",
            row["employee_iqama"],
            row["iban"],
            f"{flt(row['net_salary']):.2f}",
            row["pay_period"],
            formatdate(row["payment_date"], "yyyy-MM-dd") if row["payment_date"] else "",
            row["employee_name"],
        ])

    # End of file (EOS)
    writer.writerow(["EOS", len(data), f"{sum(flt(r['net_salary']) for r in data):.2f}"])

    sif_content = output.getvalue()
    filename = f"WPS_{payroll_document}_{pay_period}.csv"

    frappe.response["filename"] = filename
    frappe.response["filecontent"] = sif_content.encode("utf-8")
    frappe.response["type"] = "download"


def _get_payment_date(payroll):
    for fieldname in ("payment_date", "posting_date"):
        value = payroll.get(fieldname)
        if value:
            return getdate(value)
    return None


def _get_pay_period_code(payroll):
    month_value = _normalize_month_number(payroll.get("month"))
    year_value = cint(payroll.get("year"))
    if month_value and year_value:
        return f"{month_value}{year_value}"

    posting_date = _get_payment_date(payroll)
    if posting_date:
        return posting_date.strftime("%m%Y")

    return ""


def _normalize_month_number(month_value):
    if month_value is None:
        return ""

    text = str(month_value).strip()
    if not text:
        return ""

    parts = [part.strip().lower() for part in text.replace('-', '/').split('/') if part.strip()]
    for part in parts:
        if part in MONTH_NUMBER_MAP:
            return MONTH_NUMBER_MAP[part]

    return MONTH_NUMBER_MAP.get(text.lower(), "")


def _get_employee_details_lookup(employee_rows):
    employees = [row.employee for row in employee_rows if row.employee]
    if not employees:
        return {}

    fields = _get_existing_fields(
        "Employee",
        ["name", "employee_name", "iban", "bank_name", "national_id", "iqama_number", "passport_number", "nationality"],
    )
    details = {
        row.name: frappe._dict(
            {
                "name": row.name,
                "employee_name": row.get("employee_name"),
                "iban": row.get("iban"),
                "bank_name": row.get("bank_name"),
                "national_id": row.get("national_id"),
                "iqama_number": row.get("iqama_number"),
                "passport_number": row.get("passport_number"),
                "nationality": row.get("nationality"),
            }
        )
        for row in frappe.get_all(
            "Employee",
            filters={"name": ["in", employees]},
            fields=fields,
            limit_page_length=0,
            as_list=False,
        )
    }
    _merge_contract_identity_details(details, employees)
    return details


def _get_identity_lookup(employee_rows):
    lookup = {}
    employees = [row.employee for row in employee_rows if row.employee]
    if not employees:
        return lookup

    for row in employee_rows:
        identity = row.get("national_id") or row.get("iqama_number") or row.get("passport_number")
        if identity:
            lookup[row.employee] = str(identity).strip()

    for doctype, employee_field, candidate_fields in (
        ("Saudi Employment Contract", "employee", ["employee", "iqama_number", "passport_number"]),
        ("Work Permit Iqama", "employee", ["employee", "iqama_number"]),
        ("Employee", "name", ["name", "national_id", "iqama_number", "passport_number"]),
    ):
        fields = _get_existing_fields(doctype, candidate_fields)
        if employee_field not in fields:
            continue
        identity_fields = [field for field in ("national_id", "iqama_number", "passport_number") if field in fields]
        if not identity_fields:
            continue

        for row in frappe.get_all(
            doctype,
            filters={"employee": ["in", employees]} if doctype != "Employee" else {"name": ["in", employees]},
            fields=fields,
            order_by="modified desc",
            limit_page_length=0,
            as_list=False,
        ):
            employee = row.get("employee") or row.get("name")
            if employee in lookup:
                continue
            identity = row.get("national_id") or row.get("iqama_number") or row.get("passport_number")
            if identity:
                lookup[employee] = str(identity).strip()

    return lookup


def _get_existing_fields(doctype, candidate_fields):
    if not frappe.db.exists("DocType", doctype):
        return []

    meta = frappe.get_meta(doctype)
    existing = []
    for fieldname in candidate_fields:
        if fieldname == "name" or meta.has_field(fieldname):
            existing.append(fieldname)
    return existing


def _merge_contract_identity_details(details, employees):
    fields = _get_existing_fields(
        "Saudi Employment Contract",
        ["employee", "iqama_number", "passport_number", "nationality"],
    )
    if "employee" not in fields:
        return

    for row in frappe.get_all(
        "Saudi Employment Contract",
        filters={"employee": ["in", employees], "docstatus": ["<", 2]},
        fields=fields,
        order_by="start_date desc, modified desc",
        limit_page_length=0,
        as_list=False,
    ):
        employee = row.get("employee")
        if employee not in details:
            continue
        for fieldname in ("iqama_number", "passport_number", "nationality"):
            if fieldname in fields and row.get(fieldname) and not details[employee].get(fieldname):
                details[employee][fieldname] = row.get(fieldname)


def _get_wps_status(iban, identity_value, net_salary):
    if not identity_value:
        return "Missing Identity"
    if not iban:
        return "Missing IBAN"
    if flt(net_salary) <= 0:
        return "Zero Net Pay"
    return "Ready"
