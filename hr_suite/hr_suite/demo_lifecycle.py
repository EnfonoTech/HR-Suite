"""
demo_lifecycle.py — HR Suite Demo Data Seeder

Creates 4 representative employees with full lifecycle data to demonstrate
the HR Suite workflow end-to-end without requiring manual data entry.

Employees:
  1. Ahmed Al-Ghamdi     — Saudi National, Senior Accountant, 3-year employee, active
  2. John Smith          — Expatriate (UK), IT Engineer, probation ending soon
  3. Sara Al-Dosari      — Saudi National, HR Assistant, disciplinary case in progress
  4. Tariq Al-Mutairi    — Saudi National, Operations Lead, being terminated (full exit)
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, nowdate, add_months, getdate


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _company() -> str:
    companies = frappe.get_all("Company", pluck="name", limit_page_length=1)
    if not companies:
        frappe.throw("Create a Company before running the HR Suite demo seeder.")
    return companies[0]


def _gender(preferred="Male") -> str:
    for candidate in (preferred, "Prefer not to say", "Male", "Female"):
        if frappe.db.exists("Gender", candidate):
            return candidate
    genders = frappe.get_all("Gender", pluck="name", limit_page_length=1)
    return genders[0] if genders else frappe.throw("Create a Gender record first.")


def _ensure_user(email: str, full_name: str, roles: tuple) -> str:
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": full_name,
            "enabled": 1,
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
    else:
        user = frappe.get_doc("User", email)
        user.enabled = 1
        user.save(ignore_permissions=True)
    for role in roles:
        if not frappe.db.exists("Role", role):
            continue
        user.add_roles(role)
    return email


def _ensure_employee(data: dict) -> str:
    existing = frappe.db.get_value("Employee", {"user_id": data.get("user_id")}, "name")
    if existing:
        emp = frappe.get_doc("Employee", existing)
        for k, v in data.items():
            setattr(emp, k, v)
        emp.save(ignore_permissions=True)
        return emp.name
    emp = frappe.get_doc({"doctype": "Employee", **data})
    emp.insert(ignore_permissions=True)
    return emp.name


def _ensure_contract(data: dict) -> str:
    existing = frappe.db.get_value(
        "Saudi Employment Contract",
        {"employee": data["employee"], "start_date": data["start_date"], "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        return existing
    doc = frappe.get_doc({"doctype": "Saudi Employment Contract", **data})
    doc.insert(ignore_permissions=True)
    try:
        doc.submit()
    except Exception:
        pass
    return doc.name


def _ensure_iqama(data: dict) -> str:
    existing = frappe.db.get_value(
        "Work Permit Iqama",
        {"employee": data["employee"], "document_type": data.get("document_type", "Iqama")},
        "name",
    )
    if existing:
        return existing
    return frappe.get_doc({"doctype": "Work Permit Iqama", **data}).insert(ignore_permissions=True).name


def _ensure_leave(data: dict) -> str:
    existing = frappe.db.get_value(
        "Saudi Annual Leave",
        {"employee": data["employee"], "leave_start_date": data["leave_start_date"], "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        return existing
    doc = frappe.get_doc({"doctype": "Saudi Annual Leave", **data})
    doc.flags.ignore_permissions = True
    try:
        from frappe.workflow.doctype.workflow_action import workflow_action
        orig = workflow_action.enqueue
        workflow_action.enqueue = lambda *a, **k: None
        try:
            doc.insert(ignore_permissions=True)
        finally:
            workflow_action.enqueue = orig
    except Exception:
        doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_gosi(data: dict) -> str:
    existing = frappe.db.get_value(
        "GOSI Contribution",
        {"employee": data["employee"], "month": data["month"], "year": data["year"]},
        "name",
    )
    if existing:
        return existing
    return frappe.get_doc({"doctype": "GOSI Contribution", **data}).insert(ignore_permissions=True).name


def _ensure_warning(data: dict) -> str:
    existing = frappe.db.get_value(
        "Employee Warning Notice",
        {"employee": data["employee"], "warning_date": data["warning_date"], "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        return existing
    return frappe.get_doc({"doctype": "Employee Warning Notice", **data}).insert(ignore_permissions=True).name


def _ensure_disciplinary(data: dict) -> str:
    existing = frappe.db.get_value(
        "Disciplinary Procedure",
        {"employee": data["employee"], "incident_date": data["incident_date"], "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        return existing
    return frappe.get_doc({"doctype": "Disciplinary Procedure", **data}).insert(ignore_permissions=True).name


def _ensure_termination(data: dict) -> str:
    existing = frappe.db.get_value(
        "Termination Notice",
        {"employee": data["employee"], "docstatus": ["<", 2]},
        "name",
    )
    if existing:
        return existing
    doc = frappe.get_doc({"doctype": "Termination Notice", **data})
    doc.insert(ignore_permissions=True)
    return doc.name


# ─── Main Seeder ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def seed_employee_lifecycle_demo():
    """
    Seed 4 demo employees covering the full HR Suite lifecycle.
    Safe to call multiple times — skips existing records.
    """
    frappe.set_user("Administrator")
    company = _company()
    male = _gender("Male")
    female = _gender("Female")
    today = getdate(nowdate())

    result = {}

    # ── Employee 1: Ahmed Al-Ghamdi — Saudi National, Active, 3-year tenure ──────
    _ensure_user("ahmed.alghamdi@demo.hr", "Ahmed Al-Ghamdi", ("Employee Self Service",))
    ahmed = _ensure_employee({
        "employee_name": "Ahmed Al-Ghamdi",
        "first_name": "Ahmed",
        "last_name": "Al-Ghamdi",
        "gender": male,
        "date_of_birth": "1988-04-15",
        "date_of_joining": add_days(today, -1095),  # ~3 years ago
        "company": company,
        "designation": "Senior Accountant",
        "department": "Finance",
        "status": "Active",
        "user_id": "ahmed.alghamdi@demo.hr",
        "hr_suite_employee_type": "Saudi National",
        "hr_suite_gosi_salary": 10000,
    })
    _ensure_contract({
        "employee": ahmed,
        "company": company,
        "contract_type": "Open Ended",
        "nationality": "Saudi Arabia",
        "start_date": add_days(today, -1095),
        "basic_salary": 10000,
        "housing_allowance": 3000,
        "transport_allowance": 800,
        "other_allowances": 200,
        "probation_period_days": 90,
    })
    _ensure_leave({
        "employee": ahmed,
        "company": company,
        "leave_start_date": add_days(today, -60),
        "leave_end_date": add_days(today, -47),
        "description": "Annual family leave — 14 working days approved",
    })
    _ensure_gosi({
        "employee": ahmed,
        "company": company,
        "month": "May",
        "year": today.year,
        "nationality": "Saudi Arabia",
        "contribution_base": 10000,
        "employee_contribution_rate": 10.0,
        "employer_contribution_rate": 12.0,
        "employee_contribution": 1000,
        "employer_contribution": 1200,
        "total_contribution": 2200,
    })
    result["employee_1_saudi_active"] = ahmed

    # ── Employee 2: John Smith — Expatriate (UK), IT Engineer, probation ending ──
    _ensure_user("john.smith@demo.hr", "John Smith", ("Employee Self Service",))
    john = _ensure_employee({
        "employee_name": "John Smith",
        "first_name": "John",
        "last_name": "Smith",
        "gender": male,
        "date_of_birth": "1992-09-22",
        "date_of_joining": add_days(today, -75),  # joined 75 days ago — probation 90 days
        "company": company,
        "designation": "IT Engineer",
        "department": "Information Technology",
        "status": "Active",
        "user_id": "john.smith@demo.hr",
        "hr_suite_employee_type": "Expatriate",
        "hr_suite_gosi_salary": 8500,
    })
    _ensure_contract({
        "employee": john,
        "company": company,
        "contract_type": "Fixed Term",
        "nationality": "British",
        "start_date": add_days(today, -75),
        "end_date": add_days(today, 290),  # 1-year contract
        "basic_salary": 8500,
        "housing_allowance": 2500,
        "transport_allowance": 600,
        "probation_period_days": 90,
        "iqama_number": "2345678901",
        "visa_type": "Work Visa",
    })
    _ensure_iqama({
        "employee": john,
        "company": company,
        "document_type": "Iqama",
        "iqama_number": "2345678901",
        "nationality": "British",
        "issue_date": add_days(today, -75),
        "expiry_date": add_days(today, 290),
        "status": "Active",
    })
    result["employee_2_expat_probation"] = john

    # ── Employee 3: Sara Al-Dosari — Saudi, Disciplinary Case In Progress ────────
    _ensure_user("sara.aldosari@demo.hr", "Sara Al-Dosari", ("Employee Self Service",))
    sara = _ensure_employee({
        "employee_name": "Sara Al-Dosari",
        "first_name": "Sara",
        "last_name": "Al-Dosari",
        "gender": female,
        "date_of_birth": "1995-11-07",
        "date_of_joining": add_days(today, -540),  # 18 months ago
        "company": company,
        "designation": "HR Assistant",
        "department": "Human Resources",
        "status": "Active",
        "user_id": "sara.aldosari@demo.hr",
        "hr_suite_employee_type": "Saudi National",
        "hr_suite_gosi_salary": 6500,
    })
    _ensure_contract({
        "employee": sara,
        "company": company,
        "contract_type": "Open Ended",
        "nationality": "Saudi Arabia",
        "start_date": add_days(today, -540),
        "basic_salary": 6500,
        "housing_allowance": 1500,
        "transport_allowance": 500,
    })
    warning_doc = _ensure_warning({
        "employee": sara,
        "company": company,
        "warning_date": add_days(today, -30),
        "warning_level": "First Written Warning",
        "issue_reason": "Repeated unauthorised early departures from workplace (4 incidents in March).",
        "corrective_action": "Formal counselling session. Weekly check-in with line manager.",
        "due_date": add_days(today, -23),
    })
    _ensure_disciplinary({
        "employee": sara,
        "company": company,
        "incident_date": add_days(today, -14),
        "violation_category": "Attendance",
        "violation_description": "Second occurrence: unauthorised absence for 2 consecutive days without notification.",
        "status": "Under Investigation",
        "warning_notice": warning_doc,
    })
    result["employee_3_disciplinary"] = sara

    # ── Employee 4: Tariq Al-Mutairi — Operations Lead, Full Exit Lifecycle ──────
    _ensure_user("tariq.almutairi@demo.hr", "Tariq Al-Mutairi", ("Employee Self Service",))
    tariq = _ensure_employee({
        "employee_name": "Tariq Al-Mutairi",
        "first_name": "Tariq",
        "last_name": "Al-Mutairi",
        "gender": male,
        "date_of_birth": "1985-06-20",
        "date_of_joining": add_days(today, -2555),  # ~7 years ago
        "company": company,
        "designation": "Operations Lead",
        "department": "Operations",
        "status": "Active",
        "user_id": "tariq.almutairi@demo.hr",
        "hr_suite_employee_type": "Saudi National",
        "hr_suite_gosi_salary": 14000,
    })
    _ensure_contract({
        "employee": tariq,
        "company": company,
        "contract_type": "Open Ended",
        "nationality": "Saudi Arabia",
        "start_date": add_days(today, -2555),
        "basic_salary": 14000,
        "housing_allowance": 4000,
        "transport_allowance": 1000,
    })
    # Annual leave disbursement record (unused leave at exit)
    existing_ald = frappe.db.get_value(
        "Annual Leave Disbursement",
        {"employee": tariq, "docstatus": ["<", 2]},
        "name",
    )
    if not existing_ald:
        frappe.get_doc({
            "doctype": "Annual Leave Disbursement",
            "employee": tariq,
            "company": company,
            "leave_days": 22,
            "daily_wage": round(14000 / 30, 2),
            "disbursement_amount": round(22 * 14000 / 30, 2),
            "disbursement_date": add_days(today, 5),
            "notes": "22 unused annual leave days at time of resignation",
        }).insert(ignore_permissions=True)

    # Termination notice (resignation)
    termination = _ensure_termination({
        "employee": tariq,
        "employee_name": "Tariq Al-Mutairi",
        "company": company,
        "department": "Operations",
        "termination_reason": "Resignation by Employee",
        "salary_payment_type": "Monthly",
        "notice_start_date": add_days(today, -5),
        "during_probation": 0,
        "termination_notes": "Employee resigned to pursue personal business. Handover in progress.",
    })
    result["employee_4_exit"] = tariq
    result["employee_4_termination_notice"] = termination

    frappe.db.commit()

    result.update({
        "seeded_on": nowdate(),
        "company": company,
        "summary": {
            "Ahmed Al-Ghamdi": "Saudi National — Active, 3 years, with contract + leave + GOSI",
            "John Smith": "Expatriate — Probation ends in 15 days, Iqama tracked",
            "Sara Al-Dosari": "Saudi National — Disciplinary procedure in progress",
            "Tariq Al-Mutairi": "Saudi National — Resignation submitted, exit lifecycle triggered",
        },
    })
    return result
