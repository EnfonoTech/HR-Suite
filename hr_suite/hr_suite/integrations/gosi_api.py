"""
integrations/gosi_api.py

GOSI — General Organization for Social Insurance (Saudi Arabia)
Saudi employer API integration for:
  · register_employee       — register new hire with GOSI
  · deregister_employee     — exit/deregister employee
  · get_employee_status     — check GOSI membership status for a Saudi ID
  · submit_contribution     — submit a single GOSI Contribution record to the portal
  · submit_monthly_batch    — submit all Pending GOSI Contributions for a period
  · get_contribution_cert   — fetch GOSI clearance / coverage certificate for company
  · get_employer_account    — employer account summary and outstanding balance
  · sync_monthly            — monthly scheduler hook

Credentials stored in Hr Suite Settings (gosi_api_* fields).
Every API call is logged to Government Portal Sync Log (portal = "GOSI").
"""
import frappe
import requests
from frappe.utils import now_datetime, getdate, add_months, format_date

_TIMEOUT = 30


# ── Shared helpers ────────────────────────────────────────────────────────────

def _settings():
    return frappe.get_single("Hr Suite Settings")


def _log(sync_type, ref, status, data, employee=None):
    try:
        frappe.get_doc({
            "doctype": "Government Portal Sync Log",
            "portal": "GOSI",
            "sync_type": sync_type,
            "employee": employee,
            "reference_no": ref,
            "status": status,
            "response_data": frappe.as_json(data) if not isinstance(data, str) else data,
            "synced_on": now_datetime(),
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "HR Suite: GOSI sync log failed")


def _handle(resp, sync_type, ref, employee=None):
    try:
        resp.raise_for_status()
        data = resp.json()
        _log(sync_type, ref, "Success", data, employee)
        return data
    except requests.HTTPError:
        body = resp.text[:500]
        _log(sync_type, ref, "Failed", {"http": resp.status_code, "body": body}, employee)
        frappe.throw(f"GOSI API error ({resp.status_code}): {body}")
    except Exception as e:
        _log(sync_type, ref, "Failed", str(e), employee)
        frappe.throw(f"GOSI request failed: {e}")


def _headers():
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled in Hr Suite Settings.")
    return {
        "Authorization": f"Bearer {s.get_password('gosi_api_key')}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Establishment-ID": s.gosi_establishment_id or "",
    }


def _base():
    return (_settings().gosi_api_base_url or "https://api.gosi.gov.sa/v1").rstrip("/")


# ── Employee registration / exit ──────────────────────────────────────────────

@frappe.whitelist()
def register_employee(employee: str):
    """Register a new employee with GOSI. Pulls details from the Employee DocType."""
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    emp = frappe.get_doc("Employee", employee)
    saudi_id = (
        frappe.db.get_value("Work Permit Iqama", {"employee": employee}, "iqama_number")
        or emp.get("custom_national_id")
        or ""
    )
    if not saudi_id:
        frappe.throw(f"No Saudi/Iqama ID found on employee {employee}.")

    payload = {
        "establishment_id": s.gosi_establishment_id,
        "saudi_id": saudi_id,
        "employee_name_en": emp.employee_name,
        "date_of_birth": str(emp.date_of_birth or ""),
        "nationality": emp.get("nationality") or emp.get("custom_nationality") or "",
        "date_of_joining": str(emp.date_of_joining or ""),
        "basic_salary": frappe.db.get_value(
            "Salary Structure Assignment",
            {"employee": employee, "docstatus": 1},
            "base",
            order_by="from_date desc",
        ) or 0,
        "job_title": emp.designation or "",
    }

    resp = requests.post(
        f"{_base()}/members/register",
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    return _handle(resp, "Employee Register", saudi_id, employee)


@frappe.whitelist()
def deregister_employee(employee: str, exit_date: str, reason: str = "Resignation"):
    """Deregister / exit an employee from GOSI."""
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    saudi_id = frappe.db.get_value("Work Permit Iqama", {"employee": employee}, "iqama_number") or ""
    if not saudi_id:
        frappe.throw(f"No Iqama ID found for employee {employee}.")

    payload = {
        "establishment_id": s.gosi_establishment_id,
        "saudi_id": saudi_id,
        "exit_date": exit_date,
        "reason": reason,
    }
    resp = requests.post(
        f"{_base()}/members/deregister",
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    return _handle(resp, "Employee Deregister", saudi_id, employee)


@frappe.whitelist()
def get_employee_status(employee: str):
    """Check GOSI membership status for an employee."""
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    saudi_id = frappe.db.get_value("Work Permit Iqama", {"employee": employee}, "iqama_number") or ""
    if not saudi_id:
        frappe.throw(f"No Iqama ID found for employee {employee}.")

    resp = requests.get(
        f"{_base()}/members/{saudi_id}/status",
        params={"establishment_id": s.gosi_establishment_id},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "Member Status", saudi_id, employee)
    return {
        "saudi_id": saudi_id,
        "gosi_status": data.get("status") or data.get("memberStatus"),
        "registration_date": data.get("registration_date"),
        "contribution_class": data.get("contribution_class"),
        "last_contribution_month": data.get("last_contribution_month"),
        "raw": data,
    }


# ── Contribution submission ───────────────────────────────────────────────────

@frappe.whitelist()
def submit_contribution(gosi_contribution: str):
    """
    Submit a single submitted GOSI Contribution record to the GOSI portal.
    Updates reference_number and payment_status on the doc when successful.
    """
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    doc = frappe.get_doc("GOSI Contribution", gosi_contribution)
    if doc.docstatus != 1:
        frappe.throw("Only submitted GOSI Contribution records can be pushed to GOSI.")

    saudi_id = frappe.db.get_value("Work Permit Iqama", {"employee": doc.employee}, "iqama_number") or ""

    payload = {
        "establishment_id": s.gosi_establishment_id,
        "saudi_id": saudi_id,
        "employee_name": doc.employee_name,
        "month": doc.month,
        "year": doc.year,
        "contribution_base": doc.contribution_base,
        "employee_contribution": doc.employee_contribution,
        "employer_contribution": doc.employer_contribution,
        "total_contribution": doc.total_contribution,
    }

    resp = requests.post(
        f"{_base()}/contributions/submit",
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "Contribution Submit", gosi_contribution, doc.employee)

    ref = data.get("reference_number") or data.get("referenceNo") or ""
    if ref:
        frappe.db.set_value("GOSI Contribution", gosi_contribution, {
            "reference_number": ref,
            "payment_status": "Paid",
            "payment_date": getdate(),
        }, update_modified=True)

    return {"reference_number": ref, "raw": data}


@frappe.whitelist()
def submit_monthly_batch(company: str, month: str, year: str):
    """
    Submit all submitted-but-unpaid GOSI Contributions for a company/period
    as a batch to the GOSI portal. Returns list of results.
    """
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    records = frappe.get_all(
        "GOSI Contribution",
        filters={
            "company": company,
            "month": month,
            "year": int(year),
            "docstatus": 1,
            "payment_status": "Pending",
        },
        fields=["name", "employee", "employee_name", "contribution_base",
                "employee_contribution", "employer_contribution", "total_contribution"],
    )

    if not records:
        frappe.throw(f"No pending submitted GOSI Contributions found for {month} {year}.")

    # Build batch payload
    members = []
    for r in records:
        saudi_id = frappe.db.get_value("Work Permit Iqama", {"employee": r.employee}, "iqama_number") or ""
        members.append({
            "saudi_id": saudi_id,
            "employee_name": r.employee_name,
            "contribution_base": r.contribution_base,
            "employee_contribution": r.employee_contribution,
            "employer_contribution": r.employer_contribution,
            "total_contribution": r.total_contribution,
        })

    payload = {
        "establishment_id": s.gosi_establishment_id,
        "month": month,
        "year": int(year),
        "members": members,
    }

    resp = requests.post(
        f"{_base()}/contributions/batch-submit",
        json=payload,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "Batch Submit", f"{month}-{year}")

    # Mark all as Paid if batch succeeded
    batch_ref = data.get("batch_reference") or data.get("batchRef") or ""
    for r in records:
        frappe.db.set_value("GOSI Contribution", r.name, {
            "payment_status": "Paid",
            "payment_date": getdate(),
            "reference_number": batch_ref,
        }, update_modified=True)

    return {
        "submitted": len(records),
        "batch_reference": batch_ref,
        "raw": data,
    }


# ── Employer account & certificate ───────────────────────────────────────────

@frappe.whitelist()
def get_employer_account():
    """Get GOSI employer account summary — registered members, outstanding balance."""
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    resp = requests.get(
        f"{_base()}/establishments/{s.gosi_establishment_id}/account",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "Employer Account", s.gosi_establishment_id)
    return {
        "establishment_id": s.gosi_establishment_id,
        "registered_members": data.get("registered_members") or data.get("totalMembers"),
        "outstanding_balance": data.get("outstanding_balance") or data.get("outstandingAmount"),
        "last_payment_date": data.get("last_payment_date"),
        "compliance_status": data.get("compliance_status") or data.get("status"),
        "raw": data,
    }


@frappe.whitelist()
def get_contribution_certificate(company: str = None):
    """
    Fetch the GOSI clearance / contribution certificate for the establishment.
    Returns a URL or base64-encoded PDF from the API.
    """
    s = _settings()
    if not s.gosi_api_enabled:
        frappe.throw("GOSI API integration is not enabled.")

    resp = requests.get(
        f"{_base()}/establishments/{s.gosi_establishment_id}/certificate",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    data = _handle(resp, "Contribution Certificate", s.gosi_establishment_id)
    return {
        "certificate_url": data.get("certificate_url") or data.get("url"),
        "valid_until": data.get("valid_until") or data.get("expiryDate"),
        "raw": data,
    }


# ── Scheduled sync ────────────────────────────────────────────────────────────

def sync_monthly_gosi():
    """
    Monthly scheduler: check GOSI account status and flag any outstanding contributions.
    Runs on the 1st of each month via hooks.py scheduler_events.
    """
    s = _settings()
    if not s.gosi_api_enabled:
        return
    try:
        get_employer_account()
    except Exception:
        _log("Employer Account", s.gosi_establishment_id or "—", "Failed", frappe.get_traceback())
