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


# ── Leave Application → country-aware validation ──────────────────────────────

def on_leave_application_validate(doc, method=None):
    """
    Validate leave against country-specific rules from Country Config.
    Warns on mismatched leave types and sick leave pay thresholds.
    """
    from hr_suite.hr_suite.utils import get_employee_work_country, get_country_config, get_sick_leave_pay
    employee = doc.employee
    country = get_employee_work_country(employee)
    cfg = get_country_config(country)
    if not cfg:
        return

    # Warn if leave type is not in Country Config leave list
    if cfg.leave_types:
        allowed_names = [lt.leave_type_name for lt in cfg.leave_types]
        leave_type = doc.leave_type or ""
        if allowed_names and not any(leave_type in name or name in leave_type for name in allowed_names):
            frappe.msgprint(
                f"Leave type <b>{leave_type}</b> is not in the Country Config for <b>{cfg.country_name}</b>. "
                "Verify this is correct.",
                indicator="orange",
                alert=True,
            )

    # Sick leave: warn on pay threshold
    if doc.leave_type and "sick" in doc.leave_type.lower():
        from frappe.utils import get_year_start, get_year_ending
        year_start = get_year_start(getdate(doc.from_date))
        year_end = get_year_ending(getdate(doc.from_date))
        existing_sick = frappe.db.sql(
            """SELECT COALESCE(SUM(total_leave_days), 0)
               FROM `tabLeave Application`
               WHERE employee=%s AND leave_type LIKE %s
                 AND from_date BETWEEN %s AND %s
                 AND docstatus=1 AND name!=%s""",
            (employee, "%sick%", year_start, year_end, doc.name or "__new__"),
        )
        sick_days_used = flt(existing_sick[0][0]) if existing_sick else 0
        pay_info = get_sick_leave_pay(employee, int(sick_days_used))
        if pay_info["rate"] == 0.0:
            frappe.msgprint(
                f"Employee has used {sick_days_used:.0f} sick days this year — additional sick leave will be "
                f"<b>unpaid</b> per {cfg.country_name} labor law.",
                indicator="orange",
                alert=True,
            )
        elif pay_info["rate"] < 1.0:
            frappe.msgprint(
                f"Employee has used {sick_days_used:.0f} sick days — this leave will be at "
                f"<b>{pay_info['label']}</b> per {cfg.country_name} labor law.",
                indicator="blue",
                alert=True,
            )


# ── Leave Allocation → sync with Country Config ───────────────────────────────

def on_leave_allocation_submit(doc, method=None):
    """
    When HRMS Leave Allocation is submitted, compare allocated days against
    the Country Config entitlement and warn if there's a mismatch.
    """
    from hr_suite.hr_suite.utils import get_employee_work_country, get_country_config
    country = get_employee_work_country(doc.employee)
    cfg = get_country_config(country)
    if not cfg or not cfg.leave_types:
        return

    for lt in cfg.leave_types:
        if lt.leave_type_name == doc.leave_type:
            expected_days = flt(lt.get("days_per_year") or lt.get("days_above_threshold") or 0)
            if expected_days and flt(doc.new_leaves_allocated) != expected_days:
                frappe.msgprint(
                    f"Country Config for <b>{cfg.country_name}</b> expects <b>{expected_days:.0f} days</b> "
                    f"for {doc.leave_type}. Allocated: {flt(doc.new_leaves_allocated):.0f}. "
                    "Update if this differs intentionally.",
                    indicator="orange",
                    alert=True,
                )
            break


# ── Salary Structure Assignment → minimum wage check ─────────────────────────

def on_salary_structure_assignment_submit(doc, method=None):
    """
    Block submission if the assigned base salary is below the country minimum wage
    defined in Country Config.
    """
    from hr_suite.hr_suite.utils import get_employee_work_country, get_country_config
    country = get_employee_work_country(doc.employee)
    cfg = get_country_config(country)
    if not cfg:
        return

    min_wage = flt(cfg.get("minimum_wage") or 0)
    if not min_wage:
        return

    base = flt(doc.base or 0)
    if base and base < min_wage:
        from frappe.utils import fmt_money
        frappe.throw(
            f"Assigned base salary <b>{fmt_money(base, currency=cfg.currency)}</b> is below the "
            f"minimum wage for <b>{cfg.country_name}</b> "
            f"(<b>{fmt_money(min_wage, currency=cfg.currency)}</b>).",
            title="Below Minimum Wage",
        )


# ── Payroll Entry → statutory contribution stubs ──────────────────────────────

def on_payroll_entry_submit(doc, method=None):
    """
    After HRMS Payroll Entry is submitted, auto-create the appropriate statutory
    contribution record for the company's country.
    """
    from hr_suite.hr_suite.utils import country_name_to_code, get_country_config
    company = doc.company or frappe.defaults.get_user_default("company")
    if not company:
        return

    company_country = frappe.db.get_value("Company", company, "country") or ""
    country = country_name_to_code(company_country) or \
        (frappe.db.get_single_value("Hr Suite Settings", "default_work_country") or "")
    if not country:
        return

    cfg = get_country_config(country)
    if not cfg:
        return

    month_name = _month_from_payroll_date(doc.start_date or doc.posting_date)
    year = str(getdate(doc.start_date or doc.posting_date).year)

    if country == "SA":
        _ensure_gosi_contribution(company, month_name, year)
    elif country == "IN":
        _ensure_epfesi_contribution(company, month_name, year)
    else:
        _ensure_statutory_contribution(company, country, cfg, month_name, year)


def _month_from_payroll_date(date_str):
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    try:
        return months[getdate(date_str).month - 1]
    except Exception:
        return "January"


def _ensure_gosi_contribution(company, month_name, year):
    if not frappe.db.exists("DocType", "GOSI Contribution"):
        return
    if frappe.db.exists("GOSI Contribution", {"month": month_name, "year": year, "company": company}):
        return
    try:
        frappe.get_doc({
            "doctype": "GOSI Contribution",
            "month": month_name,
            "year": year,
            "company": company,
            "payment_status": "Pending",
        }).insert(ignore_permissions=True)
        frappe.msgprint(
            f"GOSI Contribution record created for {month_name} {year}. Open it to review and submit.",
            indicator="blue", alert=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: GOSI Contribution auto-create failed")


def _ensure_epfesi_contribution(company, month_name, year):
    if not frappe.db.exists("DocType", "EPF ESI Contribution"):
        return
    if frappe.db.exists("EPF ESI Contribution", {"month": month_name, "year": year, "company": company}):
        return
    try:
        frappe.get_doc({
            "doctype": "EPF ESI Contribution",
            "month": month_name,
            "year": year,
            "company": company,
            "payment_status": "Pending",
        }).insert(ignore_permissions=True)
        frappe.msgprint(
            f"EPF/ESI Contribution record created for {month_name} {year}.",
            indicator="blue", alert=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: EPF/ESI Contribution auto-create failed")


def _ensure_statutory_contribution(company, country, cfg, month_name, year):
    if not frappe.db.exists("DocType", "Statutory Contribution"):
        return
    if frappe.db.exists("Statutory Contribution", {
        "month": month_name, "year": year, "company": company, "country_code": country,
    }):
        return
    try:
        frappe.get_doc({
            "doctype": "Statutory Contribution",
            "month": month_name,
            "year": year,
            "company": company,
            "country_code": country,
            "scheme": cfg.statutory_scheme or "",
            "payment_status": "Pending",
        }).insert(ignore_permissions=True)
        frappe.msgprint(
            f"{cfg.statutory_scheme or 'Statutory'} Contribution record created for "
            f"{month_name} {year} ({cfg.country_name}).",
            indicator="blue", alert=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Statutory Contribution auto-create failed ({country})")


# ── Employee Separation → auto-create EOSB / settlement ──────────────────────

def on_employee_separation_submit(doc, method=None):
    """
    When HRMS Employee Separation is submitted, auto-calculate settlement
    using the country formula and create an End of Service Benefit record.
    """
    from hr_suite.hr_suite.utils import get_employee_work_country, calculate_settlement
    employee = doc.employee
    country = get_employee_work_country(employee)

    reason_map = {
        "Resigned": "Resignation by Employee",
        "Resigned - Loss of Confidence": "Resignation by Employee",
        "Laid Off": "Termination by Employer",
        "Terminated": "Termination by Employer",
        "Retired": "Retirement",
        "Contract Completion": "End of Contract",
        "Death": "Death",
        "Absconding": "Disciplinary Dismissal (Article 80)",
    }
    termination_reason = reason_map.get(doc.reason_for_leaving or "", "Termination by Employer")
    separation_date = str(doc.resignation_date or doc.last_working_day or getdate())

    try:
        result = calculate_settlement(
            employee=employee,
            termination_reason=termination_reason,
            termination_date=separation_date,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: Settlement calc failed for {employee}")
        return

    if not frappe.db.exists("DocType", "End of Service Benefit"):
        return
    if frappe.db.exists("End of Service Benefit", {"employee": employee, "docstatus": ["<", 2]}):
        return

    try:
        eosb = frappe.get_doc({
            "doctype": "End of Service Benefit",
            "employee": employee,
            "termination_date": separation_date,
            "termination_reason": termination_reason,
            "last_basic_salary": flt(result.get("basic_salary")),
            "eosb_gross": flt(result.get("gross_entitlement")),
            "net_eosb": flt(result.get("net_entitlement")),
            "calculation_notes": (
                f"Auto-created from Employee Separation {doc.name}.\n"
                f"Country: {country} | Formula: {result.get('formula', '')}\n"
                f"{result.get('notes', '')}"
            ),
        })
        eosb.insert(ignore_permissions=True)
        frappe.msgprint(
            f"End of Service Benefit <b>{eosb.name}</b> created. "
            f"Net: <b>{result.get('net_entitlement', 0):,.2f}</b>. Please review and submit.",
            indicator="green",
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"HR Suite: EOSB auto-create failed for {employee}")
