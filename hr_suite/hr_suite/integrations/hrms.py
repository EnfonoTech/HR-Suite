"""
integrations/hrms.py
Hooks that bridge Frappe HRMS standard DocTypes (Employee, Job Offer, Salary Slip,
Leave Allocation, Appraisal) with HR Suite's country-aware modules.

All functions here are registered in hooks.py under doc_events.
"""
import frappe
from frappe.utils import flt, getdate

# Error Log title used by every statutory-deduction diagnostic, so a site can filter
# `Error Log` by method to see exactly which payroll runs skipped a deduction.
_ERROR_TITLE_STATUTORY = "HR Suite: statutory deduction not injected"


# ── Job Offer → Employee creation ────────────────────────────────────────────

def on_job_offer_submit(doc, method=None):
    """When a Job Offer is submitted in Frappe HRMS, auto-create an Employee record."""
    if not doc.applicant_name:
        return

    if frappe.db.exists("Employee", {"employee_name": doc.applicant_name, "status": "Active"}):
        return  # Employee already exists — do nothing

    # Job Offer has no direct job_title field; resolve via Job Applicant → Job Opening
    job_opening_name = (
        frappe.db.get_value("Job Applicant", doc.job_applicant, "job_title")
        if doc.job_applicant
        else None
    )
    # `branch` and `custom_work_country` are site customisations — HRMS's own Job Opening
    # ships neither, and querying a column that does not exist is a hard SQL error.
    opening_meta = frappe.get_meta("Job Opening")
    opening_fields = [f for f in ("branch", "custom_work_country", "location") if opening_meta.has_field(f)]
    job_opening = (
        frappe.db.get_value("Job Opening", job_opening_name, opening_fields, as_dict=True)
        if job_opening_name and opening_fields
        else {}
    ) or {}

    # Derive country: explicit field > branch keyword > company country
    from hr_suite.hr_suite.utils import country_name_to_code
    company = doc.company or frappe.defaults.get_user_default("company") or ""
    company_country = frappe.db.get_value("Company", company, "country") or "" if company else ""

    work_country = (
        job_opening.get("custom_work_country")
        or _country_from_branch(job_opening.get("branch") or job_opening.get("location"))
        or country_name_to_code(company_country)
        or ""
    )

    emp = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": doc.applicant_name,
        "company": doc.company or frappe.defaults.get_user_default("company"),
        "status": "Active",
        "date_of_joining": doc.offer_date or getdate(),
        "designation": doc.designation or "",
        "gender": "Male",  # placeholder — HR updates during onboarding
    })
    emp.insert(ignore_permissions=True)

    # The derived work country is only storable where the site added the field — same
    # guard Country Employment Contract uses when it syncs the country back.
    if work_country and frappe.db.has_column("Employee", "work_country"):
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
    Inject country-specific statutory deductions into the Salary Slip as extra
    deduction rows before submission, using HR Suite Country Config rates.

    CONSTRAINT — THIS HOOK MUST NEVER RAISE. Read before changing it.

    `PayrollEntry.submit_salary_slips_for_employees`
    (hrms/payroll/doctype/payroll_entry/payroll_entry.py:1570-1608) submits every slip
    first and only afterwards builds the accrual Journal Entry. That whole block sits
    inside one `try: ... except Exception: frappe.db.rollback()`, so ANYTHING that
    throws after the slips are submitted rolls the entire payroll run back and leaves
    only a Payroll Failure Log behind.

    Two consequences:

    1. A deduction component we inject here is read back by
       `PayrollEntry.get_salary_component_account` (payroll_entry.py:334-349), which
       throws `Please set account in Salary Component {0}` when the component has no
       `Salary Component Account` row for the payroll company. A component created
       without accounts therefore kills every payroll run — and the message names the
       Salary Component, not HR Suite, so nobody traces it back here. That is why
       `_upsert_deduction_component` resolves an account BEFORE it touches the slip and
       skips the injection outright when it cannot.

    2. Any other unexpected error here would do the same. A statutory-deduction
       convenience must not be able to roll back payroll, so the body is wrapped and
       failures are logged, not propagated. Validation that SHOULD stop the user
       belongs on the Salary Structure / Salary Component, not in this hook.
    """
    try:
        _inject_statutory_deductions(doc)
    except Exception:
        frappe.log_error(
            title=_ERROR_TITLE_STATUTORY,
            message=frappe.get_traceback(),
        )


def _inject_statutory_deductions(doc):
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

    # Must be the employee's actual Basic component, not Salary Slip gross pay —
    # EPF/GCC ceilings apply to Basic only, and gross pay overstates it whenever
    # HRA/other allowances exist.
    basic = flt(get_employee_basic_salary_global(employee))

    if country in ("SA", "AE", "BH", "OM"):
        _inject_gcc_deduction(doc, cfg, basic, country)
    elif country == "IN":
        _inject_india_deductions(doc, basic)

    # before_submit runs after HRMS's own validate()/set_net_pay(), which already
    # computed total_deduction/net_pay from the deductions table as it stood then.
    # Recompute now so the injected row above is actually reflected on the submitted slip.
    doc.set_net_pay()


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
    """Set the statutory deduction row on the slip, but only if it is safe to post.

    A deduction row whose Salary Component has no `Salary Component Account` for
    `doc.company` makes the payroll accrual JE throw and rolls the whole run back
    (see `before_salary_slip_submit`). So the component's accounting is settled up
    front; when it cannot be, nothing is injected and the reason is logged.
    """
    if not amount:
        return

    if not _ensure_salary_component_account(component_name, doc.company):
        return

    for row in doc.get("deductions") or []:
        if row.salary_component == component_name:
            row.amount = amount
            return

    doc.append("deductions", {
        "salary_component": component_name,
        "amount": amount,
    })


def _ensure_salary_component_account(component_name: str, company: str) -> bool:
    """Statutory-injection wrapper. True when the component is safe to post."""
    ok, _reason = ensure_salary_component_account(component_name, company)
    return ok


def ensure_salary_component_account(
    component_name: str,
    company: str,
    component_type: str = "Deduction",
    fallback_account: str = "",
    depends_on_payment_days: int = 1,
    error_title: str = _ERROR_TITLE_STATUTORY,
) -> tuple:
    """Guarantee a `Salary Component Account` exists for (component, company).

    Returns ``(True, "")`` when the component may be posted for this company, and
    ``(False, reason)`` otherwise — `reason` being a finished sentence fit to show a
    user, so a caller can refuse to create its deduction and say why instead of
    letting `PayrollEntry.get_salary_component_account` (payroll_entry.py:334-349)
    throw mid-run and roll every Salary Slip back.

    Resolution order:
      1. an existing `Salary Component Account` row for this component + company;
      2. an `Hr Suite Settings` → Deduction Accounts row naming THIS component
         for this company;
      3. an `Hr Suite Settings` → Deduction Accounts row for this company with no
         component named (the generic statutory mapping);
      4. `fallback_account`, when the caller can derive one from the Chart of
         Accounts itself (Employee Loan uses the same receivable its disbursement
         Journal Entry debits, so recovery and disbursement net off);
      5. nothing — the caller is told why and posts nothing.

    The component is CREATED when it does not exist, but only once an account has
    been resolved, so this never leaves an unpostable component behind.
    """
    from frappe import _

    if not company:
        reason = _("The document has no Company, so Salary Component {0} cannot be account-mapped.").format(
            component_name
        )
        frappe.log_error(title=error_title, message=reason)
        return False, reason

    component_exists = bool(frappe.db.exists("Salary Component", component_name))

    if component_exists and frappe.db.get_value(
        "Salary Component Account",
        {"parent": component_name, "parenttype": "Salary Component", "company": company},
        "account",
    ):
        return True, ""

    account = _get_configured_deduction_account(company, component_name) or _validated_account(
        fallback_account, company
    )
    if not account:
        reason = _(
            "Salary Component {0} has no account for {1}. Map one under HR Suite Settings "
            "\u2192 Deduction Accounts, or add a Salary Component Account row on the component "
            "itself. Nothing was posted, so the payroll run is not rolled back by the accrual "
            "Journal Entry."
        ).format(component_name, company)
        frappe.log_error(title=error_title, message=reason)
        return False, reason

    if component_exists:
        component = frappe.get_doc("Salary Component", component_name)
    else:
        component = frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": component_name,
            "salary_component_abbr": component_name[:4].upper(),
            "type": component_type,
            "is_tax_applicable": 0,
            # A recovery of a fixed sum (a loan instalment, a penalty) is NOT scaled by
            # payment days; only pay-rate components are. Salary Component defaults this
            # to 1, so it has to be said explicitly.
            "depends_on_payment_days": depends_on_payment_days,
        })

    component.append("accounts", {"company": company, "account": account})
    if component_exists:
        component.save(ignore_permissions=True)
    else:
        component.insert(ignore_permissions=True)
    return True, ""


def _validated_account(account: str, company: str) -> str:
    """`account` if it is a real postable account of `company`, else ""."""
    if not account:
        return ""
    row = frappe.db.get_value("Account", account, ["company", "is_group"], as_dict=True)
    if not row or row.company != company or row.is_group:
        return ""
    return account


def _get_configured_deduction_account(company: str, component_name: str = "") -> str:
    """Deduction account mapped on Hr Suite Settings for this company, or "".

    A row naming the component wins over the generic company row, so a site can send
    loan recovery to the employee-loan receivable while GOSI still lands on its own
    liability.
    """
    settings = frappe.get_cached_doc("Hr Suite Settings")
    generic = ""
    for row in settings.get("statutory_deduction_accounts") or []:
        if row.company != company or not row.account:
            continue
        # A mapping left pointing at another company's tree would produce a GL entry
        # the accrual JE cannot post, so it is treated as unconfigured.
        if frappe.db.get_value("Account", row.account, "company") != company:
            continue
        row_component = (row.get("salary_component") or "").strip()
        if row_component and row_component == component_name:
            return row.account
        if not row_component and not generic:
            generic = row.account
    return generic


def _get_configured_statutory_account(company: str) -> str:
    """Kept for callers that only want the generic per-company statutory mapping."""
    return _get_configured_deduction_account(company)


def get_employee_payroll_currency(employee: str, on_date=None, company: str = "") -> str:
    """The currency an `Additional Salary` for this employee must carry.

    `Additional Salary.currency` is mandatory and read-only, so a server-side creator
    has to set it: hrms's own creators all do (employee_incentive.py:30,
    employee_advance.py:318). It is the currency of the Salary Structure Assignment in
    force — the same value `get_employee_currency`
    (salary_structure_assignment.py:196-204) returns — falling back to the company
    default. Returns "" when neither is known, which is the caller's signal to refuse.
    """
    filters = {"employee": employee, "docstatus": 1}
    if on_date:
        filters["from_date"] = ["<=", on_date]

    currency = frappe.db.get_value(
        "Salary Structure Assignment", filters, "currency", order_by="from_date desc"
    )
    if currency:
        return currency

    if company:
        return frappe.db.get_value("Company", company, "default_currency") or ""
    return ""


# ── Salary Slip / Additional Salary → Employee Loan write-back ───────────────
#
# These three hooks NEVER touch the Salary Slip's earnings or deductions. They only
# record, on the Employee Loan, what the payroll documents did — which instalment a
# submitted slip actually took, and which instalment a cancelled slip or a cancelled
# booking gave back. That write-back is what makes re-running a payroll period
# idempotent instead of double-deducting.
#
# Like `before_salary_slip_submit`, they must never raise: a failure after the slips are
# submitted sits inside `PayrollEntry.submit_salary_slips_for_employees`'s single
# try/except (payroll_entry.py:1570-1608) and would roll the entire run back. A loan
# ledger that is briefly out of step is recoverable; a rolled-back payroll is not.

_ERROR_TITLE_LOAN_WRITEBACK = "HR Suite: loan instalment write-back failed"


def on_salary_slip_submit(doc, method=None):
    try:
        from hr_suite.hr_suite.doctype.employee_loan.employee_loan import (
            mark_installments_deducted_from_salary_slip,
        )

        mark_installments_deducted_from_salary_slip(doc)
    except Exception:
        frappe.log_error(title=_ERROR_TITLE_LOAN_WRITEBACK, message=frappe.get_traceback())


def on_salary_slip_cancel(doc, method=None):
    try:
        from hr_suite.hr_suite.doctype.employee_loan.employee_loan import (
            release_installments_from_salary_slip,
        )

        release_installments_from_salary_slip(doc)
    except Exception:
        frappe.log_error(title=_ERROR_TITLE_LOAN_WRITEBACK, message=frappe.get_traceback())


def on_additional_salary_cancel(doc, method=None):
    """Free the loan instalment a cancelled/deleted Additional Salary was booking.

    Frappe refuses to cancel an Additional Salary that a SUBMITTED Salary Slip links to
    (`Salary Detail.additional_salary` is a Link field on a submitted document), so
    reaching here means no payslip has taken the money and the instalment is genuinely
    free to be deducted in a later period.
    """
    if doc.get("ref_doctype") != "Employee Loan":
        return
    try:
        from hr_suite.hr_suite.doctype.employee_loan.employee_loan import (
            release_installment_for_additional_salary,
        )

        release_installment_for_additional_salary(doc.name)
    except Exception:
        frappe.log_error(title=_ERROR_TITLE_LOAN_WRITEBACK, message=frappe.get_traceback())


# ── Appraisal ────────────────────────────────────────────────────────────────
#
# `on_appraisal_submit` was REMOVED here, together with its `Appraisal: on_submit`
# registration in hooks.py. It had two defects that made it unsafe to keep:
#
#   * it wrote `rating` onto an already-SUBMITTED `Staff Rating` with
#     `frappe.db.set_value` although that field is not `allow_on_submit` — a silent
#     write around the submit contract, invisible to the version history;
#   * it attributed the rating to `Employee.reports_to`, and bailed out entirely when
#     that was empty. On sft-uat all 17 employees have `reports_to` NULL, so the hook
#     was a no-op there anyway.
#
# It also carried a dead branch that synced `hrsuite_promotion_transfer` /
# `hrsuite_salary_adjustment` from the Appraisal onto Promotion Transfer / Salary
# Adjustment. Neither Custom Field is shipped by hr_suite (`fixtures/custom_field.json`
# has no Appraisal row), so `doc.get(...)` was always None and nothing was ever synced.
#
# The Appraisal surface — scoring, appraiser/reviewer and any downstream sync — is
# owned by the HR Suite Performance Management module. Register that module's own
# handler on `Appraisal: on_submit`; do not reinstate this one.

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
    try:
        # Final Settlement SLA derives settlement_due_date / document_return_due_date from
        # last_working_day in validate_compliance_doc — feed it that, not a due_date field
        # the DocType does not have.
        sla = frappe.get_doc({
            "doctype": "Final Settlement SLA",
            "employee": emp_doc.name,
            "last_working_day": emp_doc.relieving_date or getdate(),
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
        # Exclude current doc only if it's already in the DB (submitted amendment)
        exclude_name = doc.name if not doc.is_new() else "__never__"
        existing_sick = frappe.db.sql(
            """SELECT COALESCE(SUM(total_leave_days), 0)
               FROM `tabLeave Application`
               WHERE employee=%s AND leave_type LIKE %s
                 AND from_date BETWEEN %s AND %s
                 AND docstatus=1 AND name!=%s""",
            (employee, "%sick%", year_start, year_end, exclude_name),
        )
        # Threshold applies to the cumulative total *including* this application,
        # not just what was used before it — otherwise the request that actually
        # crosses a tier boundary never gets the warning for its own days.
        sick_days_before = flt(existing_sick[0][0]) if existing_sick else 0
        sick_days_used = sick_days_before + flt(doc.total_leave_days)
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


# ── Payroll Entry → statutory contribution stubs ──────────────────────────────

def on_payroll_entry_submit(doc, method=None):
    """
    After HRMS Payroll Entry is submitted, auto-create the appropriate statutory
    contribution record for each employee in the run, based on their work country.
    """
    from hr_suite.hr_suite.utils import (
        country_name_to_code, get_country_config, get_employee_work_country,
        get_employee_basic_salary_global,
    )
    company = doc.company or frappe.defaults.get_user_default("company")
    if not company:
        return

    payroll_date = doc.start_date or doc.posting_date
    if not payroll_date:
        frappe.log_error("HR Suite: Payroll Entry has no start_date or posting_date — skipping contribution stub creation")
        return
    month_name = _month_from_payroll_date(payroll_date)
    year = getdate(payroll_date).year  # Int — matches DocType field type

    default_country = country_name_to_code(frappe.db.get_value("Company", company, "country") or "") or \
        country_name_to_code(frappe.db.get_single_value("Hr Suite Settings", "default_work_country") or "")

    for row in doc.employees:
        country = get_employee_work_country(row.employee) or default_country
        if not country:
            continue

        cfg = get_country_config(country)
        if not cfg:
            continue

        basic = get_employee_basic_salary_global(row.employee)
        if not basic:
            continue

        if country == "SA":
            _ensure_gosi_contribution(row.employee, row.employee_name, company, month_name, year, basic)
        elif country == "IN":
            _ensure_epfesi_contribution(row.employee, row.employee_name, company, month_name, year, basic)
        else:
            _ensure_statutory_contribution(row.employee, row.employee_name, company, country, cfg, month_name, year, basic)


def _month_from_payroll_date(date_str):
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    try:
        return months[getdate(date_str).month - 1]
    except Exception:
        return "January"


def _ensure_gosi_contribution(employee, employee_name, company, month_name, year, contribution_base):
    if not frappe.db.exists("DocType", "GOSI Contribution"):
        return
    if frappe.db.exists("GOSI Contribution", {"employee": employee, "month": month_name, "year": year, "company": company}):
        return
    try:
        frappe.get_doc({
            "doctype": "GOSI Contribution",
            "employee": employee,
            "employee_name": employee_name,
            "company": company,
            "month": month_name,
            "year": year,
            "contribution_base": contribution_base,
            "payment_status": "Pending",
        }).insert(ignore_permissions=True)
        frappe.msgprint(
            f"GOSI Contribution record created for {employee_name} — {month_name} {year}. Open it to review and submit.",
            indicator="blue", alert=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: GOSI Contribution auto-create failed")


def _ensure_epfesi_contribution(employee, employee_name, company, month_name, year, basic_salary):
    if not frappe.db.exists("DocType", "EPF ESI Contribution"):
        return
    if frappe.db.exists("EPF ESI Contribution", {"employee": employee, "month": month_name, "year": year, "company": company}):
        return
    try:
        frappe.get_doc({
            "doctype": "EPF ESI Contribution",
            "employee": employee,
            "employee_name": employee_name,
            "company": company,
            "month": month_name,
            "year": year,
            "basic_salary": basic_salary,
        }).insert(ignore_permissions=True)
        frappe.msgprint(
            f"EPF/ESI Contribution record created for {employee_name} — {month_name} {year}.",
            indicator="blue", alert=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: EPF/ESI Contribution auto-create failed")


def _ensure_statutory_contribution(employee, employee_name, company, country, cfg, month_name, year, contribution_base):
    if not frappe.db.exists("DocType", "Statutory Contribution"):
        return
    if frappe.db.exists("Statutory Contribution", {
        "employee": employee, "month": month_name, "year": year, "company": company, "work_country": country,
    }):
        return
    try:
        frappe.get_doc({
            "doctype": "Statutory Contribution",
            "employee": employee,
            "employee_name": employee_name,
            "company": company,
            "work_country": country,
            "scheme": cfg.statutory_scheme or "Other",
            "month": month_name,
            "year": year,
            "contribution_base": contribution_base,
        }).insert(ignore_permissions=True)
        frappe.msgprint(
            f"{cfg.statutory_scheme or 'Statutory'} Contribution record created for "
            f"{employee_name} — {month_name} {year} ({cfg.country_name}).",
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
    # HRMS Employee Separation doctype: reason is on the Employee record itself
    hrms_reason = frappe.db.get_value("Employee", employee, "reason_for_leaving") or ""
    termination_reason = reason_map.get(hrms_reason, "Termination by Employer")
    # Employee Separation has resignation_letter_date and boarding_begins_on;
    # authoritative exit date is Employee.relieving_date
    separation_date = str(
        doc.resignation_letter_date
        or doc.boarding_begins_on
        or frappe.db.get_value("Employee", employee, "relieving_date")
        or getdate()
    )

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
            "termination_reason": _eosb_select_reason(termination_reason),
            "last_basic_salary": flt(result.get("basic_salary")),
            "eosb_gross": flt(result.get("gross_entitlement")),
            "net_eosb": flt(result.get("net_entitlement")),
            "calculation_notes": (
                f"Auto-created from Employee Separation {doc.name}.\n"
                f"Country: {country} | Formula: {result.get('formula', '')}\n"
                f"{result.get('notes') or result.get('calculation_notes') or ''}"
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


# End of Service Benefit.termination_reason is a Select field with a fixed set of
# options; the human-readable reasons used for settlement-formula token matching
# (e.g. "Resignation by Employee") don't all line up with it, so translate here.
_EOSB_SELECT_REASON_MAP = {
    "Resignation by Employee": "Resignation",
    "Termination by Employer": "Termination by Employer",
    "End of Contract": "End of Fixed Term",
    "Retirement": "Retirement",
    "Death": "Death",
    "Disciplinary Dismissal (Article 80)": "Dismissal",
}


def _eosb_select_reason(termination_reason: str) -> str:
    return _EOSB_SELECT_REASON_MAP.get(termination_reason, "Termination by Employer")


# ── Exit Interview → sync Exit Clearance completion flag ─────────────────────

def on_exit_interview_update(doc, method=None):
    """Sync exit interview completion flag back to linked Exit Clearance."""
    _sync_exit_clearance_completion(doc, force_incomplete=False)


def on_exit_interview_trash(doc, method=None):
    """Clear the exit interview completion flag when the record is deleted."""
    _sync_exit_clearance_completion(doc, force_incomplete=True)


def _sync_exit_clearance_completion(doc, force_incomplete=False):
    ec = doc.get("hrsuite_exit_clearance") or frappe.db.get_value(
        "Exit Clearance", {"exit_interview": doc.name, "docstatus": ["<", 2]}, "name"
    )
    if not ec or not frappe.db.exists("Exit Clearance", ec):
        return
    COMPLETED = {"Completed", "Cancelled"}
    is_completed = 0 if force_incomplete else int((doc.status or "") in COMPLETED)
    frappe.db.set_value(
        "Exit Clearance",
        ec,
        "exit_interview_completed",
        is_completed,
        update_modified=False,
    )


# ── Salary Structure Assignment → minimum wage guard ──────────────────────────

def validate_minimum_wage(doc, method=None):
    """Block submission if Base is below the employee's country's configured minimum wage."""
    from frappe import _
    from frappe.utils import flt
    from hr_suite.hr_suite.utils import get_employee_work_country, get_country_config

    if not doc.employee:
        return

    country = get_employee_work_country(doc.employee)
    cfg = get_country_config(country)
    minimum_wage = flt(cfg.minimum_wage) if cfg else 0
    if not minimum_wage:
        return

    if flt(doc.base) < minimum_wage:
        frappe.throw(_("Below Minimum Wage: Base ({0}) is less than the minimum wage ({1}) for {2}").format(
            flt(doc.base), minimum_wage, cfg.country_name or country
        ))
