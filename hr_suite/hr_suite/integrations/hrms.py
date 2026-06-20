"""
integrations/hrms.py
Hooks that bridge Frappe HRMS standard DocTypes (Employee, Job Offer, Salary Slip,
Leave Allocation, Appraisal) with HR Suite's country-aware modules.

All functions here are registered in hooks.py under doc_events.
"""
import frappe
from frappe.utils import flt, getdate


# ── Job Offer → Employee creation ────────────────────────────────────────────

def on_job_offer_submit(doc, method=None):
    """
    When a Job Offer is submitted in Frappe HRMS, auto-create an Employee record
    with work_country derived from the Job Opening or the company's country.
    """
    if not doc.applicant_name:
        return

    if frappe.db.exists("Employee", {"employee_name": doc.applicant_name, "status": "Active"}):
        return  # Employee already exists — do nothing

    job_opening = frappe.db.get_value(
        "Job Opening",
        doc.job_title,
        ["branch", "custom_work_country"],
        as_dict=True,
    ) or {}

    # Derive country: explicit field > branch keyword > company country
    from hr_suite.hr_suite.utils import country_name_to_code
    company = doc.company or frappe.defaults.get_user_default("company") or ""
    company_country = frappe.db.get_value("Company", company, "country") or "" if company else ""

    work_country = (
        job_opening.get("custom_work_country")
        or _country_from_branch(job_opening.get("branch"))
        or country_name_to_code(company_country)
        or ""
    )

    emp = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": doc.applicant_name,
        "company": doc.company or frappe.defaults.get_user_default("company"),
        "status": "Active",
        "date_of_joining": doc.offer_date or getdate(),
        "employment_type": "Regular",
        "gender": "Male",  # placeholder — HR updates during onboarding
    })
    emp.insert(ignore_permissions=True)

    if frappe.db.has_column("Employee", "work_country"):
        frappe.db.set_value("Employee", emp.name, "work_country", work_country)

    frappe.msgprint(
        f"Employee record <b>{emp.name}</b> created from Job Offer. "
        "Please complete the employee profile.",
        indicator="green",
    )


def _country_from_branch(branch: str) -> str:
    if not branch:
        return ""
    b = (branch or "").upper()
    mapping = {
        "SA": "SA", "SAUDI": "SA", "KSA": "SA", "RIYADH": "SA", "JEDDAH": "SA",
        "UAE": "AE", "DUBAI": "AE", "ABU DHABI": "AE",
        "BH": "BH", "BAHRAIN": "BH", "MANAMA": "BH",
        "IN": "IN", "INDIA": "IN", "BANGALORE": "IN", "MUMBAI": "IN", "DELHI": "IN",
        "OM": "OM", "OMAN": "OM", "MUSCAT": "OM",
    }
    for token, code in mapping.items():
        if token in b:
            return code
    return ""


# ── Employee after_insert → seed country defaults ────────────────────────────

def on_employee_insert(doc, method=None):
    """
    After a new Employee is created, seed leave allocations and fire country
    default setup based on work_country.
    """
    _seed_leave_allocations(doc)


def _seed_leave_allocations(emp_doc):
    from hr_suite.hr_suite.utils import seed_country_leave_types
    try:
        seed_country_leave_types(emp_doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Leave seed failed for {emp_doc.name}")


# ── Salary Slip → inject statutory deductions ────────────────────────────────

def before_salary_slip_submit(doc, method=None):
    """
    Inject country-specific statutory deductions into the Salary Slip
    as Additional Salary component lines before submission.
    Uses HR Suite Country Config rates.
    """
    from hr_suite.hr_suite.utils import (
        get_employee_work_country,
        get_country_config,
        get_employee_basic_salary_global,
    )

    employee = doc.employee
    country = get_employee_work_country(employee)
    cfg = get_country_config(country)
    if not cfg:
        return

    basic = flt(doc.get("base_gross_pay") or get_employee_basic_salary_global(employee))

    if country in ("SA", "AE", "BH", "OM"):
        _inject_gcc_deduction(doc, cfg, basic, country)
    elif country == "IN":
        _inject_india_deductions(doc, basic)


def _inject_gcc_deduction(doc, cfg, basic, country):
    scheme = cfg.statutory_scheme or ""
    if not scheme or scheme in ("None", "EPF+ESI", "DEWS"):
        return

    ceiling = flt(cfg.contribution_ceiling)
    base = min(basic, ceiling) if ceiling else basic

    # Use national rate for locals, expat rate for foreign nationals
    from hr_suite.hr_suite.utils import get_employee_is_national
    is_national = get_employee_is_national(doc.employee, country)
    emp_rate = flt(cfg.national_employee_rate if is_national else cfg.expat_employee_rate)
    if not emp_rate:
        return

    emp_amount = round(base * emp_rate / 100, 2)
    _upsert_deduction_component(doc, scheme, emp_amount)


def _inject_india_deductions(doc, basic):
    from hr_suite.hr_suite.doctype.epf_esi_contribution.epf_esi_contribution import (
        EPF_WAGE_CEILING, ESI_GROSS_CEILING
    )
    epf_wage = min(basic, EPF_WAGE_CEILING)
    epf_amount = round(epf_wage * 0.12, 2)
    _upsert_deduction_component(doc, "EPF", epf_amount)

    gross = flt(doc.get("gross_pay") or basic)
    if gross <= ESI_GROSS_CEILING:
        esi_amount = round(gross * 0.0075, 2)
        _upsert_deduction_component(doc, "ESI", esi_amount)


def _upsert_deduction_component(doc, component_name: str, amount: float):
    if not amount:
        return
    if not frappe.db.exists("Salary Component", component_name):
        frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": component_name,
            "salary_component_abbr": component_name[:4].upper(),
            "type": "Deduction",
            "is_tax_applicable": 0,
        }).insert(ignore_permissions=True)

    for row in doc.get("deductions") or []:
        if row.salary_component == component_name:
            row.amount = amount
            return

    doc.append("deductions", {
        "salary_component": component_name,
        "amount": amount,
    })


# ── Appraisal → push rating to Staff Rating ──────────────────────────────────

def on_appraisal_submit(doc, method=None):
    """
    When a Frappe HRMS Appraisal is submitted, create / update a Staff Rating
    in HR Suite so the rating feeds into EOSB / gratuity multiplier.
    """
    if not frappe.db.exists("DocType", "Staff Rating"):
        return

    score = flt(doc.get("total_score") or doc.get("score"))
    if not score:
        return

    existing = frappe.db.get_value(
        "Staff Rating",
        {"employee": doc.employee, "appraisal_cycle": doc.appraisal_cycle or doc.name},
        "name",
    )
    if existing:
        frappe.db.set_value("Staff Rating", existing, "rating_score", score)
        return

    sr = frappe.get_doc({
        "doctype": "Staff Rating",
        "employee": doc.employee,
        "rating_date": doc.end_date or getdate(),
        "rating_score": score,
        "appraisal_cycle": doc.appraisal_cycle or "",
        "notes": f"Auto-created from Appraisal {doc.name}",
    })
    try:
        sr.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Staff Rating sync failed for {doc.employee}")


# ── Employee status "Left" → trigger exit checklist ──────────────────────────

def on_employee_update(doc, method=None):
    """
    When Employee status changes to 'Left', auto-create an Exit Clearance record
    and a Final Settlement SLA reminder if they don't already exist.
    """
    if doc.status != "Left":
        return

    _ensure_exit_clearance(doc)
    _ensure_final_settlement_sla(doc)


def _ensure_exit_clearance(emp_doc):
    if not frappe.db.exists("DocType", "Exit Clearance"):
        return
    if frappe.db.exists("Exit Clearance", {"employee": emp_doc.name, "docstatus": ["<", 2]}):
        return
    try:
        ec = frappe.get_doc({
            "doctype": "Exit Clearance",
            "employee": emp_doc.name,
        })
        ec.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Exit Clearance auto-create failed for {emp_doc.name}")


def _ensure_final_settlement_sla(emp_doc):
    if not frappe.db.exists("DocType", "Final Settlement SLA"):
        return
    if frappe.db.exists("Final Settlement SLA", {"employee": emp_doc.name}):
        return
    from frappe.utils import add_days
    try:
        sla = frappe.get_doc({
            "doctype": "Final Settlement SLA",
            "employee": emp_doc.name,
            "due_date": add_days(getdate(), 30),
        })
        sla.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Final Settlement SLA auto-create failed for {emp_doc.name}")
